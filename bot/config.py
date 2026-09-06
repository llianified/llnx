"""Konfigurasi bot: dibaca dari config.yaml, bisa dioverride via CLI."""
from __future__ import annotations

from dataclasses import dataclass, fields


@dataclass
class Config:
    # umum
    exchange: str = "binance"
    chain: str = "solana"          # solana | ethereum | bsc | base | arbitrum | polygon
    token_address: str = ""        # isi = mode DEX (paper): pantau token ini di `chain`
    solana_mint: str = ""          # alias lama utk token_address (chain solana)
    safety_check: bool = True      # cek honeypot/authority sebelum live
    jupiter_slippage_bps: int = 100  # 100 = 1% (real swap Solana)
    symbol: str = "BTC/USDT"
    timeframe: str = "1m"
    strategy: str = "sma"          # sma | rsi | grid
    starting_cash: float = 5.0
    fee_rate: float = 0.001
    min_notional: float = 5.0
    poll_interval_sec: int = 60

    # strategi SMA
    sma_fast: int = 9
    sma_slow: int = 21

    # strategi RSI
    rsi_period: int = 14
    rsi_oversold: float = 30.0
    rsi_overbought: float = 70.0

    # strategi Grid/DCA
    grid_step_pct: float = 0.02
    grid_take_profit_pct: float = 0.03
    grid_max_steps: int = 5

    # manajemen risiko global (0 = nonaktif)
    stop_loss_pct: float = 0.0
    take_profit_pct: float = 0.0

    # notifikasi telegram (kosongkan untuk mematikan; lebih aman lewat env var)
    telegram_token: str = ""
    telegram_chat_id: str = ""

    # mode uang real (default OFF & sandbox)
    live_real: bool = False
    live_sandbox: bool = True

    # file output
    state_file: str = "state.json"
    trades_file: str = "trades.csv"

    def __post_init__(self) -> None:
        if self.sma_fast >= self.sma_slow:
            raise ValueError(
                f"sma_fast ({self.sma_fast}) harus < sma_slow ({self.sma_slow})")
        if self.starting_cash <= 0:
            raise ValueError("starting_cash harus > 0")
        if not 0 <= self.fee_rate < 1:
            raise ValueError("fee_rate harus di rentang [0, 1)")
        if self.strategy.lower() not in ("sma", "rsi", "grid"):
            raise ValueError(f"strategy '{self.strategy}' tidak dikenal")
        if self.solana_mint and not self.token_address:
            self.token_address = self.solana_mint  # kompatibilitas mundur

    @classmethod
    def from_yaml(cls, path: str) -> "Config":
        import yaml
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})

    def with_overrides(self, **kwargs) -> "Config":
        data = {f.name: getattr(self, f.name) for f in fields(self)}
        data.update({k: v for k, v in kwargs.items() if v is not None})
        return Config(**data)
