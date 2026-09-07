"""Download real candles so a backtest means something.

Synthetic prices are smooth by construction, and every strategy looks like a
genius on them. Real data has gaps, spikes and long flat stretches -- the
things that actually decide whether a strategy survives. This pulls closed
candles straight from Binance's public API (no key, standard library only)
and writes a CSV that `llnx backtest --csv` and `llnx optimize --csv` read.
"""
from __future__ import annotations

import csv
from typing import List, Sequence

from .datafeed import BINANCE, market_symbol
from .http import get_json

MAX_PER_REQUEST = 1000          # Binance's own cap
COLUMNS = ("timestamp", "open", "high", "low", "close", "volume")


def klines_to_rows(klines: Sequence[Sequence]) -> List[list]:
    """Binance klines -> plain rows. Malformed entries are dropped."""
    rows = []
    for k in klines:
        if not k or len(k) < 6:
            continue
        rows.append([int(k[0]), float(k[1]), float(k[2]), float(k[3]),
                     float(k[4]), float(k[5])])
    return rows


def fetch_klines(symbol: str, timeframe: str, count: int,
                 get=get_json, log=print) -> List[list]:
    """The last `count` closed candles, oldest first.

    Binance hands out 1000 at a time, so longer histories are walked backwards
    a page at a time.
    """
    market = market_symbol(symbol)
    rows: List[list] = []
    end = None
    while len(rows) < count:
        limit = min(MAX_PER_REQUEST, count - len(rows) + 1)
        url = f"{BINANCE}/klines?symbol={market}&interval={timeframe}&limit={limit}"
        if end is not None:
            url += f"&endTime={end}"
        page = klines_to_rows(get(url))
        if not page:
            break
        rows = page + rows
        end = page[0][0] - 1        # keep walking back from the oldest candle
        log(f"[fetch] {len(rows)} candles...")
        if len(page) < limit:       # the exchange ran out of history
            break
    rows = rows[-count:]
    return rows[:-1] if rows else rows      # drop the candle still forming


def write_csv(path: str, rows: Sequence[Sequence]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(COLUMNS)
        writer.writerows(rows)
