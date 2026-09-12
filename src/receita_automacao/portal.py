from __future__ import annotations

from datetime import datetime
import re
from time import monotonic
from typing import Any

from playwright.async_api import BrowserContext, Locator, Page, Playwright, async_playwright

from .config import PortalConfig, RuntimeConfig
from .eventlog import EventLogger, masked_identifier
from .models import CompanyRecord, PortalResult, PortalResultStatus, digits_only


CNPJ_TEXT_RE = re.compile(r"(?<!\d)(\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2})(?!\d)")

ADDITIONAL_CONFIRMATION_MARKERS = (
    "confirmação adicional",
    "confirme a operação",
    "confirmar acesso",
    "autorizar acesso",
    "autorize o acesso",
)

SECURITY_CHALLENGE_MARKERS = (
    "captcha",
    "código de verificação",
    "verificação em duas etapas",
    "desafio de segurança",
    "confirme sua identidade",
    "selecione um certificado",
)


class PortalStageError(RuntimeError):
    def __init__(self, code: str, stage: str, message: str):
        super().__init__(message)
        self.code = code
        self.stage = stage


def classify_manual_gate(url: str, body_text: str) -> str | None:
    """Classify a manual gate without logging page contents or sensitive data."""
    normalized = body_text.casefold()
    if any(marker in normalized for marker in SECURITY_CHALLENGE_MARKERS):
        return "security_challenge"
    if any(marker in normalized for marker in ADDITIONAL_CONFIRMATION_MARKERS):
        return "additional_confirmation"
    if "/login/" in url.casefold() or "entre com sua conta gov.br" in normalized:
        return "login"
    return None


async def _click_option_and_submit(page: Any, procurador_option: Any) -> None:
    """Critical sequence: intentionally contains no diagnostics/focus changes between actions."""
    await procurador_option.click()
    await page.keyboard.press("Tab")
    await page.wait_for_timeout(300)
    await page.keyboard.press("Tab")
    await page.wait_for_timeout(300)
    await page.keyboard.press("Space")


class ReceitaPortalClient:
    def __init__(self, portal: PortalConfig, runtime: RuntimeConfig, logger: EventLogger):
        self.config = portal
        self.runtime = runtime
        self.logger = logger
        self.playwright: Playwright | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None
        self.last_representation_action: float | None = None

    async def __aenter__(self) -> "ReceitaPortalClient":
        self.runtime.browser_profile_dir.mkdir(parents=True, exist_ok=True)
        self.playwright = await async_playwright().start()
        channel = self.config.browser_channel or None
        self.context = await self.playwright.chromium.launch_persistent_context(
            user_data_dir=str(self.runtime.browser_profile_dir),
            channel=channel,
            headless=False,
            accept_downloads=True,
        )
        self.page = self.context.pages[0] if self.context.pages else await self.context.new_page()
        await self.page.goto(self.config.url, wait_until="domcontentloaded")
        await self.wait_for_manual_authentication()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self.context is not None:
            await self.context.close()
        if self.playwright is not None:
            await self.playwright.stop()

    def seconds_until_next_representation(self) -> float:
        if self.last_representation_action is None:
            return 0.0
        elapsed = monotonic() - self.last_representation_action
        return max(0.0, self.config.minimum_seconds_between_representations - elapsed)

    async def wait_for_manual_authentication(self) -> None:
        assert self.page is not None
        started = monotonic()
        last_gate: str | None = None
        event_names = {
            "login": "portal_login_required",
            "additional_confirmation": "portal_additional_confirmation_required",
            "security_challenge": "portal_security_challenge_required",
        }

        while monotonic() - started < self.config.manual_login_timeout_seconds:
            try:
                body_text = await self.page.locator("body").inner_text(timeout=1500)
            except Exception:
                body_text = ""

            gate = classify_manual_gate(self.page.url, body_text)
            if gate is not None:
                if gate != last_gate:
                    self.logger.emit(
                        event_names[gate],
                        stage=gate,
                        detail="Intervenção manual necessária no navegador aberto pela automação.",
                    )
                last_gate = gate
                await self.page.wait_for_timeout(1000)
                continue

            url = self.page.url.lower()
            if "/servico/pendencias/" in url and "/login/" not in url:
                return

            if last_gate != "login":
                self.logger.emit(
                    "portal_login_required",
                    stage="login",
                    detail="Aguardando autenticação manual e redirecionamento ao serviço.",
                )
                last_gate = "login"
            await self.page.wait_for_timeout(1000)

        raise PortalStageError(
            "login_timeout",
            "login",
            "O portal não chegou à área autenticada dentro do tempo configurado.",
        )

    async def probe(self) -> dict[str, object]:
        assert self.page is not None
        return {
            "url": self.page.url,
            "cnpj_input_visible": await self._visible_count(self.page.locator(self.config.cnpj_input_selector)),
            "submit_visible": await self._visible_count(self.page.locator(self.config.submit_selector)),
            "ng_select_visible": await self._visible_count(self.page.locator(self.config.procurador_select_selector)),
            "sidebar_selector_configured": bool(self.config.sidebar_toggle_selector),
            "identity_scope_configured": bool(self.config.identity_scope_selector),
            "download_selector_configured": bool(self.config.report_download_selector),
        }

    async def process_company(self, company: CompanyRecord) -> PortalResult:
        assert self.page is not None
        started = self.logger.timer()
        await self._ensure_representation_panel(company)
        form = await self._representation_form(company)
        await self._fill_cnpj(form, company)
        await self._select_procurador_and_submit(form, company)
        confirmed = await self._confirm_represented_cnpj(company)
        status = await self._wait_analysis_result(company)
        report_path: str | None = None
        if status is PortalResultStatus.HAS_PENDENCIES:
            report_path = await self._download_report(company)
        self.logger.emit(
            "company_completed",
            company=company.company_name,
            identifier=company.identifier,
            stage="completed",
            duration_seconds=self.logger.elapsed(started),
            result=status.value,
        )
        return PortalResult(status=status, confirmed_cnpj=confirmed, report_path=report_path)

    async def _ensure_representation_panel(self, company: CompanyRecord) -> None:
        assert self.page is not None
        input_locator = self.page.locator(self.config.cnpj_input_selector)
        if await self._visible_count(input_locator) == 1:
            return

        if self.config.sidebar_toggle_selector:
            toggle = self.page.locator(self.config.sidebar_toggle_selector)
            if await self._visible_count(toggle) != 1:
                raise PortalStageError(
                    "sidebar_toggle_not_unique",
                    "open_representation_panel",
                    "O seletor do cabeçalho não identificou exatamente um controle visível.",
                )
            await toggle.click()
            try:
                await input_locator.wait_for(state="visible", timeout=5000)
            except Exception as exc:
                raise PortalStageError(
                    "cnpj_field_not_visible_after_sidebar",
                    "find_cnpj_field",
                    f"A barra foi acionada, mas o campo interno de CNPJ não ficou visível: {exc}",
                ) from exc
            return

        raise PortalStageError(
            "cnpj_field_not_found",
            "find_cnpj_field",
            "O campo interno de CNPJ não está visível e sidebar_toggle_selector ainda não foi validado.",
        )

    async def _representation_form(self, company: CompanyRecord) -> Locator:
        assert self.page is not None
        submit = self.page.locator(self.config.submit_selector)
        count = await self._visible_count(submit)
        if count != 1:
            raise PortalStageError(
                "represent_submit_not_unique",
                "find_submit",
                f"Esperado 1 botão submit Representar visível; encontrados {count}.",
            )

        form = submit.locator("xpath=ancestor::form[1]")
        if await form.count() == 1:
            return form

        scope = submit.locator(
            "xpath=ancestor::*[.//input[@placeholder='Digite o CPF ou CNPJ']][1]"
        )
        if await scope.count() == 1:
            return scope

        raise PortalStageError(
            "representation_form_not_found",
            "find_submit",
            "O botão submit correto foi encontrado, mas não foi possível delimitar o formulário/contêiner do CNPJ.",
        )

    async def _fill_cnpj(self, form: Locator, company: CompanyRecord) -> None:
        field = form.locator(self.config.cnpj_input_selector)
        count = await self._visible_count(field)
        if count != 1:
            raise PortalStageError(
                "cnpj_field_not_unique",
                "fill_cnpj",
                f"Esperado 1 input interno de CNPJ visível no formulário; encontrados {count}.",
            )
        try:
            await field.fill(company.identifier)
        except Exception as exc:
            raise PortalStageError(
                "cnpj_fill_failed",
                "fill_cnpj",
                f"Não foi possível preencher o CNPJ: {exc}",
            ) from exc

    async def _select_procurador_and_submit(self, form: Locator, company: CompanyRecord) -> None:
        assert self.page is not None
        select = form.locator(self.config.procurador_select_selector)
        count = await self._visible_count(select)
        if count != 1:
            raise PortalStageError(
                "procurador_select_not_unique",
                "select_procurador",
                f"Esperado 1 ng-select visível no formulário; encontrados {count}.",
            )

        self.logger.emit(
            "before_procurador_selection",
            company=company.company_name,
            identifier=company.identifier,
            stage="select_procurador",
        )
        try:
            await select.click()
            option_candidates = self.page.locator(self.config.procurador_option_selector).filter(
                has_text=re.compile(r"^\s*Procurador\s*$", re.IGNORECASE)
            )
            if await self._visible_count(option_candidates) != 1:
                raise PortalStageError(
                    "procurador_option_not_unique",
                    "select_procurador",
                    "A opção Procurador não foi identificada de forma única e visível.",
                )
            option = option_candidates.first
            await _click_option_and_submit(self.page, option)
            self.last_representation_action = monotonic()
        except PortalStageError:
            raise
        except Exception as exc:
            raise PortalStageError(
                "procurador_or_submit_failed",
                "select_procurador",
                f"Falha ao selecionar Procurador ou enviar a sequência Tab/Tab/Espaço: {exc}",
            ) from exc

        self.logger.emit(
            "representation_sequence_sent",
            company=company.company_name,
            identifier=company.identifier,
            stage="submit_representation",
            sequence="Tab,300ms,Tab,300ms,Space",
        )

    async def _confirm_represented_cnpj(self, company: CompanyRecord) -> str:
        assert self.page is not None
        deadline = monotonic() + self.config.representation_timeout_seconds
        while monotonic() < deadline:
            found = await self._read_cnpj_from_identity_area()
            if found:
                if found != company.identifier:
                    raise PortalStageError(
                        "representation_cnpj_mismatch",
                        "confirm_representation",
                        f"A representação mudou, mas o CNPJ cadastral exibido não corresponde ao solicitado ({masked_identifier(found)}).",
                    )
                self.logger.emit(
                    "representation_confirmed",
                    company=company.company_name,
                    identifier=company.identifier,
                    stage="confirm_representation",
                )
                return found
            await self.page.wait_for_timeout(500)

        raise PortalStageError(
            "representation_not_confirmed",
            "confirm_representation",
            "Representar foi acionado, mas o CNPJ solicitado não apareceu na área de dados cadastrais.",
        )

    async def _read_cnpj_from_identity_area(self) -> str | None:
        assert self.page is not None
        scopes: list[Locator] = []
        if self.config.identity_scope_selector:
            candidate = self.page.locator(self.config.identity_scope_selector)
            if await self._visible_count(candidate) == 1 and await self._safe_identity_scope(candidate):
                scopes.append(candidate)
        else:
            headings = self.page.get_by_text(re.compile(r"Dados\s+cadastrais", re.IGNORECASE), exact=False)
            for index in range(min(await headings.count(), 5)):
                heading = headings.nth(index)
                if not await heading.is_visible():
                    continue
                current = heading
                for _ in range(5):
                    current = current.locator("xpath=..")
                    try:
                        text = await current.inner_text(timeout=1000)
                    except Exception:
                        continue
                    if "CNPJ" not in text.upper() or not CNPJ_TEXT_RE.search(text):
                        continue
                    if await self._safe_identity_scope(current):
                        scopes.append(current)
                    break

        for scope in scopes:
            try:
                text = await scope.inner_text(timeout=1500)
            except Exception:
                continue
            match = CNPJ_TEXT_RE.search(text)
            if match:
                value = digits_only(match.group(1))
                if len(value) == 14:
                    return value
        return None

    async def _safe_identity_scope(self, scope: Locator) -> bool:
        """Reject scopes that also contain the representation form/recent-input region."""
        if await scope.locator(self.config.cnpj_input_selector).count() > 0:
            return False
        if await scope.locator(self.config.submit_selector).count() > 0:
            return False
        return True

    async def _wait_analysis_result(self, company: CompanyRecord) -> PortalResultStatus:
        assert self.page is not None
        deadline = monotonic() + self.config.analysis_timeout_seconds
        while monotonic() < deadline:
            if await self._any_visible_text(self.config.no_pendencies_texts):
                return PortalResultStatus.NO_PENDENCIES
            if await self._any_visible_text(self.config.pending_texts):
                return PortalResultStatus.HAS_PENDENCIES
            await self.page.wait_for_timeout(500)
        raise PortalStageError(
            "analysis_not_loaded",
            "wait_analysis",
            "A representação foi confirmada, mas nenhum marcador explícito de resultado carregou no prazo.",
        )

    async def _download_report(self, company: CompanyRecord) -> str:
        assert self.page is not None
        control: Locator | None = None
        if self.config.report_download_selector:
            candidate = self.page.locator(self.config.report_download_selector)
            if await self._visible_count(candidate) == 1:
                control = candidate
        else:
            regex = re.compile(r"(baixar.*relat|relat.*baixar|download.*relat|relat.*download)", re.IGNORECASE)
            buttons = self.page.get_by_role("button", name=regex)
            links = self.page.get_by_role("link", name=regex)
            visible: list[Locator] = []
            for collection in (buttons, links):
                for index in range(min(await collection.count(), 10)):
                    item = collection.nth(index)
                    if await item.is_visible():
                        visible.append(item)
            if len(visible) == 1:
                control = visible[0]

        if control is None:
            raise PortalStageError(
                "report_download_control_not_found",
                "download_report",
                "Há pendências confirmadas, mas o controle único para baixar o relatório não foi localizado.",
            )

        target_dir = self.runtime.report_dir / company.identifier
        target_dir.mkdir(parents=True, exist_ok=True)
        try:
            async with self.page.expect_download(timeout=self.config.download_timeout_seconds * 1000) as info:
                await control.click()
            download = await info.value
            safe_name = re.sub(r"[^A-Za-z0-9._ -]+", "_", download.suggested_filename or "relatorio_pendencias.pdf")
            destination = target_dir / safe_name
            await download.save_as(str(destination))
            return str(destination.resolve())
        except Exception as exc:
            raise PortalStageError(
                "report_download_failed",
                "download_report",
                f"Falha ao baixar/salvar o relatório: {exc}",
            ) from exc

    async def capture_evidence(self, stage: str, identifier: str) -> str | None:
        if self.page is None:
            return None
        self.runtime.evidence_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = self.runtime.evidence_dir / f"{stamp}_{stage}_{masked_identifier(identifier).replace('*', 'x')}.png"
        try:
            await self.page.screenshot(path=str(path), full_page=True)
            return str(path.resolve())
        except Exception:
            return None

    async def _visible_count(self, locator: Locator) -> int:
        total = await locator.count()
        visible = 0
        for index in range(total):
            try:
                if await locator.nth(index).is_visible():
                    visible += 1
            except Exception:
                continue
        return visible

    async def _any_visible_text(self, texts: tuple[str, ...]) -> bool:
        assert self.page is not None
        for text in texts:
            locator = self.page.get_by_text(re.compile(re.escape(text), re.IGNORECASE), exact=False)
            for index in range(min(await locator.count(), 10)):
                if await locator.nth(index).is_visible():
                    return True
        return False
