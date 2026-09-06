from bot.scan import parse_trending


def test_parse_trending_extracts_address_and_volume():
    data = {"data": [
        {"id": "solana_POOL1",
         "attributes": {"name": "BONK / SOL", "base_token_price_usd": "0.00001",
                        "volume_usd": {"h24": "12345.6"}},
         "relationships": {"base_token": {"data": {"id": "solana_MINTBONK"}}}},
    ]}
    cands = parse_trending(data, "solana")
    assert len(cands) == 1
    c = cands[0]
    assert c.address == "MINTBONK"
    assert c.volume_usd == 12345.6
    assert c.name == "BONK / SOL"


def test_parse_trending_handles_empty():
    assert parse_trending({}, "bsc") == []
