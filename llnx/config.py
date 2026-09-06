"""llnx configuration: loaded from config.yaml, overridable from the CLI."""
from __future__ import annotations

from dataclasses import dataclass, fields


MODES = ("paper", "sandbox", "live")


def _parse_scalar(raw: str):
    """Turn a YAML scalar into a Python value (str/int/float/bool)."""
    text = raw.strip()
    if text[:1] in ("'", '"') and text[:1] == text[-1:] and len(text) >= 2:
        return text[1:-1]
    low = text.lower()
    if low in ("true", "yes", "on"):
        return True
    if low in ("false", "no", "off"):
        return False
    if low in ("null", "none", "~", ""):
        return ""
    try:
        return int(text)
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        return text


def parse_simple_yaml(text: str) -> dict:
    """Read the flat `key: value` config this project uses.

    Enough for config.yaml, so PyYAML stays optional -- handy on Termux where
    building wheels is slow. PyYAML is used instead when it is installed.
    """
    data = {}
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#") or line[:1].isspace():
            continue
        key, sep, rest = line.partition(":")
        if not sep:
            continue
        value, _, _ = rest.partition(" #")   # strip trailing comment
        data[key.strip()] = _parse_scalar(value)
    return data


@dataclass
class Config:
    # general
    exchange: str = "binance"
    chain: str = "solana"          # solana | ethereum | bsc | base | arbitrum | polygon
    token_address: str = ""        # set = DEX paper mode: track this token on `chain`
    solana_mint: str = ""          # old alias for token_address (solana chain)
    safety_check: bool = True      # scan for honeypot/authority before going live
    jupiter_slippage_bps: int = 100  # 100 = 1% (real Solana swaps)
    symbol: str = "BTC/USDT"
    timeframe: str = "1m"
    strategy: str = "sma"          # sma | rsi | grid
    starting_cash: float = 5.0
    fee_rate: float = 0.001
    min_notional: float = 5.0
    poll_interval_sec: int = 60

    # SMA strategy
    sma_fast: int = 9
    sma_slow: int = 21

    # RSI strategy
    rsi_period: int = 14
    rsi_oversold: float = 30.0
    rsi_overbought: float = 70.0

    # Grid/DCA strategy
    grid_step_pct: float = 0.02
    grid_take_profit_pct: float = 0.03
    grid_max_steps: int = 5

    # global risk management (0 = off)
    stop_loss_pct: float = 0.0
    take_profit_pct: float = 0.0

    # ── auto-execution ──────────────────────────────────────────
    # paper   = simulated orders against a virtual balance
    # sandbox = real order flow on the exchange testnet / a Jupiter dry run
    # live    = real orders with real money
    # empty = derive it from the older live_real/live_sandbox pair
    mode: str = ""
    auto_execute: bool = True       # False = print the signal, send nothing

    # guardrails, applied to every order (0 = off)
    max_daily_loss_pct: float = 0.10    # stop buying after -10% on the day
    max_trades_per_day: int = 20
    cooldown_sec: int = 0               # min seconds between orders
    max_order_pct: float = 0.0          # cap one order at X% of equity
    max_consecutive_failures: int = 3   # stand down after N failures in a row
    kill_switch_file: str = "STOP"      # `touch STOP` stops the bot

    # telegram notifications (leave empty to disable; env vars are safer)
    telegram_token: str = ""
    telegram_chat_id: str = ""

    # real-money mode (off and sandboxed by default)
    live_real: bool = False
    live_sandbox: bool = True

    # output files
    state_file: str = "state.json"
    trades_file: str = "trades.csv"
    orders_file: str = "orders.jsonl"   # every order attempt, filled or not

    def __post_init__(self) -> None:
        if self.sma_fast >= self.sma_slow:
            raise ValueError(
                f"sma_fast ({self.sma_fast}) must be < sma_slow ({self.sma_slow})")
        if self.starting_cash <= 0:
            raise ValueError("starting_cash must be > 0")
        if not 0 <= self.fee_rate < 1:
            raise ValueError("fee_rate must be within [0, 1)")
        if self.strategy.lower() not in ("sma", "rsi", "grid"):
            raise ValueError(f"unknown strategy '{self.strategy}'")
        if self.solana_mint and not self.token_address:
            self.token_address = self.solana_mint  # backwards compatibility

        mode = (self.mode or "").lower()
        if not mode:
            # older configs said live_real/live_sandbox instead of mode
            mode = (("sandbox" if self.live_sandbox else "live") if self.live_real
                    else "paper")
        elif mode not in MODES:
            raise ValueError(f"unknown mode '{self.mode}'. Options: {', '.join(MODES)}")
        # mode is the single source of truth; the old pair follows it
        self.mode = mode
        self.live_real = mode != "paper"
        self.live_sandbox = mode == "sandbox"
        if not 0 <= self.max_daily_loss_pct < 1:
            raise ValueError("max_daily_loss_pct must be within [0, 1)")
        if not 0 <= self.max_order_pct <= 1:
            raise ValueError("max_order_pct must be within [0, 1]")

    @classmethod
    def from_yaml(cls, path: str) -> "Config":
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        try:
            import yaml
        except ImportError:
            data = parse_simple_yaml(text)
        else:
            data = yaml.safe_load(text) or {}
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})

    def with_overrides(self, **kwargs) -> "Config":
        data = {f.name: getattr(self, f.name) for f in fields(self)}
        data.update({k: v for k, v in kwargs.items() if v is not None})
        return Config(**data)
