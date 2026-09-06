"""Sumber data harga token Solana (untuk PAPER trading) — tanpa API key.

- Harga terkini: DexScreener (per mint address, USD).
- Candle historis (buat SMA/RSI): GeckoTerminal OHLCV (USD).
Semua harga di-USD-kan biar konsisten dengan broker (saldo virtual USD).

Butuh koneksi internet saat live (bukan saat unit test / backtest offline).
Tidak butuh wallet — ini simulasi.
"""
from __future__ import annotations

import json
import urllib.request
from collections import deque
from typing import List, Optional

DEXSCREENER = "https://api.dexscreener.com/latest/dex/tokens/{mint}"
GECKOTERMINAL = ("https://api.geckoterminal.com/api/v2/networks/solana/pools/"
                 "{pool}/ohlcv/{res}?aggregate={agg}&limit={limit}&currency=usd&token=base")

_TF = {"1m": ("minute", 1), "5m": ("minute", 5), "15m": ("minute", 15),
       "1h": ("hour", 1), "4h": ("hour", 4)}


def _get_json(url: str, timeout: int = 15) -> dict:
    req = urllib.request.Request(
        url, headers={"User-Agent": "bot-trading/0.1", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


# ── fungsi murni (bisa dites tanpa jaringan) ────────────────────
def pick_pair(pairs: list) -> Optional[dict]:
    """Pilih pair Solana dengan likuiditas USD terbesar."""
    sol = [p for p in pairs if p.get("chainId") == "solana"]
    cand = sol or list(pairs)
    if not cand:
        return None
    return max(cand, key=lambda p: float((p.get("liquidity") or {}).get("usd") or 0))


def closes_from_ohlcv(ohlcv_list: list) -> List[float]:
    """Ambil harga close dari ohlcv_list GeckoTerminal ([ts,o,h,l,c,v], terbaru dulu)."""
    rows = sorted((r for r in ohlcv_list if r and len(r) >= 5), key=lambda r: r[0])
    return [float(r[4]) for r in rows]


def gt_timeframe(tf: str):
    return _TF.get(tf, ("minute", 1))


# ── feed ────────────────────────────────────────────────────────
class SolanaDataFeed:
    def __init__(self, mint: str, timeframe: str) -> None:
        if not mint:
            raise ValueError("mint address kosong")
        self.mint = mint
        self.timeframe = timeframe
        self.pair_address: Optional[str] = None
        self.symbol = f"{mint[:4]}…/USD"
        self._buf: deque = deque(maxlen=600)

    def connect(self) -> None:
        """Resolusi pair terbaik dari DexScreener (dipanggil sekali saat mulai)."""
        data = _get_json(DEXSCREENER.format(mint=self.mint))
        pair = pick_pair(data.get("pairs") or [])
        if not pair:
            raise RuntimeError(f"token {self.mint} tidak ditemukan / tanpa likuiditas")
        self.pair_address = pair.get("pairAddress")
        base = (pair.get("baseToken") or {}).get("symbol", "?")
        self.symbol = f"{base}/USD"

    def _ensure(self) -> None:
        if self.pair_address is None:
            self.connect()

    def fetch_price(self) -> float:
        self._ensure()
        data = _get_json(DEXSCREENER.format(mint=self.mint))
        pair = pick_pair(data.get("pairs") or [])
        if not pair or not pair.get("priceUsd"):
            raise RuntimeError("harga USD tidak tersedia")
        price = float(pair["priceUsd"])
        self._buf.append(price)
        return price

    def fetch_closes(self, limit: int) -> List[float]:
        self._ensure()
        try:
            res, agg = gt_timeframe(self.timeframe)
            url = GECKOTERMINAL.format(pool=self.pair_address, res=res, agg=agg,
                                       limit=limit + 1)
            data = _get_json(url)
            lst = (((data.get("data") or {}).get("attributes") or {})
                   .get("ohlcv_list") or [])
            closes = closes_from_ohlcv(lst)
            if len(closes) > 1:
                return closes[:-1]  # buang candle yang masih berjalan
        except Exception:
            pass
        # fallback: pakai harga yang sudah terkumpul dari polling
        return list(self._buf)
