"""Guardrails: what stops an auto-executing bot, and what never stops an exit."""
from llnx.guards import Guardrails, SessionState, build_guardrails, utc_day
from llnx.config import Config


def fresh(equity=100.0, ts=1_700_000_000.0):
    state = SessionState()
    state.roll_day(ts, equity)
    return state


def test_nothing_is_blocked_by_default():
    g = Guardrails(kill_switch_file="")
    s = fresh()
    assert g.block_reason("BUY", equity=100, state=s, now=1_700_000_000.0) is None
    assert g.block_reason("SELL", equity=100, state=s, now=1_700_000_000.0) is None


def test_kill_switch_stops_both_sides(tmp_path):
    path = tmp_path / "STOP"
    g = Guardrails(kill_switch_file=str(path))
    s = fresh()
    assert not g.kill_switch_on()
    path.write_text("stop", encoding="utf-8")
    assert g.kill_switch_on()
    for side in ("BUY", "SELL"):
        reason = g.block_reason(side, equity=100, state=s, now=0)
        assert reason and "kill switch" in reason


def test_daily_loss_stops_buying_but_lets_the_position_out():
    g = Guardrails(max_daily_loss_pct=0.10, kill_switch_file="")
    s = fresh(equity=100.0)
    assert g.block_reason("BUY", equity=95.0, state=s, now=0) is None
    reason = g.block_reason("BUY", equity=89.0, state=s, now=0)
    assert reason and "daily loss limit" in reason
    # the halt sticks for the day, but a stop-loss can still sell
    assert g.block_reason("BUY", equity=99.0, state=s, now=0) == s.halt_reason
    assert g.block_reason("SELL", equity=89.0, state=s, now=0) is None


def test_trade_cap_and_cooldown():
    g = Guardrails(max_trades_per_day=2, cooldown_sec=60, kill_switch_file="")
    s = fresh(ts=1000.0)
    s.on_fill(1000.0)
    assert "cooldown" in g.block_reason("BUY", equity=100, state=s, now=1030.0)
    assert g.block_reason("BUY", equity=100, state=s, now=1061.0) is None
    s.on_fill(1061.0)
    reason = g.block_reason("BUY", equity=100, state=s, now=2000.0)
    assert "trade cap" in reason


def test_a_new_utc_day_clears_the_counters():
    s = fresh(equity=100.0, ts=0.0)
    s.on_fill(0.0)
    s.halt_reason = "halted"
    assert s.roll_day(90_000.0, 80.0) is True     # 25 hours later
    assert (s.trades_today, s.halt_reason, s.day_start_equity) == (0, "", 80.0)
    assert s.roll_day(90_100.0, 80.0) is False
    assert s.day == utc_day(90_100.0)


def test_failures_in_a_row_stand_the_bot_down():
    g = Guardrails(max_consecutive_failures=2, kill_switch_file="")
    s = fresh()
    s.on_failure()
    assert g.block_reason("BUY", equity=100, state=s, now=0) is None
    s.on_failure()
    assert "failed in a row" in g.block_reason("BUY", equity=100, state=s, now=0)
    s.on_fill(0.0)                                # a good order clears it
    assert g.block_reason("BUY", equity=100, state=s, now=0) is None


def test_order_cap_shrinks_an_order():
    g = Guardrails(max_order_pct=0.25)
    assert g.cap_order(100.0, equity=200.0) == 50.0
    assert g.cap_order(10.0, equity=200.0) == 10.0
    assert Guardrails(max_order_pct=0.0).cap_order(100.0, equity=200.0) == 100.0


def test_built_from_the_config():
    g = build_guardrails(Config(max_daily_loss_pct=0.2, max_trades_per_day=5,
                                cooldown_sec=30, max_order_pct=0.5))
    assert (g.max_daily_loss_pct, g.max_trades_per_day) == (0.2, 5)
    assert "30s" in g.describe()


def test_session_state_survives_a_restart():
    s = fresh()
    s.on_fill(1234.0)
    back = SessionState.from_dict(s.to_dict())
    assert back == s
    assert SessionState.from_dict({"day": "x", "nonsense": 1}).day == "x"
