from receita_automacao.models import EntityType, CompanyRecord, is_valid_cnpj, parse_entity_type


def test_cnpj_validation():
    assert is_valid_cnpj("11.222.333/0001-81")
    assert not is_valid_cnpj("11.222.333/0001-82")
    assert not is_valid_cnpj("00000000000000")


def test_only_explicit_cnpj_is_eligible():
    assert parse_entity_type("CNPJ") is EntityType.CNPJ
    assert parse_entity_type("CPF") is EntityType.CPF
    caepf = CompanyRecord("k", 2, "Teste", EntityType.CAEPF, "11222333000181")
    assert not caepf.eligible_for_automation
