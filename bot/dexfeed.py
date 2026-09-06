"""Feed harga DEX multi-chain (paper) — DexScreener + GeckoTerminal, USD.

Berlaku untuk semua chain di registry (Solana & EVM). Tanpa wallet/API key.
"""
from __future__ import annotations

from collections import deque
from typing import List, Optional

from .chains import Chain, get_chain
from .http import get_json

DEXSCREENER = "https://api.dexscreener.com/latest/dex/tokens/{addr}"
GECKOTERMINAL = ("https://api.geckoterminal.com/api/v2/networks/{net}/pools/"
                 "{pool}/ohlcv/{res}?aggregate={agg}&limit={limit}&currency=usd&token=base")

_TF = {"1m": ("minute", 1), "5m": ("minute", 5), "15m": ("minute", 15),
       "1h": ("hour", 1), "4h": ("hour", 4)}


# ── fungsi murni (bisa dites tanpa jaringan) ────────────────────
def pick_pair(pairs: list, chain_slug: Optional[str] = None) -> Optional[dict]:
    """Pilih pair dengan likuiditas USD terbesar (opsional filter chain)."""
    cand = [p for p in pairs if p.get("chainId") == chain_slug] if chain_slug else list(pairs)
    cand = cand or list(pairs)
    if not cand:
        return None
    return max(cand, key=lambda p: float((p.get("liquidity") or {}).get("usd") or 0))


def closes_from_ohlcv(ohlcv_list: list) -> List[float]:
    """Ambil harga close dari ohlcv_list GeckoTerminal ([ts,o,h,l,c,v])."""
    rows = sorted((r for r in ohlcv_list if r and len(r) >= 5), key=lambda r: r[0])
    return [float(r[4]) for r in rows]


def gt_timeframe(tf: str):
    return _TF.get(tf, ("minute", 1))


# ── feed ────────────────────────────────────────────────────────
class DexFeed:
    def __init__(self, chain, address: str, timeframe: str) -> None:
        if not address:
            raise ValueError("token address kosong")
        self.chain: Chain = chain if isinstance(chain, Chain) else get_chain(chain)
        self.address = address
        self.timeframe = timeframe
        self.pair_address: Optional[str] = None
        self.symbol = f"{address[:4]}…/USD"
        self._buf: deque = deque(maxlen=600)

    def connect(self) -> None:
        data = get_json(DEXSCREENER.format(addr=self.address))
        pair = pick_pair(data.get("pairs") or [], self.chain.dexscreener)
        if not pair:
            raise RuntimeError(f"token {self.address} tak ditemukan di {self.chain.name}")
        self.pair_address = pair.get("pairAddress")
        base = (pair.get("baseToken") or {}).get("symbol", "?")
        self.symbol = f"{base}/USD"

    def _ensure(self) -> None:
        if self.pair_address is None:
            self.connect()

    def fetch_price(self) -> float:
        self._ensure()
        data = get_json(DEXSCREENER.format(addr=self.address))
        pair = pick_pair(data.get("pairs") or [], self.chain.dexscreener)
        if not pair or not pair.get("priceUsd"):
            raise RuntimeError("harga USD tidak tersedia")
        price = float(pair["priceUsd"])
        self._buf.append(price)
        return price

    def fetch_closes(self, limit: int) -> List[float]:
        self._ensure()
        try:
            res, agg = gt_timeframe(self.timeframe)
            url = GECKOTERMINAL.format(net=self.chain.gecko, pool=self.pair_address,
                                       res=res, agg=agg, limit=limit + 1)
            data = get_json(url)
            lst = (((data.get("data") or {}).get("attributes") or {})
                   .get("ohlcv_list") or [])
            closes = closes_from_ohlcv(lst)
            if len(closes) > 1:
                return closes[:-1]
        except Exception:
            pass
        return list(self._buf)
