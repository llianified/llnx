"""JupiterBroker: real Solana swaps through the Jupiter aggregator.

Same interface as PaperBroker, so the engine cannot tell the difference.

  dry_run=True (default)
      Real Jupiter quotes -- so the price already includes the route, the swap
      fee and the price impact -- but nothing is signed or sent. The balances
      are virtual. No wallet needed.

  dry_run=False
      A real swap. Needs SOLANA_PRIVATE_KEY (base58) and SOLANA_RPC_URL in the
      environment plus the `solders` package. The transaction is sent AND
      confirmed on chain before the trade is booked, and the balances are then
      re-read from the wallet, so the bot's position is the chain's position
      and not an estimate. Start with tiny amounts.

The trade is priced off the quote itself (spend / tokens received), which is
what the swap actually costs. `fee` records the gap to the screen price, i.e.
what the route, the fee and the impact took.
"""
from __future__ import annotations

import base64
import os
from datetime import datetime, timezone
from typing import Optional

from .broker import PaperBroker, Trade
from .http import get_json, post_json
from . import wallet

USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"  # 6 decimals
USDC_DECIMALS = 6
QUOTE = ("https://quote-api.jup.ag/v6/quote?inputMint={i}&outputMint={o}"
         "&amount={a}&slippageBps={bps}")
SWAP = "https://quote-api.jup.ag/v6/swap"
TOKEN_META = "https://tokens.jup.ag/token/{mint}"
DEFAULT_DECIMALS = 9


class JupiterBroker:
    is_live = True

    def __init__(self, token_mint: str, *, dry_run: bool = True, cash: float = 20.0,
                 fee_rate: float = 0.003, min_notional: float = 1.0,
                 slippage_bps: int = 100, log=print) -> None:
        self.token = token_mint
        self.dry_run = dry_run
        self.slippage_bps = slippage_bps
        self.min_notional = min_notional
        self.log = log
        self.trades: list = []
        self._decimals: Optional[int] = None

        # dry run keeps virtual balances; the quote already contains the fees,
        # so the paper broker must not charge a second one
        self._paper = PaperBroker(fee_rate=0.0, min_notional=min_notional, cash=cash)
        # live keeps the chain's balances plus our own entry bookkeeping
        self._live_cash = 0.0
        self._live_position = 0.0
        self._live_position_raw = 0    # base units, exact
        self._avg_entry = 0.0
        self._last_buy_price = 0.0
        self.keypair = None
        self.rpc_url = ""

        if not dry_run:
            self._connect_wallet()

    # ── the broker interface ─────────────────────────────────────
    @property
    def cash(self) -> float:
        return self._paper.cash if self.dry_run else self._live_cash

    @property
    def position(self) -> float:
        return self._paper.position if self.dry_run else self._live_position

    @property
    def avg_entry(self) -> float:
        return self._paper.avg_entry if self.dry_run else self._avg_entry

    @property
    def last_buy_price(self) -> float:
        return self._paper.last_buy_price if self.dry_run else self._last_buy_price

    def equity(self, price: float) -> float:
        return self.cash + self.position * price

    def restore_entry(self, avg_entry: float, last_buy_price: float) -> None:
        """The chain knows the balance, not what it was paid for."""
        self._avg_entry = avg_entry
        self._last_buy_price = last_buy_price

    # ── wallet ───────────────────────────────────────────────────
    def _connect_wallet(self) -> None:
        key = os.environ.get("SOLANA_PRIVATE_KEY")
        self.rpc_url = os.environ.get("SOLANA_RPC_URL", "")
        if not key or not self.rpc_url:
            raise RuntimeError("SOLANA_PRIVATE_KEY / SOLANA_RPC_URL are not set")
        try:
            from solders.keypair import Keypair
        except ImportError as e:
            raise RuntimeError(f"the solders package is not installed: {e}")
        self.keypair = Keypair.from_base58_string(key)
        self.owner = str(self.keypair.pubkey())
        gas = wallet.sol_balance(self.rpc_url, self.owner)
        self.log(f"[jupiter] wallet {self.owner[:4]}…{self.owner[-4:]}  "
                 f"gas {gas:.4f} SOL")
        if gas < 0.005:
            self.log("[jupiter] warning: very little SOL for fees -- swaps will fail")
        self.refresh()

    def refresh(self) -> None:
        """Re-read the wallet. After an error the chain is the source of truth."""
        if self.dry_run:
            return
        self._live_cash, _ = wallet.token_balance(self.rpc_url, self.owner, USDC)
        self._live_position, self._live_position_raw = wallet.token_balance(
            self.rpc_url, self.owner, self.token)

    # ── token metadata ───────────────────────────────────────────
    @property
    def decimals(self) -> int:
        if self._decimals is None:
            self._decimals = self._fetch_decimals()
        return self._decimals

    def _fetch_decimals(self) -> int:
        try:
            meta = get_json(TOKEN_META.format(mint=self.token)) or {}
            if meta.get("decimals") is not None:
                return int(meta["decimals"])
        except Exception:
            pass
        if self.rpc_url:
            dec = wallet.token_decimals(self.rpc_url, self.token)
            if dec is not None:
                return dec
        self.log(f"[jupiter] could not read the decimals, assuming {DEFAULT_DECIMALS}")
        return DEFAULT_DECIMALS

    # ── quotes ───────────────────────────────────────────────────
    def _quote(self, in_mint: str, out_mint: str, atomic: int) -> dict:
        q = get_json(QUOTE.format(i=in_mint, o=out_mint, a=int(atomic),
                                  bps=self.slippage_bps))
        if not q or not q.get("outAmount"):
            raise RuntimeError(f"Jupiter has no route for {in_mint[:6]}→{out_mint[:6]}")
        return q

    # ── orders ───────────────────────────────────────────────────
    def buy(self, price: float, quote_amount: Optional[float] = None) -> Optional[Trade]:
        spend = self.cash if quote_amount is None else min(quote_amount, self.cash)
        if spend < self.min_notional:
            return None

        quote = self._quote(USDC, self.token, int(spend * 10 ** USDC_DECIMALS))
        received = int(quote["outAmount"]) / 10 ** self.decimals
        if received <= 0:
            return None
        effective = spend / received          # what the swap really costs
        impact = max(0.0, spend - received * price)

        signature = "" if self.dry_run else self._swap(quote)
        return self._book("BUY", effective, received, spend, impact, signature)

    def sell(self, price: float, fraction: float = 1.0) -> Optional[Trade]:
        if self.position <= 0:
            return None
        fraction = max(0.0, min(1.0, fraction))
        # live: spend exact base units, so "sell everything" really empties it
        atomic = (int(self._live_position_raw * fraction) if not self.dry_run
                  else int(self.position * fraction * 10 ** self.decimals))
        amount = atomic / 10 ** self.decimals
        if atomic <= 0:
            return None

        quote = self._quote(self.token, USDC, atomic)
        received = int(quote["outAmount"]) / 10 ** USDC_DECIMALS
        if received <= 0:
            return None
        effective = received / amount
        impact = max(0.0, amount * price - received)

        signature = "" if self.dry_run else self._swap(quote)
        return self._book("SELL", effective, amount, received, impact, signature,
                          fraction=fraction)

    def _book(self, side: str, price: float, amount: float, notional: float,
              fee: float, signature: str, fraction: float = 1.0) -> Optional[Trade]:
        """Record a swap that has already happened (or been simulated)."""
        tag = "dry-run" if self.dry_run else f"LIVE {signature[:8]}…"
        if self.dry_run:
            # fee_rate is 0 on the paper broker, so the amounts match the quote
            trade = (self._paper.buy(price, notional) if side == "BUY"
                     else self._paper.sell(price, fraction))
            if trade is None:
                return None
            trade.fee = fee
            trade.equity_after = self._paper.equity(price)
        else:
            self._track_entry(side, price, amount)
            self.refresh()          # the chain, not our arithmetic
            trade = Trade(
                timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                side=side, price=price, amount=amount, fee=fee,
                cash_after=self.cash, position_after=self.position,
                equity_after=self.equity(price))
            self.trades.append(trade)
        trade.reason = (trade.reason + " · jupiter " + tag).strip(" ·")
        return trade

    def _track_entry(self, side: str, price: float, amount: float) -> None:
        """Average entry price, kept by hand because the chain does not track it."""
        if side == "BUY":
            new_pos = self._live_position + amount
            self._avg_entry = ((self._live_position * self._avg_entry + amount * price)
                               / new_pos if new_pos > 0 else price)
            self._last_buy_price = price
        elif self._live_position - amount <= 1e-12:
            self._avg_entry = 0.0
            self._last_buy_price = 0.0

    # ── the real swap ────────────────────────────────────────────
    def _swap(self, quote: dict) -> str:
        """Sign, send and CONFIRM the swap. Returns the signature.

        Raises if anything goes wrong: an unconfirmed swap must never be
        booked as a trade.
        """
        from solders.transaction import VersionedTransaction

        body = post_json(SWAP, {
            "quoteResponse": quote,
            "userPublicKey": self.owner,
            "wrapAndUnwrapSol": True,
            "dynamicComputeUnitLimit": True,
            "prioritizationFeeLamports": "auto",
        })
        if not body.get("swapTransaction"):
            raise RuntimeError(f"Jupiter returned no transaction: {body}")

        raw = base64.b64decode(body["swapTransaction"])
        tx = VersionedTransaction.from_bytes(raw)
        signed = VersionedTransaction(tx.message, [self.keypair])
        signature = wallet.rpc(self.rpc_url, "sendTransaction",
                               [base64.b64encode(bytes(signed)).decode(),
                                {"encoding": "base64", "maxRetries": 3}])
        self.log(f"[jupiter] sent {signature} -- waiting for confirmation...")
        status = wallet.confirm_signature(self.rpc_url, signature)
        self.log(f"[jupiter] {status}: {signature}")
        return signature
