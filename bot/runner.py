"""Runner mode paper LIVE: loop ambil harga real-time, jalankan engine, simpan state."""
from __future__ import annotations

import csv
import json
import os
import signal
import time
from typing import Optional

from .broker import PaperBroker
from .config import Config
from .engine import TradingEngine
from .strategy import SmaCrossStrategy


def _load_broker(cfg: Config) -> PaperBroker:
    if os.path.exists(cfg.state_file):
        with open(cfg.state_file, "r", encoding="utf-8") as f:
            broker = PaperBroker.from_dict(json.load(f))
        print(f"[state] Melanjutkan dari {cfg.state_file}: "
              f"cash={broker.cash:.4f} position={broker.position:.8f}")
        return broker
    return PaperBroker(fee_rate=cfg.fee_rate, min_notional=cfg.min_notional,
                       cash=cfg.starting_cash)


def _save_broker(cfg: Config, broker: PaperBroker) -> None:
    tmp = cfg.state_file + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(broker.to_dict(), f, indent=2)
    os.replace(tmp, cfg.state_file)


def _append_trade(cfg: Config, trade) -> None:
    new_file = not os.path.exists(cfg.trades_file)
    with open(cfg.trades_file, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new_file:
            w.writerow(["timestamp", "side", "price", "amount", "fee",
                        "cash_after", "position_after", "equity_after"])
        w.writerow([trade.timestamp, trade.side, f"{trade.price:.8f}",
                    f"{trade.amount:.8f}", f"{trade.fee:.8f}",
                    f"{trade.cash_after:.8f}", f"{trade.position_after:.8f}",
                    f"{trade.equity_after:.8f}"])


def run_live(cfg: Config) -> None:
    from .datafeed import CcxtDataFeed  # import di sini supaya butuh ccxt hanya saat live

    strategy = SmaCrossStrategy(cfg.sma_fast, cfg.sma_slow)
    broker = _load_broker(cfg)
    engine = TradingEngine(strategy, broker)
    feed = CcxtDataFeed(cfg.exchange, cfg.symbol, cfg.timeframe)

    print("=" * 60)
    print(f"  PAPER TRADING (SIMULASI — TANPA UANG SUNGGUHAN)")
    print(f"  {cfg.exchange} | {cfg.symbol} | timeframe {cfg.timeframe}")
    print(f"  SMA {cfg.sma_fast}/{cfg.sma_slow} | fee {cfg.fee_rate*100:.2f}%")
    print(f"  Modal awal: {cfg.starting_cash} | cek tiap {cfg.poll_interval_sec}s")
    print(f"  Tekan Ctrl+C untuk berhenti (state tersimpan otomatis).")
    print("=" * 60)

    running = {"go": True}

    def _stop(signum, frame):
        running["go"] = False
        print("\n[stop] Sinyal berhenti diterima, menyimpan state...")

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    while running["go"]:
        try:
            closes = feed.fetch_closes(limit=strategy.warmup + 2)
            price = feed.fetch_price()
            result = engine.step(closes, price)

            tag = result.signal
            if result.executed:
                _append_trade(cfg, result.executed)
                _save_broker(cfg, broker)
                tag = f">>> {result.executed.side} EKSEKUSI @ {price:.2f}"
            print(f"[{time.strftime('%H:%M:%S')}] harga={price:.2f} "
                  f"sinyal={result.signal:<4} equity={result.equity:.4f}  {tag if result.executed else ''}")
        except Exception as e:  # jaringan bisa gagal; jangan bikin bot mati
            print(f"[warn] error tick: {e!r} — coba lagi nanti")

        # tidur bertahap supaya Ctrl+C responsif
        for _ in range(cfg.poll_interval_sec):
            if not running["go"]:
                break
            time.sleep(1)

    _save_broker(cfg, broker)
    print(f"[stop] State disimpan ke {cfg.state_file}. Sampai jumpa.")
