"""The execution layer: guards enforced, orders journalled, failures reconciled."""
import json

import pytest

from llnx.broker import PaperBroker, Trade
from llnx.execution import OrderExecutor, read_journal
from llnx.guards import Guardrails, SessionState
from llnx.strategies.base import Decision

NO_GUARDS = Guardrails(kill_switch_file="")


def paper(cash=100.0):
    return PaperBroker(fee_rate=0.0, min_notional=0.0, cash=cash)


def executor(broker=None, guards=NO_GUARDS, path="", **kw):
    return OrderExecutor(broker or paper(), guards, journal_path=str(path),
                         log=lambda *a: None, **kw)


class BrokenBroker:
    """A venue that errors, and can be asked for its balances afterwards."""
    is_live = True

    def __init__(self):
        self.cash, self.position = 50.0, 0.0
        self.avg_entry = self.last_buy_price = 0.0
        self.trades = []
        self.refreshed = 0

    def equity(self, price):
        return self.cash + self.position * price

    def buy(self, price, quote_amount=None):
        raise RuntimeError("exchange said no")

    def sell(self, price, fraction=1.0):
        raise RuntimeError("exchange said no")

    def refresh(self):
        self.refreshed += 1
        self.cash, self.position = 10.0, 0.4


def test_a_filled_order_reaches_the_broker_and_the_journal(tmp_path):
    path = tmp_path / "orders.jsonl"
    x = executor(path=path)
    x.on_decision(Decision("BUY", reason="golden cross"))
    trade = x.buy(10.0, 50.0)
    assert isinstance(trade, Trade) and trade.amount == 5.0
    assert x.position == 5.0 and x.cash == 50.0
    row = read_journal(str(path))[-1]
    assert row["status"] == "filled" and row["signal"] == "golden cross"
    assert row["requested"] == 50.0 and row["unit"] == "quote"


def test_a_blocked_order_is_never_sent(tmp_path):
    path = tmp_path / "orders.jsonl"
    broker = paper()
    x = executor(broker, Guardrails(max_trades_per_day=1, kill_switch_file=""),
                 path=path)
    assert x.buy(10.0, 10.0) is not None
    assert x.buy(10.0, 10.0) is None            # the cap bites
    assert broker.position == 1.0               # only the first order happened
    assert "trade cap" in x.last_block
    statuses = [r["status"] for r in read_journal(str(path))]
    assert statuses == ["filled", "blocked"]


def test_an_exit_still_goes_through_a_daily_loss_halt():
    broker = paper()
    x = executor(broker, Guardrails(max_daily_loss_pct=0.1, kill_switch_file=""))
    x.buy(10.0)                                  # all in at 10
    assert broker.position == 10.0
    assert x.buy(5.0, 10.0) is None              # equity halved: no more buying
    assert x.sell(5.0) is not None               # but the position can leave
    assert broker.position == 0.0


def test_a_failed_order_is_counted_and_the_balances_re_read(tmp_path):
    path = tmp_path / "orders.jsonl"
    broker = BrokenBroker()
    x = executor(broker, NO_GUARDS, path=path)
    assert x.buy(10.0, 20.0) is None
    assert broker.refreshed == 1 and x.cash == 10.0    # reconciled from the venue
    assert x.state.consecutive_failures == 1
    row = read_journal(str(path))[-1]
    assert row["status"] == "failed" and "exchange said no" in row["error"]


def test_the_bot_stands_down_after_a_run_of_failures():
    broker = BrokenBroker()
    x = executor(broker, Guardrails(max_consecutive_failures=2, kill_switch_file=""))
    x.buy(10.0, 20.0)
    x.buy(10.0, 20.0)
    x.buy(10.0, 20.0)                            # blocked before it is sent
    assert broker.refreshed == 2                 # only two orders were attempted
    assert "failed in a row" in x.last_block


def test_signal_only_mode_sends_nothing(tmp_path):
    path = tmp_path / "orders.jsonl"
    broker = paper()
    x = executor(broker, path=path, auto_execute=False)
    assert x.buy(10.0, 50.0) is None
    assert broker.position == 0.0
    assert read_journal(str(path))[-1]["status"] == "signal"


def test_the_order_cap_is_applied_before_sending():
    broker = paper()
    x = executor(broker, Guardrails(max_order_pct=0.2, kill_switch_file=""))
    x.buy(10.0)                                  # would be all 100 of the cash
    assert broker.cash == 80.0


def test_a_broker_that_refuses_is_journalled_as_rejected(tmp_path):
    path = tmp_path / "orders.jsonl"
    broker = PaperBroker(fee_rate=0.0, min_notional=50.0, cash=10.0)
    x = executor(broker, path=path)
    assert x.buy(10.0) is None                   # under the minimum
    assert read_journal(str(path))[-1]["status"] == "rejected"


def test_the_journal_survives_a_broken_line(tmp_path):
    path = tmp_path / "orders.jsonl"
    path.write_text('{"status": "filled"}\nnot json\n\n{"status": "blocked"}\n',
                    encoding="utf-8")
    assert [r["status"] for r in read_journal(str(path))] == ["filled", "blocked"]
    assert read_journal(str(tmp_path / "missing.jsonl")) == []


def test_state_is_shared_so_a_restart_keeps_the_daily_counters():
    state = SessionState()
    x = executor(state=state)
    x.buy(10.0, 10.0)
    assert state.trades_today == 1
    assert json.loads(json.dumps(state.to_dict()))["trades_today"] == 1
