"""Menu interaktif — jalan tanpa perlu hafal flag CLI."""
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
            print("  ! angka tidak valid")


def _ask_int(prompt, default):
    while True:
        try:
            return int(float(_ask(prompt, default)))
        except ValueError:
            print("  ! angka tidak valid")


def _header(cfg: Config):
    print("\n" + LINE)
    print("  🤖  BOT TRADING — MENU UTAMA")
    print(LINE)
    print(f"  Modal awal : {cfg.starting_cash:g} ({cfg.symbol})")
    print(f"  Timeframe  : {cfg.timeframe}   Strategi: {cfg.strategy.upper()}")
    sl = f"{cfg.stop_loss_pct*100:g}%" if cfg.stop_loss_pct else "off"
    tp = f"{cfg.take_profit_pct*100:g}%" if cfg.take_profit_pct else "off"
    print(f"  Stop-loss  : {sl}   Take-profit: {tp}")
    print(LINE)
    print("  1) Ubah modal & pasar")
    print("  2) Pilih strategi & parameter")
    print("  3) Atur stop-loss / take-profit")
    print("  4) Jalankan BACKTEST (uji cepat, tanpa internet)")
    print("  5) Mulai PAPER TRADING live (simulasi, tanpa uang)")
    print("  6) Lihat status & riwayat transaksi")
    print("  7) Mode uang REAL (lanjutan) — hati-hati")
    print("  0) Keluar")
    print(LINE)


def _edit_market(cfg: Config) -> Config:
    print("\n-- Modal & Pasar --")
    return cfg.with_overrides(
        starting_cash=_ask_float("Modal awal", cfg.starting_cash),
        symbol=_ask("Pasangan (mis. BTC/USDT)", cfg.symbol).upper(),
        timeframe=_ask("Timeframe (1m/5m/15m/1h)", cfg.timeframe),
        exchange=_ask("Exchange", cfg.exchange),
    )


def _edit_strategy(cfg: Config) -> Config:
    print("\n-- Pilih Strategi --")
    for i, (name, desc) in enumerate(AVAILABLE.items(), 1):
        mark = " (aktif)" if name == cfg.strategy else ""
        print(f"  {i}) {name.upper():5} — {desc}{mark}")
    names = list(AVAILABLE)
    choice = _ask("Nomor strategi", names.index(cfg.strategy) + 1)
    try:
        strat = names[int(choice) - 1]
    except (ValueError, IndexError):
        strat = cfg.strategy
    cfg = cfg.with_overrides(strategy=strat)

    if strat == "sma":
        print("  -- Parameter SMA --")
        fast = _ask_int("SMA cepat", cfg.sma_fast)
        slow = _ask_int("SMA lambat", cfg.sma_slow)
        cfg = cfg.with_overrides(sma_fast=fast, sma_slow=slow)
    elif strat == "rsi":
        print("  -- Parameter RSI --")
        cfg = cfg.with_overrides(
            rsi_period=_ask_int("Periode RSI", cfg.rsi_period),
            rsi_oversold=_ask_float("Oversold (beli di bawah)", cfg.rsi_oversold),
            rsi_overbought=_ask_float("Overbought (jual di atas)", cfg.rsi_overbought))
    elif strat == "grid":
        print("  -- Parameter Grid/DCA --")
        cfg = cfg.with_overrides(
            grid_step_pct=_ask_float("Step turun per beli (mis. 0.02=2%)", cfg.grid_step_pct),
            grid_take_profit_pct=_ask_float("Take-profit (mis. 0.03=3%)", cfg.grid_take_profit_pct),
            grid_max_steps=_ask_int("Maks langkah (pembagian modal)", cfg.grid_max_steps))
    return cfg


def _edit_risk(cfg: Config) -> Config:
    print("\n-- Stop-loss / Take-profit global (0 = nonaktif) --")
    print("  Contoh: 0.05 = 5%. Berlaku untuk semua strategi.")
    return cfg.with_overrides(
        stop_loss_pct=_ask_float("Stop-loss", cfg.stop_loss_pct),
        take_profit_pct=_ask_float("Take-profit", cfg.take_profit_pct))


def _run_backtest(cfg: Config):
    print("\n-- Backtest (data sintetis) --")
    closes = synthetic_prices(n=500)
    rep = run_backtest(closes, cfg)
    print(LINE)
    print(f"  Strategi     : {rep.strategy}")
    print(f"  Modal awal   : {rep.starting_cash:.2f}")
    print(f"  Equity akhir : {rep.final_equity:.2f}")
    print(f"  Transaksi    : {rep.n_trades}   Total fee: {rep.total_fees:.4f}")
    print(f"  Return       : {rep.return_pct:+.2f}%   Buy&hold: {rep.buy_hold_pct:+.2f}%")
    print(LINE)
    print("  (Hasil backtest BUKAN jaminan hasil live.)")
    input("  Tekan Enter untuk kembali...")


def _show_status(cfg: Config):
    print("\n-- Status & Riwayat --")
    if os.path.exists(cfg.state_file):
        with open(cfg.state_file) as f:
            st = json.load(f)
        print(f"  cash={st.get('cash', 0):.4f}  position={st.get('position', 0):.8f}"
              f"  avg_entry={st.get('avg_entry', 0):.4f}")
    else:
        print("  Belum ada state (belum pernah paper trading).")
    if os.path.exists(cfg.trades_file):
        with open(cfg.trades_file) as f:
            rows = f.read().strip().splitlines()
        print(f"  {len(rows)-1} transaksi tercatat. 5 terakhir:")
        for row in rows[-5:]:
            print("   ", row)
    else:
        print("  Belum ada transaksi.")
    input("  Tekan Enter untuk kembali...")


def _real_mode(cfg: Config) -> Config:
    print("\n" + "!" * 58)
    print("  MODE UANG REAL — order pakai dana ASLI (atau sandbox/testnet).")
    print("  Butuh API key lewat env: EXCHANGE_API_KEY, EXCHANGE_API_SECRET")
    print("  Sangat disarankan pakai SANDBOX dulu (uang bohongan).")
    print("!" * 58)
    on = _ask("Aktifkan mode real? (y/n)", "n").lower().startswith("y")
    sandbox = _ask("Pakai sandbox/testnet? (y/n)", "y").lower().startswith("y")
    return cfg.with_overrides(live_real=on, live_sandbox=sandbox)


def run_menu(cfg: Config) -> None:
    while True:
        _header(cfg)
        choice = input("  Pilih: ").strip()
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
                try:
                    import ccxt  # noqa: F401
                except ImportError:
                    print("  ! ccxt belum terpasang: pip install -r requirements.txt")
                    input("  Enter untuk kembali..."); continue
                run_live(cfg)
            elif choice == "6":
                _show_status(cfg)
            elif choice == "7":
                cfg = _real_mode(cfg)
            elif choice == "0":
                print("  Sampai jumpa 👋")
                return
            else:
                print("  ! pilihan tidak dikenal")
        except ValueError as e:
            print(f"  ! {e}")
            input("  Enter untuk kembali...")
        except KeyboardInterrupt:
            print("\n  (dibatalkan)")
