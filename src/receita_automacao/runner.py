from __future__ import annotations

import asyncio
from pathlib import Path

from .config import AppConfig
from .eventlog import EventLogger
from .excel import ExcelGateway
from .models import CompanyRecord
from .portal import PortalStageError, ReceitaPortalClient
from .state import StateStore


class AutomationRunner:
    def __init__(self, config: AppConfig):
        self.config = config
        self.logger = EventLogger(config.runtime.event_log)
        self.state = StateStore(config.runtime.state_db)

    async def run(self, *, limit: int | None = None, retry_failed: bool = False) -> None:
        self.state.set_control("run")
        if retry_failed:
            self.state.requeue_failed()

        with ExcelGateway(self.config.excel) as excel:
            selected = excel.read_selected_companies()
            eligible: list[CompanyRecord] = []
            for record in selected:
                if not record.eligible_for_automation:
                    self.logger.emit(
                        "manual_or_invalid_identifier_skipped",
                        company=record.company_name,
                        identifier=record.identifier,
                        stage="queue",
                        entity_type=record.entity_type.value,
                    )
                    continue
                if self.config.excel.skip_rows_with_existing_status and record.previous_status:
                    self.logger.emit(
                        "existing_result_preserved",
                        company=record.company_name,
                        identifier=record.identifier,
                        stage="queue",
                    )
                    continue
                eligible.append(record)

            self.state.register(eligible)
            self._sync_completed_to_excel(excel)

            jobs = self.state.pending(limit=limit)
            if not jobs:
                self.logger.emit("queue_empty", stage="queue")
                return

            async with ReceitaPortalClient(self.config.portal, self.config.runtime, self.logger) as portal:
                for company in jobs:
                    if not await self._wait_until_allowed(portal):
                        self.logger.emit("processing_stopped_by_user", stage="control")
                        return

                    self.state.mark_started(company.source_key)
                    started = self.logger.timer()
                    self.logger.emit(
                        "company_started",
                        company=company.company_name,
                        identifier=company.identifier,
                        stage="start",
                    )
                    try:
                        result = await portal.process_company(company)
                        processed_at = self.state.mark_result(
                            company.source_key,
                            result.status.value,
                            result.report_path,
                        )
                        status_text = "SEM PENDÊNCIAS" if result.status.value == "SEM_PENDENCIAS" else "COM PENDÊNCIAS"
                        written = excel.write_result(
                            company.row_number,
                            status_text,
                            result.report_path,
                            processed_at,
                        )
                        if written:
                            excel.save()
                            self.state.mark_excel_synced(company.source_key)
                        else:
                            self.logger.emit(
                                "excel_result_not_overwritten",
                                company=company.company_name,
                                identifier=company.identifier,
                                stage="excel_write",
                            )
                    except PortalStageError as exc:
                        evidence = await portal.capture_evidence(exc.stage, company.identifier)
                        self.state.mark_failed(company.source_key, exc.code, str(exc))
                        self.logger.emit(
                            "portal_failure",
                            company=company.company_name,
                            identifier=company.identifier,
                            stage=exc.stage,
                            duration_seconds=self.logger.elapsed(started),
                            error_code=exc.code,
                            error_original=str(exc),
                            evidence_path=evidence,
                        )
                        # Fail closed: do not continue to another taxpayer after portal uncertainty.
                        return
                    except Exception as exc:
                        evidence = await portal.capture_evidence("unexpected", company.identifier)
                        self.state.mark_failed(company.source_key, "unexpected_error", repr(exc))
                        self.logger.emit(
                            "unexpected_failure",
                            company=company.company_name,
                            identifier=company.identifier,
                            stage="unexpected",
                            duration_seconds=self.logger.elapsed(started),
                            error_original=repr(exc),
                            evidence_path=evidence,
                        )
                        return

    def _sync_completed_to_excel(self, excel: ExcelGateway) -> None:
        for row in self.state.unsynced_completed():
            portal_result = str(row["portal_result"] or "")
            status_text = "SEM PENDÊNCIAS" if portal_result == "SEM_PENDENCIAS" else "COM PENDÊNCIAS"
            written = excel.write_result(
                int(row["row_number"]),
                status_text,
                row["report_path"],
                str(row["processed_at"] or ""),
            )
            if written:
                excel.save()
                self.state.mark_excel_synced(str(row["source_key"]))

    async def _wait_until_allowed(self, portal: ReceitaPortalClient) -> bool:
        while True:
            command = self.state.get_control()
            if command == "stop":
                return False
            if command == "pause":
                await asyncio.sleep(1)
                continue
            remaining = portal.seconds_until_next_representation()
            if remaining <= 0:
                return True
            await asyncio.sleep(min(1.0, remaining))
