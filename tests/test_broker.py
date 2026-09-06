"""Test paper broker: eksekusi, fee, min_notional, persistensi."""
from bot.broker import PaperBroker


def test_buy_then_sell_applies_fees():
    b = PaperBroker(fee_rate=0.001, min_notional=0.0, cash=100.0)
    b.buy(price=10.0)
    assert b.cash == 0.0
    # 100 - 0.1 fee = 99.9 dibelikan @10 -> 9.99 unit
    assert round(b.position, 6) == 9.99
    b.sell(price=10.0)
    assert b.position == 0.0
    # jual 9.99 @10 = 99.9, dikurangi fee 0.0999 -> 99.8001
    assert round(b.cash, 4) == 99.8001


def test_double_buy_is_ignored():
    b = PaperBroker(fee_rate=0.0, min_notional=0.0, cash=50.0)
    assert b.buy(10.0) is not None
    assert b.buy(10.0) is None  # sudah punya posisi


def test_sell_without_position_is_ignored():
    b = PaperBroker(cash=50.0)
    assert b.sell(10.0) is None


def test_min_notional_blocks_small_order():
    b = PaperBroker(fee_rate=0.0, min_notional=5.0, cash=3.0)
    assert b.buy(10.0) is None  # 3 < 5 minimum
    assert b.position == 0.0


def test_equity_marks_to_price():
    b = PaperBroker(fee_rate=0.0, min_notional=0.0, cash=100.0)
    b.buy(10.0)          # dapat 10 unit
    assert b.equity(20.0) == 200.0  # harga naik 2x


def test_persistence_roundtrip():
    b = PaperBroker(fee_rate=0.002, min_notional=1.0, cash=42.0)
    b.buy(7.0)
    restored = PaperBroker.from_dict(b.to_dict())
    assert restored.cash == b.cash
    assert restored.position == b.position
    assert restored.entry_price == b.entry_price
