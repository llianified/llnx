"""Live price feeds for centralised exchanges.

`BinanceFeed` talks to Binance's public REST API through the standard library,
so paper trading needs no third-party packages at all. `CcxtDataFeed` covers
every other exchange and is only imported when ccxt is installed.

Both feeds read public market data -- no API key, no account.
"""
from __future__ import annotations

from typing import List

from .http import get_json

BINANCE = "https://api.binance.com/api/v3"


def market_symbol(symbol: str) -> str:
    """'BTC/USDT' -> 'BTCUSDT' (Binance market notation)."""
    return symbol.replace("/", "").replace("-", "").upper()


def closes_from_klines(klines: list) -> List[float]:
    """Close price of each Binance kline ([openTime, o, h, l, c, ...])."""
    return [float(k[4]) for k in klines if k and len(k) >= 5]


class BinanceFeed:
    """Public Binance data over plain HTTPS (no ccxt needed)."""

    def __init__(self, symbol: str, timeframe: str) -> None:
        self.symbol = symbol
        self.market = market_symbol(symbol)
        self.timeframe = timeframe

    def fetch_closes(self, limit: int) -> List[float]:
        """Closing price of the last `limit` finished candles.

        The most recent candle is still forming, so it is dropped and signals
        only ever see closed candles.
        """
        url = (f"{BINANCE}/klines?symbol={self.market}"
               f"&interval={self.timeframe}&limit={limit + 1}")
        klines = get_json(url)
        return closes_from_klines(klines[:-1])

    def fetch_price(self) -> float:
        """Last traded price, used as the simulated fill price."""
        data = get_json(f"{BINANCE}/ticker/price?symbol={self.market}")
        return float(data["price"])


class CcxtDataFeed:
    """Any exchange ccxt supports. Requires: pip install ccxt."""

    def __init__(self, exchange: str, symbol: str, timeframe: str) -> None:
        import ccxt  # imported here so backtests and tests never need ccxt

        if not hasattr(ccxt, exchange):
            raise ValueError(f"ccxt does not know the exchange '{exchange}'")
        self.symbol = symbol
        self.timeframe = timeframe
        self.exchange = getattr(ccxt, exchange)({"enableRateLimit": True})

    def fetch_closes(self, limit: int) -> List[float]:
        ohlcv = self.exchange.fetch_ohlcv(self.symbol, self.timeframe, limit=limit + 1)
        return [c[4] for c in ohlcv[:-1]]  # index 4 = close, drop the open candle

    def fetch_price(self) -> float:
        ticker = self.exchange.fetch_ticker(self.symbol)
        return float(ticker["last"])
