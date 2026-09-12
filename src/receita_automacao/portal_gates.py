from __future__ import annotations

import asyncio
from time import monotonic
from typing import Any

from playwright.async_api import Locator, Page

from .eventlog import EventLogger
from .models import digits_only
from .worker_common import (
    EXPLICIT_NO_AUTH_RE,
    QueueCompany,
    RepresentationSafetyError,
    SECURITY_CHALLENGE_RE,
    WorkerError,
    clean,
    format_cnpj,
)


async def visible_items(locator: Locator, limit: int = 20) -> list[Locator]:
    items: list[Locator] = []
    count = await locator.count()
    for index in range(min(count, limit)):
        item = locator.nth(index)
        try:
            if await item.is_visible():
                items.append(item)
        except Exception:
            continue
    return items


async def visible_text(root: Any, regex: Any) -> bool:
    locator = root.get_by_text(regex).first
    try:
        return await locator.is_visible()
    except Exception:
        return False


async def explicit_no_authorization_visible(page: Page) -> bool:
    return await visible_text(page, EXPLICIT_NO_AUTH_RE)


async def ensure_authenticated(page: Page) -> None:
    if "acesso.gov.br" in page.url or "/login" in page.url.lower():
        raise WorkerError(
            "login_required",
            "login",
            "Portal da Receita sem login. Use Preparar navegador e conclua o acesso com certificado.",
            fatal=True,
        )


async def wait_human_security_challenge(page: Page, progress: Any) -> None:
    await ensure_authenticated(page)
    warned = False
    deadline = monotonic() + 300
    while monotonic() < deadline:
        await ensure_authenticated(page)
        page_challenge = await visible_text(page, SECURITY_CHALLENGE_RE)
        frame_challenge = False
        for frame in page.frames:
            try:
                if await visible_text(frame, SECURITY_CHALLENGE_RE):
                    frame_challenge = True
                    break
            except Exception:
                continue
        if not page_challenge and not frame_challenge:
            if warned:
                progress.update(
                    status="PROCESSANDO",
                    stage="Validação de segurança concluída",
                    message="",
                )
            return
        warned = True
        progress.update(
            status="AGUARDANDO_VALIDACAO",
            stage="Desafio de segurança do portal",
            message=(
                "Resolva manualmente o desafio no navegador. "
                "A consulta retomará automaticamente nesta empresa."
            ),
        )
        await asyncio.sleep(1)
    raise WorkerError(
        "security_challenge_timeout",
        "security_challenge",
        "O desafio de segurança não foi concluído dentro de 5 minutos.",
        fatal=True,
    )


async def handle_post_submit_confirmation(
    page: Page,
    progress: Any,
    logger: EventLogger,
    company: QueueCompany,
) -> None:
    """Wait only for a distinct post-submit Representar dialog; never resubmit the form blindly."""
    await wait_human_security_challenge(page, progress)
    dialogs = page.get_by_role("dialog").filter(
        has=page.get_by_role("heading", name="Representar", exact=True)
    )
    visible = await visible_items(dialogs)
    if not visible:
        return
    if len(visible) != 1:
        raise RepresentationSafetyError(
            "additional_confirmation_not_unique",
            "additional_confirmation",
            "O portal exibiu mais de uma confirmação de representação visível.",
        )

    dialog = visible[0]
    text = clean(await dialog.inner_text())
    digits = digits_only(text)
    if len(digits) >= 14 and company.identificador not in digits:
        raise RepresentationSafetyError(
            "additional_confirmation_cnpj_mismatch",
            "additional_confirmation",
            "A confirmação adicional do portal referencia outro CNPJ.",
        )

    progress.update(
        status="AGUARDANDO_CONFIRMACAO",
        stage="Confirmação adicional do portal",
        message=(
            "Confirme manualmente no navegador a representação do CNPJ "
            f"{format_cnpj(company.identificador)}."
        ),
    )
    logger.emit(
        "additional_confirmation_required",
        company=company.nome,
        identifier=company.identificador,
        stage="additional_confirmation",
        code=company.codigo,
    )

    deadline = monotonic() + 180
    while monotonic() < deadline:
        await wait_human_security_challenge(page, progress)
        if not await dialog.is_visible():
            progress.update(
                status="PROCESSANDO",
                stage="Confirmação adicional concluída",
                message="",
            )
            return
        await asyncio.sleep(1)

    raise RepresentationSafetyError(
        "additional_confirmation_timeout",
        "additional_confirmation",
        "A confirmação adicional não foi concluída dentro de 3 minutos.",
    )
