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


def test_the_mode_shows_up_in_the_status_band_and_on_the_button():
    async def steps(pilot, app):
        assert "live" in app._status()
        assert app.query_one("#run").has_class("-live")
        app.query_one("#mode").value = "paper"
        for _ in range(3):
            await pilot.pause()
        assert not app.query_one("#run").has_class("-live")
        assert app.cfg.mode == "paper"

    drive(steps, mode="live")


# ── the log rows ─────────────────────────────────────────────────
def tick(price=68120.5, executed=None, blocked="", **kw):
    data = {"ts": 1_767_517_442.0, "price": price, "action": "HOLD", "reason": "",
            "equity": 100.0, "executed": executed, "cash": 100.0, "position": 0.0,
            "avg_entry": 0.0, "trades_today": 0, "mode": "paper", "blocked": blocked}
    data.update(kw)
    return data


def fill(side="BUY", amount=0.00036, price=68120.5, reason="golden cross 9/21"):
    from llnx.broker import Trade
    return Trade(timestamp="", side=side, price=price, amount=amount, fee=0.0,
                 cash_after=0.0, position_after=0.0, equity_after=0.0, reason=reason)


def rows_at(width, height, ticks):
    """Feed ticks to a TUI of this size and return the log lines it wrote."""
    async def go():
        app = tui.LlnxTUI(Config())
        async with app.run_test(size=(width, height)) as pilot:
            await pilot.pause(); await pilot.pause()
            app.logbox._history.clear()
            for t in ticks:
                app._on_tick(t)
            await pilot.pause()
            return list(app.logbox._history)
    return asyncio.run(go())


def plain(row):
    """The row as it reaches the screen, without the colour markup."""
    import re
    return re.sub(r"\[[^\]]*\]", "", row)


def test_a_quiet_poll_is_one_dim_row():
    row = plain(rows_at(120, 30, [tick()])[0])
    assert row.split()[1:] == ["68120.5", "·"]


def test_a_fill_shows_side_amount_price_and_reason():
    row = plain(rows_at(120, 30, [tick(executed=fill())])[0])
    assert "buy" in row and "0.00036" in row and "68120.5" in row
    assert "golden cross 9/21" in row


def test_a_block_is_shown_as_held():
    row = plain(rows_at(120, 30, [tick(blocked="cooldown: 44s to go")])[0])
    assert "held" in row and "cooldown: 44s to go" in row


def test_rows_never_wrap_on_a_phone():
    ticks = [tick(), tick(executed=fill()),
             tick(executed=fill("SELL", reason="STOP-LOSS -2%")),
             tick(blocked="daily loss limit hit: equity 88.4000 <= 90.0000")]
    for width in (45, 60, 96, 120):
        for row in rows_at(width, 30, ticks):
            assert len(plain(row)) <= width - 4, f"row too long at {width}: {row}"


def test_the_status_band_follows_the_ticks():
    async def go():
        app = tui.LlnxTUI(Config(starting_cash=100.0))
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause(); await pilot.pause()
            app._on_tick(tick(equity=104.0, cash=50.0, position=0.5, trades_today=3))
            await pilot.pause()
            return app._status()
    band = plain(asyncio.run(go()))
    assert "equity 104" in band and "+4.00%" in band
    assert "pos 0.5" in band and "today 3" in band
