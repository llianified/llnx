"""CEX execution: what the exchange actually filled is what gets booked."""
import pytest

from llnx.live_broker import CcxtBroker, fee_in_quote, is_settled, settle_fill


# ── reading a ccxt order ─────────────────────────────────────────
def test_the_average_fill_price_wins_over_the_screen_price():
    order = {"status": "closed", "filled": 0.5, "cost": 51.0, "average": 102.0}
    amount, price, _ = settle_fill(order, 100.0, "USDT", 0.001)
    assert (amount, price) == (0.5, 102.0)


def test_the_price_falls_back_to_cost_then_to_the_screen_price():
    _, price, _ = settle_fill({"filled": 2.0, "cost": 210.0}, 100.0, "USDT", 0.001)
    assert price == 105.0
    _, price, _ = settle_fill({"filled": 2.0}, 100.0, "USDT", 0.001)
    assert price == 100.0
    amount, _, _ = settle_fill({"amount": 3.0}, 100.0, "USDT", 0.001)
    assert amount == 3.0          # nothing filled yet: fall back to what we asked


def test_a_fee_in_the_base_currency_is_converted():
    order = {"filled": 0.5, "average": 100.0, "fee": {"cost": 0.001, "currency": "BTC"}}
    assert fee_in_quote(order, 0.5, 100.0, "USDT", 0.001) == pytest.approx(0.1)


def test_a_fee_in_the_quote_currency_is_taken_as_is():
    order = {"fee": {"cost": 0.05, "currency": "USDT"}}
    assert fee_in_quote(order, 0.5, 100.0, "USDT", 0.001) == 0.05


def test_several_fees_are_added_up_and_a_missing_one_is_estimated():
    order = {"fees": [{"cost": 0.02, "currency": "USDT"},
                      {"cost": 0.0001, "currency": "BTC"}]}
    assert fee_in_quote(order, 0.5, 100.0, "USDT", 0.001) == pytest.approx(0.03)
    assert fee_in_quote({}, 0.5, 100.0, "USDT", 0.001) == pytest.approx(0.05)


def test_an_order_is_settled_once_the_exchange_is_done_with_it():
    assert is_settled({"status": "closed"})
    assert is_settled({"status": "canceled"})
    assert not is_settled({"status": "open", "remaining": 0.5})
    assert not is_settled({"status": "open", "remaining": 0.0})
    assert is_settled({"status": "", "remaining": 0})


# ── the broker itself, on a fake exchange ────────────────────────
class FakeExchange:
    def __init__(self, *, with_cost=True, order=None):
        self.has = {"createMarketBuyOrderWithCost": with_cost}
        self.orders = []
        self.balances = {"USDT": {"free": 100.0}, "BTC": {"free": 0.0}}
        self.order = order or {"id": "1", "status": "closed", "filled": 0.49,
                               "cost": 50.0, "average": 102.0,
                               "fee": {"cost": 0.05, "currency": "USDT"}}

    def amount_to_precision(self, symbol, amount):
        return f"{float(amount):.6f}"

    def fetch_balance(self):
        return self.balances

    def create_market_buy_order_with_cost(self, symbol, cost):
        self.orders.append(("buy-cost", cost))
        self.balances = {"USDT": {"free": 50.0}, "BTC": {"free": 0.49}}
        return self.order

    def create_order(self, symbol, type_, side, amount):
        self.orders.append((side, amount))
        if side == "buy":
            self.balances = {"USDT": {"free": 50.0}, "BTC": {"free": 0.49}}
        else:
            self.balances = {"USDT": {"free": 99.9}, "BTC": {"free": 0.0}}
        return self.order

    def fetch_order(self, oid, symbol):
        return self.order


def broker(exchange, min_notional=5.0, min_amount=0.0):
    """A CcxtBroker wired to a fake exchange, without importing ccxt."""
    b = object.__new__(CcxtBroker)
    b.exchange = exchange
    b.symbol, b.base, b.quote = "BTC/USDT", "BTC", "USDT"
    b.fee_rate, b.min_notional, b.min_amount = 0.001, min_notional, min_amount
    b.settle_timeout, b.log = 1, lambda *a: None
    b.avg_entry = b.last_buy_price = 0.0
    b.trades = []
    b.refresh()
    return b


def test_a_market_buy_spends_cash_and_books_the_real_fill():
    ex = FakeExchange()
    b = broker(ex)
    trade = b.buy(100.0, 50.0)
    assert ex.orders == [("buy-cost", 50.0)]      # cost, not a guessed amount
    assert trade.price == 102.0 and trade.amount == 0.49 and trade.fee == 0.05
    assert b.avg_entry == 102.0 and b.last_buy_price == 102.0
    assert b.cash == 50.0 and b.position == 0.49  # balances re-read from the venue


def test_an_exchange_without_cost_orders_gets_an_amount():
    ex = FakeExchange(with_cost=False)
    b = broker(ex)
    b.buy(100.0, 50.0)
    assert ex.orders == [("buy", 0.5)]            # 50 / 100, at precision


def test_orders_below_the_minimum_are_not_sent():
    ex = FakeExchange()
    b = broker(ex, min_notional=20.0)
    assert b.buy(100.0, 10.0) is None
    b = broker(FakeExchange(), min_amount=1.0)
    assert b.buy(100.0, 50.0) is None             # 0.5 BTC is under the min amount
    assert ex.orders == []


def test_selling_everything_clears_the_entry_price():
    ex = FakeExchange()
    b = broker(ex)
    b.buy(100.0, 50.0)
    ex.order = {"id": "2", "status": "closed", "filled": 0.49, "cost": 49.0,
                "average": 100.0, "fee": {"cost": 0.049, "currency": "USDT"}}
    trade = b.sell(100.0)
    assert ex.orders[-1] == ("sell", 0.49)
    assert trade.amount == 0.49 and b.position == 0.0
    assert b.avg_entry == 0.0 and b.last_buy_price == 0.0


def test_an_order_that_never_fills_is_not_booked():
    ex = FakeExchange(order={"id": "3", "status": "canceled", "filled": 0.0})
    b = broker(ex)
    assert b.buy(100.0, 50.0) is None
    assert b.trades == []


def test_selling_with_no_position_does_nothing():
    b = broker(FakeExchange())
    assert b.sell(100.0) is None


def test_a_restart_can_hand_back_the_average_entry():
    b = broker(FakeExchange())
    b.restore_entry(99.5, 99.5)
    assert b.avg_entry == 99.5 and b.last_buy_price == 99.5
