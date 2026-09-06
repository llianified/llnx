"""Feed selection and the dependency-free Binance feed."""
import pytest

from llnx.config import Config
from llnx.datafeed import BinanceFeed, closes_from_klines, market_symbol
from llnx.feeds import build_feed


def test_market_symbol_drops_separators():
    assert market_symbol("BTC/USDT") == "BTCUSDT"
    assert market_symbol("eth-usdt") == "ETHUSDT"


def test_closes_from_klines_takes_the_close_column():
    klines = [[1, "1", "2", "0.5", "1.5", "10"], [2, "1.5", "3", "1", "2.5", "5"]]
    assert closes_from_klines(klines) == [1.5, 2.5]


def test_binance_is_the_default_and_needs_no_extra_package():
    feed, symbol = build_feed(Config())
    assert isinstance(feed, BinanceFeed)
    assert symbol == "BTC/USDT" and feed.market == "BTCUSDT"


def test_other_exchanges_explain_they_need_ccxt(monkeypatch):
    monkeypatch.setattr("llnx.feeds.has_ccxt", lambda: False)
    with pytest.raises(RuntimeError, match="ccxt"):
        build_feed(Config(exchange="kraken"))


def test_a_token_address_switches_to_the_dex_feed():
    cfg = Config(token_address="So11111111111111111111111111111111111111112")
    feed, symbol = build_feed(cfg)          # connect() fails offline, feed still built
    assert feed.__class__.__name__ == "DexFeed"
    assert symbol.endswith("/USD")
