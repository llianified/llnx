"""Pemilih sumber data: Solana (bila ada mint) atau CEX via ccxt."""
from __future__ import annotations

from .config import Config


def build_feed(cfg: Config):
    """Kembalikan (feed, symbol_label). Solana bila cfg.solana_mint diisi."""
    if cfg.solana_mint:
        from .solana_feed import SolanaDataFeed
        feed = SolanaDataFeed(cfg.solana_mint, cfg.timeframe)
        try:
            feed.connect()
        except Exception:
            pass  # biar error muncul saat tick pertama, bukan bikin start gagal total
        return feed, feed.symbol
    from .datafeed import CcxtDataFeed
    return CcxtDataFeed(cfg.exchange, cfg.symbol, cfg.timeframe), cfg.symbol
