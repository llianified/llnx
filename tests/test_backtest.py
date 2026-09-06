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
