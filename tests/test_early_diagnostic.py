from receita_automacao.diagnostic_worker import DIAGNOSTIC_STAGES


def test_early_diagnostic_stages_are_explicit():
    assert DIAGNOSTIC_STAGES == ("connected-only", "after-open")
