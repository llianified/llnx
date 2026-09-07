"""Backtest: run any strategy over a historical or synthetic price series.

The return alone says very little. A strategy that made 40% by sitting through
a 60% drawdown is not the same animal as one that made 30% while never being
more than 8% underwater, and on a small account the fee bill decides more than
the entries do. So the report carries the numbers that separate them: drawdown,
win rate, profit factor, how much of the time the money was actually at risk,
and what the fees cost.
"""
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
    max_drawdown_pct: float = 0.0    # worst peak-to-trough fall in equity
    win_rate_pct: float = 0.0        # share of closed round trips in profit
    profit_factor: float = 0.0       # gross profit / gross loss (inf = no losses)
    avg_trade_pct: float = 0.0       # average round trip, as % of starting cash
    exposure_pct: float = 0.0        # share of candles holding a position
    n_round_trips: int = 0

    @property
    def fees_pct(self) -> float:
        return self.total_fees / self.starting_cash * 100 if self.starting_cash else 0.0

    @property
    def score(self) -> float:
        """Return per unit of pain -- what to rank a parameter sweep by.

        A 30% gain through a 10% drawdown scores better than a 40% gain
        through a 50% one, which is the ordering an account actually lives by.
        """
        return self.return_pct / (1.0 + self.max_drawdown_pct)


# ── pure helpers ─────────────────────────────────────────────────
def max_drawdown(curve: Sequence[float]) -> float:
    """Worst peak-to-trough fall of an equity curve, in percent."""
    peak, worst = float("-inf"), 0.0
    for value in curve:
        peak = max(peak, value)
        if peak > 0:
            worst = max(worst, (peak - value) / peak)
    return worst * 100


def round_trips(trades: Sequence) -> List[float]:
    """Realised profit of every buy→sell cycle, in quote currency.

    Partial sells (the grid does them) close a matching share of the cost
    basis, so averaging down and selling in pieces still adds up.
    """
    position = cost = 0.0
    out: List[float] = []
    for t in trades:
        if t.side == "BUY":
            position += t.amount
            cost += t.amount * t.price + t.fee
        else:
            if position <= 0:
                continue
            sold = min(t.amount, position)
            basis = cost * (sold / position)
            out.append(sold * t.price - t.fee - basis)
            cost -= basis
            position -= sold
    return out


def run_backtest(closes: Sequence[float], cfg: Config) -> BacktestReport:
    strategy = build_strategy(cfg.strategy, cfg)
    broker = PaperBroker(fee_rate=cfg.fee_rate, min_notional=0.0,
                         cash=cfg.starting_cash)
    risk = RiskManager(cfg.stop_loss_pct, cfg.take_profit_pct,
                       cfg.trailing_stop_pct)
    engine = TradingEngine(strategy, broker, cfg.starting_cash, risk=risk,
                           symbol=cfg.symbol)

    curve, held = [], 0
    warmup = strategy.warmup
    for i in range(warmup, len(closes)):
        result = engine.step(closes[:i], closes[i])
        curve.append(result.equity)
        if broker.position > 0:
            held += 1

    final_price = closes[-1] if closes else 0.0
    final_equity = broker.equity(final_price)
    trips = round_trips(broker.trades)
    wins = [t for t in trips if t > 0]
    losses = [t for t in trips if t < 0]
    gross_loss = abs(sum(losses))

    return BacktestReport(
        strategy=strategy.describe(),
        starting_cash=cfg.starting_cash,
        final_equity=final_equity,
        n_trades=len(broker.trades),
        total_fees=sum(t.fee for t in broker.trades),
        return_pct=(final_equity / cfg.starting_cash - 1) * 100,
        buy_hold_pct=(final_price / closes[0] - 1) * 100 if closes else 0.0,
        max_drawdown_pct=max_drawdown(curve),
        win_rate_pct=len(wins) / len(trips) * 100 if trips else 0.0,
        profit_factor=(sum(wins) / gross_loss if gross_loss
                       else (float("inf") if wins else 0.0)),
        avg_trade_pct=(sum(trips) / len(trips) / cfg.starting_cash * 100
                       if trips else 0.0),
        exposure_pct=held / len(curve) * 100 if curve else 0.0,
        n_round_trips=len(trips),
    )


def synthetic_prices(n: int = 500, start: float = 100.0, seed: int = 42) -> List[float]:
    """Synthetic prices for offline demos: a random walk that changes its mind.

    The old version was a sine wave with noise, and any crossover strategy
    made a fortune on it -- a smooth cycle is the one thing an oscillator
    cannot lose to. This walks randomly instead, in runs: the drift flips
    between up, down and flat every so often, and volatility clusters the way
    it really does. Strategies can still win here, but they have to earn it.

    Fetch real candles (`llnx fetch`) before believing any number.
    """
    rng = random.Random(seed)
    out, price = [], start
    drift, vol, run_left = 0.0, 0.012, 0
    for _ in range(n):
        if run_left <= 0:                      # a new regime starts
            run_left = rng.randint(30, 120)
            drift = rng.choice([0.0015, 0.0006, 0.0, -0.0006, -0.0015])
            vol = rng.uniform(0.006, 0.02)
        run_left -= 1
        shock = rng.gauss(0, 1)
        price *= math.exp(drift + vol * shock - 0.5 * vol * vol)
        out.append(round(max(price, 0.01), 2))
    return out


def read_closes(path: str) -> List[float]:
    """Close prices from a CSV.

    Uses the column named `close` when the file has a header, and the last
    column otherwise -- so both `llnx fetch` output and a plain OHLCV dump
    from anywhere else work.
    """
    with open(path, encoding="utf-8") as f:
        rows = [line.strip() for line in f if line.strip()]
    if not rows:
        return []
    index = -1
    header = [c.strip().lower() for c in rows[0].split(",")]
    if any(c and not _looks_numeric(c) for c in header):
        index = header.index("close") if "close" in header else -1
        rows = rows[1:]
    return [float(r.split(",")[index]) for r in rows]


def _looks_numeric(text: str) -> bool:
    try:
        float(text)
    except ValueError:
        return False
    return True
