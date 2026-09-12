from receita_automacao.portal import classify_manual_gate


def test_classifies_login_page():
    assert classify_manual_gate("https://servicos.receitafederal.gov.br/login/", "Autenticação") == "login"


def test_classifies_additional_confirmation():
    assert classify_manual_gate("https://servicos.receitafederal.gov.br/servico/", "Confirmação adicional necessária") == "additional_confirmation"


def test_classifies_security_challenge_before_login():
    assert classify_manual_gate("https://servicos.receitafederal.gov.br/login/", "Digite o código de verificação") == "security_challenge"


def test_returns_none_for_authenticated_service_without_gate():
    assert classify_manual_gate("https://servicos.receitafederal.gov.br/servico/pendencias/", "Análise de pendências") is None
