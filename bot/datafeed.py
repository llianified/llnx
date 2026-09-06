"""Sumber data harga live via ccxt (data publik, TIDAK butuh API key).

Dipakai hanya di mode paper LIVE. Mode backtest/test tidak mengimpor ini.
"""
from __future__ import annotations

from typing import List


class CcxtDataFeed:
    def __init__(self, exchange: str, symbol: str, timeframe: str) -> None:
        import ccxt  # import lokal supaya backtest/test tak butuh ccxt

        if not hasattr(ccxt, exchange):
            raise ValueError(f"exchange '{exchange}' tidak dikenal ccxt")
        self.symbol = symbol
        self.timeframe = timeframe
        self.exchange = getattr(ccxt, exchange)({"enableRateLimit": True})

    def fetch_closes(self, limit: int) -> List[float]:
        """Ambil harga penutupan `limit` candle terakhir.

        Candle terakhir yang dikembalikan ccxt biasanya masih berjalan (belum
        closed), jadi kita buang agar sinyal dihitung dari candle final saja.
        """
        ohlcv = self.exchange.fetch_ohlcv(self.symbol, self.timeframe, limit=limit + 1)
        closed = ohlcv[:-1]
        return [c[4] for c in closed]  # index 4 = close

    def fetch_price(self) -> float:
        """Harga terakhir (last trade) sebagai harga eksekusi simulasi."""
        ticker = self.exchange.fetch_ticker(self.symbol)
        return float(ticker["last"])
