#!/usr/bin/env python3
"""Paper/real trading bot - entry point.

Easiest (full-screen TUI):
  python3 main.py

Straight to the point:
  python3 main.py backtest --strategy rsi --cash 20
  python3 main.py paper --strategy grid --symbol ETH/USDT
  python3 main.py status
"""
from __future__ import annotations

import argparse
import os

from bot.backtest import run_backtest, synthetic_prices
from bot.config import Config
from bot.chains import CHAINS
from bot.strategies import AVAILABLE


def _load_config(path: str) -> Config:
    if os.path.exists(path):
        return Config.from_yaml(path)
    print(f"[info] no {path}, using defaults.")
    return Config()


def _apply_overrides(cfg: Config, args) -> Config:
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


def cmd_paper(cfg: Config, args) -> None:
    if getattr(args, "real", False):
        cfg = cfg.with_overrides(live_real=True,
                                 live_sandbox=not getattr(args, "mainnet", False))
    from bot.runner import run_live
    run_live(cfg)


def cmd_status(cfg: Config, args) -> None:
    import json
    if os.path.exists(cfg.state_file):
        with open(cfg.state_file) as f:
            st = json.load(f)
        print(f"cash={st.get('cash',0):.4f} position={st.get('position',0):.8f} "
              f"avg_entry={st.get('avg_entry',0):.4f}")
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


def cmd_scan(cfg: Config, args) -> None:
    from bot.scan import scan_trending
    from bot.safety import check_token
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
    from bot.safety import check_token
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
    common.add_argument("--token", help="token address (DEX paper mode)")
    common.add_argument("--chain", choices=list(CHAINS), help="network (default solana)")

    p = argparse.ArgumentParser(description="Paper/real trading bot", parents=[common])
    sub = p.add_subparsers(dest="cmd")

    sub.add_parser("tui", parents=[common], help="full-screen TUI (default)")
    sub.add_parser("menu", parents=[common], help="plain text menu")

    bt = sub.add_parser("backtest", parents=[common], help="quick strategy test")
    bt.add_argument("--csv", help="price CSV (last column = close)")
    bt.add_argument("--n", type=int, default=500)
    bt.add_argument("--seed", type=int, default=42)

    pp = sub.add_parser("paper", parents=[common], help="live trading (paper/real)")
    pp.add_argument("--real", action="store_true", help="real money (sandbox by default)")
    pp.add_argument("--mainnet", action="store_true", help="mainnet instead of sandbox")

    sub.add_parser("status", parents=[common], help="state & trade history")

    sc = sub.add_parser("scan", parents=[common], help="scan trending tokens per chain")
    sc.add_argument("--limit", type=int, default=10)
    sc.add_argument("--safety", action="store_true", help="safety-check each candidate")

    ck = sub.add_parser("check", parents=[common], help="token safety check (honeypot etc.)")
    ck.add_argument("--token-address", dest="token2", help="token address")
    return p


def main() -> None:
    args = build_parser().parse_args()
    cfg = _apply_overrides(_load_config(args.config), args)
    cmd = args.cmd or "tui"
    if cmd == "tui":
        try:
            from bot.tui import run_tui
        except ModuleNotFoundError:
            print("[info] textual is not installed, falling back to the text menu.")
            print("       For the TUI: pip install textual")
            from bot.menu import run_menu
            run_menu(cfg)
        else:
            run_tui(cfg)
    elif cmd == "menu":
        from bot.menu import run_menu
        run_menu(cfg)
    elif cmd == "backtest":
        cmd_backtest(cfg, args)
    elif cmd == "paper":
        cmd_paper(cfg, args)
    elif cmd == "status":
        cmd_status(cfg, args)
    elif cmd == "scan":
        cmd_scan(cfg, args)
    elif cmd == "check":
        cmd_check(cfg, args)


if __name__ == "__main__":
    main()
