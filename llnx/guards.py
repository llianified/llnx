"""Guardrails: the limits an auto-executing bot has to respect.

A bot that places its own orders needs a hand on the brake. These rules are
checked before every order and are pure functions of the session state, so
they are cheap to test and behave the same in paper and in live mode.

  kill switch      a file on disk stops the bot (`touch STOP`)
  daily loss       stop opening new positions after -X% on the day
  trade cap        at most N trades per day
  cooldown         wait N seconds between orders
  order cap        no single order larger than X% of equity
  failure halt     N failed orders in a row and the bot stands down

Exits are never blocked by the risk limits: once the daily loss is hit or the
trade cap is spent, the bot stops BUYING but a stop-loss can still sell. Two
things do stop everything -- the kill switch, because "stop trading" has to
mean exactly that, and a run of failed orders, because a venue that keeps
rejecting orders is not one to keep firing at.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, fields
from datetime import datetime, timezone
from typing import Optional


def utc_day(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d")


@dataclass
class SessionState:
    """What the guardrails need to remember between orders."""
    day: str = ""                    # UTC day the counters belong to
    day_start_equity: float = 0.0    # equity at the start of that day
    trades_today: int = 0
    last_trade_ts: float = 0.0
    consecutive_failures: int = 0
    halt_reason: str = ""            # set once tripped, cleared by a new day

    def roll_day(self, ts: float, equity: float) -> bool:
        """Start a new trading day when the UTC date changes. True if rolled."""
        today = utc_day(ts)
        if today == self.day:
            return False
        self.day = today
        self.day_start_equity = equity
        self.trades_today = 0
        self.halt_reason = ""
        self.consecutive_failures = 0
        return True

    def on_fill(self, ts: float) -> None:
        self.trades_today += 1
        self.last_trade_ts = ts
        self.consecutive_failures = 0

    def on_failure(self) -> None:
        self.consecutive_failures += 1

    def to_dict(self) -> dict:
        return {
            "day": self.day, "day_start_equity": self.day_start_equity,
            "trades_today": self.trades_today, "last_trade_ts": self.last_trade_ts,
            "consecutive_failures": self.consecutive_failures,
            "halt_reason": self.halt_reason,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SessionState":
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in (data or {}).items() if k in known})


@dataclass
class Guardrails:
    max_daily_loss_pct: float = 0.0     # 0.10 = stand down after -10% on the day
    max_trades_per_day: int = 0         # 0 = unlimited
    cooldown_sec: int = 0               # min seconds between orders
    max_order_pct: float = 0.0          # 0.25 = never spend >25% of equity at once
    max_consecutive_failures: int = 3   # 0 = never halt on failures
    kill_switch_file: str = "STOP"      # empty = no kill switch

    def kill_switch_on(self) -> bool:
        return bool(self.kill_switch_file) and os.path.exists(self.kill_switch_file)

    def cap_order(self, quote_amount: float, equity: float) -> float:
        """Shrink an order that is larger than the per-order cap."""
        if self.max_order_pct > 0 and equity > 0:
            return min(quote_amount, equity * self.max_order_pct)
        return quote_amount

    def block_reason(self, side: str, *, equity: float, state: SessionState,
                     now: float) -> Optional[str]:
        """Why this order must not be sent, or None when it may go ahead."""
        # these two mean the bot must not touch the venue at all
        if self.kill_switch_on():
            return f"kill switch: {self.kill_switch_file} exists"
        if (self.max_consecutive_failures > 0
                and state.consecutive_failures >= self.max_consecutive_failures):
            return (f"halted: {state.consecutive_failures} orders failed in a row "
                    "-- check the venue, then restart")

        # the risk limits below only stop new positions. An exit is how you
        # survive a bad day; it is never what the daily loss limit blocks.
        if side.upper() != "BUY":
            return None
        if state.halt_reason:
            return state.halt_reason

        if self.max_daily_loss_pct > 0 and state.day_start_equity > 0:
            floor = state.day_start_equity * (1 - self.max_daily_loss_pct)
            if equity <= floor:
                state.halt_reason = (
                    f"daily loss limit hit: equity {equity:.4f} <= "
                    f"{floor:.4f} (-{self.max_daily_loss_pct*100:g}% on the day)")
                return state.halt_reason
        if self.max_trades_per_day > 0 and state.trades_today >= self.max_trades_per_day:
            return f"daily trade cap reached ({self.max_trades_per_day})"
        if self.cooldown_sec > 0 and state.last_trade_ts > 0:
            waited = now - state.last_trade_ts
            if waited < self.cooldown_sec:
                return f"cooldown: {self.cooldown_sec - waited:.0f}s to go"
        return None

    def describe(self) -> str:
        bits = []
        if self.max_daily_loss_pct > 0:
            bits.append(f"daily loss {self.max_daily_loss_pct*100:g}%")
        if self.max_trades_per_day > 0:
            bits.append(f"{self.max_trades_per_day} trades/day")
        if self.cooldown_sec > 0:
            bits.append(f"cooldown {self.cooldown_sec}s")
        if self.max_order_pct > 0:
            bits.append(f"order <= {self.max_order_pct*100:g}% equity")
        if self.kill_switch_file:
            bits.append(f"kill switch '{self.kill_switch_file}'")
        return " | ".join(bits) or "none"


def build_guardrails(cfg) -> Guardrails:
    return Guardrails(
        max_daily_loss_pct=getattr(cfg, "max_daily_loss_pct", 0.0),
        max_trades_per_day=getattr(cfg, "max_trades_per_day", 0),
        cooldown_sec=getattr(cfg, "cooldown_sec", 0),
        max_order_pct=getattr(cfg, "max_order_pct", 0.0),
        max_consecutive_failures=getattr(cfg, "max_consecutive_failures", 3),
        kill_switch_file=getattr(cfg, "kill_switch_file", "STOP"),
    )
