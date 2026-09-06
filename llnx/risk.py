"""Global stop-loss and take-profit, applied to every strategy.

Checked BEFORE the strategy runs. When one triggers, the whole position is
sold. Set a percentage to 0 to switch it off.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .strategies.base import Context, Decision


@dataclass
class RiskManager:
    stop_loss_pct: float = 0.0
    take_profit_pct: float = 0.0

    @property
    def active(self) -> bool:
        return self.stop_loss_pct > 0 or self.take_profit_pct > 0

    def check(self, ctx: Context) -> Optional[Decision]:
        if ctx.position <= 0 or ctx.avg_entry <= 0:
            return None
        if self.stop_loss_pct > 0 and ctx.price <= ctx.avg_entry * (1 - self.stop_loss_pct):
            return Decision("SELL", reason=f"STOP-LOSS -{self.stop_loss_pct*100:g}%")
        if self.take_profit_pct > 0 and ctx.price >= ctx.avg_entry * (1 + self.take_profit_pct):
            return Decision("SELL", reason=f"TAKE-PROFIT +{self.take_profit_pct*100:g}%")
        return None
