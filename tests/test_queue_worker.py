import json
from pathlib import Path

import pytest

from receita_automacao.portal_representation import critical_submit_sequence
from receita_automacao.queue_contract import ResultStore, load_queue
from receita_automacao.worker_common import (
    classify_explicit_no_authorization,
    parse_analysis_result,
)

VALID_CNPJ = "11222333000181"
OTHER_CNPJ = "11444777000161"


def make_queue(tmp_path: Path) -> Path:
    queue = {
        "tipo": "RECEITA",
        "cdpUrl": "http://127.0.0.1:9225",
        "progressPath": str(tmp_path / "progresso.json"),
        "progressTextPath": str(tmp_path / "progresso.txt"),
        "resultPath": str(tmp_path / "resultado.json"),
        "resultTsvPath": str(tmp_path / "resultado.tsv"),
        "pausePath": str(tmp_path / "pausar.flag"),
        "outputDirectory": str(tmp_path / "relatorios"),
        "empresas": [
            {
                "codigo": "1",
                "nome": "EMPRESA TESTE",
                "identificador": VALID_CNPJ,
                "tipoIdentificador": "CNPJ",
                "tipoInscricao": "CNPJ",
            },
            {
                "codigo": "2",
                "nome": "PESSOA MANUAL",
                "identificador": "12345678901",
                "tipoIdentificador": "CPF",
                "tipoInscricao": "CPF",
            },
            {
                "codigo": "3",
                "nome": "CNPJ INVALIDO",
                "identificador": "11111111111111",
                "tipoIdentificador": "CNPJ",
                "tipoInscricao": "CNPJ",
            },
        ],
    }
    path = tmp_path / "fila.json"
    path.write_text(json.dumps(queue), encoding="utf-8")
    return path


def test_load_queue_filters_to_valid_cnpj(tmp_path):
    queue = load_queue(make_queue(tmp_path))
    assert [company.codigo for company in queue.companies] == ["1"]
    assert queue.companies[0].identificador == VALID_CNPJ
    assert queue.manual_skipped == 2


def test_analysis_requires_requested_cnpj_and_explicit_result():
    text = f"Dados cadastrais CNPJ {VALID_CNPJ} Resultado da Análise Sem pendência"
    assert parse_analysis_result(text, VALID_CNPJ, True) == "SEM_PENDENCIAS"
    assert parse_analysis_result(text, OTHER_CNPJ, True) is None
    assert parse_analysis_result(text, VALID_CNPJ, False) is None
    assert parse_analysis_result(f"CNPJ {VALID_CNPJ} Resultado da Análise", VALID_CNPJ, True) is None


def test_generic_navigation_error_is_not_no_authorization():
    assert not classify_explicit_no_authorization("Empresa não localizada")
    assert not classify_explicit_no_authorization("Falha na navegação do portal")
    assert classify_explicit_no_authorization("A empresa não possui procuração ativa")


def test_result_store_preserves_legacy_tsv_contract(tmp_path):
    queue = load_queue(make_queue(tmp_path))
    store = ResultStore(queue)
    store.append(
        {
            "codigo": "1",
            "nome": "EMPRESA TESTE",
            "dataHora": "11/09/2026 21:00:00",
            "status": "Concluido",
            "resultado": "Sem pendencias",
            "relatorio": "",
            "quantidade": 0,
            "competencias": "",
            "detalhes": "Relatório não necessário: resultado sem pendências.",
        }
    )

    raw_bytes = queue.paths.result_tsv_path.read_bytes()
    assert raw_bytes.startswith(b"\xef\xbb\xbf")
    assert b"\r\r\n" not in raw_bytes
    assert b"\r\n" in raw_bytes

    raw = queue.paths.result_tsv_path.read_text(encoding="utf-8-sig")
    lines = raw.splitlines()
    assert lines[0] == "codigo\tnome\tdataHora\tstatus\tresultado\trelatorio\tquantidade\tcompetencias\tdetalhes"
    assert lines[1].split("\t")[:5] == [
        "1",
        "EMPRESA TESTE",
        "11/09/2026 21:00:00",
        "Concluido",
        "Sem pendencias",
    ]


class FakeKeyboard:
    def __init__(self, events):
        self.events = events

    async def press(self, key):
        self.events.append(("press", key))


class FakePage:
    def __init__(self, events):
        self.events = events
        self.keyboard = FakeKeyboard(events)

    async def wait_for_timeout(self, milliseconds):
        self.events.append(("wait", milliseconds))


class FakeOption:
    def __init__(self, events):
        self.events = events

    async def click(self):
        self.events.append(("click", "Procurador"))


@pytest.mark.asyncio
async def test_critical_sequence_has_no_extra_operations():
    events = []
    await critical_submit_sequence(FakePage(events), FakeOption(events))
    assert events == [
        ("click", "Procurador"),
        ("press", "Tab"),
        ("wait", 300),
        ("press", "Tab"),
        ("wait", 300),
        ("press", "Space"),
    ]
