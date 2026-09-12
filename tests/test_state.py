from receita_automacao.models import CompanyRecord, EntityType
from receita_automacao.state import StateStore


def test_completed_job_is_preserved_and_not_requeued(tmp_path):
    store = StateStore(tmp_path / "state.sqlite3")
    record = CompanyRecord("source|2|11222333000181", 2, "Empresa Teste", EntityType.CNPJ, "11222333000181")
    store.register([record])
    assert len(store.pending()) == 1

    store.mark_started(record.source_key)
    store.mark_result(record.source_key, "SEM_PENDENCIAS", None)

    assert store.pending() == []
    assert len(store.unsynced_completed()) == 1


def test_pause_resume_stop_control(tmp_path):
    store = StateStore(tmp_path / "state.sqlite3")
    store.set_control("pause")
    assert store.get_control() == "pause"
    store.set_control("run")
    assert store.get_control() == "run"
    store.set_control("stop")
    assert store.get_control() == "stop"
