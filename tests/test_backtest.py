"""Backtests run for every strategy without blowing up."""
import pytest

from llnx.backtest import run_backtest, synthetic_prices
from llnx.config import Config


@pytest.mark.parametrize("strategy", ["sma", "rsi", "grid"])
def test_backtest_runs_for_each_strategy(strategy):
    cfg = Config(strategy=strategy, starting_cash=100.0)
    rep = run_backtest(synthetic_prices(n=400, seed=3), cfg)
    assert rep.final_equity > 0
    assert rep.n_trades >= 0


def test_backtest_with_stop_loss():
    cfg = Config(strategy="sma", starting_cash=100.0, stop_loss_pct=0.03)
    rep = run_backtest(synthetic_prices(n=400, seed=5), cfg)
    assert rep.final_equity > 0


def test_synthetic_deterministic():
    assert synthetic_prices(n=50, seed=7) == synthetic_prices(n=50, seed=7)


# ── the metrics that decide whether a strategy is worth running ──
def test_max_drawdown_is_the_worst_peak_to_trough():
    from llnx.backtest import max_drawdown
    assert max_drawdown([100, 120, 90, 130, 65]) == pytest.approx(50.0)
    assert max_drawdown([100, 110, 120]) == 0.0
    assert max_drawdown([]) == 0.0


def test_round_trips_pair_buys_with_sells():
    from llnx.backtest import round_trips
    from llnx.broker import PaperBroker
    broker = PaperBroker(fee_rate=0.0, min_notional=0.0, cash=100.0)
    broker.buy(10.0, 100.0)          # 10 units at 10
    broker.sell(12.0)                # +20
    broker.buy(20.0, 100.0)          # 5 units at 20 (cash is 120 now, spend 100)
    broker.sell(18.0)                # -10
    trips = round_trips(broker.trades)
    assert len(trips) == 2
    assert trips[0] == pytest.approx(20.0)
    assert trips[1] == pytest.approx(-10.0)


def test_a_partial_sell_closes_a_share_of_the_basis():
    from llnx.backtest import round_trips
    from llnx.broker import PaperBroker
    broker = PaperBroker(fee_rate=0.0, min_notional=0.0, cash=100.0)
    broker.buy(10.0, 100.0)          # 10 units at 10
    broker.sell(20.0, fraction=0.5)  # sell 5 at 20: basis 50, proceeds 100
    trips = round_trips(broker.trades)
    assert len(trips) == 1 and trips[0] == pytest.approx(50.0)


def test_the_report_carries_the_risk_numbers():
    cfg = Config(strategy="breakout", starting_cash=100.0)
    rep = run_backtest(synthetic_prices(n=1200, seed=19), cfg)
    assert 0 <= rep.max_drawdown_pct <= 100
    assert 0 <= rep.exposure_pct <= 100
    assert 0 <= rep.win_rate_pct <= 100
    assert rep.n_round_trips >= 0
    assert rep.fees_pct >= 0
    # score prefers the same return through less pain
    from llnx.backtest import BacktestReport
    calm = BacktestReport("x", 100, 130, 4, 0, 30.0, 0, max_drawdown_pct=10.0)
    rough = BacktestReport("x", 100, 130, 4, 0, 30.0, 0, max_drawdown_pct=40.0)
    assert calm.score > rough.score


@pytest.mark.parametrize("strategy", ["ema", "breakout"])
def test_the_new_strategies_backtest(strategy):
    rep = run_backtest(synthetic_prices(n=800, seed=19),
                       Config(strategy=strategy, starting_cash=100.0))
    assert rep.final_equity > 0


def test_a_trailing_stop_changes_the_outcome():
    closes = synthetic_prices(n=1500, seed=19)
    plain = run_backtest(closes, Config(strategy="ema", starting_cash=100.0))
    trailed = run_backtest(closes, Config(strategy="ema", starting_cash=100.0,
                                          trailing_stop_pct=0.05))
    assert trailed.return_pct != plain.return_pct


def test_read_closes_handles_a_header_and_a_bare_file(tmp_path):
    from llnx.backtest import read_closes
    ohlcv = tmp_path / "ohlcv.csv"
    ohlcv.write_text("timestamp,open,high,low,close,volume\n"
                     "1,10,12,9,11,100\n2,11,13,10,12,120\n", encoding="utf-8")
    assert read_closes(str(ohlcv)) == [11.0, 12.0]
    bare = tmp_path / "bare.csv"
    bare.write_text("1,10\n2,11\n", encoding="utf-8")
    assert read_closes(str(bare)) == [10.0, 11.0]
    empty = tmp_path / "empty.csv"
    empty.write_text("", encoding="utf-8")
    assert read_closes(str(empty)) == []
