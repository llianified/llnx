"""CcxtBroker: places REAL orders on a centralised exchange, through ccxt.

Same interface as PaperBroker, so the engine cannot tell the difference.
Defaults to the exchange sandbox/testnet (fake money, real order flow). Only
move to mainnet once paper and sandbox runs look right.

What matters here is that the bot books what the exchange actually did, not
what it hoped would happen: every order is polled until it is closed and the
filled amount, the average fill price and the fee come from the order itself.
A market order rarely fills at the price on screen, and a bot that assumes it
did will drift away from its real position within a handful of trades.

Keys come from the environment, never from the code:
  EXCHANGE_API_KEY, EXCHANGE_API_SECRET

Requires: pip install ccxt
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Optional, Tuple

from .broker import Trade

# how long to keep asking the exchange about an order before giving up on it
SETTLE_TIMEOUT_SEC = 30
SETTLE_POLL_SEC = 1.0


# ── pure helpers (testable without ccxt or a network) ────────────
def fee_in_quote(order: dict, filled: float, price: float, quote: str,
                 fee_rate: float) -> float:
    """The order fee expressed in the quote currency.

    ccxt reports fees in whatever currency the exchange charged them in: the
    quote (usual for sells), the base (usual for buys) or a discount token
    like BNB. Only the first two can be converted exactly; anything else falls
    back to the configured estimate.
    """
    entries = [f for f in (order.get("fees") or []) if f] or []
    single = order.get("fee")
    if single and not entries:
        entries = [single]
    total = 0.0
    seen = False
    for f in entries:
        cost = f.get("cost")
        if cost is None:
            continue
        cur = (f.get("currency") or "").upper()
        if cur == quote.upper():
            total += float(cost)
            seen = True
        elif cur and price > 0:
            total += float(cost) * price   # base (or another coin) at fill price
            seen = True
    if seen:
        return total
    return filled * price * fee_rate       # nothing usable: estimate it


def settle_fill(order: dict, fallback_price: float, quote: str,
                fee_rate: float) -> Tuple[float, float, float]:
    """(filled amount, average fill price, fee in quote) from a ccxt order."""
    filled = float(order.get("filled") or 0.0)
    if not filled:
        filled = float(order.get("amount") or 0.0)
    cost = float(order.get("cost") or 0.0)
    price = (float(order.get("average") or 0.0)
             or (cost / filled if filled and cost else 0.0)
             or float(order.get("price") or 0.0)
             or fallback_price)
    return filled, price, fee_in_quote(order, filled, price, quote, fee_rate)


def is_settled(order: dict) -> bool:
    """True once the exchange is done with the order, however it ended."""
    status = (order.get("status") or "").lower()
    if status in ("closed", "canceled", "cancelled", "expired", "rejected"):
        return True
    remaining = order.get("remaining")
    return remaining is not None and float(remaining) <= 0 and status != "open"


class CcxtBroker:
    is_live = True

    def __init__(self, exchange_id: str, symbol: str, *, sandbox: bool = True,
                 fee_rate: float = 0.001, min_notional: float = 5.0,
                 settle_timeout: int = SETTLE_TIMEOUT_SEC, log=print) -> None:
        import ccxt

        key = os.environ.get("EXCHANGE_API_KEY", "")
        secret = os.environ.get("EXCHANGE_API_SECRET", "")
        if not key or not secret:
            raise RuntimeError(
                "EXCHANGE_API_KEY / EXCHANGE_API_SECRET are not set in the environment.")
        if not hasattr(ccxt, exchange_id):
            raise ValueError(f"ccxt does not know the exchange '{exchange_id}'")

        self.symbol = symbol
        self.base, self.quote = symbol.split("/")
        self.fee_rate = fee_rate
        self.sandbox = sandbox
        self.settle_timeout = settle_timeout
        self.log = log
        self.avg_entry = 0.0
        self.last_buy_price = 0.0
        self.cash = 0.0
        self.position = 0.0
        self.trades: list = []

        self.exchange = getattr(ccxt, exchange_id)({
            "apiKey": key, "secret": secret, "enableRateLimit": True,
        })
        if sandbox:
            self.exchange.set_sandbox_mode(True)
        self.exchange.load_markets()
        self.market = self.exchange.market(symbol)
        limits = (self.market.get("limits") or {})
        self.min_amount = float((limits.get("amount") or {}).get("min") or 0.0)
        # the exchange minimum wins: an order below it is refused anyway
        exchange_min_cost = float((limits.get("cost") or {}).get("min") or 0.0)
        self.min_notional = max(min_notional, exchange_min_cost)
        if exchange_min_cost > min_notional:
            self.log(f"[live] {symbol} needs at least {exchange_min_cost:g} "
                     f"{self.quote} per order")
        self.refresh()

    # ── balances ─────────────────────────────────────────────────
    def refresh(self) -> None:
        bal = self.exchange.fetch_balance()
        self.cash = float(bal.get(self.quote, {}).get("free", 0.0) or 0.0)
        self.position = float(bal.get(self.base, {}).get("free", 0.0) or 0.0)

    def equity(self, price: float) -> float:
        return self.cash + self.position * price

    def restore_entry(self, avg_entry: float, last_buy_price: float) -> None:
        """The exchange knows the balance, not what it was paid for."""
        self.avg_entry = avg_entry
        self.last_buy_price = last_buy_price

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    # ── order settlement ─────────────────────────────────────────
    def _settle(self, order: dict, fallback_price: float):
        """Poll the exchange until the order is done, then read the real fill."""
        oid = order.get("id")
        deadline = time.time() + self.settle_timeout
        while oid and not is_settled(order) and time.time() < deadline:
            time.sleep(SETTLE_POLL_SEC)
            try:
                order = self.exchange.fetch_order(oid, self.symbol)
            except Exception as e:
                self.log(f"[live] could not read order {oid}: {e!r}")
                break
        if oid and not is_settled(order):
            self.log(f"[live] order {oid} is still open after {self.settle_timeout}s "
                     "-- booking what has filled so far")
        return settle_fill(order, fallback_price, self.quote, self.fee_rate)

    # ── orders ───────────────────────────────────────────────────
    def buy(self, price: float, quote_amount: Optional[float] = None) -> Optional[Trade]:
        spend = self.cash if quote_amount is None else min(quote_amount, self.cash)
        if spend < self.min_notional:
            return None
        amount = float(self.exchange.amount_to_precision(self.symbol, spend / price))
        if amount <= 0 or (self.min_amount and amount < self.min_amount):
            return None

        # A market buy is a request to spend money, not to receive an exact
        # amount, so hand the exchange the cost when it accepts one.
        if self.exchange.has.get("createMarketBuyOrderWithCost"):
            order = self.exchange.create_market_buy_order_with_cost(self.symbol, spend)
        else:
            order = self.exchange.create_order(self.symbol, "market", "buy", amount)

        filled, fill_price, fee = self._settle(order, price)
        if filled <= 0:
            self.log("[live] the BUY did not fill")
            self.refresh()
            return None

        old_pos = self.position
        new_pos = old_pos + filled
        self.avg_entry = ((old_pos * self.avg_entry + filled * fill_price) / new_pos
                          if new_pos > 0 else fill_price)
        self.last_buy_price = fill_price
        self.refresh()
        return self._record("BUY", fill_price, filled, fee)

    def sell(self, price: float, fraction: float = 1.0) -> Optional[Trade]:
        if self.position <= 0:
            return None
        fraction = max(0.0, min(1.0, fraction))
        amount = float(self.exchange.amount_to_precision(self.symbol,
                                                         self.position * fraction))
        if amount <= 0 or (self.min_amount and amount < self.min_amount):
            return None

        order = self.exchange.create_order(self.symbol, "market", "sell", amount)
        filled, fill_price, fee = self._settle(order, price)
        if filled <= 0:
            self.log("[live] the SELL did not fill")
            self.refresh()
            return None

        self.refresh()
        if self.position <= 1e-12:
            self.avg_entry = 0.0
            self.last_buy_price = 0.0
        return self._record("SELL", fill_price, filled, fee)

    def _record(self, side: str, price: float, amount: float, fee: float) -> Trade:
        trade = Trade(
            timestamp=self._now(), side=side, price=price, amount=amount, fee=fee,
            cash_after=self.cash, position_after=self.position,
            equity_after=self.equity(price),
        )
        self.trades.append(trade)
        return trade
