"""Strategi Grid / DCA: beli bertahap saat harga turun, jual saat take-profit.

Cocok untuk pasar sideways / turun. Modal dibagi rata jadi `max_steps` bagian;
tiap kali harga turun `step_pct` dari pembelian terakhir, beli satu bagian lagi
(averaging down). Jual semua saat harga >= entry rata-rata * (1 + take_profit_pct).
"""
from __future__ import annotations

from typing import Sequence

from .base import HOLD, Context, Decision, Strategy


class GridDcaStrategy(Strategy):
    name = "grid"

    def __init__(self, step_pct: float = 0.02, take_profit_pct: float = 0.03,
                 max_steps: int = 5) -> None:
        if step_pct <= 0 or take_profit_pct <= 0:
            raise ValueError("step_pct & take_profit_pct harus > 0")
        if max_steps < 1:
            raise ValueError("max_steps harus >= 1")
        self.step_pct, self.take_profit_pct, self.max_steps = (
            step_pct, take_profit_pct, max_steps)

    @property
    def warmup(self) -> int:
        return 1

    def describe(self) -> str:
        return (f"Grid/DCA turun {self.step_pct*100:g}%/langkah, "
                f"TP +{self.take_profit_pct*100:g}%, maks {self.max_steps} langkah")

    def _chunk(self, ctx: Context) -> float:
        return ctx.starting_cash / self.max_steps

    def evaluate(self, closes: Sequence[float], ctx: Context) -> Decision:
        price = ctx.price
        # Take-profit terhadap entry rata-rata
        if ctx.position > 0 and ctx.avg_entry > 0 and \
                price >= ctx.avg_entry * (1 + self.take_profit_pct):
            return Decision("SELL", reason=f"take-profit +{self.take_profit_pct*100:g}%")
        chunk = self._chunk(ctx)
        # Entry pertama
        if ctx.position == 0:
            return Decision("BUY", quote_amount=chunk, reason="entry pertama grid")
        # Averaging down: harga turun step_pct dari beli terakhir & masih ada cash
        if ctx.last_buy_price > 0 and price <= ctx.last_buy_price * (1 - self.step_pct) \
                and ctx.cash > 0:
            return Decision("BUY", quote_amount=chunk,
                            reason=f"DCA turun {self.step_pct*100:g}%")
        return HOLD
