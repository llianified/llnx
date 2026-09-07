"""Global stop-loss, trailing stop and take-profit, applied to every strategy.

Checked BEFORE the strategy runs, so an exit always wins over an entry. When
one triggers, the whole position is sold. Set a percentage to 0 to switch it
off.

The trailing stop is the one that changes returns the most. A fixed
take-profit caps the winner that was going to pay for the losers; a trailing
stop keeps the floor moving up under the position and only sells once the
price actually turns. Use one or the other, rarely both.

The peak is remembered while the position is open. A restart re-seeds it from
the current price, so a bot that comes back up mid-position starts trailing
from where it finds the market, not from a peak it never saw.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .strategies.base import Context, Decision


@dataclass
class RiskManager:
    stop_loss_pct: float = 0.0
    take_profit_pct: float = 0.0
    trailing_stop_pct: float = 0.0

    def __post_init__(self) -> None:
        self.peak = 0.0        # highest price seen while holding

    @property
    def active(self) -> bool:
        return (self.stop_loss_pct > 0 or self.take_profit_pct > 0
                or self.trailing_stop_pct > 0)

    def describe(self) -> str:
        bits = []
        if self.stop_loss_pct > 0:
            bits.append(f"SL {self.stop_loss_pct*100:g}%")
        if self.trailing_stop_pct > 0:
            bits.append(f"trail {self.trailing_stop_pct*100:g}%")
        if self.take_profit_pct > 0:
            bits.append(f"TP {self.take_profit_pct*100:g}%")
        return " | ".join(bits) or "off"

    def check(self, ctx: Context) -> Optional[Decision]:
        if ctx.position <= 0 or ctx.avg_entry <= 0:
            self.peak = 0.0
            return None
        self.peak = max(self.peak, ctx.price, ctx.avg_entry)

        if self.stop_loss_pct > 0 and ctx.price <= ctx.avg_entry * (1 - self.stop_loss_pct):
            return Decision("SELL", reason=f"STOP-LOSS -{self.stop_loss_pct*100:g}%")
        if self.trailing_stop_pct > 0:
            floor = self.peak * (1 - self.trailing_stop_pct)
            if ctx.price <= floor and self.peak > ctx.avg_entry:
                return Decision("SELL",
                                reason=f"TRAILING -{self.trailing_stop_pct*100:g}% "
                                       f"from {self.peak:.8g}")
        if self.take_profit_pct > 0 and ctx.price >= ctx.avg_entry * (1 + self.take_profit_pct):
            return Decision("SELL", reason=f"TAKE-PROFIT +{self.take_profit_pct*100:g}%")
        return None
