import pytest

from receita_automacao.portal_representation import select_procurador_and_submit
from receita_automacao.worker_common import (
    PROFILE_ARROW_SELECTOR,
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


class FakeArrow:
    def __init__(self, events):
        self.events = events

    async def is_visible(self):
        return True

    async def click(self):
        self.events.append(("arrow_click", "ng-arrow-wrapper"))


class FakeNgSelect:
    def __init__(self, arrow=None):
        self.arrow = arrow

    async def count(self):
        return 1

    async def is_visible(self):
        return True

    def locator(self, selector):
        assert selector == PROFILE_ARROW_SELECTOR
        return FakeCollection([] if self.arrow is None else [self.arrow])


class FakePlaceholder(FakeClickableText):
    def __init__(self, text, events, ng_select):
        super().__init__(text, "placeholder_click", events)
        self.ng_select = ng_select

    def locator(self, selector):
        assert selector == "xpath=ancestor::ng-select[1]"
        return self.ng_select


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


def make_company():
    return QueueCompany(
        codigo="1",
        nome="EMPRESA TESTE",
        identificador=VALID_CNPJ,
        tipo_identificador="CNPJ",
        tipo_inscricao="CNPJ",
    )


@pytest.mark.asyncio
async def test_profile_arrow_opens_select_before_critical_sequence():
    events = []
    arrow = FakeArrow(events)
    ng_select = FakeNgSelect(arrow)
    placeholder = FakePlaceholder("Digite um perfil de representação", events, ng_select)
    option = FakeClickableText("Procurador", "option_click", events)
    form = FakeForm(placeholder)
    page = FakePage(option, events)

    await select_procurador_and_submit(page, form, make_company(), FakeLogger())

    assert events == [
        ("arrow_click", "ng-arrow-wrapper"),
        ("option_click", "Procurador"),
        ("press", "Tab"),
        ("wait", 300),
        ("press", "Tab"),
        ("wait", 300),
        ("press", "Space"),
    ]


@pytest.mark.asyncio
async def test_profile_placeholder_is_safe_fallback_when_arrow_is_not_visible():
    events = []
    ng_select = FakeNgSelect(None)
    placeholder = FakePlaceholder("Digite um perfil de representação", events, ng_select)
    option = FakeClickableText("Procurador", "option_click", events)
    form = FakeForm(placeholder)
    page = FakePage(option, events)

    await select_procurador_and_submit(page, form, make_company(), FakeLogger())

    assert events == [
        ("placeholder_click", "Digite um perfil de representação"),
        ("option_click", "Procurador"),
        ("press", "Tab"),
        ("wait", 300),
        ("press", "Tab"),
        ("wait", 300),
        ("press", "Space"),
    ]
