"""Test logika feed Solana (fungsi murni, tanpa jaringan)."""
import pytest

from bot.config import Config
from bot.feeds import build_feed
from bot.solana_feed import (SolanaDataFeed, closes_from_ohlcv, gt_timeframe,
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
    # GeckoTerminal: [ts, o, h, l, c, v], urutan terbaru dulu
    ohlcv = [[300, 1, 1, 1, 30, 9], [100, 1, 1, 1, 10, 9], [200, 1, 1, 1, 20, 9]]
    assert closes_from_ohlcv(ohlcv) == [10.0, 20.0, 30.0]


def test_gt_timeframe_mapping():
    assert gt_timeframe("1m") == ("minute", 1)
    assert gt_timeframe("4h") == ("hour", 4)
    assert gt_timeframe("ngawur") == ("minute", 1)  # default aman


def test_feed_init_is_offline():
    # __init__ tidak boleh menyentuh jaringan
    f = SolanaDataFeed("So11111111111111111111111111111111111111112", "1m")
    assert f.pair_address is None
    assert f.symbol.endswith("/USD")


def test_build_feed_picks_solana_when_mint_set():
    cfg = Config(solana_mint="So11111111111111111111111111111111111111112")
    feed, symbol = build_feed(cfg)  # connect() gagal diam2 (tanpa net) -> tetap objek Solana
    assert isinstance(feed, SolanaDataFeed)
    assert symbol.endswith("/USD")
