from llnx.dexfeed import DexFeed, pick_pair


def test_pick_pair_filters_by_chain():
    pairs = [
        {"chainId": "bsc", "liquidity": {"usd": 90}, "pairAddress": "bsc-hi"},
        {"chainId": "solana", "liquidity": {"usd": 10}, "pairAddress": "sol-lo"},
        {"chainId": "solana", "liquidity": {"usd": 80}, "pairAddress": "sol-hi"},
    ]
    assert pick_pair(pairs, "solana")["pairAddress"] == "sol-hi"
    assert pick_pair(pairs, "bsc")["pairAddress"] == "bsc-hi"


def test_dexfeed_init_offline():
    f = DexFeed("base", "0xdeadbeef", "5m")
    assert f.pair_address is None
    assert f.chain.kind == "evm"
    assert f.symbol.endswith("/USD")
