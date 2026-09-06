"""Engine: menyatukan strategi + broker. Murni logika, tanpa IO/jaringan.

Dipisah dari bagian jaringan supaya gampang di-test dan di-backtest.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from .broker import PaperBroker, Trade
from .strategy import SmaCrossStrategy


@dataclass
class StepResult:
    signal: str                 # "BUY" / "SELL" / "HOLD"
    executed: Optional[Trade]   # Trade bila ada order tereksekusi, else None
    price: float
    equity: float


class TradingEngine:
    def __init__(self, strategy: SmaCrossStrategy, broker: PaperBroker) -> None:
        self.strategy = strategy
        self.broker = broker

    def step(self, closes: Sequence[float], price: float) -> StepResult:
        """Proses satu tick.

        `closes` = deret harga penutupan candle yang SUDAH closed (untuk sinyal).
        `price`  = harga eksekusi saat ini.
        """
        signal = self.strategy.signal(closes)
        executed = None
        if signal == "BUY":
            executed = self.broker.buy(price)
        elif signal == "SELL":
            executed = self.broker.sell(price)
        return StepResult(
            signal=signal,
            executed=executed,
            price=price,
            equity=self.broker.equity(price),
        )
