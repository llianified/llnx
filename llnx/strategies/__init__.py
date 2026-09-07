"""Strategy registry: build a strategy from its name plus a Config."""
from __future__ import annotations

from .base import Context, Decision, Strategy
from .breakout import BreakoutStrategy
from .ema import EmaTrendStrategy
from .grid import GridDcaStrategy
from .rsi import RsiStrategy
from .sma import SmaCrossStrategy

# name -> short description, used by the menu and --help
AVAILABLE = {
    "sma": "SMA crossover - buy the golden cross, sell the death cross",
    "ema": "EMA crossover, but only in an uptrend - fewer, better entries",
    "breakout": "Donchian breakout with a volatility stop - trend following",
    "rsi": "RSI - buy when oversold, sell when overbought",
    "grid": "Grid/DCA - buy in steps on the way down, sell at take-profit",
}


def build_strategy(name: str, cfg) -> Strategy:
    name = (name or "sma").lower()
    if name == "sma":
        return SmaCrossStrategy(cfg.sma_fast, cfg.sma_slow)
    if name == "ema":
        return EmaTrendStrategy(cfg.ema_fast, cfg.ema_slow, cfg.ema_trend)
    if name == "breakout":
        return BreakoutStrategy(cfg.breakout_entry, cfg.breakout_exit,
                                cfg.breakout_atr_period, cfg.breakout_atr_mult)
    if name == "rsi":
        return RsiStrategy(cfg.rsi_period, cfg.rsi_oversold, cfg.rsi_overbought)
    if name == "grid":
        return GridDcaStrategy(cfg.grid_step_pct, cfg.grid_take_profit_pct,
                               cfg.grid_max_steps)
    raise ValueError(f"unknown strategy '{name}'. Options: {', '.join(AVAILABLE)}")


__all__ = ["Context", "Decision", "Strategy", "AVAILABLE", "build_strategy",
           "SmaCrossStrategy", "EmaTrendStrategy", "BreakoutStrategy",
           "RsiStrategy", "GridDcaStrategy"]
