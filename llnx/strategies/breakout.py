"""Donchian breakout with a volatility trailing stop.

Buy when the price closes above everything it did in the last `entry` candles
-- the oldest idea in trend following, and still the one that survives fees,
because it trades rarely and only when something is actually moving.

Two things get you out, whichever comes first:
  * the price closes below the low of the last `exit` candles, or
  * it falls `atr_mult` average moves below its peak since the entry.

The peak is remembered by the strategy, so a restart re-seeds it from the
current price -- the global trailing stop in risk.py behaves the same way.
"""
from __future__ import annotations

from typing import Sequence

from .base import HOLD, Context, Decision, Strategy
from .indicators import avg_move, highest, lowest


class BreakoutStrategy(Strategy):
    name = "breakout"

    def __init__(self, entry: int = 20, exit: int = 10, atr_period: int = 14,
                 atr_mult: float = 2.0) -> None:
        if entry < 2 or exit < 2:
            raise ValueError("entry and exit must be >= 2")
        if atr_mult <= 0:
            raise ValueError("atr_mult must be > 0")
        self.entry, self.exit = entry, exit
        self.atr_period, self.atr_mult = atr_period, atr_mult
        self._peak = 0.0

    @property
    def warmup(self) -> int:
        return max(self.entry, self.exit, self.atr_period) + 2

    def describe(self) -> str:
        return (f"Breakout {self.entry}/{self.exit} with a "
                f"{self.atr_mult:g}x volatility stop")

    def evaluate(self, closes: Sequence[float], ctx: Context) -> Decision:
        if len(closes) < self.warmup:
            return HOLD
        price = closes[-1]

        if ctx.position <= 0:
            self._peak = 0.0
            # the channel excludes the current candle, or it could never break out
            if price > highest(closes[:-1], self.entry):
                return Decision("BUY", reason=f"{self.entry}-candle breakout")
            return HOLD

        self._peak = max(self._peak, price, ctx.avg_entry)
        stop = self._peak - self.atr_mult * avg_move(closes, self.atr_period)
        if price <= stop:
            return Decision("SELL", reason=f"volatility stop {self.atr_mult:g}x")
        if price < lowest(closes[:-1], self.exit):
            return Decision("SELL", reason=f"{self.exit}-candle low")
        return HOLD
