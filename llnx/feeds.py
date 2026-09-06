"""Pick a price source: DEX token (when token_address is set) or an exchange."""
from __future__ import annotations

from .config import Config


def has_ccxt() -> bool:
    try:
        import ccxt  # noqa: F401
    except ImportError:
        return False
    return True


def build_feed(cfg: Config):
    """Return (feed, symbol_label) for the current config."""
    if cfg.token_address:
        from .dexfeed import DexFeed
        feed = DexFeed(cfg.chain, cfg.token_address, cfg.timeframe)
        try:
            feed.connect()
        except Exception:
            pass
        return feed, feed.symbol

    if cfg.exchange.lower() == "binance":
        from .datafeed import BinanceFeed        # stdlib only
        return BinanceFeed(cfg.symbol, cfg.timeframe), cfg.symbol

    if not has_ccxt():
        raise RuntimeError(
            f"exchange '{cfg.exchange}' needs ccxt (pip install ccxt). "
            "Set exchange: binance in config.yaml to stay dependency-free.")
    from .datafeed import CcxtDataFeed
    return CcxtDataFeed(cfg.exchange, cfg.symbol, cfg.timeframe), cfg.symbol
