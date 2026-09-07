"""The TUI run button: paper starts, live asks first. Skipped without textual."""
import asyncio
import os

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
        log("  market   : binance | btc/usdt | 1m")   # the CLI's own indent
        log("  [fake] running")                       # ...and its [tags]
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
    """The label of every field the settings bar is actually showing.

    Measured, not inferred: a field is off screen either because it is hidden
    itself or because the settings screen holding it is.
    """
    out = []
    for field in app.query(".field"):
        if not field.has_class("hidden") and field.size.height > 0:
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


async def open_tab(app, pilot, name):
    """Tap one of the settings tabs, the way a finger would."""
    app.query_one(f"#tab_{name}").press()
    await settle(pilot)


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
        await open_tab(app, pilot, "strategy")
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
        await open_tab(app, pilot, "trading")
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
        await open_tab(app, pilot, "trading")
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


# ── one settings screen at a time ────────────────────────────────
def test_the_bar_shows_one_settings_screen_at_a_time():
    async def steps(app, pilot):
        seen = {}
        for name in tui.SECTIONS:
            await open_tab(app, pilot, name)
            seen[name] = visible_labels(app)
        return seen
    seen = with_app(steps, strategy="ema")
    assert "pair" in seen["market"] and "pair" not in seen["trading"]
    assert "mode" in seen["trading"] and "mode" not in seen["exits"]
    assert "trend filter ema" in seen["strategy"]
    assert "stop-loss (%)" in seen["exits"] and "cooldown (s)" not in seen["exits"]
    assert "cooldown (s)" in seen["limits"]
    # nothing appears on two screens at once
    everything = [label for labels in seen.values() for label in labels]
    assert len(everything) == len(set(everything))


def test_the_open_tab_is_the_one_that_looks_open():
    async def steps(app, pilot):
        await open_tab(app, pilot, "limits")
        return {name: app.query_one(f"#tab_{name}").has_class("-on")
                for name in tui.SECTIONS}
    marked = with_app(steps)
    assert marked["limits"] is True
    assert sum(marked.values()) == 1


def test_switching_screens_never_buries_the_output():
    """The settings bar takes what it needs and the log keeps the rest."""
    async def steps(app, pilot):
        heights = {}
        for name in tui.SECTIONS:
            await open_tab(app, pilot, name)
            fields = app.query_one("#fields")
            heights[name] = (fields.size.height, fields.virtual_size.height,
                             app.query_one("#log").size.height)
        return heights
    for name, (shown, needed, log) in with_app(steps, strategy="ema").items():
        assert shown >= needed, f"{name}: fields clipped ({shown} < {needed})"
        assert log >= 10, f"{name}: only {log} rows left for the log"


def test_the_status_band_admits_when_the_dex_has_no_token_yet():
    """Picking dex must not leave the pair on show as if it were trading."""
    async def steps(app, pilot):
        app.query_one("#market").value = "dex"
        await settle(pilot)
        return plain(app._status())
    band = with_app(steps, symbol="BTC/USDT", chain="solana")
    assert "no token yet" in band and "btc/usdt" not in band


# ── the log keeps one left margin ────────────────────────────────
def test_a_long_detail_wraps_under_its_own_indent():
    """A line is a heading or sits under one; wrapping must not break that."""
    async def steps(app, pilot):
        app.logbox._history.clear()
        app._log_detail("daily loss 10% | 20 trades/day | cooldown 300s | "
                        "order <= 25% equity | kill switch 'STOP'", indent=7)
        await pilot.pause()
        return list(app.logbox._history)

    async def go():
        app = tui.LlnxTUI(Config())
        async with app.run_test(size=(45, 40)) as pilot:
            await pilot.pause(); await pilot.pause()
            return await steps(app, pilot)
    lines = [plain(line) for line in asyncio.run(go())]
    assert len(lines) > 1, "this should have needed more than one line"
    assert all(line.startswith(" " * 7) for line in lines)
    assert all(len(line) <= 45 for line in lines)


def test_runner_output_lands_flush_left_like_every_other_heading():
    """The CLI indents its banner; in here that reads as a stray space."""
    written = []

    async def steps(pilot, app):     # drive() hands them over in this order
        app._trading = True
        app._run_worker(False)       # the faked runner logs "  [fake] running"
        for _ in range(8):
            await pilot.pause()
        app._trading = False
        written.extend(plain(line) for line in app.logbox._history)

    drive(steps)
    logged = [line for line in written if "binance" in line]
    assert logged, "the runner's output should reach the log"
    assert not any(line.startswith(" ") for line in logged)


def test_the_setup_checklist_reaches_the_log():
    async def steps(app, pilot):
        app.action_guide()
        await settle(pilot)
        return "\n".join(plain(line) for line in app.logbox._history)
    out = with_app(steps, token_address="MINT")
    assert "going live on solana" in out
    assert "SOLANA_PRIVATE_KEY" in out and "then go live" in out
    assert "type the phrase" in out


# ── typing the wallet in ─────────────────────────────────────────
def keys_flow(tmp_path, button, market="dex"):
    """Open the keys modal, fill it in, press a button, return what was logged."""
    written = []

    async def go():
        app = tui.LlnxTUI(Config(token_address="MINT" if market == "dex" else ""))
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(); await pilot.pause()
            app.action_keys()
            await settle(pilot)
            screen = app.screen
            masked = {i.id: i.password for i in screen.query("Input")}
            screen.query_one("#key_SOLANA_RPC_URL").value = "https://my.rpc/x"
            screen.query_one("#key_SOLANA_PRIVATE_KEY").value = "5JsecretKEYvalue"
            app.logbox._history.clear()
            screen.query_one(button).press()
            await settle(pilot, 5)
            written.extend(plain(line) for line in app.logbox._history)
            return masked
    masked = asyncio.run(go())
    return masked, "\n".join(written)


def test_the_private_key_is_masked_while_you_type_it(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SOLANA_PRIVATE_KEY", raising=False)
    masked, _ = keys_flow(tmp_path, "#keys_session")
    assert masked["key_SOLANA_PRIVATE_KEY"] is True
    assert masked["key_SOLANA_RPC_URL"] is False      # an endpoint is not a secret


def test_the_key_never_reaches_the_log(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SOLANA_PRIVATE_KEY", raising=False)
    _, log = keys_flow(tmp_path, "#keys_session")
    assert "5JsecretKEYvalue" not in log
    assert "SOLANA_PRIVATE_KEY" in log and "hidden" in log


def test_this_session_only_writes_nothing_to_disk(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SOLANA_PRIVATE_KEY", raising=False)
    keys_flow(tmp_path, "#keys_session")
    assert not (tmp_path / ".llnx.env").exists()
    assert os.environ["SOLANA_RPC_URL"] == "https://my.rpc/x"


def test_remembering_writes_a_file_only_you_can_read(tmp_path, monkeypatch):
    import stat

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SOLANA_PRIVATE_KEY", raising=False)
    _, log = keys_flow(tmp_path, "#keys_save")
    saved = tmp_path / ".llnx.env"
    assert saved.exists()
    assert stat.S_IMODE(os.stat(saved).st_mode) == 0o600
    assert "readable only by you" in log


def test_escaping_the_modal_changes_nothing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SOLANA_PRIVATE_KEY", raising=False)

    async def go():
        app = tui.LlnxTUI(Config(token_address="MINT"))
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(); await pilot.pause()
            app.action_keys()
            await settle(pilot)
            app.logbox._history.clear()
            await pilot.press("escape")
            await settle(pilot)
            return "\n".join(plain(line) for line in app.logbox._history)
    assert "unchanged" in asyncio.run(go())
    assert not (tmp_path / ".llnx.env").exists()


def test_an_exchange_config_asks_for_exchange_keys(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    async def go():
        app = tui.LlnxTUI(Config())
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(); await pilot.pause()
            app.action_keys()
            await settle(pilot)
            return sorted(i.id for i in app.screen.query("Input"))
    assert asyncio.run(go()) == ["key_EXCHANGE_API_KEY", "key_EXCHANGE_API_SECRET"]
