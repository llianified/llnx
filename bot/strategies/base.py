"""The strategy contract: a Context goes in, a Decision comes out."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence


@dataclass
class Context:
    """Market and portfolio state at the moment of the decision."""
    price: float
    cash: float
    position: float
    avg_entry: float
    last_buy_price: float
    starting_cash: float


@dataclass
class Decision:
    action: str                          # "BUY" | "SELL" | "HOLD"
    quote_amount: Optional[float] = None  # BUY: quote value; None = all in
    fraction: Optional[float] = None      # SELL: share of the position; None = all
    reason: str = ""


HOLD = Decision("HOLD")


class Strategy:
    name = "base"

    @property
    def warmup(self) -> int:
        """Candles needed before the signal means anything."""
        return 1

    def describe(self) -> str:
        return self.name

    def evaluate(self, closes: Sequence[float], ctx: Context) -> Decision:
        raise NotImplementedError
