"""Engine: menyatukan risk manager + strategi + broker + notifier.

Alur tiap tick:
  1. Cek risk manager (SL/TP). Kalau terpicu -> jual, selesai.
  2. Kalau tidak, jalankan strategi -> BUY / SELL / HOLD.
Logika ini murni & tak tahu soal jaringan (mudah dites & di-backtest).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from .broker import Trade
from .notify import NullNotifier
from .risk import RiskManager
from .strategies.base import Context, Decision, Strategy


@dataclass
class StepResult:
    decision: Decision
    executed: Optional[Trade]
    price: float
    equity: float


class TradingEngine:
    def __init__(self, strategy: Strategy, broker, starting_cash: float,
                 risk: Optional[RiskManager] = None, notifier=None,
                 symbol: str = "") -> None:
        self.strategy = strategy
        self.broker = broker
        self.starting_cash = starting_cash
        self.risk = risk
        self.notifier = notifier or NullNotifier()
        self.symbol = symbol

    def _context(self, price: float) -> Context:
        b = self.broker
        return Context(
            price=price, cash=b.cash, position=b.position,
            avg_entry=b.avg_entry, last_buy_price=b.last_buy_price,
            starting_cash=self.starting_cash,
        )

    def step(self, closes: Sequence[float], price: float) -> StepResult:
        ctx = self._context(price)
        decision: Decision = Decision("HOLD")
        executed: Optional[Trade] = None

        # 1) Risk manager punya prioritas
        if self.risk and self.risk.active:
            rd = self.risk.check(ctx)
            if rd is not None:
                executed = self.broker.sell(price)
                decision = rd

        # 2) Strategi (kalau risk tidak menjual)
        if executed is None:
            decision = self.strategy.evaluate(closes, ctx)
            if decision.action == "BUY":
                executed = self.broker.buy(price, decision.quote_amount)
            elif decision.action == "SELL":
                executed = self.broker.sell(price, decision.fraction or 1.0)

        if executed is not None:
            executed.reason = decision.reason
            self.notifier.notify_trade(executed, self.symbol)

        return StepResult(decision=decision, executed=executed, price=price,
                          equity=self.broker.equity(price))
