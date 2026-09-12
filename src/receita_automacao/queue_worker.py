from __future__ import annotations

import argparse
import asyncio
from datetime import datetime
from pathlib import Path
import re
import sys
from time import monotonic
from typing import Any

from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from .eventlog import EventLogger
from .portal_download import download_receita_report
from .portal_gates import (
    ensure_authenticated,
    explicit_no_authorization_visible,
    handle_post_submit_confirmation,
    visible_text,
    wait_human_security_challenge,
)
from .portal_representation import (
    close_representation_menu,
    discard_old_confirmation_dialogs,
    fill_cnpj,
    find_receita_page,
    open_representation_menu,
    select_procurador_and_submit,
    validate_representation_form,
    wait_confirmed_analysis,
)
from .queue_contract import ProgressState, QueueInput, ResultStore, load_queue
from .worker_common import (
    ALREADY_ACTIVE_RE,
    COOLDOWN_RE,
    PORTAL_URL,
    PortalUnstableError,
    QueueCompany,
    RepresentationSafetyError,
    WorkerError,
    clean,
    concise_error,
    format_cnpj,
    local_timestamp,
)


class ReceitaQueueWorker:
    def __init__(self, queue: QueueInput):
        self.queue = queue
        self.progress = ProgressState(queue)
        self.results = ResultStore(queue)
        self.logger = EventLogger(queue.paths.event_log)
        self.last_representation_at: float | None = None
        self.browser: Browser | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None

    async def run(self) -> int:
        self.queue.paths.output_directory.mkdir(parents=True, exist_ok=True)
        self.queue.paths.evidence_directory.mkdir(parents=True, exist_ok=True)
        self.progress.update()
        try:
            async with async_playwright() as playwright:
                self.browser = await playwright.chromium.connect_over_cdp(self.queue.cdp_url)
                if not self.browser.contexts:
                    raise WorkerError(
                        "browser_context_missing",
                        "connect_browser",
                        "O Chrome preparado não possui contexto acessível.",
                        fatal=True,
                    )
                self.context = self.browser.contexts[0]
                self.page = await find_receita_page(self.context)
                self.page.set_default_timeout(15000)
                self.page.set_default_navigation_timeout(45000)
                if "/servico/pendencias" not in self.page.url:
                    await self.page.goto(PORTAL_URL, wait_until="domcontentloaded")
                await ensure_authenticated(self.page)
                await wait_human_security_challenge(self.page, self.progress)
                return await self._run_companies()
        except WorkerError as exc:
            self.progress.data["errors"] = int(self.progress.data.get("errors", 0)) + 1
            self.progress.update(
                status="ERRO_FATAL",
                stage=exc.stage,
                phase=0,
                message=str(exc),
            )
            self.logger.emit(
                "fatal_worker_error",
                stage=exc.stage,
                error_code=exc.code,
                error_original=str(exc),
            )
            self.results.save()
            return 2
        except Exception as exc:
            self.progress.data["errors"] = int(self.progress.data.get("errors", 0)) + 1
            self.progress.update(
                status="ERRO_FATAL",
                stage="unexpected",
                phase=0,
                message=concise_error(exc),
            )
            self.logger.emit(
                "unexpected_worker_error",
                stage="unexpected",
                error_original=repr(exc),
            )
            self.results.save()
            return 3

    async def _run_companies(self) -> int:
        completed_codes = self.results.completed_codes
        companies = [
            company for company in self.queue.companies if company.codigo not in completed_codes
        ]
        already_done = len(self.queue.companies) - len(companies)
        if already_done:
            self.progress.data["completed"] = already_done
            self.progress.data["successful"] = already_done
            self.progress.update(
                stage="Retomando resultados preservados",
                message=f"{already_done} empresa(s) já concluída(s) nesta execução.",
            )

        consecutive_instability = 0
        for company in companies:
            await self._wait_if_paused()
            await self._wait_safe_interval()
            started = monotonic()
            self.progress.update(
                status="PROCESSANDO",
                currentCode=company.codigo,
                currentName=company.nome,
                stage="Iniciando consulta na Receita",
                phase=0.05,
                message="",
            )
            self.logger.emit(
                "company_started",
                company=company.nome,
                identifier=company.identificador,
                stage="start",
                code=company.codigo,
            )

            fatal = False
            try:
                result = await self._process_company(company)
                self.results.append(result)
                self.progress.data["successful"] = int(self.progress.data.get("successful", 0)) + 1
                consecutive_instability = 0
                self.logger.emit(
                    "company_completed",
                    company=company.nome,
                    identifier=company.identificador,
                    stage="completed",
                    code=company.codigo,
                    duration_seconds=round(monotonic() - started, 3),
                    result=result.get("resultado", ""),
                )
            except PortalUnstableError as exc:
                consecutive_instability += 1
                await self._record_error(company, exc, started, portal_unstable=True)
            except RepresentationSafetyError as exc:
                fatal = True
                await self._record_error(company, exc, started, portal_unstable=False)
            except WorkerError as exc:
                fatal = exc.fatal
                await self._record_error(company, exc, started, portal_unstable=False)
            except Exception as exc:
                generic = WorkerError(
                    "navigation_failure",
                    "unexpected",
                    concise_error(exc),
                    fatal=False,
                )
                await self._record_error(
                    company,
                    generic,
                    started,
                    portal_unstable=False,
                    original=repr(exc),
                )

            self.progress.data["completed"] = int(self.progress.data.get("completed", 0)) + 1
            last_detail = clean(self.results.results[-1].get("detalhes")) if self.results.results else ""
            self.progress.update(stage="Empresa finalizada", phase=0, message=last_detail)

            if fatal:
                self.progress.update(
                    status="ERRO_FATAL",
                    stage="Consulta interrompida por segurança na representação",
                    phase=0,
                    message="A representação da empresa atual não pôde ser confirmada com segurança.",
                )
                return 4
            if consecutive_instability >= 3:
                self.progress.update(
                    status="PORTAL_INSTAVEL",
                    currentCode="",
                    currentName="",
                    stage="Consulta encerrada após 3 falhas consecutivas do portal",
                    phase=0,
                    message="O portal apresentou instabilidade repetida. Tente novamente mais tarde.",
                )
                return 5

        final_status = (
            "CONCLUIDO_COM_ERROS" if int(self.progress.data.get("errors", 0)) else "CONCLUIDO"
        )
        self.progress.update(
            status=final_status,
            currentCode="",
            currentName="",
            stage="Processamento finalizado",
            phase=0,
            message="",
        )
        return 0

    async def _process_company(self, company: QueueCompany) -> dict[str, Any]:
        assert self.page is not None
        await ensure_authenticated(self.page)
        await wait_human_security_challenge(self.page, self.progress)
        await discard_old_confirmation_dialogs(self.page)
        await close_representation_menu(self.page)

        self.progress.update(
            stage="Abrindo o menu de representação",
            phase=0.15,
            message=f"Empresa {company.codigo}",
        )
        field = await open_representation_menu(self.page)
        await fill_cnpj(field, company)

        if await visible_text(self.page, COOLDOWN_RE):
            await self._wait_fixed_cooldown(40)
            await field.fill("")
            await field.press_sequentially(company.identificador, delay=90)

        if await visible_text(self.page, ALREADY_ACTIVE_RE):
            await close_representation_menu(self.page)
        else:
            form = await validate_representation_form(self.page, field, company)
            await select_procurador_and_submit(self.page, form, company, self.logger)
            self.last_representation_at = monotonic()
            self.progress.update(
                stage="Sequência Tab, Tab e Espaço enviada",
                phase=0.4,
                message=(
                    "Aguardando confirmação da representação para "
                    f"{format_cnpj(company.identificador)}."
                ),
            )
            await handle_post_submit_confirmation(
                self.page,
                self.progress,
                self.logger,
                company,
            )

        result_status, main_text = await wait_confirmed_analysis(
            self.page,
            self.progress,
            self.logger,
            company,
        )
        await close_representation_menu(self.page)

        categories = self._extract_categories(main_text)
        if result_status == "SEM_PENDENCIAS":
            return {
                "codigo": company.codigo,
                "nome": company.nome,
                "dataHora": local_timestamp(),
                "status": "Concluido",
                "resultado": "Sem pendencias",
                "relatorio": "",
                "quantidade": 0,
                "competencias": "",
                "detalhes": "Relatório não necessário: resultado sem pendências.",
            }

        self.progress.update(
            stage="Localizando e baixando relatório da Receita",
            phase=0.75,
            message="",
        )
        report = await download_receita_report(
            self.page,
            company,
            self.queue.paths.output_directory,
        )
        return {
            "codigo": company.codigo,
            "nome": company.nome,
            "dataHora": local_timestamp(),
            "status": "Concluido",
            "resultado": "Com pendencias",
            "relatorio": report,
            "quantidade": len(categories),
            "competencias": "",
            "detalhes": "; ".join(categories),
        }

    async def _record_error(
        self,
        company: QueueCompany,
        exc: WorkerError,
        started: float,
        *,
        portal_unstable: bool,
        original: str | None = None,
    ) -> None:
        assert self.page is not None
        self.progress.data["errors"] = int(self.progress.data.get("errors", 0)) + 1
        explicit_no_auth = await explicit_no_authorization_visible(self.page)
        if explicit_no_auth:
            self.progress.data["withoutAuthorization"] = (
                int(self.progress.data.get("withoutAuthorization", 0)) + 1
            )
        result_label = (
            "Portal instável"
            if portal_unstable
            else ("Sem procuração ativa" if explicit_no_auth else "Falha na navegação do portal")
        )
        evidence = await self._capture_evidence(exc.stage, company.codigo)
        detail = concise_error(exc)
        self.results.append(
            {
                "codigo": company.codigo,
                "nome": company.nome,
                "dataHora": local_timestamp(),
                "status": "Erro",
                "resultado": result_label,
                "relatorio": "",
                "quantidade": 0,
                "competencias": "",
                "detalhes": detail,
                "detalhesTecnicos": original or str(exc),
            }
        )
        self.logger.emit(
            "company_failed",
            company=company.nome,
            identifier=company.identificador,
            stage=exc.stage,
            code=company.codigo,
            duration_seconds=round(monotonic() - started, 3),
            error_code=exc.code,
            error_original=original or str(exc),
            evidence_path=evidence,
        )

    async def _wait_if_paused(self) -> None:
        if not self.queue.paths.pause_path.exists():
            return
        self.progress.pause_started_at = monotonic()
        while self.queue.paths.pause_path.exists():
            self.progress.update(
                status="PAUSADO",
                stage="Consulta pausada pelo usuário",
                message="Clique em Continuar consulta para retomar do mesmo ponto.",
            )
            await asyncio.sleep(1)
        assert self.progress.pause_started_at is not None
        self.progress.paused_total += monotonic() - self.progress.pause_started_at
        self.progress.pause_started_at = None
        self.progress.update(status="PROCESSANDO", stage="Retomando consulta", message="")

    async def _wait_safe_interval(self) -> None:
        if self.last_representation_at is None:
            return
        while True:
            elapsed = monotonic() - self.last_representation_at
            remaining = max(0, int(40 - elapsed + 0.999))
            if remaining <= 0:
                return
            await self._wait_if_paused()
            self.progress.update(
                stage=f"Aguardando {remaining}s para trocar a representação na Receita",
                phase=0,
                message="Intervalo de segurança: 40 segundos entre representações.",
            )
            await asyncio.sleep(1)

    async def _wait_fixed_cooldown(self, seconds: int) -> None:
        for remaining in range(seconds, 0, -1):
            await self._wait_if_paused()
            self.progress.update(
                stage=f"Aguardando {remaining}s para trocar a representação na Receita",
                phase=0,
                message="Intervalo de segurança solicitado pelo portal.",
            )
            await asyncio.sleep(1)

    async def _capture_evidence(self, stage: str, code: str) -> str | None:
        if self.page is None:
            return None
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_stage = re.sub(r"[^A-Za-z0-9_-]+", "_", stage)
        safe_code = re.sub(r"[^A-Za-z0-9_-]+", "_", code)
        path = self.queue.paths.evidence_directory / f"{stamp}_{safe_code}_{safe_stage}.png"
        try:
            await self.page.screenshot(path=str(path), full_page=True)
            return str(path.resolve())
        except Exception:
            return None

    @staticmethod
    def _extract_categories(text: str) -> list[str]:
        mapping = (
            ("Dívida Ativa da União", "Divida Ativa da Uniao"),
            ("Dívida DCTFWeb", "Divida DCTFWeb"),
            ("Dívida PGDAS-D", "Divida PGDAS-D"),
            ("Parcelamento", "Parcelamento"),
        )
        return [label for needle, label in mapping if needle in text]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Worker Python compatível com a fila VBA de Pendências Fiscais"
    )
    parser.add_argument(
        "--queue",
        required=True,
        type=Path,
        help="Caminho para fila.json criada pelo Excel",
    )
    return parser


async def async_main(queue_path: Path) -> int:
    try:
        queue = load_queue(queue_path)
    except Exception as exc:
        print(f"Fila inválida: {exc}", file=sys.stderr)
        return 2
    return await ReceitaQueueWorker(queue).run()


def main() -> None:
    args = build_parser().parse_args()
    raise SystemExit(asyncio.run(async_main(args.queue)))


if __name__ == "__main__":
    main()
