"""Scan trending tokens per chain, via GeckoTerminal trending pools."""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

from .chains import get_chain
from .http import get_json

TRENDING = "https://api.geckoterminal.com/api/v2/networks/{net}/trending_pools?page=1"


@dataclass
class Candidate:
    name: str
    address: str        # token address (mint or contract)
    price_usd: float
    volume_usd: float
    pool: str
    chain: str


def parse_trending(data: dict, chain_id: str) -> List[Candidate]:
    out: List[Candidate] = []
    for item in (data.get("data") or []):
        attr = item.get("attributes") or {}
        rel = item.get("relationships") or {}
        tok_id = (((rel.get("base_token") or {}).get("data") or {}).get("id") or "")
        address = tok_id.split("_", 1)[1] if "_" in tok_id else tok_id
        pool = (item.get("id") or "").split("_", 1)[-1] or attr.get("address", "")
        try:
            price = float(attr.get("base_token_price_usd") or 0)
        except (TypeError, ValueError):
            price = 0.0
        try:
            volume = float((attr.get("volume_usd") or {}).get("h24") or 0)
        except (TypeError, ValueError):
            volume = 0.0
        if address:
            out.append(Candidate(name=attr.get("name", "?"), address=address,
                                 price_usd=price, volume_usd=volume, pool=pool,
                                 chain=chain_id))
    return out


def scan_trending(chain_id: str, limit: int = 10) -> List[Candidate]:
    chain = get_chain(chain_id)
    data = get_json(TRENDING.format(net=chain.gecko), timeout=20)
    return parse_trending(data, chain_id)[:limit]
