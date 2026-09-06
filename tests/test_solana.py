"""Solana feed logic: pure functions, no network."""
import pytest

from llnx.config import Config
from llnx.feeds import build_feed
from llnx.solana_feed import (SolanaDataFeed, closes_from_ohlcv, gt_timeframe,
                             pick_pair)


def test_pick_pair_prefers_solana_high_liquidity():
    pairs = [
        {"chainId": "ethereum", "liquidity": {"usd": 999999}, "pairAddress": "eth"},
        {"chainId": "solana", "liquidity": {"usd": 1000}, "pairAddress": "lo"},
        {"chainId": "solana", "liquidity": {"usd": 50000}, "pairAddress": "hi"},
    ]
    assert pick_pair(pairs)["pairAddress"] == "hi"


def test_pick_pair_empty():
    assert pick_pair([]) is None


def test_closes_from_ohlcv_sorts_and_extracts_close():
    # GeckoTerminal: [ts, o, h, l, c, v], newest first
    ohlcv = [[300, 1, 1, 1, 30, 9], [100, 1, 1, 1, 10, 9], [200, 1, 1, 1, 20, 9]]
    assert closes_from_ohlcv(ohlcv) == [10.0, 20.0, 30.0]


def test_gt_timeframe_mapping():
    assert gt_timeframe("1m") == ("minute", 1)
    assert gt_timeframe("4h") == ("hour", 4)
    assert gt_timeframe("nonsense") == ("minute", 1)  # safe default


def test_feed_init_is_offline():
    # __init__ must not touch the network
    f = SolanaDataFeed("So11111111111111111111111111111111111111112", "1m")
    assert f.pair_address is None
    assert f.symbol.endswith("/USD")


def test_build_feed_picks_dex_when_mint_set():
    from llnx.dexfeed import DexFeed
    cfg = Config(solana_mint="So11111111111111111111111111111111111111112")
    feed, symbol = build_feed(cfg)  # connect() fails quietly offline -> still a DEX feed
    assert isinstance(feed, DexFeed)
    assert feed.chain.id == "solana"
    assert symbol.endswith("/USD")
