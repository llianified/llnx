"""Pemilih sumber data: DEX multi-chain (bila ada token_address) atau CEX ccxt."""
from __future__ import annotations

from .config import Config


def build_feed(cfg: Config):
    """Kembalikan (feed, symbol_label)."""
    if cfg.token_address:
        from .dexfeed import DexFeed
        feed = DexFeed(cfg.chain, cfg.token_address, cfg.timeframe)
        try:
            feed.connect()
        except Exception:
            pass
        return feed, feed.symbol
    from .datafeed import CcxtDataFeed
    return CcxtDataFeed(cfg.exchange, cfg.symbol, cfg.timeframe), cfg.symbol
