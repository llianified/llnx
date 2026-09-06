#!/usr/bin/env python3
"""Bot trading paper/real — entry point.

Paling gampang (menu interaktif):
  python main.py

Langsung (power user):
  python main.py backtest --strategy rsi --cash 20
  python main.py paper --strategy grid --symbol ETH/USDT
  python main.py status
"""
from __future__ import annotations

import argparse
import os
import sys

from bot.backtest import run_backtest, synthetic_prices
from bot.config import Config
from bot.strategies import AVAILABLE


def _load_config(path: str) -> Config:
    if os.path.exists(path):
        return Config.from_yaml(path)
    print(f"[info] {path} tidak ada, pakai default.")
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
    )


def cmd_backtest(cfg: Config, args) -> None:
    if args.csv:
        with open(args.csv, encoding="utf-8") as f:
            closes = [float(l.strip().split(",")[-1])
                      for l in f if l.strip() and not l[0].isalpha()]
        src = f"CSV {args.csv} ({len(closes)} baris)"
    else:
        closes = synthetic_prices(n=args.n, seed=args.seed)
        src = f"data sintetis ({args.n} candle, seed={args.seed})"
    rep = run_backtest(closes, cfg)
    print("=" * 60)
    print(f"  BACKTEST — {src}")
    print(f"  Strategi     : {rep.strategy}")
    print("-" * 60)
    print(f"  Modal awal   : {rep.starting_cash:.2f}")
    print(f"  Equity akhir : {rep.final_equity:.2f}")
    print(f"  Transaksi    : {rep.n_trades}   Total fee: {rep.total_fees:.4f}")
    print(f"  Return       : {rep.return_pct:+.2f}%   Buy&hold: {rep.buy_hold_pct:+.2f}%")
    print("=" * 60)
    print("  (Hasil backtest BUKAN jaminan hasil live.)")


def cmd_paper(cfg: Config, args) -> None:
    if getattr(args, "real", False):
        cfg = cfg.with_overrides(live_real=True,
                                 live_sandbox=not getattr(args, "mainnet", False))
    try:
        import ccxt  # noqa: F401
    except ImportError:
        print("[error] ccxt belum terpasang. Jalankan: pip install -r requirements.txt")
        sys.exit(1)
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
        print("Belum ada state.")
    if os.path.exists(cfg.trades_file):
        with open(cfg.trades_file) as f:
            rows = f.read().strip().splitlines()
        print(f"{len(rows)-1} transaksi. 10 terakhir:")
        for r in rows[-10:]:
            print(" ", r)
    else:
        print("Belum ada transaksi.")


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--config", default="config.yaml")
    common.add_argument("--cash", type=float, help="modal awal")
    common.add_argument("--symbol", help="pasangan, mis. ETH/USDT")
    common.add_argument("--timeframe", help="timeframe, mis. 5m")
    common.add_argument("--strategy", choices=list(AVAILABLE), help="pilih strategi")
    common.add_argument("--fast", type=int, help="SMA cepat")
    common.add_argument("--slow", type=int, help="SMA lambat")
    common.add_argument("--sl", type=float, help="stop-loss (mis. 0.05)")
    common.add_argument("--tp", type=float, help="take-profit (mis. 0.10)")

    p = argparse.ArgumentParser(description="Bot trading paper/real", parents=[common])
    sub = p.add_subparsers(dest="cmd")

    sub.add_parser("tui", parents=[common], help="antarmuka TUI full-screen (default)")
    sub.add_parser("menu", parents=[common], help="menu teks sederhana")

    bt = sub.add_parser("backtest", parents=[common], help="uji strategi cepat")
    bt.add_argument("--csv", help="CSV harga (kolom terakhir = close)")
    bt.add_argument("--n", type=int, default=500)
    bt.add_argument("--seed", type=int, default=42)

    pp = sub.add_parser("paper", parents=[common], help="trading live (paper/real)")
    pp.add_argument("--real", action="store_true", help="mode uang real (default sandbox)")
    pp.add_argument("--mainnet", action="store_true", help="pakai mainnet, bukan sandbox")

    sub.add_parser("status", parents=[common], help="lihat state & riwayat")
    return p


def main() -> None:
    args = build_parser().parse_args()
    cfg = _apply_overrides(_load_config(args.config), args)
    cmd = args.cmd or "tui"
    if cmd == "tui":
        try:
            from bot.tui import run_tui
        except ModuleNotFoundError:
            print("[info] Textual belum terpasang, pakai menu teks.")
            print("       Untuk TUI keren: pip install -r requirements.txt")
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


if __name__ == "__main__":
    main()
