"""Paper broker: partial orders, fees, average entry, min_notional."""
from bot.broker import PaperBroker


def test_buy_then_sell_applies_fees():
    b = PaperBroker(fee_rate=0.001, min_notional=0.0, cash=100.0)
    b.buy(10.0)
    assert b.cash == 0.0
    assert round(b.position, 6) == 9.99
    assert b.avg_entry == 10.0
    b.sell(10.0)
    assert b.position == 0.0
    assert round(b.cash, 4) == 99.8001


def test_partial_buy_averages_entry():
    b = PaperBroker(fee_rate=0.0, min_notional=0.0, cash=100.0)
    b.buy(10.0, quote_amount=50)   # 5 units @10
    b.buy(20.0, quote_amount=50)   # 2.5 units @20
    # avg entry = (5*10 + 2.5*20)/7.5 = (50+50)/7.5 = 13.333...
    assert round(b.avg_entry, 4) == round(100 / 7.5, 4)
    assert b.last_buy_price == 20.0


def test_partial_sell():
    b = PaperBroker(fee_rate=0.0, min_notional=0.0, cash=100.0)
    b.buy(10.0)               # 10 units
    b.sell(10.0, fraction=0.5)
    assert round(b.position, 6) == 5.0


def test_min_notional_blocks_small_order():
    b = PaperBroker(fee_rate=0.0, min_notional=5.0, cash=3.0)
    assert b.buy(10.0) is None
    assert b.position == 0.0


def test_persistence_roundtrip():
    b = PaperBroker(fee_rate=0.002, min_notional=1.0, cash=42.0)
    b.buy(7.0, quote_amount=20)
    r = PaperBroker.from_dict(b.to_dict())
    assert r.cash == b.cash and r.position == b.position
    assert r.avg_entry == b.avg_entry and r.last_buy_price == b.last_buy_price
