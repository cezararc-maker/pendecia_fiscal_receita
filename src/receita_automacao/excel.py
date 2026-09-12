from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import ExcelConfig
from .models import CompanyRecord, digits_only, parse_entity_type


class ExcelIntegrationError(RuntimeError):
    pass


class ExcelGateway:
    """Edits the existing workbook through Excel COM to preserve VBA/buttons/features."""

    def __init__(self, config: ExcelConfig):
        self.config = config
        self.app: Any = None
        self.workbook: Any = None
        self.sheet: Any = None
        self._owns_app = False
        self._owns_workbook = False
        self.headers: dict[str, int] = {}

    def __enter__(self) -> "ExcelGateway":
        if not self.config.workbook_path.exists():
            raise ExcelIntegrationError(f"Planilha não encontrada: {self.config.workbook_path}")
        try:
            import win32com.client  # type: ignore[import-not-found]
        except ImportError as exc:
            raise ExcelIntegrationError("pywin32 é obrigatório no Windows para preservar a planilha .xlsm") from exc

        if self.config.attach_if_open:
            try:
                self.app = win32com.client.GetActiveObject("Excel.Application")
            except Exception:
                self.app = None

        if self.app is None:
            self.app = win32com.client.DispatchEx("Excel.Application")
            self._owns_app = True
            self.app.Visible = self.config.excel_visible

        target = str(self.config.workbook_path.resolve()).casefold()
        for workbook in self.app.Workbooks:
            try:
                if str(Path(workbook.FullName).resolve()).casefold() == target:
                    self.workbook = workbook
                    break
            except Exception:
                continue

        if self.workbook is None:
            self.workbook = self.app.Workbooks.Open(str(self.config.workbook_path.resolve()))
            self._owns_workbook = True

        try:
            self.sheet = self.workbook.Worksheets(self.config.sheet_name)
        except Exception as exc:
            raise ExcelIntegrationError(f"Aba não encontrada: {self.config.sheet_name}") from exc

        self.headers = self._read_headers()
        self._require_headers()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        try:
            if self._owns_workbook and self.workbook is not None:
                self.workbook.Close(SaveChanges=False)
        finally:
            if self._owns_app and self.app is not None:
                self.app.Quit()

    def _read_headers(self) -> dict[str, int]:
        used_columns = int(self.sheet.UsedRange.Columns.Count)
        headers: dict[str, int] = {}
        for column in range(1, used_columns + 1):
            value = self.sheet.Cells(self.config.header_row, column).Value
            label = str(value or "").strip()
            if label:
                headers[label] = column
        return headers

    def _require_headers(self) -> None:
        required = [
            self.config.selection_header,
            self.config.entity_type_header,
            self.config.identifier_header,
            self.config.company_name_header,
            self.config.status_header,
            self.config.report_path_header,
            self.config.processed_at_header,
        ]
        missing = [header for header in required if header not in self.headers]
        if missing:
            raise ExcelIntegrationError("Cabeçalhos não encontrados: " + ", ".join(missing))

    def read_selected_companies(self) -> list[CompanyRecord]:
        last_row = int(self.sheet.UsedRange.Rows.Count + self.sheet.UsedRange.Row - 1)
        selected = set(self.config.selected_values)
        records: list[CompanyRecord] = []

        for row in range(self.config.header_row + 1, last_row + 1):
            selection = str(self.sheet.Cells(row, self.headers[self.config.selection_header]).Value or "").strip().upper()
            if selection not in selected:
                continue

            entity_type = parse_entity_type(self.sheet.Cells(row, self.headers[self.config.entity_type_header]).Value)
            identifier = digits_only(self.sheet.Cells(row, self.headers[self.config.identifier_header]).Value)
            company_name = str(self.sheet.Cells(row, self.headers[self.config.company_name_header]).Value or "").strip()
            previous_status = str(self.sheet.Cells(row, self.headers[self.config.status_header]).Value or "").strip()
            source_key = f"{self.config.workbook_path.resolve()}|{self.config.sheet_name}|{row}|{identifier}"
            records.append(
                CompanyRecord(
                    source_key=source_key,
                    row_number=row,
                    company_name=company_name,
                    entity_type=entity_type,
                    identifier=identifier,
                    previous_status=previous_status,
                )
            )
        return records

    def write_result(self, row: int, status: str, report_path: str | None, processed_at: str) -> bool:
        status_cell = self.sheet.Cells(row, self.headers[self.config.status_header])
        existing = str(status_cell.Value or "").strip()
        if existing and not self.config.overwrite_existing_results:
            return False

        status_cell.Value = status
        self.sheet.Cells(row, self.headers[self.config.report_path_header]).Value = report_path or ""
        self.sheet.Cells(row, self.headers[self.config.processed_at_header]).Value = processed_at
        return True

    def save(self) -> None:
        self.workbook.Save()
