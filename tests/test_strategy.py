"""Test strategi SMA crossover."""
from bot.strategy import SmaCrossStrategy, sma


def test_sma_basic():
    assert sma([1, 2, 3, 4], 2) == 3.5
    assert sma([10, 20, 30], 3) == 20.0


def test_golden_cross_gives_buy():
    # pasar datar (fast==slow), lalu lonjakan tepat di candle terakhir -> BUY
    closes = [10] * 20 + [40]
    strat = SmaCrossStrategy(fast=3, slow=8)
    assert strat.signal(closes) == "BUY"


def test_death_cross_gives_sell():
    # pasar datar, lalu penurunan tajam tepat di candle terakhir -> SELL
    closes = [40] * 20 + [10]
    strat = SmaCrossStrategy(fast=3, slow=8)
    assert strat.signal(closes) == "SELL"


def test_no_cross_gives_hold():
    closes = [10] * 30
    strat = SmaCrossStrategy(fast=3, slow=8)
    assert strat.signal(closes) == "HOLD"


def test_warmup_returns_hold():
    strat = SmaCrossStrategy(fast=9, slow=21)
    assert strat.signal([1, 2, 3]) == "HOLD"


def test_fast_must_be_less_than_slow():
    import pytest
    with pytest.raises(ValueError):
        SmaCrossStrategy(fast=21, slow=9)
