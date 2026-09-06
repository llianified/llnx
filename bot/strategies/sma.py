"""Strategi SMA crossover: beli golden cross, jual death cross (all-in)."""
from __future__ import annotations

from typing import Sequence

from .base import HOLD, Context, Decision, Strategy
from .indicators import cross_signal


class SmaCrossStrategy(Strategy):
    name = "sma"

    def __init__(self, fast: int, slow: int) -> None:
        if fast >= slow:
            raise ValueError("fast harus < slow")
        self.fast, self.slow = fast, slow

    @property
    def warmup(self) -> int:
        return self.slow + 1

    def describe(self) -> str:
        return f"SMA crossover {self.fast}/{self.slow}"

    def evaluate(self, closes: Sequence[float], ctx: Context) -> Decision:
        sig = cross_signal(closes, self.fast, self.slow)
        if sig == "BUY" and ctx.position == 0:
            return Decision("BUY", reason=f"golden cross {self.fast}/{self.slow}")
        if sig == "SELL" and ctx.position > 0:
            return Decision("SELL", reason=f"death cross {self.fast}/{self.slow}")
        return HOLD
