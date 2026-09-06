"""Solana RPC helpers: balances, token decimals and transaction confirmation.

Kept apart from the broker so the parsing can be tested without a network and
without a wallet. Everything here talks plain JSON-RPC over urllib.
"""
from __future__ import annotations

import time
from typing import Optional

from .http import post_json

LAMPORTS = 1_000_000_000
TOKEN_PROGRAM = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
CONFIRM_TIMEOUT_SEC = 90
CONFIRM_POLL_SEC = 2.0
CONFIRMED = ("confirmed", "finalized")


class RpcError(RuntimeError):
    pass


def rpc(url: str, method: str, params: list, timeout: int = 20):
    """One JSON-RPC call. Raises RpcError when the node reports one."""
    body = post_json(url, {"jsonrpc": "2.0", "id": 1, "method": method,
                           "params": params}, timeout=timeout)
    if "error" in body:
        raise RpcError(f"{method}: {body['error']}")
    return body.get("result")


# ── pure parsing helpers ─────────────────────────────────────────
def sum_token_accounts(result: dict) -> tuple:
    """(uiAmount, raw) totals over a getTokenAccountsByOwner reply.

    The raw integer matters: selling "everything" has to spend exactly the
    number of base units the chain holds, and the float can round above it.
    """
    total, raw = 0.0, 0
    for acc in (result or {}).get("value") or []:
        info = (((acc.get("account") or {}).get("data") or {})
                .get("parsed") or {}).get("info") or {}
        amount = (info.get("tokenAmount") or {})
        if amount.get("uiAmount"):
            total += float(amount["uiAmount"])
        if amount.get("amount"):
            raw += int(amount["amount"])
    return total, raw


def signature_state(result: dict) -> tuple:
    """(status, error) for the first signature in a getSignatureStatuses reply.

    status is one of: "pending" (the node has not seen it yet), "processed",
    "confirmed", "finalized".
    """
    values = (result or {}).get("value") or []
    entry = values[0] if values else None
    if not entry:
        return "pending", None
    return (entry.get("confirmationStatus") or "processed"), entry.get("err")


# ── calls ────────────────────────────────────────────────────────
def sol_balance(url: str, pubkey: str) -> float:
    result = rpc(url, "getBalance", [pubkey])
    return float((result or {}).get("value") or 0) / LAMPORTS


def token_balance(url: str, owner: str, mint: str) -> tuple:
    """(uiAmount, raw base units) of `mint` held by `owner`."""
    result = rpc(url, "getTokenAccountsByOwner",
                 [owner, {"mint": mint}, {"encoding": "jsonParsed"}])
    return sum_token_accounts(result)


def token_decimals(url: str, mint: str) -> Optional[int]:
    try:
        result = rpc(url, "getTokenSupply", [mint])
    except Exception:
        return None
    dec = ((result or {}).get("value") or {}).get("decimals")
    return int(dec) if dec is not None else None


def confirm_signature(url: str, signature: str, *, timeout: int = CONFIRM_TIMEOUT_SEC,
                      poll: float = CONFIRM_POLL_SEC, sleep=time.sleep) -> str:
    """Wait until the transaction is confirmed on chain.

    A swap that was sent is not a swap that happened -- it can still be dropped
    or fail on chain. Nothing is booked until this returns.
    """
    deadline = time.time() + timeout
    while True:
        result = rpc(url, "getSignatureStatuses", [[signature],
                                                   {"searchTransactionHistory": True}])
        status, err = signature_state(result)
        if err:
            raise RpcError(f"the swap failed on chain: {err} (sig {signature})")
        if status in CONFIRMED:
            return status
        if time.time() >= deadline:
            raise RpcError(
                f"the swap was not confirmed within {timeout}s (sig {signature}). "
                "Check it on a block explorer before trading again.")
        sleep(poll)
