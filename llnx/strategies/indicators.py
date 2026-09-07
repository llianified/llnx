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


# An EMA never fully forgets, but it forgets fast: after this many periods the
# oldest weight is under 0.1%, so only the tail is read. That keeps every
# indicator O(period) instead of O(len(closes)), which is what makes a
# parameter sweep over thousands of candles finish in seconds.
EMA_TAIL = 5


def ema(values: Sequence[float], period: int) -> float:
    """Exponential moving average of the last values, seeded with an SMA."""
    if period <= 0:
        raise ValueError("period must be > 0")
    if len(values) < period:
        raise ValueError(f"need at least {period} values, got {len(values)}")
    window = values[-min(len(values), period * EMA_TAIL):]
    alpha = 2.0 / (period + 1)
    out = sum(window[:period]) / period
    for value in window[period:]:
        out += alpha * (value - out)
    return out


def avg_move(closes: Sequence[float], period: int) -> float:
    """Average absolute move per candle -- a close-only stand-in for ATR.

    The feeds only hand us closes (a DEX pool has no candles of its own), so
    the range is measured between closes instead of high to low. It scales
    with volatility the same way, which is all a volatility stop needs.
    """
    if period <= 0:
        raise ValueError("period must be > 0")
    if len(closes) < period + 1:
        return 0.0
    window = closes[-(period + 1):]
    return sum(abs(window[i] - window[i - 1])
               for i in range(1, len(window))) / period


def highest(values: Sequence[float], period: int) -> float:
    """Highest of the last `period` values."""
    return max(values[-period:])


def lowest(values: Sequence[float], period: int) -> float:
    """Lowest of the last `period` values."""
    return min(values[-period:])
