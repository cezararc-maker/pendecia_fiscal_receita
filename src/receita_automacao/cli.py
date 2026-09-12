from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from .config import load_config
from .eventlog import EventLogger
from .portal import ReceitaPortalClient
from .runner import AutomationRunner
from .state import StateStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="receita-pendencias")
    parser.add_argument("--config", default="config.local.toml", help="Arquivo TOML local")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Processar fila selecionada na planilha")
    run.add_argument("--limit", type=int, default=None, help="Limitar quantidade de empresas")
    run.add_argument("--retry-failed", action="store_true", help="Recolocar falhas anteriores na fila")

    sub.add_parser("status", help="Mostrar resumo local da fila")
    sub.add_parser("pause", help="Pausar antes da próxima empresa")
    sub.add_parser("resume", help="Retomar processamento")
    sub.add_parser("stop", help="Interromper antes da próxima empresa segura")
    sub.add_parser("probe", help="Abrir portal e diagnosticar localizadores sem representar empresa")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    config = load_config(Path(args.config))
    state = StateStore(config.runtime.state_db)

    if args.command == "run":
        asyncio.run(AutomationRunner(config).run(limit=args.limit, retry_failed=args.retry_failed))
        return
    if args.command == "status":
        print(json.dumps(state.summary(), ensure_ascii=False, indent=2))
        return
    if args.command in {"pause", "resume", "stop"}:
        state.set_control("run" if args.command == "resume" else args.command)
        print(f"Controle atualizado: {args.command}")
        return
    if args.command == "probe":
        asyncio.run(_probe(config))


async def _probe(config) -> None:
    logger = EventLogger(config.runtime.event_log)
    async with ReceitaPortalClient(config.portal, config.runtime, logger) as portal:
        print(json.dumps(await portal.probe(), ensure_ascii=False, indent=2))
