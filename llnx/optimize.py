"""Parameter sweep: try the grid, rank what worked, and check it out of sample.

Every strategy has knobs, and the best settings for last month are usually not
the best for next month. So the sweep splits the series in two: it ranks
candidates on the first part (in sample) and then replays the winners on the
part they have never seen (out of sample).

The out-of-sample column is the only one worth anything. A candidate that made
80% in sample and lost money out of sample did not find an edge, it memorised
the data -- and the grid is large enough that a few will do exactly that by
chance. Prefer settings that are merely good in both halves.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Sequence

from .backtest import BacktestReport, run_backtest
from .config import Config

# The knobs worth turning, and sensible ranges for each strategy.
GRIDS: Dict[str, Dict[str, list]] = {
    "sma": {"sma_fast": [5, 9, 12, 20, 30], "sma_slow": [21, 30, 50, 100, 200]},
    "ema": {"ema_fast": [8, 12, 20], "ema_slow": [21, 26, 50],
            "ema_trend": [50, 100, 200]},
    "breakout": {"breakout_entry": [10, 20, 30, 55], "breakout_exit": [5, 10, 20],
                 "breakout_atr_mult": [1.5, 2.0, 3.0]},
    "rsi": {"rsi_period": [7, 14, 21], "rsi_oversold": [20, 25, 30, 35],
            "rsi_overbought": [65, 70, 75, 80]},
    "grid": {"grid_step_pct": [0.01, 0.02, 0.03, 0.05],
             "grid_take_profit_pct": [0.02, 0.03, 0.05, 0.08],
             "grid_max_steps": [3, 5, 8]},
}
# swept on top of the strategy grid when asked for: the biggest single lever
TRAIL_VALUES = [0.0, 0.03, 0.05, 0.08]

# how each knob is written in the results table
SHORT_NAMES = {
    "sma_fast": "fast", "sma_slow": "slow",
    "ema_fast": "fast", "ema_slow": "slow", "ema_trend": "trend",
    "breakout_entry": "entry", "breakout_exit": "exit",
    "breakout_atr_period": "atr_len", "breakout_atr_mult": "atr",
    "rsi_period": "period", "rsi_oversold": "oversold",
    "rsi_overbought": "overbought",
    "grid_step_pct": "step", "grid_take_profit_pct": "tp",
    "grid_max_steps": "steps", "trailing_stop_pct": "trail",
}

METRICS: Dict[str, Callable[[BacktestReport], float]] = {
    "score": lambda r: r.score,                  # return per unit of drawdown
    "return": lambda r: r.return_pct,
    "profit_factor": lambda r: min(r.profit_factor, 1e6),
    "drawdown": lambda r: -r.max_drawdown_pct,   # less is better
}


@dataclass
class Candidate:
    params: dict
    in_sample: BacktestReport
    out_sample: Optional[BacktestReport] = None

    def label(self) -> str:
        parts = []
        for key, value in self.params.items():
            name = SHORT_NAMES.get(key, key)
            if isinstance(value, float) and 0 < value < 1:
                parts.append(f"{name}={value*100:g}%")
            else:
                parts.append(f"{name}={value:g}" if isinstance(value, float)
                             else f"{name}={value}")
        return " ".join(parts)


def combinations(grid: Dict[str, list]) -> List[dict]:
    keys = list(grid)
    return [dict(zip(keys, values)) for values in itertools.product(*grid.values())]


def build_grid(strategy: str, trail: bool = False) -> Dict[str, list]:
    grid = dict(GRIDS[strategy])
    if trail:
        grid["trailing_stop_pct"] = list(TRAIL_VALUES)
    return grid


def try_backtest(closes: Sequence[float], cfg: Config,
                 params: dict) -> Optional[BacktestReport]:
    """Run one candidate. Impossible combinations (fast >= slow) are skipped."""
    try:
        candidate_cfg = cfg.with_overrides(**params)
        return run_backtest(closes, candidate_cfg)
    except (ValueError, ZeroDivisionError):
        return None


def sweep(closes: Sequence[float], cfg: Config, *, strategy: str = "",
          split: float = 0.7, metric: str = "score", top: int = 10,
          trail: bool = False, on_progress: Optional[Callable[[int, int], None]] = None
          ) -> List[Candidate]:
    """Rank the grid on the first `split` of the data, then replay out of sample."""
    strategy = strategy or cfg.strategy
    if strategy not in GRIDS:
        raise ValueError(f"no grid for strategy '{strategy}'")
    if metric not in METRICS:
        raise ValueError(f"unknown metric '{metric}'. Options: {', '.join(METRICS)}")
    if not 0.3 <= split <= 0.95:
        raise ValueError("split must be within [0.3, 0.95]")

    cut = int(len(closes) * split)
    in_closes, out_closes = closes[:cut], closes[cut:]
    base = cfg.with_overrides(strategy=strategy)
    candidates: List[Candidate] = []

    combos = combinations(build_grid(strategy, trail))
    for i, params in enumerate(combos, 1):
        if on_progress:
            on_progress(i, len(combos))
        report = try_backtest(in_closes, base, params)
        if report is not None:
            candidates.append(Candidate(params=params, in_sample=report))

    rank = METRICS[metric]
    candidates.sort(key=lambda c: rank(c.in_sample), reverse=True)
    best = candidates[:top]
    for candidate in best:                       # only the winners are replayed
        candidate.out_sample = try_backtest(out_closes, base, candidate.params)
    return best


def sweep_all(closes: Sequence[float], cfg: Config, **kwargs) -> Dict[str, List[Candidate]]:
    """One sweep per strategy, for when the question is 'which one at all?'."""
    return {name: sweep(closes, cfg, strategy=name, **kwargs) for name in GRIDS}
