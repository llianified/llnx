"""CcxtBroker: eksekusi order UANG SUNGGUHAN via ccxt.  ⚠️ EKSPERIMENTAL.

Interface-nya sama dengan PaperBroker sehingga engine tak perlu tahu bedanya.
Default ke SANDBOX/TESTNET (uang bohongan, alur order asli). Gunakan mainnet
hanya setelah puas menguji di paper & sandbox.

API key dibaca dari environment (JANGAN ditulis di kode/commit):
  EXCHANGE_API_KEY, EXCHANGE_API_SECRET
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Optional

from .broker import Trade


class CcxtBroker:
    is_live = True

    def __init__(self, exchange_id: str, symbol: str, *, sandbox: bool = True,
                 fee_rate: float = 0.001, min_notional: float = 5.0) -> None:
        import ccxt

        key = os.environ.get("EXCHANGE_API_KEY", "")
        secret = os.environ.get("EXCHANGE_API_SECRET", "")
        if not key or not secret:
            raise RuntimeError(
                "EXCHANGE_API_KEY / EXCHANGE_API_SECRET belum di-set di environment.")
        if not hasattr(ccxt, exchange_id):
            raise ValueError(f"exchange '{exchange_id}' tidak dikenal ccxt")

        self.symbol = symbol
        self.base, self.quote = symbol.split("/")
        self.fee_rate = fee_rate
        self.min_notional = min_notional
        self.sandbox = sandbox
        self.avg_entry = 0.0
        self.last_buy_price = 0.0
        self.trades: list = []

        self.exchange = getattr(ccxt, exchange_id)({
            "apiKey": key, "secret": secret, "enableRateLimit": True,
        })
        if sandbox:
            self.exchange.set_sandbox_mode(True)
        self.exchange.load_markets()
        self.refresh()

    # ── Saldo ────────────────────────────────────────────────────
    def refresh(self) -> None:
        bal = self.exchange.fetch_balance()
        self.cash = float(bal.get(self.quote, {}).get("free", 0.0) or 0.0)
        self.position = float(bal.get(self.base, {}).get("free", 0.0) or 0.0)

    def equity(self, price: float) -> float:
        return self.cash + self.position * price

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    # ── Order ────────────────────────────────────────────────────
    def buy(self, price: float, quote_amount: Optional[float] = None) -> Optional[Trade]:
        spend = self.cash if quote_amount is None else min(quote_amount, self.cash)
        if spend < self.min_notional:
            return None
        amount = float(self.exchange.amount_to_precision(self.symbol, spend / price))
        if amount <= 0:
            return None
        try:
            self.exchange.create_order(self.symbol, "market", "buy", amount)
        except Exception as e:
            print(f"[live] order BUY gagal: {e!r}")
            return None
        old_pos = self.position
        self.refresh()
        filled = max(self.position - old_pos, amount)
        new_pos = old_pos + filled
        self.avg_entry = ((old_pos * self.avg_entry + filled * price) / new_pos
                          if new_pos > 0 else price)
        self.last_buy_price = price
        return self._record("BUY", price, filled, spend * self.fee_rate)

    def sell(self, price: float, fraction: float = 1.0) -> Optional[Trade]:
        if self.position <= 0:
            return None
        fraction = max(0.0, min(1.0, fraction))
        amount = float(self.exchange.amount_to_precision(self.symbol,
                                                         self.position * fraction))
        if amount <= 0:
            return None
        try:
            self.exchange.create_order(self.symbol, "market", "sell", amount)
        except Exception as e:
            print(f"[live] order SELL gagal: {e!r}")
            return None
        self.refresh()
        if self.position <= 1e-12:
            self.avg_entry = 0.0
            self.last_buy_price = 0.0
        return self._record("SELL", price, amount, amount * price * self.fee_rate)

    def _record(self, side: str, price: float, amount: float, fee: float) -> Trade:
        trade = Trade(
            timestamp=self._now(), side=side, price=price, amount=amount, fee=fee,
            cash_after=self.cash, position_after=self.position,
            equity_after=self.equity(price),
        )
        self.trades.append(trade)
        return trade
