"""Token safety checks: RugCheck for Solana, GoPlus for EVM.

Looks for honeypots, mint/freeze authority, buy/sell tax, locked LP and so
on. Run it before buying anything for real. The parsers are pure functions,
so they can be tested without the network.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple

from .chains import get_chain
from .http import get_json

RUGCHECK = "https://api.rugcheck.xyz/v1/tokens/{mint}/report"
GOPLUS = "https://api.gopluslabs.io/api/v1/token_security/{cid}?contract_addresses={addr}"

_RANK = {"unknown": 0, "ok": 1, "warn": 2, "danger": 3}


@dataclass
class SafetyReport:
    chain: str
    address: str
    level: str = "unknown"                 # ok | warn | danger | unknown
    flags: List[Tuple[str, str]] = field(default_factory=list)  # (level, message)
    source: str = ""

    @property
    def blocking(self) -> bool:
        return self.level == "danger"

    def add(self, level: str, msg: str) -> None:
        self.flags.append((level, msg))
        if _RANK.get(level, 0) > _RANK.get(self.level, 0):
            self.level = level

    def summary(self) -> str:
        word = {"ok": "safe", "warn": "careful", "danger": "DANGER",
                "unknown": "unknown"}[self.level]
        return f"{word} ({len(self.flags)} notes)"


def _pct(v) -> float:
    try:
        return float(v) * 100 if abs(float(v)) <= 1 else float(v)
    except (TypeError, ValueError):
        return 0.0


# ── pure parsers ────────────────────────────────────────────────
def parse_rugcheck(data: dict, address: str) -> SafetyReport:
    r = SafetyReport(chain="solana", address=address, source="rugcheck")
    if data.get("mintAuthority"):
        r.add("warn", "mint authority is active - supply can be increased")
    if data.get("freezeAuthority"):
        r.add("danger", "freeze authority is active - your tokens can be frozen")
    for risk in (data.get("risks") or []):
        lvl = "danger" if str(risk.get("level", "")).lower() in ("danger", "high") else "warn"
        name = risk.get("name") or "risk"
        r.add(lvl, f"{name}: {risk.get('description', '')}".strip(": "))
    if not r.flags:
        r.add("ok", "no obvious flags from rugcheck")
    return r


def parse_goplus(data: dict, address: str) -> SafetyReport:
    r = SafetyReport(chain="evm", address=address, source="goplus")
    result = data.get("result") or {}
    info = result.get(address.lower()) or (next(iter(result.values()), {}) if result else {})
    if not info:
        r.level = "unknown"
        r.add("unknown", "goplus returned nothing")
        return r
    if str(info.get("is_honeypot")) == "1":
        r.add("danger", "HONEYPOT - the token cannot be sold")
    if str(info.get("cannot_sell_all")) == "1":
        r.add("danger", "cannot sell the full position (cannot_sell_all)")
    buy_tax, sell_tax = _pct(info.get("buy_tax")), _pct(info.get("sell_tax"))
    if sell_tax >= 20 or buy_tax >= 20:
        r.add("danger", f"extreme tax (buy {buy_tax:g}% / sell {sell_tax:g}%)")
    elif sell_tax > 5 or buy_tax > 5:
        r.add("warn", f"high tax (buy {buy_tax:g}% / sell {sell_tax:g}%)")
    if str(info.get("is_mintable")) == "1":
        r.add("warn", "the contract can mint new tokens")
    if str(info.get("can_take_back_ownership")) == "1":
        r.add("warn", "the owner can take ownership back")
    if str(info.get("hidden_owner")) == "1":
        r.add("warn", "there is a hidden owner")
    if str(info.get("is_open_source")) == "0":
        r.add("warn", "the contract is not open-source or unverified")
    holders = info.get("lp_holders") or []
    locked = any(str(h.get("is_locked")) == "1" for h in holders)
    if holders and not locked:
        r.add("warn", "liquidity (LP) does not look locked")
    elif locked:
        r.add("ok", "part of the LP is locked")
    if not r.flags:
        r.add("ok", "no obvious flags from goplus")
    return r


# ── network ─────────────────────────────────────────────────────
def check_token(chain_id: str, address: str) -> SafetyReport:
    chain = get_chain(chain_id)
    try:
        if chain.kind == "solana":
            data = get_json(RUGCHECK.format(mint=address), timeout=20)
            return parse_rugcheck(data, address)
        data = get_json(GOPLUS.format(cid=chain.goplus, addr=address), timeout=20)
        return parse_goplus(data, address)
    except Exception as e:
        rep = SafetyReport(chain=chain.id, address=address)
        rep.add("unknown", f"check failed: {e!r}")
        return rep
