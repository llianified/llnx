"""The TUI run button: paper starts, live asks first. Skipped without textual."""
import asyncio

import pytest

pytest.importorskip("textual", reason="textual is optional; TUI tests skipped")

from llnx import tui                                       # noqa: E402
from llnx.config import Config                             # noqa: E402


class FakeRunner:
    """Stands in for runner.run_live and records how it was called."""

    def __init__(self):
        self.calls = []
        self.stop = asyncio.Event()

    def __call__(self, cfg, *, confirmed=False, log=print, should_run=None,
                 on_tick=None):
        self.calls.append({"mode": cfg.mode, "confirmed": confirmed})
        log("[fake] running")            # square brackets must not break the log
        while should_run():
            pass


def drive(steps, mode="paper"):
    """Run `steps(pilot, app)` against a TUI whose runner is faked out."""
    fake = FakeRunner()

    async def go():
        app = tui.LlnxTUI(Config(mode=mode))
        original, tui.run_live = tui.run_live, fake
        try:
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                await steps(pilot, app)
                app._trading = False     # let the worker thread finish
                for _ in range(6):
                    await pilot.pause()
        finally:
            tui.run_live = original
        return app

    return asyncio.run(go()), fake


def test_paper_starts_straight_away():
    async def steps(pilot, app):
        app.action_run()
        for _ in range(5):
            await pilot.pause()
        assert app._trading is True

    app, fake = drive(steps)
    assert fake.calls == [{"mode": "paper", "confirmed": False}]


def test_live_does_nothing_until_the_phrase_is_typed():
    async def steps(pilot, app):
        app.query_one("#mode").value = "live"
        await pilot.pause()
        app.action_run()
        await pilot.pause()
        assert isinstance(app.screen, tui.ConfirmLive)
        assert app._trading is False          # nothing has started yet
        app.screen.query_one("#phrase").value = "yes please"
        await pilot.press("enter")
        for _ in range(4):
            await pilot.pause()
        assert app._trading is False          # the wrong phrase changes nothing

    app, fake = drive(steps, mode="live")
    assert fake.calls == []


def test_the_right_phrase_arms_live_mode():
    async def steps(pilot, app):
        app.query_one("#mode").value = "live"
        await pilot.pause()
        app.action_run()
        await pilot.pause()
        app.screen.query_one("#phrase").value = tui.CONFIRM_PHRASE.lower()
        await pilot.press("enter")
        for _ in range(5):
            await pilot.pause()

    app, fake = drive(steps, mode="live")
    assert fake.calls == [{"mode": "live", "confirmed": True}]


def test_escape_cancels_the_confirmation():
    async def steps(pilot, app):
        app.query_one("#mode").value = "live"
        await pilot.pause()
        app.action_run()
        await pilot.pause()
        await pilot.press("escape")
        for _ in range(4):
            await pilot.pause()
        assert not isinstance(app.screen, tui.ConfirmLive)

    app, fake = drive(steps, mode="live")
    assert fake.calls == []


def test_the_mode_shows_up_in_the_header_and_on_the_button():
    async def steps(pilot, app):
        assert "live" in app._summary()
        assert app.query_one("#run").has_class("-live")
        app.query_one("#mode").value = "paper"
        for _ in range(3):
            await pilot.pause()
        assert not app.query_one("#run").has_class("-live")
        assert app.cfg.mode == "paper"

    drive(steps, mode="live")
