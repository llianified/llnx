"""The live loop: state that survives a restart, and the ways it refuses to run."""
import json

import pytest

from llnx import feeds, runner
from llnx.broker import PaperBroker
from llnx.config import Config
from llnx.guards import SessionState


class FakeFeed:
    """A price series that walks up and then down, so a crossover happens."""

    def __init__(self):
        self.prices = ([100.0] * 6 + [104.0, 108.0, 112.0, 116.0]
                       + [96.0, 92.0, 88.0, 84.0]) * 3
        self.i = 0

    def fetch_closes(self, limit):
        return self.prices[max(0, self.i - limit):self.i] or [100.0]

    def fetch_price(self):
        price = self.prices[min(self.i, len(self.prices) - 1)]
        self.i += 1
        return price


@pytest.fixture
def paper_cfg(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(feeds, "build_feed", lambda cfg: (FakeFeed(), "FAKE/USDT"))
    return Config(strategy="sma", sma_fast=2, sma_slow=4, starting_cash=100.0,
                  min_notional=1.0, poll_interval_sec=0, mode="paper",
                  kill_switch_file=str(tmp_path / "STOP"))


def ticks(n):
    """A should_run() that lets the loop turn `n` times."""
    left = {"n": n}
    def go():
        left["n"] -= 1
        return left["n"] >= 0
    return go


def test_a_paper_run_trades_and_writes_everything_down(paper_cfg, tmp_path):
    runner.run_live(paper_cfg, should_run=ticks(14), log=lambda *a: None)
    state = json.loads((tmp_path / "state.json").read_text())
    assert state["session"]["trades_today"] >= 1
    assert (tmp_path / "trades.csv").exists()
    orders = (tmp_path / "orders.jsonl").read_text().strip().splitlines()
    assert any(json.loads(o)["status"] == "filled" for o in orders)


def test_the_next_run_picks_up_where_the_last_one_stopped(paper_cfg, tmp_path):
    runner.run_live(paper_cfg, should_run=ticks(10), log=lambda *a: None)
    first = json.loads((tmp_path / "state.json").read_text())
    runner.run_live(paper_cfg, should_run=ticks(2), log=lambda *a: None)
    second = json.loads((tmp_path / "state.json").read_text())
    assert second["cash"] == pytest.approx(first["cash"])
    assert second["session"]["day"] == first["session"]["day"]
    assert second["session"]["trades_today"] >= first["session"]["trades_today"]


def test_the_kill_switch_stops_the_loop_before_any_order(paper_cfg, tmp_path):
    (tmp_path / "STOP").write_text("stop", encoding="utf-8")
    lines = []
    runner.run_live(paper_cfg, should_run=ticks(20), log=lines.append)
    assert any("kill switch" in str(l) for l in lines)
    assert not (tmp_path / "trades.csv").exists()


def test_signals_only_decides_but_sends_nothing(paper_cfg, tmp_path):
    cfg = paper_cfg.with_overrides(auto_execute=False)
    runner.run_live(cfg, should_run=ticks(14), log=lambda *a: None)
    orders = [json.loads(o) for o in
              (tmp_path / "orders.jsonl").read_text().strip().splitlines()]
    assert orders and all(o["status"] == "signal" for o in orders)
    assert not (tmp_path / "trades.csv").exists()


def test_live_mode_needs_the_phrase(paper_cfg, monkeypatch):
    monkeypatch.delenv(runner.CONFIRM_ENV, raising=False)
    monkeypatch.setattr("builtins.input", lambda *a: "no thanks")
    with pytest.raises(SystemExit, match="not confirmed"):
        runner.build_broker(paper_cfg.with_overrides(mode="live"), {},
                            log=lambda *a: None)


def test_the_phrase_can_come_from_the_environment(monkeypatch):
    monkeypatch.setenv(runner.CONFIRM_ENV, "i understand")
    assert runner.confirm_live(log=lambda *a: None) is True
    monkeypatch.setenv(runner.CONFIRM_ENV, "sure")
    monkeypatch.setattr("builtins.input", lambda *a: "sure")
    assert runner.confirm_live(log=lambda *a: None) is False


def test_state_is_saved_and_read_back(tmp_path):
    broker = PaperBroker(fee_rate=0.001, min_notional=1.0, cash=42.0)
    broker.buy(10.0, 20.0)
    session = SessionState(day="2026-01-01", trades_today=3)
    path = str(tmp_path / "state.json")
    runner.save_state(path, broker, session)
    state = runner.load_state(path)
    assert state["session"]["trades_today"] == 3
    assert PaperBroker.from_dict(state).cash == broker.cash
    assert runner.load_state(str(tmp_path / "nope.json")) == {}
    (tmp_path / "broken.json").write_text("{oops", encoding="utf-8")
    assert runner.load_state(str(tmp_path / "broken.json")) == {}


def test_a_live_broker_gets_its_entry_price_back_after_a_restart():
    class Live:
        position = 0.5
        def __init__(self):
            self.avg_entry = self.last_buy_price = 0.0
        def restore_entry(self, avg, last):
            self.avg_entry, self.last_buy_price = avg, last

    broker = Live()
    runner.restore_entry(broker, {"avg_entry": 101.5}, log=lambda *a: None)
    assert broker.avg_entry == 101.5 and broker.last_buy_price == 101.5

    flat = Live()
    flat.position = 0.0
    runner.restore_entry(flat, {"avg_entry": 101.5}, log=lambda *a: None)
    assert flat.avg_entry == 0.0        # nothing held, nothing to restore


def test_the_banner_says_which_money_is_at_risk():
    assert "no real money" in runner.mode_banner(Config(mode="paper"), False)
    assert "testnet" in runner.mode_banner(Config(mode="sandbox"), False)
    assert "dry run" in runner.mode_banner(Config(mode="sandbox"), True)
    assert "REAL MONEY" in runner.mode_banner(Config(mode="live"), False)
    assert "REAL SOLANA" in runner.mode_banner(Config(mode="live"), True)
