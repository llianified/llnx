"""Live runner (paper or real): poll prices, step the engine, save state."""
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
        print(f"[state] resuming from {cfg.state_file}: "
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
    print("  REAL MONEY MODE. Orders will spend the funds in your account.")
    print("  Only do this once paper and sandbox runs look right.")
    print("!" * 60)
    ans = input('  Type "I UNDERSTAND" to continue: ').strip()
    return ans == "I UNDERSTAND"


def _build_broker(cfg: Config):
    # ── DEX mode (token_address is set) ──
    if cfg.token_address:
        if not cfg.live_real:
            return _load_paper_broker(cfg), False
        from .chains import get_chain
        chain = get_chain(cfg.chain)
        if chain.kind != "solana":
            raise SystemExit(f"[stop] real swaps on {chain.name} (EVM) are not supported "
                             "yet -- stay on paper. Only Solana can execute for real.")
        from .jupiter_broker import JupiterBroker
        if not cfg.live_sandbox and not _confirm_real():
            print("[stop] cancelled.")
            sys.exit(0)
        broker = JupiterBroker(cfg.token_address, dry_run=cfg.live_sandbox,
                               cash=cfg.starting_cash, fee_rate=cfg.fee_rate,
                               min_notional=cfg.min_notional,
                               slippage_bps=cfg.jupiter_slippage_bps)
        return broker, True
    # ── exchange mode ──
    if not cfg.live_real:
        return _load_paper_broker(cfg), False
    from .live_broker import CcxtBroker
    if not cfg.live_sandbox and not _confirm_real():
        print("[stop] cancelled.")
        sys.exit(0)
    broker = CcxtBroker(cfg.exchange, cfg.symbol, sandbox=cfg.live_sandbox,
                        fee_rate=cfg.fee_rate, min_notional=cfg.min_notional)
    return broker, True


def run_live(cfg: Config) -> None:
    from .feeds import build_feed

    strategy = build_strategy(cfg.strategy, cfg)
    broker, is_real = _build_broker(cfg)
    risk = RiskManager(cfg.stop_loss_pct, cfg.take_profit_pct)
    notifier = build_notifier(cfg)
    feed, symbol = build_feed(cfg)
    engine = TradingEngine(strategy, broker, cfg.starting_cash, risk=risk,
                           notifier=notifier, symbol=symbol)

    if cfg.token_address:
        from .chains import get_chain
        source = f"{get_chain(cfg.chain).name} DEX (DexScreener/GeckoTerminal)"
    else:
        source = cfg.exchange
    if is_real and cfg.token_address:
        mode = ("SOLANA SWAP - DRY RUN (real quotes, nothing is sent)"
                if cfg.live_sandbox else "!!! REAL SOLANA SWAPS !!!")
    elif is_real and cfg.live_sandbox:
        mode = "REAL MODE - SANDBOX/TESTNET (fake money, real order flow)"
    elif is_real:
        mode = "!!! REAL MONEY - MAINNET !!!"
    else:
        mode = "PAPER (simulated, no real money)"

    print("=" * 62)
    print(f"  mode     : {mode}")
    print(f"  market   : {source} | {symbol} | {cfg.timeframe}")
    print(f"  strategy : {strategy.describe()}")
    print(f"  risk     : SL {cfg.stop_loss_pct*100:g}% | TP {cfg.take_profit_pct*100:g}%"
          + ("  (off)" if not risk.active else ""))
    print(f"  notify   : {'telegram on' if notifier.enabled else 'off'}")
    print(f"  polling every {cfg.poll_interval_sec}s. Ctrl+C to stop.")
    print("=" * 62)
    if notifier.enabled:
        notifier.notify(f"bot started - {mode}\n{symbol} | {strategy.describe()}")

    if cfg.token_address and cfg.safety_check:
        from .safety import check_token
        print("[safety] checking the token...")
        rep = check_token(cfg.chain, cfg.token_address)
        print(f"[safety] {rep.summary()} (source: {rep.source or '-'})")
        for lvl, msg in rep.flags[:8]:
            print(f"   - [{lvl}] {msg}")
        if rep.blocking and is_real:
            raise SystemExit("[stop] the token looks DANGEROUS - real trading cancelled.")
        if rep.blocking:
            print("   [safety] the token looks DANGEROUS - continuing on paper only.")

    run = {"go": True}

    def _stop(signum, frame):
        run["go"] = False
        print("\n[stop] saving state...")

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
            print(f"[{time.strftime('%H:%M:%S')}] price={price:.2f} "
                  f"signal={res.decision.action:<4} equity={res.equity:.4f}  {mark}")
        except Exception as e:
            print(f"[warn] tick failed: {e!r} - will retry")

        for _ in range(cfg.poll_interval_sec):
            if not run["go"]:
                break
            time.sleep(1)

    if not is_real:
        _save_paper_broker(cfg, broker)
    print("[stop] done.")
