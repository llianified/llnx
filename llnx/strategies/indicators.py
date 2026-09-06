"""Plain technical indicators, standard library only."""
from __future__ import annotations

from typing import Optional, Sequence


def sma(values: Sequence[float], period: int) -> float:
    if period <= 0:
        raise ValueError("period must be > 0")
    if len(values) < period:
        raise ValueError(f"need at least {period} values, got {len(values)}")
    return sum(values[-period:]) / period


def cross_signal(closes: Sequence[float], fast: int, slow: int) -> str:
    """Detect an SMA cross on the last candle.

    'BUY'  = golden cross (fast crosses ABOVE slow)
    'SELL' = death cross  (fast crosses BELOW slow)
    'HOLD' = no cross
    """
    if len(closes) < slow + 1:
        return "HOLD"
    prev_fast, prev_slow = sma(closes[:-1], fast), sma(closes[:-1], slow)
    curr_fast, curr_slow = sma(closes, fast), sma(closes, slow)
    if prev_fast <= prev_slow and curr_fast > curr_slow:
        return "BUY"
    if prev_fast >= prev_slow and curr_fast < curr_slow:
        return "SELL"
    return "HOLD"


def rsi(closes: Sequence[float], period: int) -> Optional[float]:
    """RSI (simple averages). Returns None while there is too little data."""
    if len(closes) < period + 1:
        return None
    gains = losses = 0.0
    for i in range(len(closes) - period, len(closes)):
        d = closes[i] - closes[i - 1]
        if d >= 0:
            gains += d
        else:
            losses += -d
    avg_gain, avg_loss = gains / period, losses / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - 100.0 / (1.0 + rs)
