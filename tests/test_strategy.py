"""Indicators and strategies."""
import pytest

from bot.config import Config
from bot.strategies import (Context, SmaCrossStrategy, RsiStrategy,
                            GridDcaStrategy, build_strategy)
from bot.strategies.indicators import cross_signal, rsi, sma


def ctx(price, position=0.0, cash=100.0, avg_entry=0.0, last_buy=0.0, start=100.0):
    return Context(price=price, cash=cash, position=position, avg_entry=avg_entry,
                   last_buy_price=last_buy, starting_cash=start)


def test_sma_basic():
    assert sma([1, 2, 3, 4], 2) == 3.5


def test_cross_golden_and_death():
    assert cross_signal([10] * 20 + [40], 3, 8) == "BUY"
    assert cross_signal([40] * 20 + [10], 3, 8) == "SELL"
    assert cross_signal([10] * 30, 3, 8) == "HOLD"


def test_sma_strategy_respects_position():
    s = SmaCrossStrategy(3, 8)
    up = [10] * 20 + [40]
    assert s.evaluate(up, ctx(40, position=0)).action == "BUY"
    # already holding -> no second buy
    assert s.evaluate(up, ctx(40, position=1)).action == "HOLD"


def test_rsi_oversold_buys():
    closes = [100 - i for i in range(20)]  # steady drop -> low RSI
    s = RsiStrategy(period=14, oversold=30, overbought=70)
    d = s.evaluate(closes, ctx(closes[-1], position=0))
    assert d.action == "BUY"


def test_rsi_overbought_sells():
    closes = [100 + i for i in range(20)]  # steady climb -> high RSI
    s = RsiStrategy(period=14, oversold=30, overbought=70)
    d = s.evaluate(closes, ctx(closes[-1], position=1, avg_entry=90))
    assert d.action == "SELL"


def test_grid_first_entry_and_dca():
    s = GridDcaStrategy(step_pct=0.02, take_profit_pct=0.03, max_steps=5)
    # flat -> first entry, buys one chunk (start/max_steps = 20)
    d = s.evaluate([100], ctx(100, position=0, start=100))
    assert d.action == "BUY" and d.quote_amount == 20
    # >2% below the last buy -> DCA
    d2 = s.evaluate([100], ctx(97, position=0.2, cash=80, avg_entry=100, last_buy=100))
    assert d2.action == "BUY"
    # >3% above the average entry -> take profit
    d3 = s.evaluate([100], ctx(104, position=0.2, cash=80, avg_entry=100, last_buy=100))
    assert d3.action == "SELL"


def test_build_strategy_from_config():
    cfg = Config()
    for name in ("sma", "rsi", "grid"):
        assert build_strategy(name, cfg).name == name
    with pytest.raises(ValueError):
        build_strategy("ngawur", cfg)
