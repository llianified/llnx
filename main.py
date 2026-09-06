#!/usr/bin/env python3
"""Entry point bot trading paper.

Contoh:
  python main.py backtest                 # demo backtest data sintetis (tanpa internet)
  python main.py backtest --cash 20       # backtest dengan modal 20
  python main.py paper                    # paper trading LIVE (butuh: pip install -r requirements.txt)
  python main.py paper --cash 10 --symbol ETH/USDT
"""
from __future__ import annotations

import argparse
import os
import sys

from bot.backtest import run_backtest, synthetic_prices
from bot.config import Config


def _load_config(path: str) -> Config:
    if os.path.exists(path):
        return Config.from_yaml(path)
    print(f"[info] {path} tidak ada, pakai default bawaan.")
    return Config()


def cmd_backtest(cfg: Config, args) -> None:
    if args.csv:
        with open(args.csv, "r", encoding="utf-8") as f:
            closes = [float(line.strip().split(",")[-1])
                      for line in f if line.strip() and not line[0].isalpha()]
        source = f"CSV {args.csv} ({len(closes)} baris)"
    else:
        closes = synthetic_prices(n=args.n, seed=args.seed)
        source = f"data sintetis ({args.n} candle, seed={args.seed})"

    rep = run_backtest(closes, fast=cfg.sma_fast, slow=cfg.sma_slow,
                       starting_cash=cfg.starting_cash, fee_rate=cfg.fee_rate,
                       min_notional=0.0)
    print("=" * 60)
    print(f"  BACKTEST — {source}")
    print(f"  SMA {cfg.sma_fast}/{cfg.sma_slow} | fee {cfg.fee_rate*100:.2f}%")
    print("-" * 60)
    print(f"  Modal awal      : {rep.starting_cash:.2f}")
    print(f"  Equity akhir    : {rep.final_equity:.2f}")
    print(f"  Jumlah transaksi: {rep.n_trades}")
    print(f"  Total fee       : {rep.total_fees:.4f}")
    print(f"  Return strategi : {rep.return_pct:+.2f}%")
    print(f"  Buy & hold      : {rep.buy_hold_pct:+.2f}%")
    print("=" * 60)
    verdict = "MENGALAHKAN" if rep.return_pct > rep.buy_hold_pct else "KALAH DARI"
    print(f"  -> Strategi {verdict} buy & hold pada data ini.")
    print("  (Catatan: hasil backtest BUKAN jaminan hasil live.)")


def cmd_paper(cfg: Config, args) -> None:
    try:
        from bot.runner import run_live
    except Exception as e:
        print(f"[error] gagal load modul live: {e!r}")
        sys.exit(1)
    try:
        import ccxt  # noqa: F401
    except ImportError:
        print("[error] ccxt belum terpasang. Jalankan: pip install -r requirements.txt")
        sys.exit(1)
    run_live(cfg)


def build_parser() -> argparse.ArgumentParser:
    # opsi umum yang berlaku untuk semua subcommand (boleh ditaruh setelah subcommand)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--config", default="config.yaml", help="path file konfigurasi")
    common.add_argument("--cash", type=float, help="modal awal (override)")
    common.add_argument("--symbol", help="pasangan trading (override), mis. ETH/USDT")
    common.add_argument("--timeframe", help="timeframe candle (override), mis. 5m")
    common.add_argument("--fast", type=int, help="periode SMA cepat (override)")
    common.add_argument("--slow", type=int, help="periode SMA lambat (override)")

    p = argparse.ArgumentParser(
        description="Bot trading paper (simulasi) — SMA crossover",
        parents=[common])
    sub = p.add_subparsers(dest="cmd", required=True)

    bt = sub.add_parser("backtest", parents=[common],
                        help="uji strategi ke data historis/sintetis")
    bt.add_argument("--csv", help="file CSV harga (kolom terakhir = close)")
    bt.add_argument("--n", type=int, default=500, help="jumlah candle sintetis")
    bt.add_argument("--seed", type=int, default=42, help="seed data sintetis")

    sub.add_parser("paper", parents=[common],
                  help="paper trading live (harga real-time, order simulasi)")
    return p


def main() -> None:
    args = build_parser().parse_args()
    cfg = _load_config(args.config).with_overrides(
        starting_cash=args.cash,
        symbol=args.symbol,
        timeframe=args.timeframe,
        sma_fast=args.fast,
        sma_slow=args.slow,
    )
    if args.cmd == "backtest":
        cmd_backtest(cfg, args)
    elif args.cmd == "paper":
        cmd_paper(cfg, args)


if __name__ == "__main__":
    main()
