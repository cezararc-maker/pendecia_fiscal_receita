import pytest

from receita_automacao.portal import _click_option_and_submit


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
async def test_procurador_sequence_has_no_extra_actions():
    events = []
    page = FakePage(events)
    option = FakeOption(events)

    await _click_option_and_submit(page, option)

    assert events == [
        ("click", "Procurador"),
        ("press", "Tab"),
        ("wait", 300),
        ("press", "Tab"),
        ("wait", 300),
        ("press", "Space"),
    ]
