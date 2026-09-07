"""The llnx command line. `main.py` and `python3 -m llnx` both call main().

  llnx                                  full-screen TUI
  llnx fetch --symbol BTC/USDT --timeframe 1h --n 3000 -o btc.csv
  llnx backtest --strategy ema --csv btc.csv
  llnx optimize --csv btc.csv --sweep-trail   hunt for settings that hold up
  llnx run --mode paper --strategy grid --symbol ETH/USDT
  llnx run --mode live --yes            real orders, real money
  llnx stop                             kill switch, from any terminal
  llnx status
"""
from __future__ import annotations

import argparse
import os

from .backtest import BacktestReport, read_closes, run_backtest, synthetic_prices
from .chains import CHAINS
from .config import MODES, Config
from .execution import read_journal
from .guards import build_guardrails
from .strategies import AVAILABLE


def _load_config(path: str) -> Config:
    if os.path.exists(path):
        return Config.from_yaml(path)
    print(f"[info] no {path}, using defaults.")
    return Config()


def _apply_overrides(cfg: Config, args) -> Config:
    execute = None
    if getattr(args, "signals_only", False):
        execute = False
    return cfg.with_overrides(
        starting_cash=getattr(args, "cash", None),
        symbol=getattr(args, "symbol", None),
        timeframe=getattr(args, "timeframe", None),
        strategy=getattr(args, "strategy", None),
        sma_fast=getattr(args, "fast", None),
        sma_slow=getattr(args, "slow", None),
        stop_loss_pct=getattr(args, "sl", None),
        take_profit_pct=getattr(args, "tp", None),
        trailing_stop_pct=getattr(args, "trail", None),
        chain=getattr(args, "chain", None),
        token_address=getattr(args, "token", None) or getattr(args, "mint", None),
        mode=getattr(args, "mode", None),
        auto_execute=execute,
        max_daily_loss_pct=getattr(args, "max_daily_loss", None),
        max_trades_per_day=getattr(args, "max_trades", None),
        cooldown_sec=getattr(args, "cooldown", None),
        max_order_pct=getattr(args, "max_order", None),
    )


def load_closes(args) -> tuple:
    """(closes, description) from a CSV when given, synthetic data otherwise."""
    if getattr(args, "csv", None):
        closes = read_closes(args.csv)
        if len(closes) < 50:
            raise SystemExit(f"[stop] {args.csv} has only {len(closes)} closes.")
        return closes, f"CSV {args.csv} ({len(closes)} candles)"
    closes = synthetic_prices(n=args.n, seed=args.seed)
    return closes, (f"synthetic data ({args.n} candles, seed={args.seed}) "
                    "-- fetch real candles for a number you can trust")


def _pf(value: float) -> str:
    return "inf" if value == float("inf") else f"{value:.2f}"


def print_report(rep: BacktestReport, cfg: Config, src: str) -> None:
    from .risk import RiskManager
    risk = RiskManager(cfg.stop_loss_pct, cfg.take_profit_pct, cfg.trailing_stop_pct)
    print("=" * 62)
    print(f"  BACKTEST - {src}")
    print(f"  strategy     : {rep.strategy}")
    print(f"  risk         : {risk.describe()}")
    print("-" * 62)
    print(f"  start cash   : {rep.starting_cash:>10.2f}    "
          f"final equity : {rep.final_equity:>10.2f}")
    print(f"  return       : {rep.return_pct:>+9.2f}%    "
          f"buy & hold   : {rep.buy_hold_pct:>+9.2f}%")
    print(f"  max drawdown : {rep.max_drawdown_pct:>9.2f}%    "
          f"exposure     : {rep.exposure_pct:>9.1f}%")
    print(f"  round trips  : {rep.n_round_trips:>10}    "
          f"win rate     : {rep.win_rate_pct:>9.1f}%")
    print(f"  profit factor: {_pf(rep.profit_factor):>10}    "
          f"avg trade    : {rep.avg_trade_pct:>+9.2f}%")
    print(f"  orders       : {rep.n_trades:>10}    "
          f"fees         : {rep.fees_pct:>9.2f}% of capital")
    print("=" * 62)
    print("  Drawdown is what you have to sit through; the return is what you get")
    print("  paid for sitting through it. A backtest is not a promise.")


def cmd_backtest(cfg: Config, args) -> None:
    closes, src = load_closes(args)
    print_report(run_backtest(closes, cfg), cfg, src)


def cmd_optimize(cfg: Config, args) -> None:
    from .optimize import GRIDS, sweep

    closes, src = load_closes(args)
    names = list(GRIDS) if args.strategy in (None, "all") else [args.strategy]
    print(f"[optimize] {src}")
    print(f"[optimize] ranking by {args.metric}, {args.split:.0%} in sample, "
          f"the rest held back"
          + (", trailing stop swept" if args.sweep_trail else ""))

    for name in names:
        try:
            best = sweep(closes, cfg, strategy=name, split=args.split,
                         metric=args.metric, top=args.top, trail=args.sweep_trail)
        except ValueError as e:
            print(f"  ! {name}: {e}")
            continue
        print()
        print(f"  {name.upper()}")
        print(f"  {'#':<3} {'settings':<44} {'in sample':<26} out of sample")
        print("  " + "-" * 96)
        for rank, c in enumerate(best, 1):
            ins, out = c.in_sample, c.out_sample
            left = (f"{ins.return_pct:+8.2f}% dd {ins.max_drawdown_pct:5.1f}% "
                    f"n {ins.n_round_trips:<3}")
            right = ("(no data)" if out is None else
                     f"{out.return_pct:+8.2f}% dd {out.max_drawdown_pct:5.1f}% "
                     f"n {out.n_round_trips:<3} pf {_pf(out.profit_factor)}")
            print(f"  {rank:<3} {c.label():<44} {left:<26} {right}")
        if best and best[0].out_sample is not None:
            print(f"      buy & hold out of sample: "
                  f"{best[0].out_sample.buy_hold_pct:+.2f}%")
    print()
    print("  Read the right-hand column. Settings that only shine in sample found")
    print("  nothing; with this many combinations a few always will by luck.")


def cmd_fetch(cfg: Config, args) -> None:
    from .history import fetch_klines, write_csv

    symbol = args.symbol or cfg.symbol
    timeframe = args.timeframe or cfg.timeframe
    print(f"[fetch] {symbol} {timeframe} x{args.n} from Binance...")
    rows = fetch_klines(symbol, timeframe, args.n)
    if not rows:
        raise SystemExit("[stop] no candles came back.")
    write_csv(args.out, rows)
    print(f"[fetch] {len(rows)} candles -> {args.out}")
    print(f"        llnx backtest --csv {args.out} --strategy ema")
    print(f"        llnx optimize --csv {args.out} --sweep-trail")


def cmd_run(cfg: Config, args) -> None:
    from .runner import run_live
    run_live(cfg, confirmed=getattr(args, "yes", False))


def cmd_status(cfg: Config, args) -> None:
    import json
    print(f"mode={cfg.mode} auto_execute={cfg.auto_execute}")
    print(f"guards: {build_guardrails(cfg).describe()}")
    if os.path.exists(cfg.state_file):
        with open(cfg.state_file) as f:
            st = json.load(f)
        print(f"cash={st.get('cash',0):.4f} position={st.get('position',0):.8f} "
              f"avg_entry={st.get('avg_entry',0):.4f}")
        session = st.get("session") or {}
        if session:
            print(f"day={session.get('day','-')} trades_today="
                  f"{session.get('trades_today',0)} "
                  f"failures={session.get('consecutive_failures',0)}")
            if session.get("halt_reason"):
                print(f"HALTED: {session['halt_reason']}")
    else:
        print("No state yet.")
    if os.path.exists(cfg.trades_file):
        with open(cfg.trades_file) as f:
            rows = f.read().strip().splitlines()
        print(f"{len(rows)-1} trades. last 10:")
        for r in rows[-10:]:
            print(" ", r)
    else:
        print("No trades yet.")
    orders = read_journal(cfg.orders_file, limit=args.orders)
    if orders:
        print(f"last {len(orders)} order attempts:")
        for o in orders:
            note = o.get("reason") or o.get("error") or ""
            print(f"  {o.get('ts','')}  {o.get('status','?'):<8} "
                  f"{o.get('side','?'):<4} {o.get('amount',0):.8g} @ "
                  f"{o.get('price',0):.8g}  {note}")


def cmd_stop(cfg: Config, args) -> None:
    """Kill switch: the running bot sees the file and shuts down."""
    path = cfg.kill_switch_file
    if not path:
        print("[error] kill_switch_file is empty in the config, nothing to touch.")
        return
    with open(path, "w", encoding="utf-8") as f:
        f.write("llnx stop\n")
    print(f"[stop] {path} created. A running bot stops within one tick "
          f"({cfg.poll_interval_sec}s).")
    print("       Trade again with: llnx resume")


def cmd_resume(cfg: Config, args) -> None:
    path = cfg.kill_switch_file
    if path and os.path.exists(path):
        os.remove(path)
        print(f"[resume] {path} removed. The bot may trade again.")
    else:
        print("[resume] no kill switch was set.")


def cmd_scan(cfg: Config, args) -> None:
    from .scan import scan_trending
    from .safety import check_token
    print(f"[scan] trending tokens on {cfg.chain} (limit {args.limit})...")
    try:
        cands = scan_trending(cfg.chain, args.limit)
    except Exception as e:
        print(f"[error] scan failed: {e!r}"); return
    for i, c in enumerate(cands, 1):
        line = (f"{i:2}. {c.name:<22} ${c.price_usd:<12.8g} "
                f"vol24h ${c.volume_usd:,.0f}")
        if args.safety:
            rep = check_token(cfg.chain, c.address)
            line += f"  | {rep.summary()}"
        print(line)
        print(f"     {c.address}")
    if not cands:
        print("  (nothing found, or the API is unreachable)")


def cmd_check(cfg: Config, args) -> None:
    from .safety import check_token
    token = getattr(args, "token2", None) or cfg.token_address
    if not token:
        print("[error] pass a token address: --token <ADDR>")
        return
    print(f"[check] {cfg.chain} · {token}")
    rep = check_token(cfg.chain, token)
    print(f"  status: {rep.summary()}  (source: {rep.source or '-'})")
    for lvl, msg in rep.flags:
        print(f"   - [{lvl}] {msg}")


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--config", default="config.yaml")
    common.add_argument("--cash", type=float, help="starting cash")
    common.add_argument("--symbol", help="pair, e.g. ETH/USDT")
    common.add_argument("--timeframe", help="candle size, e.g. 5m")
    common.add_argument("--strategy", choices=list(AVAILABLE), help="which strategy")
    common.add_argument("--fast", type=int, help="fast SMA")
    common.add_argument("--slow", type=int, help="slow SMA")
    common.add_argument("--sl", type=float, help="stop-loss, e.g. 0.05")
    common.add_argument("--tp", type=float, help="take-profit, e.g. 0.10")
    common.add_argument("--trail", type=float,
                        help="trailing stop, e.g. 0.05 (sell 5%% off the peak)")
    common.add_argument("--mint", help="alias for --token (Solana mint)")
    common.add_argument("--token", help="token address (trade a DEX token)")
    common.add_argument("--chain", choices=list(CHAINS), help="network (default solana)")
    common.add_argument("--mode", choices=list(MODES),
                        help="paper (simulated) | sandbox (testnet) | live (real money)")

    p = argparse.ArgumentParser(
        prog="llnx", description="llnx - a crypto bot that places its own orders",
        parents=[common])
    sub = p.add_subparsers(dest="cmd")

    sub.add_parser("tui", parents=[common], help="full-screen TUI (default)")
    sub.add_parser("menu", parents=[common], help="plain text menu")

    data = argparse.ArgumentParser(add_help=False)
    data.add_argument("--csv", help="price CSV (a `close` column, or the last one)")
    data.add_argument("--n", type=int, default=500, help="synthetic candles")
    data.add_argument("--seed", type=int, default=42)

    sub.add_parser("backtest", parents=[common, data], help="quick strategy test")

    op = sub.add_parser("optimize", parents=[common, data],
                        help="sweep the parameters and check them out of sample")
    op.add_argument("--metric", default="score",
                    choices=["score", "return", "profit_factor", "drawdown"],
                    help="what to rank by (default: return per unit of drawdown)")
    op.add_argument("--top", type=int, default=8, help="how many to report")
    op.add_argument("--split", type=float, default=0.7,
                    help="share of the data used to rank (default 0.7)")
    op.add_argument("--sweep-trail", action="store_true", dest="sweep_trail",
                    help="also sweep the trailing stop (4x the combinations, "
                         "usually worth it)")

    fe = sub.add_parser("fetch", parents=[common], help="download real candles to a CSV")
    fe.add_argument("--n", type=int, default=2000, help="how many candles")
    fe.add_argument("-o", "--out", default="candles.csv", help="output CSV")

    for name, help_text in (("run", "trade in the selected mode"),
                            ("paper", "alias for run --mode paper")):
        rr = sub.add_parser(name, parents=[common], help=help_text)
        rr.add_argument("--yes", action="store_true",
                        help="skip the live confirmation prompt (be sure)")
        rr.add_argument("--signals-only", action="store_true",
                        help="decide but place nothing (auto_execute off)")
        rr.add_argument("--max-daily-loss", type=float,
                        help="stop buying after this daily loss, e.g. 0.10")
        rr.add_argument("--max-trades", type=int, help="max trades per day")
        rr.add_argument("--cooldown", type=int, help="seconds between orders")
        rr.add_argument("--max-order", type=float,
                        help="cap one order at this share of equity, e.g. 0.25")

    st = sub.add_parser("status", parents=[common], help="state, orders & history")
    st.add_argument("--orders", type=int, default=10, help="order journal rows")

    sub.add_parser("stop", parents=[common], help="kill switch: stop a running bot")
    sub.add_parser("resume", parents=[common], help="clear the kill switch")

    sc = sub.add_parser("scan", parents=[common], help="scan trending tokens per chain")
    sc.add_argument("--limit", type=int, default=10)
    sc.add_argument("--safety", action="store_true", help="safety-check each candidate")

    ck = sub.add_parser("check", parents=[common], help="token safety check (honeypot etc.)")
    ck.add_argument("--token-address", dest="token2", help="token address")
    return p


COMMANDS = {"backtest": cmd_backtest, "optimize": cmd_optimize, "fetch": cmd_fetch,
            "run": cmd_run, "status": cmd_status, "stop": cmd_stop,
            "resume": cmd_resume, "scan": cmd_scan, "check": cmd_check}


def main() -> None:
    args = build_parser().parse_args()
    cmd = args.cmd or "tui"
    if cmd == "paper":                      # the old name for `run --mode paper`
        args.mode = args.mode or "paper"
        cmd = "run"
    cfg = _apply_overrides(_load_config(args.config), args)

    if cmd == "tui":
        try:
            from .tui import run_tui
        except ModuleNotFoundError:
            print("[info] textual is not installed, falling back to the text menu.")
            print("       For the TUI: pip install textual")
            from .menu import run_menu
            run_menu(cfg)
        else:
            run_tui(cfg)
    elif cmd == "menu":
        from .menu import run_menu
        run_menu(cfg)
    else:
        COMMANDS[cmd](cfg, args)
