"""Kontrak dasar strategi: Context masuk, Decision keluar."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence


@dataclass
class Context:
    """Kondisi pasar & portofolio saat pengambilan keputusan."""
    price: float
    cash: float
    position: float
    avg_entry: float
    last_buy_price: float
    starting_cash: float


@dataclass
class Decision:
    action: str                          # "BUY" | "SELL" | "HOLD"
    quote_amount: Optional[float] = None  # BUY: nilai quote; None = all-in
    fraction: Optional[float] = None      # SELL: fraksi posisi; None = semua
    reason: str = ""


HOLD = Decision("HOLD")


class Strategy:
    name = "base"

    @property
    def warmup(self) -> int:
        """Jumlah candle minimum sebelum sinyal valid."""
        return 1

    def describe(self) -> str:
        return self.name

    def evaluate(self, closes: Sequence[float], ctx: Context) -> Decision:
        raise NotImplementedError
