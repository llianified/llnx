"""The llnx command line. `main.py` and `python3 -m llnx` both call main().

  llnx                                  full-screen TUI
  llnx backtest --strategy rsi --cash 20
  llnx run --mode paper --strategy grid --symbol ETH/USDT
  llnx run --mode live --yes            real orders, real money
  llnx stop                             kill switch, from any terminal
  llnx status
"""
from __future__ import annotations

import argparse
import os

from .backtest import run_backtest, synthetic_prices
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
        chain=getattr(args, "chain", None),
        token_address=getattr(args, "token", None) or getattr(args, "mint", None),
        mode=getattr(args, "mode", None),
        auto_execute=execute,
        max_daily_loss_pct=getattr(args, "max_daily_loss", None),
        max_trades_per_day=getattr(args, "max_trades", None),
        cooldown_sec=getattr(args, "cooldown", None),
        max_order_pct=getattr(args, "max_order", None),
    )


def cmd_backtest(cfg: Config, args) -> None:
    if args.csv:
        with open(args.csv, encoding="utf-8") as f:
            closes = [float(l.strip().split(",")[-1])
                      for l in f if l.strip() and not l[0].isalpha()]
        src = f"CSV {args.csv} ({len(closes)} rows)"
    else:
        closes = synthetic_prices(n=args.n, seed=args.seed)
        src = f"synthetic data ({args.n} candles, seed={args.seed})"
    rep = run_backtest(closes, cfg)
    print("=" * 60)
    print(f"  BACKTEST - {src}")
    print(f"  strategy     : {rep.strategy}")
    print("-" * 60)
    print(f"  start cash   : {rep.starting_cash:.2f}")
    print(f"  final equity : {rep.final_equity:.2f}")
    print(f"  trades       : {rep.n_trades}   total fees: {rep.total_fees:.4f}")
    print(f"  return       : {rep.return_pct:+.2f}%   buy&hold: {rep.buy_hold_pct:+.2f}%")
    print("=" * 60)
    print("  (a backtest is no promise of live results)")


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

    bt = sub.add_parser("backtest", parents=[common], help="quick strategy test")
    bt.add_argument("--csv", help="price CSV (last column = close)")
    bt.add_argument("--n", type=int, default=500)
    bt.add_argument("--seed", type=int, default=42)

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


COMMANDS = {"backtest": cmd_backtest, "run": cmd_run, "status": cmd_status,
            "stop": cmd_stop, "resume": cmd_resume, "scan": cmd_scan,
            "check": cmd_check}


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
