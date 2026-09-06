"""Compatibility shim: SolanaDataFeed is a Solana-only DexFeed. See dexfeed.py."""
from __future__ import annotations

from .chains import get_chain
from .dexfeed import DexFeed, closes_from_ohlcv, gt_timeframe
from .dexfeed import pick_pair as _pick_pair


def pick_pair(pairs, chain_slug="solana"):
    return _pick_pair(pairs, chain_slug)


class SolanaDataFeed(DexFeed):
    def __init__(self, mint: str, timeframe: str) -> None:
        super().__init__(get_chain("solana"), mint, timeframe)
        self.mint = mint


__all__ = ["SolanaDataFeed", "pick_pair", "closes_from_ohlcv", "gt_timeframe"]
