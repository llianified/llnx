"""Grid / DCA: buy in steps while the price falls, sell at take-profit.

Suits sideways or falling markets. The cash is split into `max_steps` equal
chunks; every time the price drops `step_pct` below the last buy, one more
chunk goes in (averaging down). Everything is sold once the price reaches
the average entry * (1 + take_profit_pct).
"""
from __future__ import annotations

from typing import Sequence

from .base import HOLD, Context, Decision, Strategy


class GridDcaStrategy(Strategy):
    name = "grid"

    def __init__(self, step_pct: float = 0.02, take_profit_pct: float = 0.03,
                 max_steps: int = 5) -> None:
        if step_pct <= 0 or take_profit_pct <= 0:
            raise ValueError("step_pct and take_profit_pct must be > 0")
        if max_steps < 1:
            raise ValueError("max_steps must be >= 1")
        self.step_pct, self.take_profit_pct, self.max_steps = (
            step_pct, take_profit_pct, max_steps)

    @property
    def warmup(self) -> int:
        return 1

    def describe(self) -> str:
        return (f"Grid/DCA {self.step_pct*100:g}% per step down, "
                f"TP +{self.take_profit_pct*100:g}%, max {self.max_steps} steps")

    def _chunk(self, ctx: Context) -> float:
        return ctx.starting_cash / self.max_steps

    def evaluate(self, closes: Sequence[float], ctx: Context) -> Decision:
        price = ctx.price
        # take-profit against the average entry
        if ctx.position > 0 and ctx.avg_entry > 0 and \
                price >= ctx.avg_entry * (1 + self.take_profit_pct):
            return Decision("SELL", reason=f"take-profit +{self.take_profit_pct*100:g}%")
        chunk = self._chunk(ctx)
        # first entry
        if ctx.position == 0:
            return Decision("BUY", quote_amount=chunk, reason="first grid entry")
        # averaging down: price fell step_pct below the last buy and cash is left
        if ctx.last_buy_price > 0 and price <= ctx.last_buy_price * (1 - self.step_pct) \
                and ctx.cash > 0:
            return Decision("BUY", quote_amount=chunk,
                            reason=f"DCA {self.step_pct*100:g}% down")
        return HOLD
