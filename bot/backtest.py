"""Backtest: jalankan strategi ke deret harga historis/sintetis."""
from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import List, Sequence

from .broker import PaperBroker
from .engine import TradingEngine
from .strategy import SmaCrossStrategy


@dataclass
class BacktestReport:
    starting_cash: float
    final_equity: float
    n_trades: int
    total_fees: float
    return_pct: float
    buy_hold_pct: float


def run_backtest(closes: Sequence[float], *, fast: int, slow: int,
                 starting_cash: float, fee_rate: float,
                 min_notional: float = 0.0) -> BacktestReport:
    strategy = SmaCrossStrategy(fast, slow)
    broker = PaperBroker(fee_rate=fee_rate, min_notional=min_notional,
                         cash=starting_cash)
    engine = TradingEngine(strategy, broker)

    warmup = strategy.warmup
    for i in range(warmup, len(closes)):
        window = closes[:i]          # candle yang sudah closed
        price = closes[i]            # harga eksekusi "sekarang"
        engine.step(window, price)

    final_price = closes[-1]
    final_equity = broker.equity(final_price)
    total_fees = sum(t.fee for t in broker.trades)
    return_pct = (final_equity / starting_cash - 1) * 100
    buy_hold_pct = (final_price / closes[0] - 1) * 100
    return BacktestReport(
        starting_cash=starting_cash,
        final_equity=final_equity,
        n_trades=len(broker.trades),
        total_fees=total_fees,
        return_pct=return_pct,
        buy_hold_pct=buy_hold_pct,
    )


def synthetic_prices(n: int = 500, start: float = 100.0, seed: int = 42) -> List[float]:
    """Bikin deret harga sintetis (tren + gelombang + noise) untuk demo offline."""
    rng = random.Random(seed)
    out = []
    price = start
    for i in range(n):
        wave = math.sin(i / 20.0) * 0.01      # siklus naik-turun
        drift = 0.0005                          # tren naik pelan
        noise = rng.uniform(-0.008, 0.008)      # noise acak
        price *= (1 + wave + drift + noise)
        out.append(round(price, 2))
    return out
