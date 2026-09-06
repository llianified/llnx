"""Text menu: everything the bot does, without memorising CLI flags."""
from __future__ import annotations

import json
import os

from .backtest import run_backtest, synthetic_prices
from .config import Config
from .strategies import AVAILABLE

LINE = "=" * 58


def _ask(prompt: str, default):
    raw = input(f"  {prompt} [{default}]: ").strip()
    return raw if raw else str(default)


def _ask_float(prompt, default):
    while True:
        try:
            return float(_ask(prompt, default))
        except ValueError:
            print("  ! not a number")


def _ask_int(prompt, default):
    while True:
        try:
            return int(float(_ask(prompt, default)))
        except ValueError:
            print("  ! not a number")


def _header(cfg: Config):
    print("\n" + LINE)
    print("  BOT TRADING - MAIN MENU")
    print(LINE)
    print(f"  cash      : {cfg.starting_cash:g} ({cfg.symbol})")
    print(f"  timeframe : {cfg.timeframe}   strategy: {cfg.strategy}")
    sl = f"{cfg.stop_loss_pct*100:g}%" if cfg.stop_loss_pct else "off"
    tp = f"{cfg.take_profit_pct*100:g}%" if cfg.take_profit_pct else "off"
    print(f"  stop-loss : {sl}   take-profit: {tp}")
    print(LINE)
    print("  1) cash & market")
    print("  2) strategy & its parameters")
    print("  3) stop-loss / take-profit")
    print("  4) run a BACKTEST (offline, no internet)")
    print("  5) start PAPER TRADING (live prices, simulated orders)")
    print("  6) status & trade history")
    print("  7) real-money mode (advanced, be careful)")
    print("  0) quit")
    print(LINE)


def _edit_market(cfg: Config) -> Config:
    print("\n-- cash & market --")
    return cfg.with_overrides(
        starting_cash=_ask_float("starting cash", cfg.starting_cash),
        symbol=_ask("pair (e.g. BTC/USDT)", cfg.symbol).upper(),
        timeframe=_ask("timeframe (1m/5m/15m/1h)", cfg.timeframe),
        exchange=_ask("exchange", cfg.exchange),
    )


def _edit_strategy(cfg: Config) -> Config:
    print("\n-- strategy --")
    for i, (name, desc) in enumerate(AVAILABLE.items(), 1):
        mark = " (current)" if name == cfg.strategy else ""
        print(f"  {i}) {name:5} - {desc}{mark}")
    names = list(AVAILABLE)
    choice = _ask("strategy number", names.index(cfg.strategy) + 1)
    try:
        strat = names[int(choice) - 1]
    except (ValueError, IndexError):
        strat = cfg.strategy
    cfg = cfg.with_overrides(strategy=strat)

    if strat == "sma":
        print("  -- SMA parameters --")
        fast = _ask_int("fast SMA", cfg.sma_fast)
        slow = _ask_int("slow SMA", cfg.sma_slow)
        cfg = cfg.with_overrides(sma_fast=fast, sma_slow=slow)
    elif strat == "rsi":
        print("  -- RSI parameters --")
        cfg = cfg.with_overrides(
            rsi_period=_ask_int("RSI period", cfg.rsi_period),
            rsi_oversold=_ask_float("oversold (buy below)", cfg.rsi_oversold),
            rsi_overbought=_ask_float("overbought (sell above)", cfg.rsi_overbought))
    elif strat == "grid":
        print("  -- Grid/DCA parameters --")
        cfg = cfg.with_overrides(
            grid_step_pct=_ask_float("step down per buy (0.02 = 2%)", cfg.grid_step_pct),
            grid_take_profit_pct=_ask_float("take-profit (0.03 = 3%)",
                                            cfg.grid_take_profit_pct),
            grid_max_steps=_ask_int("max steps (how many chunks)", cfg.grid_max_steps))
    return cfg


def _edit_risk(cfg: Config) -> Config:
    print("\n-- global stop-loss / take-profit (0 = off) --")
    print("  0.05 means 5%. Applies to every strategy.")
    return cfg.with_overrides(
        stop_loss_pct=_ask_float("stop-loss", cfg.stop_loss_pct),
        take_profit_pct=_ask_float("take-profit", cfg.take_profit_pct))


def _run_backtest(cfg: Config):
    print("\n-- backtest (synthetic data) --")
    closes = synthetic_prices(n=500)
    rep = run_backtest(closes, cfg)
    print(LINE)
    print(f"  strategy     : {rep.strategy}")
    print(f"  start cash   : {rep.starting_cash:.2f}")
    print(f"  final equity : {rep.final_equity:.2f}")
    print(f"  trades       : {rep.n_trades}   total fees: {rep.total_fees:.4f}")
    print(f"  return       : {rep.return_pct:+.2f}%   buy&hold: {rep.buy_hold_pct:+.2f}%")
    print(LINE)
    print("  (a backtest is no promise of live results)")
    input("  press Enter to go back...")


def _show_status(cfg: Config):
    print("\n-- status & history --")
    if os.path.exists(cfg.state_file):
        with open(cfg.state_file) as f:
            st = json.load(f)
        print(f"  cash={st.get('cash', 0):.4f}  position={st.get('position', 0):.8f}"
              f"  avg_entry={st.get('avg_entry', 0):.4f}")
    else:
        print("  no state yet (paper trading has never run).")
    if os.path.exists(cfg.trades_file):
        with open(cfg.trades_file) as f:
            rows = f.read().strip().splitlines()
        print(f"  {len(rows)-1} trades recorded. last 5:")
        for row in rows[-5:]:
            print("   ", row)
    else:
        print("  no trades yet.")
    input("  press Enter to go back...")


def _real_mode(cfg: Config) -> Config:
    print("\n" + "!" * 58)
    print("  REAL MONEY MODE - orders spend real funds (or sandbox money).")
    print("  Keys come from the environment: EXCHANGE_API_KEY, EXCHANGE_API_SECRET")
    print("  Start with the sandbox. Really.")
    print("!" * 58)
    on = _ask("enable real mode? (y/n)", "n").lower().startswith("y")
    sandbox = _ask("use sandbox/testnet? (y/n)", "y").lower().startswith("y")
    return cfg.with_overrides(live_real=on, live_sandbox=sandbox)


def run_menu(cfg: Config) -> None:
    while True:
        _header(cfg)
        choice = input("  pick: ").strip()
        try:
            if choice == "1":
                cfg = _edit_market(cfg)
            elif choice == "2":
                cfg = _edit_strategy(cfg)
            elif choice == "3":
                cfg = _edit_risk(cfg)
            elif choice == "4":
                _run_backtest(cfg)
            elif choice == "5":
                from .runner import run_live
                run_live(cfg)
            elif choice == "6":
                _show_status(cfg)
            elif choice == "7":
                cfg = _real_mode(cfg)
            elif choice == "0":
                print("  bye")
                return
            else:
                print("  ! unknown option")
        except ValueError as e:
            print(f"  ! {e}")
            input("  press Enter to go back...")
        except KeyboardInterrupt:
            print("\n  (cancelled)")
