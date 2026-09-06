"""Backtest: run any strategy over a historical or synthetic price series."""
from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import List, Sequence

from .broker import PaperBroker
from .config import Config
from .engine import TradingEngine
from .risk import RiskManager
from .strategies import build_strategy


@dataclass
class BacktestReport:
    strategy: str
    starting_cash: float
    final_equity: float
    n_trades: int
    total_fees: float
    return_pct: float
    buy_hold_pct: float


def run_backtest(closes: Sequence[float], cfg: Config) -> BacktestReport:
    strategy = build_strategy(cfg.strategy, cfg)
    broker = PaperBroker(fee_rate=cfg.fee_rate, min_notional=0.0,
                         cash=cfg.starting_cash)
    risk = RiskManager(cfg.stop_loss_pct, cfg.take_profit_pct)
    engine = TradingEngine(strategy, broker, cfg.starting_cash, risk=risk,
                           symbol=cfg.symbol)

    warmup = strategy.warmup
    for i in range(warmup, len(closes)):
        engine.step(closes[:i], closes[i])

    final_price = closes[-1]
    final_equity = broker.equity(final_price)
    return BacktestReport(
        strategy=strategy.describe(),
        starting_cash=cfg.starting_cash,
        final_equity=final_equity,
        n_trades=len(broker.trades),
        total_fees=sum(t.fee for t in broker.trades),
        return_pct=(final_equity / cfg.starting_cash - 1) * 100,
        buy_hold_pct=(final_price / closes[0] - 1) * 100,
    )


def synthetic_prices(n: int = 500, start: float = 100.0, seed: int = 42) -> List[float]:
    """Synthetic prices (trend + wave + noise) for offline demos."""
    rng = random.Random(seed)
    out, price = [], start
    for i in range(n):
        wave = math.sin(i / 20.0) * 0.01
        drift = 0.0005
        noise = rng.uniform(-0.008, 0.008)
        price *= (1 + wave + drift + noise)
        out.append(round(price, 2))
    return out
