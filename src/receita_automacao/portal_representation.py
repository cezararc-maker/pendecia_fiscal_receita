from __future__ import annotations

import asyncio
import re
from time import monotonic
from typing import Any

from playwright.async_api import BrowserContext, Locator, Page

from .eventlog import EventLogger, masked_identifier
from .models import digits_only
from .portal_gates import (
    explicit_no_authorization_visible,
    visible_items,
    visible_text,
    wait_human_security_challenge,
)
from .worker_common import (
    ANALYSIS_HEADING_RE,
    CNPJ_INPUT_SELECTOR,
    COMBO_SELECTOR,
    PORTAL_HOST,
    PORTAL_URL,
    PROFILE_BUTTON_SELECTOR,
    QueueCompany,
    RepresentationSafetyError,
    SUBMIT_SELECTOR,
    WorkerError,
    parse_analysis_result,
)


async def find_receita_page(context: BrowserContext) -> Page:
    for page in context.pages:
        if PORTAL_HOST in page.url:
            return page
    page = await context.new_page()
    await page.goto(PORTAL_URL, wait_until="domcontentloaded")
    return page


async def discard_old_confirmation_dialogs(page: Page) -> None:
    dialogs = page.get_by_role("dialog").filter(
        has=page.get_by_role("heading", name="Representar", exact=True)
    )
    for dialog in reversed(await visible_items(dialogs)):
        cancel = await visible_items(dialog.get_by_role("button", name="Cancelar", exact=True))
        if cancel:
            await cancel[0].click()
        else:
            close = await visible_items(
                dialog.get_by_role("button", name=re.compile("Fechar", re.IGNORECASE))
            )
            if close:
                await close[0].click()
            else:
                await page.keyboard.press("Escape")
        try:
            await dialog.wait_for(state="hidden", timeout=10000)
        except Exception as exc:
            raise RepresentationSafetyError(
                "old_confirmation_not_closed",
                "additional_confirmation",
                "Uma confirmação antiga de representação permaneceu aberta.",
            ) from exc


async def open_representation_menu(page: Page) -> Locator:
    fields = await visible_items(page.locator(CNPJ_INPUT_SELECTOR))
    if len(fields) == 1:
        return fields[0]
    if len(fields) > 1:
        raise WorkerError(
            "cnpj_field_not_unique",
            "find_cnpj_field",
            f"Foram encontrados {len(fields)} campos internos de CNPJ visíveis.",
        )

    button = page.locator(PROFILE_BUTTON_SELECTOR).first
    if not await button.is_visible():
        raise WorkerError(
            "profile_button_not_found",
            "open_representation_panel",
            "O nome/perfil no cabeçalho não foi encontrado para abrir a representação.",
        )
    await button.scroll_into_view_if_needed()
    await button.click()
    try:
        await page.locator(CNPJ_INPUT_SELECTOR).wait_for(state="visible", timeout=15000)
    except Exception as exc:
        raise WorkerError(
            "cnpj_field_not_found",
            "find_cnpj_field",
            f"A barra lateral abriu, mas o campo interno de CNPJ não ficou visível: {exc}",
        ) from exc
    fields = await visible_items(page.locator(CNPJ_INPUT_SELECTOR))
    if len(fields) != 1:
        raise WorkerError(
            "cnpj_field_not_unique",
            "find_cnpj_field",
            f"Esperado 1 campo interno de CNPJ visível; encontrados {len(fields)}.",
        )
    return fields[0]


async def close_representation_menu(page: Page) -> None:
    fields = await visible_items(page.locator(CNPJ_INPUT_SELECTOR))
    if not fields:
        return
    close_buttons = await visible_items(page.get_by_role("button", name="Fechar Menu"))
    if close_buttons:
        await close_buttons[0].click()
    else:
        await page.keyboard.press("Escape")
    try:
        await page.locator(CNPJ_INPUT_SELECTOR).wait_for(state="hidden", timeout=10000)
    except Exception as exc:
        raise WorkerError(
            "representation_menu_not_closed",
            "close_representation_panel",
            f"A barra de representação não fechou: {exc}",
        ) from exc


async def fill_cnpj(field: Locator, company: QueueCompany) -> None:
    try:
        await field.click()
        await field.fill("")
        await field.press_sequentially(company.identificador, delay=90)
    except Exception as exc:
        raise WorkerError(
            "cnpj_fill_failed",
            "fill_cnpj",
            f"Não foi possível preencher o CNPJ no campo interno: {exc}",
        ) from exc
    typed = digits_only(await field.input_value())
    if typed != company.identificador:
        raise RepresentationSafetyError(
            "typed_cnpj_mismatch",
            "fill_cnpj",
            f"O campo contém {masked_identifier(typed)} em vez do CNPJ solicitado.",
        )


async def validate_representation_form(
    page: Page,
    field: Locator,
    company: QueueCompany,
) -> Locator:
    submits = await visible_items(page.locator(SUBMIT_SELECTOR))
    if len(submits) != 1:
        raise WorkerError(
            "represent_submit_not_unique",
            "find_submit",
            f"Esperado 1 botão submit Representar visível; encontrados {len(submits)}.",
        )
    submit = submits[0]
    if not await submit.is_enabled():
        raise WorkerError(
            "represent_submit_disabled",
            "find_submit",
            "O botão submit Representar está visível, mas desabilitado.",
        )
    form = submit.locator("xpath=ancestor::form[1]")
    if await form.count() != 1 or not await form.is_visible():
        raise WorkerError(
            "representation_form_not_found",
            "find_submit",
            "O botão submit correto não pertence a um formulário visível único.",
        )
    form_fields = await visible_items(form.locator(CNPJ_INPUT_SELECTOR))
    if len(form_fields) != 1:
        raise WorkerError(
            "cnpj_field_not_in_submit_form",
            "find_submit",
            "O campo interno de CNPJ e o submit Representar não estão no mesmo formulário.",
        )
    typed = digits_only(await form_fields[0].input_value())
    if typed != company.identificador:
        raise RepresentationSafetyError(
            "form_cnpj_mismatch",
            "find_submit",
            "O formulário do botão Representar não corresponde ao CNPJ solicitado.",
        )
    return form


async def critical_submit_sequence(page: Any, procurador_option: Locator) -> None:
    """Exact sequence: no focus changes, diagnostics or file writes between actions."""
    await procurador_option.click()
    await page.keyboard.press("Tab")
    await page.wait_for_timeout(300)
    await page.keyboard.press("Tab")
    await page.wait_for_timeout(300)
    await page.keyboard.press("Space")


async def select_procurador_and_submit(
    page: Page,
    form: Locator,
    company: QueueCompany,
    logger: EventLogger,
) -> None:
    combos = await visible_items(form.locator(COMBO_SELECTOR))
    if len(combos) != 1:
        raise WorkerError(
            "procurador_field_not_found",
            "select_procurador",
            f"Esperado 1 campo interno do perfil no formulário; encontrados {len(combos)}.",
        )
    logger.emit(
        "before_procurador_selection",
        company=company.nome,
        identifier=company.identificador,
        stage="select_procurador",
        code=company.codigo,
    )
    try:
        await combos[0].scroll_into_view_if_needed()
        await combos[0].click()
        options = await visible_items(page.get_by_role("option", name="Procurador", exact=True))
        if len(options) != 1:
            raise WorkerError(
                "procurador_option_not_unique",
                "select_procurador",
                f"Esperada 1 opção Procurador visível; encontradas {len(options)}.",
            )
        await critical_submit_sequence(page, options[0])
    except WorkerError:
        raise
    except Exception as exc:
        raise WorkerError(
            "procurador_or_submit_failed",
            "select_procurador",
            f"Falha ao selecionar Procurador ou enviar Tab/Tab/Espaço: {exc}",
        ) from exc

    logger.emit(
        "representation_sequence_sent",
        company=company.nome,
        identifier=company.identificador,
        stage="submit_representation",
        code=company.codigo,
        sequence="Tab,300ms,Tab,300ms,Space",
    )


async def wait_confirmed_analysis(
    page: Page,
    progress: Any,
    logger: EventLogger,
    company: QueueCompany,
) -> tuple[str, str]:
    deadline = monotonic() + 90
    while monotonic() < deadline:
        await wait_human_security_challenge(page, progress)
        if await explicit_no_authorization_visible(page):
            raise WorkerError(
                "explicit_no_authorization",
                "confirm_representation",
                "O portal informou explicitamente ausência de procuração ativa.",
            )
        main = page.get_by_role("main").last
        try:
            text = await main.inner_text(timeout=2000)
        except Exception:
            text = ""
        heading_visible = await visible_text(page, ANALYSIS_HEADING_RE)
        result = parse_analysis_result(text, company.identificador, heading_visible)
        if result is not None:
            logger.emit(
                "representation_confirmed",
                company=company.nome,
                identifier=company.identificador,
                stage="confirm_representation",
                code=company.codigo,
                result=result,
            )
            return result, text
        await asyncio.sleep(1)

    raise RepresentationSafetyError(
        "representation_not_confirmed",
        "confirm_representation",
        (
            "Representar foi acionado, mas o Resultado da Análise não confirmou o CNPJ "
            "solicitado e o resultado correspondente dentro de 90 segundos."
        ),
    )
