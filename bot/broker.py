"""Paper broker: mensimulasikan eksekusi order dengan saldo virtual.

Model sederhana single-symbol, all-in:
  - Saldo `cash` dalam mata uang quote (mis. USDT).
  - `position` = jumlah aset base yang dipegang (mis. BTC).
  - BUY  = pakai seluruh cash beli base (dikurangi fee).
  - SELL = jual seluruh position jadi cash (dikurangi fee).

TIDAK ada uang sungguhan yang berpindah. Ini murni simulasi.
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


@dataclass
class PaperBroker:
    fee_rate: float = 0.001
    min_notional: float = 5.0
    cash: float = 5.0
    position: float = 0.0
    entry_price: float = 0.0
    trades: list = field(default_factory=list)

    def equity(self, price: float) -> float:
        """Nilai total portofolio bila di-mark ke harga sekarang."""
        return self.cash + self.position * price

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    def buy(self, price: float) -> Optional[Trade]:
        """Beli all-in. Return Trade bila tereksekusi, None bila dilewati."""
        if self.position > 0 or self.cash <= 0:
            return None
        if self.cash < self.min_notional:
            # Order lebih kecil dari minimum exchange -> di dunia nyata pasti ditolak.
            return None
        fee = self.cash * self.fee_rate
        spendable = self.cash - fee
        amount = spendable / price
        self.position = amount
        self.entry_price = price
        self.cash = 0.0
        return self._record("BUY", price, amount, fee)

    def sell(self, price: float) -> Optional[Trade]:
        """Jual seluruh posisi. Return Trade bila tereksekusi, None bila dilewati."""
        if self.position <= 0:
            return None
        gross = self.position * price
        fee = gross * self.fee_rate
        amount = self.position
        self.cash = gross - fee
        self.position = 0.0
        self.entry_price = 0.0
        return self._record("SELL", price, amount, fee)

    def _record(self, side: str, price: float, amount: float, fee: float) -> Trade:
        trade = Trade(
            timestamp=self._now(),
            side=side,
            price=price,
            amount=amount,
            fee=fee,
            cash_after=self.cash,
            position_after=self.position,
            equity_after=self.equity(price),
        )
        self.trades.append(trade)
        return trade

    # ── Persistensi ──────────────────────────────────────────────
    def to_dict(self) -> dict:
        return {
            "fee_rate": self.fee_rate,
            "min_notional": self.min_notional,
            "cash": self.cash,
            "position": self.position,
            "entry_price": self.entry_price,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PaperBroker":
        return cls(
            fee_rate=data.get("fee_rate", 0.001),
            min_notional=data.get("min_notional", 5.0),
            cash=data.get("cash", 5.0),
            position=data.get("position", 0.0),
            entry_price=data.get("entry_price", 0.0),
        )
