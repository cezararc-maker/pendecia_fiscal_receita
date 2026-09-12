import pytest

from receita_automacao.portal_representation import validate_representation_form
from receita_automacao.worker_common import QueueCompany


VALID_CNPJ = "11222333000181"


class FakeCollection:
    def __init__(self, items):
        self.items = items

    async def count(self):
        return len(self.items)

    def nth(self, index):
        return self.items[index]


class FakeField:
    async def is_visible(self):
        return True

    async def input_value(self):
        return VALID_CNPJ


class FakeForm:
    def __init__(self, field):
        self.field = field

    async def count(self):
        return 1

    async def is_visible(self):
        return True

    def locator(self, _selector):
        return FakeCollection([self.field])


class FakeSubmit:
    def __init__(self, form):
        self.form = form

    async def is_visible(self):
        return True

    async def is_enabled(self):
        raise AssertionError(
            "validate_representation_form must not inspect enabled state before Procurador"
        )

    def locator(self, selector):
        assert selector == "xpath=ancestor::form[1]"
        return self.form


class FakePage:
    def __init__(self, submit):
        self.submit = submit

    def locator(self, _selector):
        return FakeCollection([self.submit])


@pytest.mark.asyncio
async def test_disabled_representar_is_expected_before_procurador():
    field = FakeField()
    form = FakeForm(field)
    submit = FakeSubmit(form)
    page = FakePage(submit)
    company = QueueCompany(
        codigo="1",
        nome="EMPRESA TESTE",
        identificador=VALID_CNPJ,
        tipo_identificador="CNPJ",
        tipo_inscricao="CNPJ",
    )

    returned_form = await validate_representation_form(page, field, company)

    assert returned_form is form
