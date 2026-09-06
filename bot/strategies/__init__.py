"""Registry strategi: bikin strategi dari nama + Config."""
from __future__ import annotations

from .base import Context, Decision, Strategy
from .grid import GridDcaStrategy
from .rsi import RsiStrategy
from .sma import SmaCrossStrategy

# nama -> deskripsi singkat untuk menu/help
AVAILABLE = {
    "sma": "SMA crossover — beli golden cross, jual death cross",
    "rsi": "RSI — beli saat oversold, jual saat overbought",
    "grid": "Grid/DCA — beli bertahap saat turun, jual saat take-profit",
}


def build_strategy(name: str, cfg) -> Strategy:
    name = (name or "sma").lower()
    if name == "sma":
        return SmaCrossStrategy(cfg.sma_fast, cfg.sma_slow)
    if name == "rsi":
        return RsiStrategy(cfg.rsi_period, cfg.rsi_oversold, cfg.rsi_overbought)
    if name == "grid":
        return GridDcaStrategy(cfg.grid_step_pct, cfg.grid_take_profit_pct,
                               cfg.grid_max_steps)
    raise ValueError(f"strategi '{name}' tidak dikenal. Pilihan: {', '.join(AVAILABLE)}")


__all__ = ["Context", "Decision", "Strategy", "AVAILABLE", "build_strategy",
           "SmaCrossStrategy", "RsiStrategy", "GridDcaStrategy"]
