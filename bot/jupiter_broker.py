"""Solana broker on top of Jupiter swaps. The real path is experimental.

Modes:
  dry_run=True (default): fetch a real Jupiter quote to estimate slippage and
    price impact, but send nothing. The accounting is simulated, no wallet
    is needed.
  dry_run=False: send an actual swap. Needs SOLANA_PRIVATE_KEY (base58) and
    SOLANA_RPC_URL in the environment plus the 'solders' package. This path
    has not been exercised on mainnet -- start with tiny amounts.

Same interface as PaperBroker, so the engine cannot tell the difference.
"""
from __future__ import annotations

import os
from typing import Optional

from .broker import PaperBroker, Trade
from .http import get_json, post_json

USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"  # 6 decimals
QUOTE = ("https://quote-api.jup.ag/v6/quote?inputMint={i}&outputMint={o}"
         "&amount={a}&slippageBps={bps}")
SWAP = "https://quote-api.jup.ag/v6/swap"
TOKEN_META = "https://tokens.jup.ag/token/{mint}"


class JupiterBroker:
    is_live = True

    def __init__(self, token_mint: str, *, dry_run: bool = True, cash: float = 20.0,
                 fee_rate: float = 0.003, min_notional: float = 1.0,
                 slippage_bps: int = 100) -> None:
        self.token = token_mint
        self.dry_run = dry_run
        self.slippage_bps = slippage_bps
        self._paper = PaperBroker(fee_rate=fee_rate, min_notional=min_notional, cash=cash)

    # ── expose the same fields as PaperBroker ────────────────────
    @property
    def cash(self): return self._paper.cash
    @property
    def position(self): return self._paper.position
    @property
    def avg_entry(self): return self._paper.avg_entry
    @property
    def last_buy_price(self): return self._paper.last_buy_price
    @property
    def trades(self): return self._paper.trades

    def equity(self, price: float) -> float:
        return self._paper.equity(price)

    # ── slippage estimate from a Jupiter quote ───────────────────
    def _buy_impact(self, usd: float) -> float:
        try:
            amt = int(max(usd, 1) * 1_000_000)  # USDC has 6 decimals
            q = get_json(QUOTE.format(i=USDC, o=self.token, a=amt, bps=self.slippage_bps))
            return float(q.get("priceImpactPct") or 0.0)
        except Exception:
            return 0.0

    def buy(self, price: float, quote_amount: Optional[float] = None) -> Optional[Trade]:
        impact = self._buy_impact(quote_amount if quote_amount else self._paper.cash)
        eff = price * (1 + abs(impact))  # impact makes the buy more expensive
        if not self.dry_run:
            self._send_swap("buy", quote_amount if quote_amount else self._paper.cash)
        t = self._paper.buy(eff, quote_amount)
        if t:
            t.reason += " · jupiter " + ("dry-run" if self.dry_run else "LIVE")
        return t

    def sell(self, price: float, fraction: float = 1.0) -> Optional[Trade]:
        if not self.dry_run and self._paper.position > 0:
            self._send_swap("sell", self._paper.position * fraction)
        t = self._paper.sell(price, fraction)
        if t:
            t.reason += " · jupiter " + ("dry-run" if self.dry_run else "LIVE")
        return t

    # ── the real swap path (experimental) ────────────────────────
    def _send_swap(self, side: str, amount: float) -> None:
        key = os.environ.get("SOLANA_PRIVATE_KEY")
        rpc = os.environ.get("SOLANA_RPC_URL")
        if not key or not rpc:
            raise RuntimeError("SOLANA_PRIVATE_KEY / SOLANA_RPC_URL are not set")
        try:
            import base64
            from solders.keypair import Keypair
            from solders.transaction import VersionedTransaction
        except ImportError as e:
            raise RuntimeError(f"the solders package is not installed: {e}")

        kp = Keypair.from_base58_string(key)
        if side == "buy":
            in_mint, out_mint = USDC, self.token
            atomic = int(amount * 1_000_000)
        else:
            in_mint, out_mint = self.token, USDC
            dec = int((get_json(TOKEN_META.format(mint=self.token)) or {}).get("decimals", 9))
            atomic = int(amount * (10 ** dec))
        quote = get_json(QUOTE.format(i=in_mint, o=out_mint, a=atomic, bps=self.slippage_bps))
        swap = post_json(SWAP, {"quoteResponse": quote,
                                "userPublicKey": str(kp.pubkey()),
                                "wrapAndUnwrapSol": True})
        raw = base64.b64decode(swap["swapTransaction"])
        tx = VersionedTransaction.from_bytes(raw)
        signed = VersionedTransaction(tx.message, [kp])
        sig = post_json(rpc, {"jsonrpc": "2.0", "id": 1, "method": "sendTransaction",
                              "params": [base64.b64encode(bytes(signed)).decode(),
                                         {"encoding": "base64"}]})
        if "error" in sig:
            raise RuntimeError(f"sending the transaction failed: {sig['error']}")
