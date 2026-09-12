from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
from time import monotonic
from typing import Any

from .models import digits_only
from .worker_common import QueueCompany, clean, format_duration

RESULT_HEADERS = (
    "codigo", "nome", "dataHora", "status", "resultado", "relatorio",
    "quantidade", "competencias", "detalhes",
)
TERMINAL_STATUSES = {
    "CONCLUIDO", "CONCLUIDO_COM_ERROS", "ERRO_FATAL", "CANCELADO", "PORTAL_INSTAVEL",
}


@dataclass(frozen=True, slots=True)
class QueuePaths:
    queue_path: Path
    progress_path: Path
    progress_text_path: Path
    result_path: Path
    result_tsv_path: Path
    pause_path: Path
    output_directory: Path
    execution_directory: Path
    event_log: Path
    evidence_directory: Path


@dataclass(frozen=True, slots=True)
class QueueInput:
    cdp_url: str
    companies: tuple[QueueCompany, ...]
    manual_skipped: int
    paths: QueuePaths


def _path_from_queue(raw: dict[str, Any], key: str, fallback: Path) -> Path:
    value = str(raw.get(key) or "").strip()
    return Path(value).expanduser() if value else fallback


def load_queue(path: Path) -> QueueInput:
    raw = json.loads(path.read_text(encoding="utf-8-sig"))
    if str(raw.get("tipo") or "").upper() != "RECEITA":
        raise ValueError("O worker Python desta etapa aceita somente filas RECEITA.")

    execution = path.resolve().parent
    paths = QueuePaths(
        queue_path=path.resolve(),
        progress_path=_path_from_queue(raw, "progressPath", execution / "progresso.json"),
        progress_text_path=_path_from_queue(raw, "progressTextPath", execution / "progresso.txt"),
        result_path=_path_from_queue(raw, "resultPath", execution / "resultado.json"),
        result_tsv_path=_path_from_queue(raw, "resultTsvPath", execution / "resultado.tsv"),
        pause_path=_path_from_queue(raw, "pausePath", execution / "pausar.flag"),
        output_directory=_path_from_queue(raw, "outputDirectory", execution / "relatorios"),
        execution_directory=execution,
        event_log=execution / "automacao-python.jsonl",
        evidence_directory=execution / "evidencias",
    )

    all_companies: list[QueueCompany] = []
    for item in raw.get("empresas") or []:
        all_companies.append(
            QueueCompany(
                codigo=clean(item.get("codigo")),
                nome=clean(item.get("nome")),
                identificador=digits_only(item.get("identificador")),
                tipo_identificador=clean(item.get("tipoIdentificador")).upper(),
                tipo_inscricao=clean(item.get("tipoInscricao")).upper(),
            )
        )

    eligible = tuple(company for company in all_companies if company.is_eligible_receita)
    if not eligible:
        raise ValueError("A fila não contém CNPJ válido elegível para consulta automática na Receita.")
    return QueueInput(
        cdp_url=str(raw.get("cdpUrl") or "http://127.0.0.1:9225"),
        companies=eligible,
        manual_skipped=len(all_companies) - len(eligible),
        paths=paths,
    )


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(text, encoding="utf-8")
    temp.replace(path)


class ProgressState:
    def __init__(self, queue: QueueInput):
        self.queue = queue
        self.started_at = monotonic()
        self.paused_total = 0.0
        self.pause_started_at: float | None = None
        self.data: dict[str, Any] = {
            "status": "INICIANDO", "percent": 0, "currentCode": "", "currentName": "",
            "stage": "Conectando ao navegador", "completed": 0, "total": len(queue.companies),
            "successful": 0, "withoutAuthorization": 0, "errors": 0,
            "manualSkipped": queue.manual_skipped, "message": "", "elapsedSeconds": 0,
            "elapsedTime": "00:00:00", "estimatedSecondsRemaining": 0,
            "estimatedRemaining": "Calculando...", "phase": 0.0,
        }

    def _recalculate(self) -> None:
        current_pause = 0.0 if self.pause_started_at is None else monotonic() - self.pause_started_at
        elapsed = max(0.0, monotonic() - self.started_at - self.paused_total - current_pause)
        self.data["elapsedSeconds"] = round(elapsed)
        self.data["elapsedTime"] = format_duration(elapsed)
        processed = max(
            0.0,
            float(self.data.get("completed", 0)) + float(self.data.get("phase", 0) or 0),
        )
        total = max(1, int(self.data.get("total", 0) or 0))
        self.data["percent"] = round(processed / total * 100)
        terminal = self.data.get("status") in TERMINAL_STATUSES
        completed = int(self.data.get("completed", 0) or 0)
        average = elapsed / completed if completed else 70.0
        remaining = 0 if terminal else max(0, round((total - processed) * average))
        self.data["estimatedSecondsRemaining"] = remaining
        if self.data.get("status") == "PAUSADO":
            self.data["estimatedRemaining"] = "Pausado"
        else:
            self.data["estimatedRemaining"] = "00:00:00" if terminal else format_duration(remaining)

    def update(self, **patch: Any) -> None:
        self.data.update(patch)
        self._recalculate()
        atomic_write(self.queue.paths.progress_path, json.dumps(self.data, ensure_ascii=False, indent=2))
        lines = [f"{key}={clean(value)}" for key, value in self.data.items()]
        atomic_write(self.queue.paths.progress_text_path, "\r\n".join(lines) + "\r\n")


class ResultStore:
    def __init__(self, queue: QueueInput):
        self.queue = queue
        self.results: list[dict[str, Any]] = self._load_existing()

    def _load_existing(self) -> list[dict[str, Any]]:
        path = self.queue.paths.result_path
        if not path.exists():
            return []
        try:
            raw = json.loads(path.read_text(encoding="utf-8-sig"))
            values = raw.get("results") if isinstance(raw, dict) else None
            return list(values) if isinstance(values, list) else []
        except Exception:
            return []

    @property
    def completed_codes(self) -> set[str]:
        return {
            clean(item.get("codigo"))
            for item in self.results
            if clean(item.get("status")).lower() == "concluido"
        }

    def append(self, result: dict[str, Any]) -> None:
        code = clean(result.get("codigo"))
        self.results = [item for item in self.results if clean(item.get("codigo")) != code]
        self.results.append(result)
        self.save()

    def save(self) -> None:
        payload = {
            "generatedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
            "type": "RECEITA",
            "results": self.results,
        }
        atomic_write(self.queue.paths.result_path, json.dumps(payload, ensure_ascii=False, indent=2))
        lines = ["\t".join(RESULT_HEADERS)]
        for result in self.results:
            lines.append("\t".join(clean(result.get(header, "")) for header in RESULT_HEADERS))
        atomic_write(self.queue.paths.result_tsv_path, "\ufeff" + "\r\n".join(lines) + "\r\n")
