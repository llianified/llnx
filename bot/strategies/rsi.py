"""RSI: buy when oversold, sell when overbought (all in)."""
from __future__ import annotations

from typing import Sequence

from .base import HOLD, Context, Decision, Strategy
from .indicators import rsi


class RsiStrategy(Strategy):
    name = "rsi"

    def __init__(self, period: int = 14, oversold: float = 30.0,
                 overbought: float = 70.0) -> None:
        if not 0 < oversold < overbought < 100:
            raise ValueError("need 0 < oversold < overbought < 100")
        self.period, self.oversold, self.overbought = period, oversold, overbought

    @property
    def warmup(self) -> int:
        return self.period + 1

    def describe(self) -> str:
        return f"RSI {self.period} (buy<{self.oversold:g}, sell>{self.overbought:g})"

    def evaluate(self, closes: Sequence[float], ctx: Context) -> Decision:
        r = rsi(closes, self.period)
        if r is None:
            return HOLD
        if r <= self.oversold and ctx.position == 0:
            return Decision("BUY", reason=f"RSI {r:.1f} oversold")
        if r >= self.overbought and ctx.position > 0:
            return Decision("SELL", reason=f"RSI {r:.1f} overbought")
        return HOLD
