from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import tomllib


@dataclass(frozen=True, slots=True)
class ExcelConfig:
    workbook_path: Path
    sheet_name: str
    header_row: int
    selection_header: str
    entity_type_header: str
    identifier_header: str
    company_name_header: str
    status_header: str
    report_path_header: str
    processed_at_header: str
    selected_values: tuple[str, ...]
    skip_rows_with_existing_status: bool
    overwrite_existing_results: bool
    attach_if_open: bool
    excel_visible: bool


@dataclass(frozen=True, slots=True)
class PortalConfig:
    url: str
    browser_channel: str
    manual_login_timeout_seconds: int
    representation_timeout_seconds: int
    analysis_timeout_seconds: int
    download_timeout_seconds: int
    minimum_seconds_between_representations: int
    submit_selector: str
    cnpj_input_selector: str
    procurador_select_selector: str
    procurador_option_selector: str
    sidebar_toggle_selector: str
    identity_scope_selector: str
    report_download_selector: str
    no_pendencies_texts: tuple[str, ...]
    pending_texts: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RuntimeConfig:
    state_db: Path
    event_log: Path
    evidence_dir: Path
    report_dir: Path
    browser_profile_dir: Path


@dataclass(frozen=True, slots=True)
class AppConfig:
    excel: ExcelConfig
    portal: PortalConfig
    runtime: RuntimeConfig


def _resolve(base: Path, raw: str) -> Path:
    expanded = Path(os.path.expandvars(raw)).expanduser()
    return expanded if expanded.is_absolute() else (base / expanded).resolve()


def load_config(path: str | Path) -> AppConfig:
    config_path = Path(path).expanduser().resolve()
    with config_path.open("rb") as handle:
        data = tomllib.load(handle)

    base = config_path.parent
    excel = data["excel"]
    portal = data["portal"]
    runtime = data["runtime"]

    return AppConfig(
        excel=ExcelConfig(
            workbook_path=_resolve(base, excel["workbook_path"]),
            sheet_name=str(excel["sheet_name"]),
            header_row=int(excel.get("header_row", 1)),
            selection_header=str(excel["selection_header"]),
            entity_type_header=str(excel["entity_type_header"]),
            identifier_header=str(excel["identifier_header"]),
            company_name_header=str(excel["company_name_header"]),
            status_header=str(excel["status_header"]),
            report_path_header=str(excel["report_path_header"]),
            processed_at_header=str(excel["processed_at_header"]),
            selected_values=tuple(str(v).strip().upper() for v in excel.get("selected_values", ["SIM"])),
            skip_rows_with_existing_status=bool(excel.get("skip_rows_with_existing_status", True)),
            overwrite_existing_results=bool(excel.get("overwrite_existing_results", False)),
            attach_if_open=bool(excel.get("attach_if_open", True)),
            excel_visible=bool(excel.get("excel_visible", False)),
        ),
        portal=PortalConfig(
            url=str(portal["url"]),
            browser_channel=str(portal.get("browser_channel", "msedge")),
            manual_login_timeout_seconds=int(portal.get("manual_login_timeout_seconds", 900)),
            representation_timeout_seconds=int(portal.get("representation_timeout_seconds", 35)),
            analysis_timeout_seconds=int(portal.get("analysis_timeout_seconds", 90)),
            download_timeout_seconds=int(portal.get("download_timeout_seconds", 60)),
            minimum_seconds_between_representations=int(portal.get("minimum_seconds_between_representations", 40)),
            submit_selector=str(portal["submit_selector"]),
            cnpj_input_selector=str(portal["cnpj_input_selector"]),
            procurador_select_selector=str(portal["procurador_select_selector"]),
            procurador_option_selector=str(portal["procurador_option_selector"]),
            sidebar_toggle_selector=str(portal.get("sidebar_toggle_selector", "")).strip(),
            identity_scope_selector=str(portal.get("identity_scope_selector", "")).strip(),
            report_download_selector=str(portal.get("report_download_selector", "")).strip(),
            no_pendencies_texts=tuple(str(v) for v in portal.get("no_pendencies_texts", [])),
            pending_texts=tuple(str(v) for v in portal.get("pending_texts", [])),
        ),
        runtime=RuntimeConfig(
            state_db=_resolve(base, runtime.get("state_db", ".runtime/estado.sqlite3")),
            event_log=_resolve(base, runtime.get("event_log", ".runtime/logs/automacao.jsonl")),
            evidence_dir=_resolve(base, runtime.get("evidence_dir", ".runtime/evidence")),
            report_dir=_resolve(base, runtime.get("report_dir", ".runtime/reports")),
            browser_profile_dir=_resolve(base, runtime.get("browser_profile_dir", ".runtime/browser-profile")),
        ),
    )
