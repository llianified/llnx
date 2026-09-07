"""EMA crossover with a trend filter: only buy crosses that go with the tide.

A plain crossover buys every wiggle, and in a sideways market that is a fee
machine. This one takes the same cross but ignores it unless the price is
above a long EMA, so entries only happen while the market is in an uptrend.
The exit stays unconditional -- once the fast EMA falls back through the slow
one, the position goes, trend or no trend.

Pair it with a trailing stop (trailing_stop_pct) rather than a fixed
take-profit: the whole point of a trend strategy is to let a winner run.
"""
from __future__ import annotations

from typing import Sequence

from .base import HOLD, Context, Decision, Strategy
from .indicators import ema


class EmaTrendStrategy(Strategy):
    name = "ema"

    def __init__(self, fast: int = 12, slow: int = 26, trend: int = 100) -> None:
        if fast >= slow:
            raise ValueError("fast must be < slow")
        if trend < slow:
            raise ValueError("trend must be >= slow")
        self.fast, self.slow, self.trend = fast, slow, trend

    @property
    def warmup(self) -> int:
        return self.trend + 2

    def describe(self) -> str:
        return f"EMA {self.fast}/{self.slow} above the {self.trend} EMA"

    def evaluate(self, closes: Sequence[float], ctx: Context) -> Decision:
        if len(closes) < self.trend + 1:
            return HOLD
        fast_now, slow_now = ema(closes, self.fast), ema(closes, self.slow)
        fast_prev, slow_prev = ema(closes[:-1], self.fast), ema(closes[:-1], self.slow)

        if ctx.position > 0:
            if fast_prev >= slow_prev and fast_now < slow_now:
                return Decision("SELL", reason=f"ema cross down {self.fast}/{self.slow}")
            return HOLD

        crossed_up = fast_prev <= slow_prev and fast_now > slow_now
        if crossed_up and closes[-1] > ema(closes, self.trend):
            return Decision("BUY", reason=f"ema cross up {self.fast}/{self.slow} in trend")
        return HOLD
