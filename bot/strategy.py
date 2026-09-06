"""Strategi SMA crossover.

Sinyal:
  BUY  -> saat SMA cepat memotong NAIK melewati SMA lambat (golden cross)
  SELL -> saat SMA cepat memotong TURUN melewati SMA lambat (death cross)
  HOLD -> tidak ada persilangan
"""
from __future__ import annotations

from typing import Sequence


def sma(values: Sequence[float], period: int) -> float:
    """Rata-rata sederhana dari `period` nilai terakhir."""
    if period <= 0:
        raise ValueError("period harus > 0")
    if len(values) < period:
        raise ValueError(f"butuh minimal {period} data, dapat {len(values)}")
    window = values[-period:]
    return sum(window) / period


class SmaCrossStrategy:
    def __init__(self, fast: int, slow: int) -> None:
        if fast >= slow:
            raise ValueError("fast harus < slow")
        self.fast = fast
        self.slow = slow

    @property
    def warmup(self) -> int:
        """Jumlah candle minimum sebelum sinyal bisa dihitung."""
        return self.slow + 1

    def signal(self, closes: Sequence[float]) -> str:
        """Hitung sinyal dari deret harga penutupan (candle yang sudah closed)."""
        if len(closes) < self.warmup:
            return "HOLD"

        prev_fast = sma(closes[:-1], self.fast)
        prev_slow = sma(closes[:-1], self.slow)
        curr_fast = sma(closes, self.fast)
        curr_slow = sma(closes, self.slow)

        crossed_up = prev_fast <= prev_slow and curr_fast > curr_slow
        crossed_down = prev_fast >= prev_slow and curr_fast < curr_slow

        if crossed_up:
            return "BUY"
        if crossed_down:
            return "SELL"
        return "HOLD"
