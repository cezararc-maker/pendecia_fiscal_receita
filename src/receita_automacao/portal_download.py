from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re

from playwright.async_api import Page

from .portal_gates import visible_items
from .worker_common import PORTAL_INSTABILITY_RE, PortalUnstableError, QueueCompany, WorkerError, clean


async def download_receita_report(page: Page, company: QueueCompany, output_directory: Path) -> str:
    control = None
    last_count = 0
    for collection in (
        page.get_by_role("button", name=re.compile(r"Baixar\s+Relat.rio", re.IGNORECASE)),
        page.get_by_role("link", name=re.compile(r"Baixar\s+Relat.rio", re.IGNORECASE)),
        page.get_by_text(re.compile(r"^Baixar\s+Relat.rio$", re.IGNORECASE)),
    ):
        visible = await visible_items(collection, limit=10)
        last_count = len(visible)
        if len(visible) == 1:
            control = visible[0]
            break
        if len(visible) > 1:
            raise WorkerError(
                "report_download_control_not_unique",
                "download_report",
                f"Foram encontrados {len(visible)} controles Baixar Relatório visíveis.",
            )

    if control is None:
        raise WorkerError(
            "report_download_control_not_found",
            "download_report",
            f"Nenhum controle único Baixar Relatório foi localizado (última contagem: {last_count}).",
        )

    output_directory.mkdir(parents=True, exist_ok=True)
    filename = (
        f"{company.codigo} - Situacao Fiscal {company.identificador} "
        f"{datetime.now().strftime('%Y%m%d')}.pdf"
    )
    destination = output_directory / re.sub(r'[<>:"/\\|?*]+', "_", filename)
    instability = page.get_by_text(PORTAL_INSTABILITY_RE).first

    try:
        async with page.expect_download(timeout=30000) as info:
            await control.scroll_into_view_if_needed()
            await control.click()
        download = await info.value
        await download.save_as(str(destination))
        return str(destination.resolve())
    except Exception as exc:
        try:
            portal_instable = await instability.is_visible()
        except Exception:
            portal_instable = False
        if portal_instable:
            message = clean(await instability.inner_text())
            raise PortalUnstableError(
                "download_report",
                message or "O portal não conseguiu gerar o relatório.",
            ) from exc
        raise WorkerError(
            "report_download_failed",
            "download_report",
            f"O download do relatório não foi concluído: {exc}",
        ) from exc
