from receita_automacao.worker_common import SECURITY_CHALLENGE_RE


def test_detects_portal_image_selection_challenge():
    text = "Selecione tudo mais silencioso que o item mostrado"
    assert SECURITY_CHALLENGE_RE.search(text)


def test_does_not_treat_regular_analysis_as_security_challenge():
    text = "Resultado da Análise Sem pendência"
    assert SECURITY_CHALLENGE_RE.search(text) is None
