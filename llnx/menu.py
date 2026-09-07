"""Text menu: everything llnx does, without memorising CLI flags."""
from __future__ import annotations

import json
import os

from .backtest import run_backtest, synthetic_prices
from .chains import CHAINS
from .config import MODES, Config
from .execution import read_journal
from .guards import build_guardrails
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
    print("  LLNX - MAIN MENU")
    print(LINE)
    execute = "auto-execute ON" if cfg.auto_execute else "signals only"
    print(f"  mode      : {cfg.mode.upper()}  ({execute})")
    market = (f"{cfg.token_address[:8]}… on {cfg.chain}" if cfg.token_address
              else f"{cfg.symbol} on {cfg.exchange}")
    print(f"  cash      : {cfg.starting_cash:g}   market: {market}")
    print(f"  timeframe : {cfg.timeframe}   strategy: {cfg.strategy}")
    from .risk import RiskManager
    print(f"  risk      : {RiskManager(cfg.stop_loss_pct, cfg.take_profit_pct, cfg.trailing_stop_pct).describe()}")
    print(f"  guards    : {build_guardrails(cfg).describe()}")
    print(LINE)
    print("  1) cash & market")
    print("  2) strategy & its parameters")
    print("  3) stop-loss / take-profit / trailing stop")
    print("  4) run a BACKTEST (offline, no internet)")
    print(f"  5) START TRADING in {cfg.mode.upper()} mode")
    print("  6) status, orders & trade history")
    print("  7) execution mode & guardrails")
    print("  0) quit")
    print(LINE)


def _edit_market(cfg: Config) -> Config:
    """One market at a time: an exchange pair, or a token address on a chain."""
    print("\n-- cash & market --")
    print("  Two ways to trade, and only one runs at a time:")
    print("    exchange : a pair like BTC/USDT")
    print("    dex      : a token address on a chain (leave it empty for the pair)")
    cfg = cfg.with_overrides(
        starting_cash=_ask_float("starting cash", cfg.starting_cash),
        timeframe=_ask("timeframe (1m/5m/15m/1h)", cfg.timeframe),
        token_address=_ask("token address (empty = trade a pair)",
                           cfg.token_address).strip())
    if cfg.token_address:
        cfg = cfg.with_overrides(
            chain=_ask(f"chain ({'/'.join(CHAINS)})", cfg.chain).lower())
        print(f"  → dex mode: {cfg.token_address[:8]}… on {cfg.chain}. "
              "The pair and the exchange are not used.")
    else:
        cfg = cfg.with_overrides(
            symbol=_ask("pair (e.g. BTC/USDT)", cfg.symbol).upper(),
            exchange=_ask("exchange", cfg.exchange))
        print(f"  → exchange mode: {cfg.symbol} on {cfg.exchange}. "
              "The chain is not used.")
    return cfg


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
    elif strat == "ema":
        print("  -- EMA parameters (entries only while above the trend EMA) --")
        cfg = cfg.with_overrides(
            ema_fast=_ask_int("fast EMA", cfg.ema_fast),
            ema_slow=_ask_int("slow EMA", cfg.ema_slow),
            ema_trend=_ask_int("trend EMA (the filter)", cfg.ema_trend))
    elif strat == "breakout":
        print("  -- Breakout parameters --")
        cfg = cfg.with_overrides(
            breakout_entry=_ask_int("buy above the high of N candles",
                                    cfg.breakout_entry),
            breakout_exit=_ask_int("sell below the low of N candles",
                                   cfg.breakout_exit),
            breakout_atr_mult=_ask_float("volatility stop (x average move)",
                                         cfg.breakout_atr_mult))
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
    print("\n-- global stop-loss / take-profit / trailing stop (0 = off) --")
    print("  0.05 means 5%. Applies to every strategy.")
    print("  A trailing stop follows the price up and sells once it turns;")
    print("  it usually beats a fixed take-profit, which caps the winners.")
    return cfg.with_overrides(
        stop_loss_pct=_ask_float("stop-loss", cfg.stop_loss_pct),
        take_profit_pct=_ask_float("take-profit", cfg.take_profit_pct),
        trailing_stop_pct=_ask_float("trailing stop", cfg.trailing_stop_pct))


def _run_backtest(cfg: Config):
    print("\n-- backtest (synthetic data) --")
    rep = run_backtest(synthetic_prices(n=1000), cfg)
    pf = "inf" if rep.profit_factor == float("inf") else f"{rep.profit_factor:.2f}"
    print(LINE)
    print(f"  strategy     : {rep.strategy}")
    print(f"  equity       : {rep.starting_cash:.2f} -> {rep.final_equity:.2f}")
    print(f"  return       : {rep.return_pct:+.2f}%   buy&hold: {rep.buy_hold_pct:+.2f}%")
    print(f"  max drawdown : {rep.max_drawdown_pct:.2f}%   exposure: {rep.exposure_pct:.0f}%")
    print(f"  round trips  : {rep.n_round_trips}   win rate: {rep.win_rate_pct:.0f}%"
          f"   profit factor: {pf}")
    print(f"  fees         : {rep.fees_pct:.2f}% of capital ({rep.n_trades} orders)")
    print(LINE)
    print("  Synthetic data. For a number worth trusting:")
    print("    llnx fetch --symbol BTC/USDT --timeframe 1h --n 3000 -o btc.csv")
    print("    llnx optimize --csv btc.csv --sweep-trail")
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
    orders = read_journal(cfg.orders_file, limit=8)
    if orders:
        print(f"  last {len(orders)} order attempts ({cfg.orders_file}):")
        for o in orders:
            note = o.get("reason") or o.get("error") or ""
            print(f"    {o.get('ts','')}  {o.get('status','?'):<8} "
                  f"{o.get('side','?'):<4} {o.get('amount',0):.8g} @ "
                  f"{o.get('price',0):.8g}  {note}")
    input("  press Enter to go back...")


def _edit_execution(cfg: Config) -> Config:
    print("\n-- execution mode --")
    print("  paper   : simulated orders, no money, no keys")
    print("  sandbox : exchange testnet, or a Solana dry run on real quotes")
    print("  live    : REAL orders with REAL money")
    print("  keys always come from the environment, never from config.yaml:")
    print("    EXCHANGE_API_KEY / EXCHANGE_API_SECRET  (exchange)")
    print("    SOLANA_PRIVATE_KEY / SOLANA_RPC_URL     (solana swaps)")
    mode = _ask(f"mode ({'/'.join(MODES)})", cfg.mode).lower()
    if mode not in MODES:
        print(f"  ! unknown mode '{mode}', keeping {cfg.mode}")
        mode = cfg.mode
    auto = _ask("execute orders automatically? (y/n)",
                "y" if cfg.auto_execute else "n").lower().startswith("y")

    print("\n-- guardrails (0 = off) --")
    cfg = cfg.with_overrides(
        mode=mode, auto_execute=auto,
        max_daily_loss_pct=_ask_float("stop buying after a daily loss of (0.10 = 10%)",
                                      cfg.max_daily_loss_pct),
        max_trades_per_day=_ask_int("max trades per day", cfg.max_trades_per_day),
        cooldown_sec=_ask_int("cooldown between orders (seconds)", cfg.cooldown_sec),
        max_order_pct=_ask_float("max size of one order (0.25 = 25% of equity)",
                                 cfg.max_order_pct),
        kill_switch_file=_ask("kill switch file (touch it to stop the bot)",
                              cfg.kill_switch_file))
    if mode == "live":
        print("\n" + "!" * 58)
        print("  LIVE MODE ARMED. The next run places real orders.")
        print("  You will be asked to type the confirmation phrase.")
        print("!" * 58)
    return cfg


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
                cfg = _edit_execution(cfg)
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
