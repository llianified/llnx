"""Responsive layout of the TUI. Skipped when textual is not installed."""
import asyncio

import pytest

pytest.importorskip("textual", reason="textual is optional; TUI tests skipped")

from llnx.config import Config
from llnx.tui import LlnxTUI, TINY_ROWS, WIDE_COLS


def run(coro):
    return asyncio.run(coro)


def sizes(width, height):
    """Return (screen classes, panel height, log height) at a terminal size."""
    async def go():
        app = LlnxTUI(Config())
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


def test_the_settings_bar_always_leaves_room_for_the_output():
    """It may take more than half the screen -- `t` folds it away -- but the
    log never disappears behind it."""
    from llnx.tui import MIN_LOG_ROWS
    for width, height in [(120, 38), (96, 20), (45, 55), (38, 24), (120, 60)]:
        _, panel, log = sizes(width, height)
        assert log > 0, f"no room left for output at {width}x{height}"
        if height > MIN_LOG_ROWS * 2:
            assert log >= 4, f"output squeezed to {log} rows at {width}x{height}"
        assert panel <= height - MIN_LOG_ROWS, f"settings too tall at {height}"


def test_settings_bar_hides_itself_on_a_tiny_terminal():
    async def go():
        app = LlnxTUI(Config())
        async with app.run_test(size=(60, TINY_ROWS - 2)) as pilot:
            await pilot.pause()
            return app.query_one("#panel").has_class("hidden")
    assert run(go())


def test_the_status_band_is_always_on_screen():
    """A bot that trades by itself has to show what it holds, panel or not."""
    async def go():
        app = LlnxTUI(Config())
        async with app.run_test(size=(60, 40)) as pilot:
            await pilot.pause(); await pilot.pause()
            with_bar = app.query_one("#status").display
            await pilot.press("t")
            await pilot.pause()
            return with_bar, app.query_one("#status").display
    with_bar, without_bar = run(go())
    assert with_bar and without_bar


def test_the_status_band_folds_to_one_line_on_a_short_terminal():
    async def go():
        app = LlnxTUI(Config())
        async with app.run_test(size=(80, 40)) as pilot:
            await pilot.pause(); await pilot.pause()
            tall = app._status()
            await pilot.resize_terminal(80, 20)
            await pilot.pause(); await pilot.pause()
            return tall, app._status()
    tall, short = run(go())
    assert "\n" in tall and "\n" not in short
    assert "equity" in short


def test_toggling_the_settings_bar():
    async def go():
        app = LlnxTUI(Config())
        async with app.run_test(size=(45, 40)) as pilot:
            await pilot.pause(); await pilot.pause()
            await pilot.press("t"); await pilot.pause()
            hidden = app.query_one("#panel").has_class("hidden")
            await pilot.press("t"); await pilot.pause()
            return hidden, app.query_one("#panel").has_class("hidden")
    hidden, back = run(go())
    assert hidden and not back


def test_the_whole_settings_bar_fits_on_a_tall_screen():
    """Nothing to scroll for on a desktop: every section is on screen."""
    async def go():
        app = LlnxTUI(Config())
        async with app.run_test(size=(120, 44)) as pilot:
            await pilot.pause(); await pilot.pause()
            fields = app.query_one("#fields")
            return fields.virtual_size.height, fields.size.height
    wanted, shown = run(go())
    assert wanted <= shown, f"settings need {wanted} rows but only {shown} are shown"


def test_strategy_labels_shrink_on_a_narrow_terminal():
    async def go():
        app = LlnxTUI(Config())
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
        app = LlnxTUI(Config())
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
        app = LlnxTUI(Config())
        async with app.run_test(size=(80, 30)) as pilot:
            await pilot.pause(); await pilot.pause()
            await pilot.press("b")
            await pilot.pause(); await pilot.pause()
            return "\n".join(app.logbox._history)
    out = run(go())
    assert "buy&hold" in out and "drawdown" in out and "profit factor" in out
