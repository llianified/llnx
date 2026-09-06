"""Konfigurasi bot: dibaca dari config.yaml, bisa dioverride via CLI."""
from __future__ import annotations

from dataclasses import dataclass, fields


@dataclass
class Config:
    exchange: str = "binance"
    symbol: str = "BTC/USDT"
    timeframe: str = "1m"
    sma_fast: int = 9
    sma_slow: int = 21
    starting_cash: float = 5.0
    fee_rate: float = 0.001
    min_notional: float = 5.0
    poll_interval_sec: int = 60
    state_file: str = "state.json"
    trades_file: str = "trades.csv"

    def __post_init__(self) -> None:
        if self.sma_fast >= self.sma_slow:
            raise ValueError(
                f"sma_fast ({self.sma_fast}) harus lebih kecil dari sma_slow ({self.sma_slow})"
            )
        if self.starting_cash <= 0:
            raise ValueError("starting_cash harus > 0")
        if not 0 <= self.fee_rate < 1:
            raise ValueError("fee_rate harus di rentang [0, 1)")

    @classmethod
    def from_yaml(cls, path: str) -> "Config":
        import yaml

        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})

    def with_overrides(self, **kwargs) -> "Config":
        """Kembalikan salinan config dengan sebagian field ditimpa (abaikan None)."""
        data = {f.name: getattr(self, f.name) for f in fields(self)}
        data.update({k: v for k, v in kwargs.items() if v is not None})
        return Config(**data)
