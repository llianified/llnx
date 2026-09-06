"""Test backtest berjalan tanpa error dan menghasilkan laporan wajar."""
from bot.backtest import run_backtest, synthetic_prices


def test_backtest_runs():
    closes = synthetic_prices(n=300, seed=1)
    rep = run_backtest(closes, fast=9, slow=21, starting_cash=5.0,
                       fee_rate=0.001, min_notional=0.0)
    assert rep.starting_cash == 5.0
    assert rep.final_equity > 0
    assert rep.n_trades >= 0
    assert rep.total_fees >= 0


def test_synthetic_is_deterministic():
    assert synthetic_prices(n=50, seed=7) == synthetic_prices(n=50, seed=7)
