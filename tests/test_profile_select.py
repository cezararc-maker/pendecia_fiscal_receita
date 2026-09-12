import pytest

from receita_automacao.portal_representation import select_procurador_and_submit
from receita_automacao.worker_common import (
    PROFILE_OPTION_SELECTOR,
    PROFILE_PLACEHOLDER_SELECTOR,
    QueueCompany,
)


VALID_CNPJ = "11222333000181"


class FakeCollection:
    def __init__(self, items):
        self.items = items

    async def count(self):
        return len(self.items)

    def nth(self, index):
        return self.items[index]


class FakeClickableText:
    def __init__(self, text, event_name, events):
        self.text = text
        self.event_name = event_name
        self.events = events

    async def is_visible(self):
        return True

    async def inner_text(self):
        return self.text

    async def click(self):
        self.events.append((self.event_name, self.text))

    async def scroll_into_view_if_needed(self):
        raise AssertionError("Profile placeholder must not trigger explicit scrolling")


class FakeForm:
    def __init__(self, placeholder):
        self.placeholder = placeholder

    def locator(self, selector):
        assert selector == PROFILE_PLACEHOLDER_SELECTOR
        return FakeCollection([self.placeholder])


class FakeKeyboard:
    def __init__(self, events):
        self.events = events

    async def press(self, key):
        self.events.append(("press", key))


class FakePage:
    def __init__(self, option, events):
        self.option = option
        self.keyboard = FakeKeyboard(events)
        self.events = events

    def locator(self, selector):
        assert selector == PROFILE_OPTION_SELECTOR
        return FakeCollection([self.option])

    async def wait_for_timeout(self, milliseconds):
        self.events.append(("wait", milliseconds))


class FakeLogger:
    def emit(self, *_args, **_kwargs):
        return None


@pytest.mark.asyncio
async def test_profile_placeholder_opens_select_without_scroll_before_critical_sequence():
    events = []
    placeholder = FakeClickableText(
        "Digite um perfil de representação",
        "placeholder_click",
        events,
    )
    option = FakeClickableText("Procurador", "option_click", events)
    form = FakeForm(placeholder)
    page = FakePage(option, events)
    company = QueueCompany(
        codigo="1",
        nome="EMPRESA TESTE",
        identificador=VALID_CNPJ,
        tipo_identificador="CNPJ",
        tipo_inscricao="CNPJ",
    )

    await select_procurador_and_submit(page, form, company, FakeLogger())

    assert events == [
        ("placeholder_click", "Digite um perfil de representação"),
        ("option_click", "Procurador"),
        ("press", "Tab"),
        ("wait", 300),
        ("press", "Tab"),
        ("wait", 300),
        ("press", "Space"),
    ]
