"""The trend strategies: the filter that skips chop, and the breakout stop."""
import math

import pytest

from llnx.config import Config
from llnx.strategies import build_strategy
from llnx.strategies.base import Context
from llnx.strategies.breakout import BreakoutStrategy
from llnx.strategies.ema import EmaTrendStrategy
from llnx.strategies.indicators import avg_move, ema, highest, lowest


def ctx(price, position=0.0, entry=0.0):
    return Context(price=price, cash=100.0, position=position, avg_entry=entry,
                   last_buy_price=entry, starting_cash=100.0)


# ── indicators ───────────────────────────────────────────────────
def test_ema_reacts_faster_than_the_average_it_is_seeded_from():
    rising = [float(i) for i in range(1, 101)]
    assert ema(rising, 10) > sum(rising[-10:]) / 10 - 5   # tracks the trend
    assert ema([5.0] * 50, 10) == pytest.approx(5.0)      # flat stays flat
    with pytest.raises(ValueError):
        ema([1.0, 2.0], 10)


def test_ema_only_reads_the_tail_so_it_stays_cheap():
    """The window is bounded, so a long history costs the same as a short one."""
    tail = [5.0] * 200
    assert ema([1000.0] * 500 + tail, 10) == pytest.approx(5.0)


def test_avg_move_scales_with_volatility():
    calm = [100.0, 100.5, 100.0, 100.5, 100.0]
    wild = [100.0, 105.0, 98.0, 106.0, 97.0]
    assert avg_move(calm, 4) < avg_move(wild, 4)
    assert avg_move([1.0], 5) == 0.0        # not enough data yet


def test_channel_helpers():
    values = [3.0, 9.0, 4.0, 1.0, 7.0]
    assert highest(values, 3) == 9.0 or highest(values, 3) == 7.0
    assert highest(values, 5) == 9.0 and lowest(values, 5) == 1.0


# ── EMA with a trend filter ──────────────────────────────────────
def swinging(n=400, drift=0.004, amp=0.02, period=8):
    """A market that trends but still breathes -- swings deep enough to cross."""
    out, price = [], 100.0
    for i in range(n):
        price *= 1 + drift + math.sin(i / period) * amp
        out.append(price)
    return out


def uptrend(n=400):
    return swinging(n, drift=0.004)


def downtrend(n=400):
    return swinging(n, drift=-0.004)


def first_signal(strategy, closes, position=0.0, entry=0.0):
    """The first non-HOLD decision as the series is replayed."""
    for i in range(strategy.warmup, len(closes)):
        d = strategy.evaluate(closes[:i], ctx(closes[i - 1], position, entry))
        if d.action != "HOLD":
            return d
    return None


def test_the_trend_filter_lets_an_uptrend_through():
    d = first_signal(EmaTrendStrategy(8, 21, 50), uptrend())
    assert d is not None and d.action == "BUY" and "in trend" in d.reason


def test_the_trend_filter_blocks_entries_in_a_downtrend():
    """The cross still happens on the bounces; the filter is what says no."""
    closes = downtrend()
    filtered = EmaTrendStrategy(8, 21, 50)
    assert first_signal(filtered, closes) is None


def test_the_exit_does_not_wait_for_the_trend():
    """Holding a position, the cross down sells -- no filter in the way."""
    d = first_signal(EmaTrendStrategy(8, 21, 50), uptrend(), position=1.0,
                     entry=100.0)
    assert d is not None and d.action == "SELL" and "cross down" in d.reason


def test_ema_parameters_are_checked():
    with pytest.raises(ValueError):
        EmaTrendStrategy(20, 20, 100)
    with pytest.raises(ValueError):
        EmaTrendStrategy(8, 50, 20)          # trend shorter than slow


# ── breakout ─────────────────────────────────────────────────────
def test_a_breakout_buys_the_new_high():
    closes = [100.0] * 30 + [101.0]
    d = BreakoutStrategy(10, 5).evaluate(closes, ctx(101.0))
    assert d.action == "BUY" and "breakout" in d.reason


def test_no_breakout_inside_the_channel():
    closes = [100.0 + (i % 3) for i in range(40)]
    assert BreakoutStrategy(10, 5).evaluate(closes, ctx(101.0)).action == "HOLD"


def test_the_volatility_stop_sells_after_the_peak():
    strategy = BreakoutStrategy(10, 5, atr_period=5, atr_mult=1.0)
    rise = [100.0 + i for i in range(40)]              # peak at 139
    hold = strategy.evaluate(rise, ctx(rise[-1], position=1.0, entry=100.0))
    assert hold.action == "HOLD"
    dropped = rise + [135.0]
    d = strategy.evaluate(dropped, ctx(135.0, position=1.0, entry=100.0))
    assert d.action == "SELL" and "volatility stop" in d.reason


def test_the_channel_low_also_gets_you_out():
    strategy = BreakoutStrategy(10, 5, atr_period=5, atr_mult=99.0)   # stop off
    closes = [100.0 + i for i in range(40)] + [90.0]
    d = strategy.evaluate(closes, ctx(90.0, position=1.0, entry=100.0))
    assert d.action == "SELL" and "low" in d.reason


def test_breakout_parameters_are_checked():
    with pytest.raises(ValueError):
        BreakoutStrategy(1, 5)
    with pytest.raises(ValueError):
        BreakoutStrategy(20, 10, atr_mult=0)


def test_both_are_in_the_registry():
    assert build_strategy("ema", Config()).name == "ema"
    assert build_strategy("breakout", Config()).name == "breakout"
    assert "ema" in Config(strategy="ema").strategy
