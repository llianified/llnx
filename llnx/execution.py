"""The auto-execution layer: turns a decision into an order that really goes out.

`TradingEngine` calls `buy()`/`sell()` on whatever broker it is given. The
executor is a broker that wraps another broker and, on every order:

  1. asks the guardrails whether the order may go out at all,
  2. shrinks it to the per-order cap,
  3. sends it to the real broker,
  4. writes the outcome -- filled, blocked, rejected or failed -- to an
     append-only journal, so there is always a record of what the bot did
     while nobody was watching,
  5. re-reads the venue balances after a failure, because after an error the
     bot's idea of the position is the one thing that must not be guessed.

Failed orders are never retried inside a tick. A market order that errors may
still have reached the venue, and firing a second one is how a bot ends up
with twice the position it wanted. The next tick decides again, with fresh
prices and fresh balances.

Set `auto_execute=False` for signal-only mode: everything runs, nothing is
sent, and the journal records what would have happened.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from typing import Optional

from .guards import Guardrails, SessionState


class OrderExecutor:
    def __init__(self, broker, guards: Optional[Guardrails] = None, *,
                 journal_path: str = "", symbol: str = "", mode: str = "paper",
                 auto_execute: bool = True, log=print, clock=time.time,
                 state: Optional[SessionState] = None) -> None:
        self.broker = broker
        self.guards = guards or Guardrails()
        self.journal_path = journal_path
        self.symbol = symbol
        self.mode = mode
        self.auto_execute = auto_execute
        self.log = log
        self.clock = clock
        self.state = state or SessionState()
        self.last_block = ""      # why the last order did not go out (for the UI)
        self.signal = ""          # the reason the engine gave for this order

    # ── the broker interface the engine expects ──────────────────
    @property
    def cash(self) -> float: return self.broker.cash
    @property
    def position(self) -> float: return self.broker.position
    @property
    def avg_entry(self) -> float: return self.broker.avg_entry
    @property
    def last_buy_price(self) -> float: return self.broker.last_buy_price
    @property
    def trades(self) -> list: return self.broker.trades
    @property
    def is_live(self) -> bool: return getattr(self.broker, "is_live", False)

    def equity(self, price: float) -> float:
        return self.broker.equity(price)

    def on_decision(self, decision) -> None:
        """The engine names the signal before it calls buy()/sell()."""
        self.signal = getattr(decision, "reason", "") or ""

    # ── orders ───────────────────────────────────────────────────
    def buy(self, price: float, quote_amount: Optional[float] = None):
        equity = self.broker.equity(price)
        now = self.clock()
        self.state.roll_day(now, equity)

        blocked = self.guards.block_reason("BUY", equity=equity, state=self.state,
                                           now=now)
        if blocked:
            return self._blocked("BUY", price, blocked, equity)

        spend = self.broker.cash if quote_amount is None else quote_amount
        capped = self.guards.cap_order(spend, equity)
        if capped < spend:
            self.log(f"[exec] order capped: {spend:.4f} -> {capped:.4f} "
                     f"({self.guards.max_order_pct*100:g}% of equity)")
        return self._send("BUY", price, equity, quote_amount=capped)

    def sell(self, price: float, fraction: float = 1.0):
        equity = self.broker.equity(price)
        now = self.clock()
        self.state.roll_day(now, equity)

        blocked = self.guards.block_reason("SELL", equity=equity, state=self.state,
                                           now=now)
        if blocked:
            return self._blocked("SELL", price, blocked, equity)
        return self._send("SELL", price, equity, fraction=fraction)

    # ── internals ────────────────────────────────────────────────
    def _send(self, side: str, price: float, equity: float, *,
              quote_amount: Optional[float] = None, fraction: float = 1.0):
        if not self.auto_execute:
            self.last_block = "signal-only mode (auto_execute is off)"
            self._journal(side, price, "signal", equity, reason=self.last_block,
                          requested=quote_amount if side == "BUY" else fraction,
                          unit="quote" if side == "BUY" else "fraction")
            self.log(f"[exec] {side} signal at {price:.8g} -- not sent, "
                     "auto_execute is off")
            return None

        try:
            trade = (self.broker.buy(price, quote_amount) if side == "BUY"
                     else self.broker.sell(price, fraction))
        except Exception as e:
            self.state.on_failure()
            self.last_block = f"order failed: {e!r}"
            self._journal(side, price, "failed", equity, error=repr(e),
                          requested=quote_amount if side == "BUY" else fraction,
                          unit="quote" if side == "BUY" else "fraction")
            self.log(f"[exec] {side} FAILED: {e!r} "
                     f"({self.state.consecutive_failures} in a row)")
            self._reconcile()
            return None

        if trade is None:
            # the broker refused it: under the minimum, or nothing to sell
            self.last_block = f"{side} not placed (below the minimum, or nothing to sell)"
            self._journal(side, price, "rejected", equity, reason=self.last_block,
                          requested=quote_amount if side == "BUY" else fraction,
                          unit="quote" if side == "BUY" else "fraction")
            return None

        self.state.on_fill(self.clock())
        self.last_block = ""
        self._journal(side, trade.price, "filled", self.broker.equity(price),
                      amount=trade.amount, fee=trade.fee, reason=trade.reason,
                      requested=quote_amount if side == "BUY" else fraction,
                      unit="quote" if side == "BUY" else "fraction")
        return trade

    def _blocked(self, side: str, price: float, reason: str, equity: float):
        self.last_block = reason
        self._journal(side, price, "blocked", equity, reason=reason)
        self.log(f"[exec] {side} blocked -- {reason}")
        return None

    def _reconcile(self) -> None:
        """After a failure the venue is the source of truth, not our numbers."""
        refresh = getattr(self.broker, "refresh", None)
        if callable(refresh):
            try:
                refresh()
                self.log(f"[exec] balances re-read: cash={self.broker.cash:.4f} "
                         f"position={self.broker.position:.8f}")
            except Exception as e:
                self.log(f"[exec] could not re-read balances: {e!r}")

    def _journal(self, side: str, price: float, status: str, equity: float, *,
                 amount: float = 0.0, fee: float = 0.0, reason: str = "",
                 error: str = "", requested=None, unit: str = "") -> None:
        if not self.journal_path:
            return
        row = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "mode": self.mode, "symbol": self.symbol, "side": side,
            "status": status, "price": price, "requested": requested, "unit": unit,
            "amount": amount, "fee": fee, "equity": equity,
            "signal": self.signal, "reason": reason, "error": error,
        }
        try:
            with open(self.journal_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(row) + "\n")
        except OSError as e:   # a full disk must not stop the bot from trading
            self.log(f"[exec] could not write the journal: {e!r}")

def read_journal(path: str, limit: int = 20) -> list:
    """Last `limit` journal rows, newest last. Bad lines are skipped."""
    if not os.path.exists(path):
        return []
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue
    return rows[-limit:]
