"""Paper broker: simulasi eksekusi order dengan saldo virtual.

Mendukung order bertahap (untuk DCA/grid) dan menghitung harga entry
rata-rata tertimbang (untuk stop-loss / take-profit).

TIDAK ada uang sungguhan yang berpindah — ini murni simulasi.
Interface-nya sama dengan CcxtBroker (mode uang real), jadi engine tak
peduli pakai broker yang mana.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class Trade:
    timestamp: str
    side: str          # "BUY" / "SELL"
    price: float
    amount: float      # jumlah base yang ditransaksikan
    fee: float         # fee dalam quote
    cash_after: float
    position_after: float
    equity_after: float
    reason: str = ""


@dataclass
class PaperBroker:
    fee_rate: float = 0.001
    min_notional: float = 5.0
    cash: float = 5.0
    position: float = 0.0
    avg_entry: float = 0.0        # harga beli rata-rata tertimbang
    last_buy_price: float = 0.0   # harga pembelian terakhir (dipakai grid)
    trades: list = field(default_factory=list)

    is_live = False               # dibedakan dari CcxtBroker

    def equity(self, price: float) -> float:
        return self.cash + self.position * price

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    def buy(self, price: float, quote_amount: Optional[float] = None) -> Optional[Trade]:
        """Beli senilai `quote_amount` (None = pakai seluruh cash)."""
        spend = self.cash if quote_amount is None else min(quote_amount, self.cash)
        if spend <= 0:
            return None
        if spend < self.min_notional:
            return None  # di bawah minimum order exchange -> pasti ditolak
        fee = spend * self.fee_rate
        amount = (spend - fee) / price
        new_pos = self.position + amount
        self.avg_entry = (self.position * self.avg_entry + amount * price) / new_pos
        self.position = new_pos
        self.cash -= spend
        self.last_buy_price = price
        return self._record("BUY", price, amount, fee)

    def sell(self, price: float, fraction: float = 1.0) -> Optional[Trade]:
        """Jual `fraction` dari posisi (1.0 = jual semua)."""
        if self.position <= 0:
            return None
        fraction = max(0.0, min(1.0, fraction))
        amount = self.position * fraction
        if amount <= 0:
            return None
        gross = amount * price
        fee = gross * self.fee_rate
        self.cash += gross - fee
        self.position -= amount
        if self.position <= 1e-12:
            self.position = 0.0
            self.avg_entry = 0.0
            self.last_buy_price = 0.0
        return self._record("SELL", price, amount, fee)

    def _record(self, side: str, price: float, amount: float, fee: float) -> Trade:
        trade = Trade(
            timestamp=self._now(), side=side, price=price, amount=amount, fee=fee,
            cash_after=self.cash, position_after=self.position,
            equity_after=self.equity(price),
        )
        self.trades.append(trade)
        return trade

    # ── Persistensi ──────────────────────────────────────────────
    def to_dict(self) -> dict:
        return {
            "fee_rate": self.fee_rate, "min_notional": self.min_notional,
            "cash": self.cash, "position": self.position,
            "avg_entry": self.avg_entry, "last_buy_price": self.last_buy_price,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PaperBroker":
        return cls(
            fee_rate=data.get("fee_rate", 0.001),
            min_notional=data.get("min_notional", 5.0),
            cash=data.get("cash", 5.0),
            position=data.get("position", 0.0),
            avg_entry=data.get("avg_entry", data.get("entry_price", 0.0)),
            last_buy_price=data.get("last_buy_price", 0.0),
        )
