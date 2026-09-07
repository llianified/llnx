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
    assert row.split()[1:] == ["68120.50", "·"]


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


def test_clear_empties_the_log_for_good():
    """A cleared line must not come back when the terminal is resized."""
    async def go():
        app = tui.LlnxTUI(Config())
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause(); await pilot.pause()
            app._on_tick(tick(executed=fill()))
            await pilot.pause()
            before = len(app.logbox._history)
            await pilot.press("l")
            await pilot.pause()
            after = len(app.logbox._history)
            await pilot.resize_terminal(80, 30)   # a resize re-writes the history
            await pilot.pause(); await pilot.pause()
            return before, after, len(app.logbox._history), len(app.logbox.lines)
    before, after, rewrapped, lines = asyncio.run(go())
    assert before > 0 and after == 0 and rewrapped == 0 and lines == 0


def test_clear_does_not_stop_a_run():
    async def steps(pilot, app):
        app.action_run()
        for _ in range(5):
            await pilot.pause()
        app.action_clear()
        await pilot.pause()
        assert app._trading is True
        assert app.logbox._history == []

    app, fake = drive(steps)
    assert fake.calls == [{"mode": "paper", "confirmed": False}]


# ── only what applies right now is on screen ─────────────────────
def visible_labels(app):
    """The label of every field the settings bar is actually showing."""
    out = []
    for field in app.query(".field"):
        if not field.has_class("hidden"):
            out.append(str(next(iter(field.query("Label"))).content))
    return out


def with_app(steps, **cfg_kwargs):
    async def go():
        app = tui.LlnxTUI(Config(**cfg_kwargs))
        async with app.run_test(size=(120, 44)) as pilot:
            await pilot.pause(); await pilot.pause()
            return await steps(app, pilot)
    return asyncio.run(go())


async def settle(pilot, times=3):
    for _ in range(times):
        await pilot.pause()


def test_the_exchange_market_hides_the_chain_and_the_token():
    async def steps(app, pilot):
        return visible_labels(app)
    labels = with_app(steps)
    assert "pair" in labels
    assert "chain" not in labels and "token address" not in labels


def test_choosing_dex_swaps_the_pair_for_a_chain_and_an_address():
    async def steps(app, pilot):
        app.query_one("#market").value = "dex"
        await settle(pilot)
        return visible_labels(app)
    labels = with_app(steps)
    assert "chain" in labels and "token address" in labels
    assert "pair" not in labels


def test_the_address_you_typed_survives_a_trip_through_the_pair():
    address = "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"

    async def steps(app, pilot):
        app.query_one("#market").value = "dex"
        await settle(pilot)
        app.query_one("#token_address").value = address
        await settle(pilot)
        typed = app.cfg.token_address
        app.query_one("#market").value = "exchange"
        await settle(pilot)
        on_pair = app.cfg.token_address        # the pair trades, so no token
        app.query_one("#market").value = "dex"
        await settle(pilot, 4)
        return typed, on_pair, app.cfg.token_address
    typed, on_pair, back = with_app(steps)
    assert typed == address and on_pair == "" and back == address


def test_only_the_chosen_strategy_keeps_its_knobs_on_screen():
    async def steps(app, pilot):
        ema = visible_labels(app)
        app.query_one("#strategy").value = "grid"
        await settle(pilot)
        return ema, visible_labels(app)
    ema, grid = with_app(steps, strategy="ema")
    assert "trend filter ema" in ema and "steps" not in ema
    assert "steps" in grid and "trend filter ema" not in grid


def test_a_strategy_you_switched_away_from_keeps_its_numbers():
    async def steps(app, pilot):
        app.query_one("#ema_trend").value = "150"
        await settle(pilot)
        app.query_one("#strategy").value = "rsi"
        await settle(pilot)
        return app.cfg.ema_trend, app.cfg.strategy
    trend, strategy = with_app(steps, strategy="ema")
    assert trend == 150 and strategy == "rsi"


def test_live_mode_drops_the_cash_box_because_the_venue_owns_the_balance():
    async def steps(app, pilot):
        paper = visible_labels(app)
        app.query_one("#mode").value = "live"
        await settle(pilot)
        return paper, visible_labels(app)
    paper, live = with_app(steps)
    assert "cash ($)" in paper and "cash ($)" not in live


def test_a_solana_dry_run_still_keeps_its_own_cash():
    async def steps(app, pilot):
        app.query_one("#market").value = "dex"
        app.query_one("#mode").value = "sandbox"
        await settle(pilot)
        return visible_labels(app)
    assert "cash ($)" in with_app(steps)


def test_percentages_are_typed_as_percentages():
    async def steps(app, pilot):
        app.query_one("#sl").value = "3"
        app.query_one("#trail").value = "5"
        app.query_one("#max_order").value = "25"
        app.query_one("#daily_loss").value = "8"
        await settle(pilot)
        return app.cfg
    cfg = with_app(steps)
    assert cfg.stop_loss_pct == 0.03 and cfg.trailing_stop_pct == 0.05
    assert cfg.max_order_pct == 0.25 and cfg.max_daily_loss_pct == 0.08


def test_the_guardrails_are_editable_instead_of_hidden_in_a_file():
    async def steps(app, pilot):
        app.query_one("#cooldown").value = "300"
        app.query_one("#max_trades").value = "3"
        await settle(pilot)
        return app.cfg
    cfg = with_app(steps)
    assert cfg.cooldown_sec == 300 and cfg.max_trades_per_day == 3


def test_every_field_explains_itself_when_you_focus_it():
    async def steps(app, pilot):
        seen = {}
        for name in ("cash", "poll", "trail", "daily_loss", "ema_trend"):
            app.query_one(f"#{name}").focus()
            await pilot.pause()
            seen[name] = str(app.query_one("#hint").content)
        return seen
    hints = with_app(steps, strategy="ema")
    assert len(set(hints.values())) == len(hints)     # each field says its own thing
    assert "wallet balance wins" in hints["cash"]
    assert "seconds" in hints["poll"]


def test_the_status_band_names_the_market_that_is_live():
    async def steps(app, pilot):
        exchange = plain(app._status())
        app.query_one("#market").value = "dex"
        await settle(pilot)
        app.query_one("#token_address").value = "0xabc123def456"
        await settle(pilot)
        return exchange, plain(app._status())
    exchange, dex = with_app(steps, symbol="ETH/USDT", chain="base")
    assert "eth/usdt" in exchange and "base" not in exchange
    assert "base" in dex and "eth/usdt" not in dex


# ── number formatting ────────────────────────────────────────────
def test_prices_stay_readable_at_both_ends_of_the_market():
    from llnx.tui import format_price
    assert format_price(68120.5) == "68120.50"
    assert format_price(1.2345) == "1.2345"
    assert format_price(0.0000182) == "0.0000182"     # never 1.82e-05
    assert "e" not in format_price(1.23e-09)
    assert format_price(0.0) == "0"


def test_amounts_shrink_to_something_a_person_can_read():
    from llnx.tui import format_amount
    assert format_amount(0.00036) == "0.00036"
    assert format_amount(1234.5) == "1,234"
    assert format_amount(1_020_408.0) == "1.02M"


def test_a_meme_token_price_reaches_the_log_intact():
    rows = rows_at(120, 30, [tick(price=0.0000182, executed=fill(
        amount=1_020_408.0, price=0.0000196, reason="20-candle breakout"))])
    row = plain(rows[0])
    assert "0.0000182" in row and "1.02M" in row and "0.0000196" in row
    assert "e-05" not in row
