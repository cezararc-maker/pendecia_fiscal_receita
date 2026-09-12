from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
import sys
from typing import Any

from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from .eventlog import EventLogger
from .portal_gates import ensure_authenticated, wait_human_security_challenge
from .portal_representation import (
    close_representation_menu,
    discard_old_confirmation_dialogs,
    find_receita_page,
    open_representation_menu,
    wait_confirmed_analysis,
)
from .queue_contract import ProgressState, QueueInput, ResultStore, load_queue
from .worker_common import PORTAL_URL, QueueCompany, WorkerError, concise_error, local_timestamp

DIAGNOSTIC_STAGES = ("connected-only", "after-open")


class EarlyDiagnosticWorker:
    def __init__(self, queue: QueueInput, *, diagnostic_stage: str):
        if diagnostic_stage not in DIAGNOSTIC_STAGES:
            raise ValueError(f"Etapa diagnóstica inválida: {diagnostic_stage}")
        if len(queue.companies) != 1:
            raise ValueError("O diagnóstico inicial exige exatamente 1 CNPJ elegível.")
        self.queue = queue
        self.diagnostic_stage = diagnostic_stage
        self.company: QueueCompany = queue.companies[0]
        self.progress = ProgressState(queue)
        self.results = ResultStore(queue)
        self.logger = EventLogger(queue.paths.event_log)
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
                return await self._run_diagnostic()
        except WorkerError as exc:
            self.progress.update(
                status="ERRO_FATAL",
                stage=exc.stage,
                phase=0,
                message=str(exc),
                errors=1,
            )
            self.logger.emit(
                "early_diagnostic_failed",
                stage=exc.stage,
                mode=self.diagnostic_stage,
                error_code=exc.code,
                error_original=str(exc),
            )
            self.results.save()
            return 2
        except Exception as exc:
            self.progress.update(
                status="ERRO_FATAL",
                stage="unexpected",
                phase=0,
                message=concise_error(exc),
                errors=1,
            )
            self.logger.emit(
                "early_diagnostic_failed",
                stage="unexpected",
                mode=self.diagnostic_stage,
                error_original=repr(exc),
            )
            self.results.save()
            return 3

    async def _run_diagnostic(self) -> int:
        assert self.page is not None
        company = self.company
        self.progress.update(
            status="PROCESSANDO",
            currentCode=company.codigo,
            currentName=company.nome,
            stage="Iniciando diagnóstico controlado",
            phase=0.05,
            message="",
        )
        self.logger.emit(
            "early_diagnostic_started",
            company=company.nome,
            identifier=company.identificador,
            code=company.codigo,
            stage=self.diagnostic_stage,
            mode=self.diagnostic_stage,
        )

        if self.diagnostic_stage == "connected-only":
            self.progress.update(
                status="AGUARDANDO_DIAGNOSTICO",
                stage="Diagnóstico: Playwright conectado, sem interação no formulário",
                phase=0.1,
                message=(
                    "Faça manualmente toda a representação: abra o menu, informe o CNPJ, "
                    "selecione Procurador e clique em Representar."
                ),
            )
            self.logger.emit(
                "diagnostic_checkpoint_connected_only",
                company=company.nome,
                identifier=company.identificador,
                code=company.codigo,
                stage="connected_only",
            )
        else:
            await discard_old_confirmation_dialogs(self.page)
            await close_representation_menu(self.page)
            await open_representation_menu(self.page)
            self.progress.update(
                status="AGUARDANDO_DIAGNOSTICO",
                stage="Diagnóstico: menu de representação aberto",
                phase=0.2,
                message=(
                    "O Python apenas abriu o menu. Preencha manualmente o CNPJ, selecione "
                    "Procurador e clique em Representar."
                ),
            )
            self.logger.emit(
                "diagnostic_checkpoint_after_open",
                company=company.nome,
                identifier=company.identificador,
                code=company.codigo,
                stage="after_open",
            )

        result_status, _ = await wait_confirmed_analysis(
            self.page,
            self.progress,
            self.logger,
            company,
            timeout_seconds=300,
        )
        await close_representation_menu(self.page)

        result_label = "Sem pendencias" if result_status == "SEM_PENDENCIAS" else "Com pendencias"
        result: dict[str, Any] = {
            "codigo": company.codigo,
            "nome": company.nome,
            "dataHora": local_timestamp(),
            "status": "Concluido",
            "resultado": result_label,
            "relatorio": "",
            "quantidade": 0,
            "competencias": "",
            "detalhes": f"Diagnóstico {self.diagnostic_stage} concluído manualmente.",
        }
        self.results.append(result)
        self.progress.update(
            status="CONCLUIDO",
            currentCode="",
            currentName="",
            stage="Diagnóstico finalizado",
            completed=1,
            successful=1,
            phase=0,
            message=f"Resultado confirmado: {result_label}.",
        )
        self.logger.emit(
            "early_diagnostic_completed",
            company=company.nome,
            identifier=company.identificador,
            code=company.codigo,
            stage=self.diagnostic_stage,
            result=result_label,
        )
        return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Diagnóstico inicial da validação visual da Receita")
    parser.add_argument("--queue", required=True, type=Path)
    parser.add_argument("--diagnostic-stage", required=True, choices=DIAGNOSTIC_STAGES)
    return parser


async def async_main(queue_path: Path, *, diagnostic_stage: str) -> int:
    try:
        queue = load_queue(queue_path)
        worker = EarlyDiagnosticWorker(queue, diagnostic_stage=diagnostic_stage)
    except Exception as exc:
        print(f"Diagnóstico inválido: {exc}", file=sys.stderr)
        return 2
    return await worker.run()


def main() -> None:
    args = build_parser().parse_args()
    raise SystemExit(asyncio.run(async_main(args.queue, diagnostic_stage=args.diagnostic_stage)))


if __name__ == "__main__":
    main()
