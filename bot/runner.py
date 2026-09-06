"""Runner mode LIVE (paper atau real): loop harga, jalankan engine, simpan state."""
from __future__ import annotations

import csv
import json
import os
import signal
import sys
import time

from .broker import PaperBroker
from .config import Config
from .engine import TradingEngine
from .notify import build_notifier
from .risk import RiskManager
from .strategies import build_strategy


def _load_paper_broker(cfg: Config) -> PaperBroker:
    if os.path.exists(cfg.state_file):
        with open(cfg.state_file, "r", encoding="utf-8") as f:
            broker = PaperBroker.from_dict(json.load(f))
        print(f"[state] lanjut dari {cfg.state_file}: "
              f"cash={broker.cash:.4f} position={broker.position:.8f}")
        return broker
    return PaperBroker(fee_rate=cfg.fee_rate, min_notional=cfg.min_notional,
                       cash=cfg.starting_cash)


def _save_paper_broker(cfg: Config, broker: PaperBroker) -> None:
    tmp = cfg.state_file + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(broker.to_dict(), f, indent=2)
    os.replace(tmp, cfg.state_file)


def _append_trade(cfg: Config, t) -> None:
    new = not os.path.exists(cfg.trades_file)
    with open(cfg.trades_file, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["timestamp", "side", "price", "amount", "fee",
                        "cash_after", "position_after", "equity_after", "reason"])
        w.writerow([t.timestamp, t.side, f"{t.price:.8f}", f"{t.amount:.8f}",
                    f"{t.fee:.8f}", f"{t.cash_after:.8f}", f"{t.position_after:.8f}",
                    f"{t.equity_after:.8f}", t.reason])


def _confirm_real() -> bool:
    print("\n" + "!" * 60)
    print("  ⚠️  MODE UANG SUNGGUHAN. Order akan memakai dana ASLI di akunmu.")
    print("  Pastikan sudah puas menguji di mode paper & sandbox.")
    print("!" * 60)
    ans = input('  Ketik "SAYA PAHAM" untuk lanjut: ').strip()
    return ans == "SAYA PAHAM"


def _build_broker(cfg: Config):
    if not cfg.live_real:
        return _load_paper_broker(cfg), False
    from .live_broker import CcxtBroker
    if not cfg.live_sandbox and not _confirm_real():
        print("[stop] dibatalkan.")
        sys.exit(0)
    broker = CcxtBroker(cfg.exchange, cfg.symbol, sandbox=cfg.live_sandbox,
                        fee_rate=cfg.fee_rate, min_notional=cfg.min_notional)
    return broker, True


def run_live(cfg: Config) -> None:
    from .datafeed import CcxtDataFeed

    strategy = build_strategy(cfg.strategy, cfg)
    broker, is_real = _build_broker(cfg)
    risk = RiskManager(cfg.stop_loss_pct, cfg.take_profit_pct)
    notifier = build_notifier(cfg)
    engine = TradingEngine(strategy, broker, cfg.starting_cash, risk=risk,
                           notifier=notifier, symbol=cfg.symbol)
    feed = CcxtDataFeed(cfg.exchange, cfg.symbol, cfg.timeframe)

    if is_real and cfg.live_sandbox:
        mode = "UANG REAL — SANDBOX/TESTNET (uang bohongan, alur asli)"
    elif is_real:
        mode = "!!! UANG SUNGGUHAN — MAINNET !!!"
    else:
        mode = "PAPER (simulasi, tanpa uang sungguhan)"

    print("=" * 62)
    print(f"  MODE     : {mode}")
    print(f"  Pasar    : {cfg.exchange} | {cfg.symbol} | {cfg.timeframe}")
    print(f"  Strategi : {strategy.describe()}")
    print(f"  Risiko   : SL {cfg.stop_loss_pct*100:g}% | TP {cfg.take_profit_pct*100:g}%"
          + ("  (nonaktif)" if not risk.active else ""))
    print(f"  Notifikasi: {'Telegram ON' if notifier.enabled else 'off'}")
    print(f"  Cek tiap {cfg.poll_interval_sec}s. Ctrl+C untuk berhenti.")
    print("=" * 62)
    if notifier.enabled:
        notifier.notify(f"🤖 Bot start — {mode}\n{cfg.symbol} | {strategy.describe()}")

    run = {"go": True}

    def _stop(signum, frame):
        run["go"] = False
        print("\n[stop] menyimpan state...")

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    while run["go"]:
        try:
            closes = feed.fetch_closes(limit=strategy.warmup + 3)
            price = feed.fetch_price()
            res = engine.step(closes, price)
            if res.executed is not None:
                _append_trade(cfg, res.executed)
                if not is_real:
                    _save_paper_broker(cfg, broker)
                mark = f">>> {res.executed.side} @ {price:.2f} ({res.executed.reason})"
            else:
                mark = ""
            print(f"[{time.strftime('%H:%M:%S')}] harga={price:.2f} "
                  f"sinyal={res.decision.action:<4} equity={res.equity:.4f}  {mark}")
        except Exception as e:
            print(f"[warn] error tick: {e!r} — coba lagi nanti")

        for _ in range(cfg.poll_interval_sec):
            if not run["go"]:
                break
            time.sleep(1)

    if not is_real:
        _save_paper_broker(cfg, broker)
    print("[stop] selesai.")
