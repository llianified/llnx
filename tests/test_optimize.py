"""The parameter sweep: it ranks in sample and replays out of sample."""
import pytest

from llnx.backtest import synthetic_prices
from llnx.config import Config
from llnx.optimize import (GRIDS, Candidate, build_grid, combinations, sweep,
                           sweep_all, try_backtest)

CLOSES = synthetic_prices(n=900, seed=19)
CFG = Config(starting_cash=100.0)


def test_the_grid_is_every_combination():
    combos = combinations({"a": [1, 2], "b": [10, 20, 30]})
    assert len(combos) == 6
    assert {"a": 1, "b": 30} in combos


def test_the_trailing_stop_multiplies_the_grid():
    plain = len(combinations(build_grid("ema")))
    with_trail = len(combinations(build_grid("ema", trail=True)))
    assert with_trail == plain * 4
    assert "trailing_stop_pct" in build_grid("ema", trail=True)


def test_impossible_settings_are_skipped_not_crashed():
    # fast >= slow is in the sma grid and must not stop the sweep
    assert try_backtest(CLOSES, CFG, {"sma_fast": 30, "sma_slow": 21}) is None
    assert try_backtest(CLOSES, CFG, {"sma_fast": 5, "sma_slow": 21}) is not None


def test_a_sweep_ranks_in_sample_and_replays_out_of_sample():
    best = sweep(CLOSES, CFG, strategy="ema", top=3)
    assert 0 < len(best) <= 3
    scores = [c.in_sample.score for c in best]
    assert scores == sorted(scores, reverse=True)
    for candidate in best:
        assert candidate.out_sample is not None
        # the two halves are different stretches of the series
        assert candidate.out_sample.n_trades != candidate.in_sample.n_trades \
            or candidate.out_sample.return_pct != candidate.in_sample.return_pct


def test_the_split_decides_how_much_is_held_back():
    early = sweep(CLOSES, CFG, strategy="sma", split=0.5, top=1)[0]
    late = sweep(CLOSES, CFG, strategy="sma", split=0.9, top=1)[0]
    assert early.out_sample.n_trades >= late.out_sample.n_trades


def test_every_metric_is_usable():
    for metric in ("score", "return", "profit_factor", "drawdown"):
        best = sweep(CLOSES, CFG, strategy="sma", metric=metric, top=2)
        assert best and best[0].in_sample is not None


def test_ranking_by_drawdown_prefers_the_calmer_settings():
    calm = sweep(CLOSES, CFG, strategy="rsi", metric="drawdown", top=1)[0]
    loud = sweep(CLOSES, CFG, strategy="rsi", metric="return", top=1)[0]
    assert calm.in_sample.max_drawdown_pct <= loud.in_sample.max_drawdown_pct


def test_bad_arguments_are_refused():
    with pytest.raises(ValueError, match="no grid"):
        sweep(CLOSES, CFG, strategy="nope")
    with pytest.raises(ValueError, match="metric"):
        sweep(CLOSES, CFG, strategy="sma", metric="vibes")
    with pytest.raises(ValueError, match="split"):
        sweep(CLOSES, CFG, strategy="sma", split=0.99)


def test_progress_is_reported_for_every_combination():
    seen = []
    sweep(CLOSES, CFG, strategy="ema", top=1,
          on_progress=lambda i, total: seen.append((i, total)))
    assert seen[0] == (1, len(combinations(build_grid("ema"))))
    assert seen[-1][0] == seen[-1][1]


def test_labels_read_like_settings_not_field_names():
    label = Candidate(params={"ema_fast": 8, "trailing_stop_pct": 0.05},
                      in_sample=None).label()
    assert label == "fast=8 trail=5%"


def test_every_strategy_has_a_grid_and_can_be_swept():
    from llnx.strategies import AVAILABLE
    assert set(GRIDS) == set(AVAILABLE)
    results = sweep_all(synthetic_prices(n=400, seed=3), CFG, top=1)
    assert set(results) == set(GRIDS)
