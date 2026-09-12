from receita_automacao.excel import normalize_excel_identifier
from receita_automacao.models import EntityType


def test_excel_identifier_uses_displayed_text_when_complete():
    value = normalize_excel_identifier("11.222.333/0001-81", 11222333000181.0, EntityType.CNPJ)
    assert value == "11222333000181"


def test_excel_identifier_recovers_numeric_value_from_scientific_display():
    value = normalize_excel_identifier("1,12223E+13", 11222333000181.0, EntityType.CNPJ)
    assert value == "11222333000181"


def test_excel_identifier_restores_leading_zero_for_numeric_cnpj():
    value = normalize_excel_identifier("1,23457E+12", 1234567800019.0, EntityType.CNPJ)
    assert value == "01234567800019"
