"""Responsive layout of the TUI. Skipped when textual is not installed."""
import asyncio

import pytest

pytest.importorskip("textual", reason="textual is optional; TUI tests skipped")

from bot.config import Config
from bot.tui import BotTUI, TINY_ROWS, WIDE_COLS


def run(coro):
    return asyncio.run(coro)


def sizes(width, height):
    """Return (screen classes, panel height, log height) at a terminal size."""
    async def go():
        app = BotTUI(Config())
        async with app.run_test(size=(width, height)) as pilot:
            await pilot.pause()
            await pilot.pause()
            return (set(app.screen.classes),
                    app.query_one("#panel").size.height,
                    app.query_one("#log").size.height)
    return run(go())


def test_wide_terminal_uses_four_columns():
    classes, _, _ = sizes(WIDE_COLS, 40)
    assert "-wide" in classes
    classes, _, _ = sizes(WIDE_COLS - 1, 40)
    assert "-wide" not in classes


def test_settings_bar_never_takes_more_than_half_the_screen():
    for width, height in [(120, 38), (96, 20), (45, 55), (38, 24)]:
        _, panel, log = sizes(width, height)
        assert panel <= height // 2, f"settings bar too tall at {width}x{height}"
        assert log > 0, f"no room left for output at {width}x{height}"


def test_settings_bar_hides_itself_on_a_tiny_terminal():
    async def go():
        app = BotTUI(Config())
        async with app.run_test(size=(60, TINY_ROWS - 2)) as pilot:
            await pilot.pause()
            return app.query_one("#panel").has_class("hidden")
    assert run(go())


def test_summary_shows_only_while_the_settings_bar_is_hidden():
    async def go():
        app = BotTUI(Config())
        async with app.run_test(size=(60, 40)) as pilot:
            await pilot.pause(); await pilot.pause()
            with_bar = app.query_one("#summary").display
            await pilot.press("t")
            await pilot.pause()
            return with_bar, app.query_one("#summary").display
    with_bar, without_bar = run(go())
    assert not with_bar and without_bar


def test_toggling_the_settings_bar():
    async def go():
        app = BotTUI(Config())
        async with app.run_test(size=(45, 40)) as pilot:
            await pilot.pause(); await pilot.pause()
            await pilot.press("t"); await pilot.pause()
            hidden = app.query_one("#panel").has_class("hidden")
            await pilot.press("t"); await pilot.pause()
            return hidden, app.query_one("#panel").has_class("hidden")
    hidden, back = run(go())
    assert hidden and not back


def test_strategy_labels_shrink_on_a_narrow_terminal():
    async def go():
        app = BotTUI(Config())
        async with app.run_test(size=(60, 40)) as pilot:
            await pilot.pause(); await pilot.pause()
            narrow = [str(p[0]) for p in app.query_one("#strategy")._options]
            await pilot.resize_terminal(120, 40)
            await pilot.pause(); await pilot.pause()
            return narrow, [str(p[0]) for p in app.query_one("#strategy")._options]
    narrow, wide = run(go())
    assert "sma" in narrow and "sma · crossover" not in narrow
    assert "sma · crossover" in wide


def test_log_is_rewrapped_when_the_terminal_is_resized():
    async def go():
        app = BotTUI(Config())
        async with app.run_test(size=(40, 30)) as pilot:
            await pilot.pause(); await pilot.pause()
            app._log("x" * 200)
            await pilot.pause()
            narrow = len(app.logbox.lines)
            await pilot.resize_terminal(120, 30)
            await pilot.pause(); await pilot.pause()
            return narrow, len(app.logbox.lines), app.logbox._history[-1]
    narrow, wide, last = run(go())
    assert last == "x" * 200
    assert wide < narrow      # old lines re-wrapped instead of staying clipped


def test_backtest_writes_a_report_to_the_log():
    async def go():
        app = BotTUI(Config())
        async with app.run_test(size=(80, 30)) as pilot:
            await pilot.pause(); await pilot.pause()
            await pilot.press("b")
            await pilot.pause(); await pilot.pause()
            return "\n".join(app.logbox._history)
    out = run(go())
    assert "final equity" in out and "buy&hold" in out
