"""The live loop: poll prices, step the engine, execute the orders, save state.

This is the same loop for every mode -- paper, sandbox and live. Only the
broker underneath changes, and the executor above it enforces the guardrails
and journals what happened. The TUI, the menu and the CLI all run this one
function, so what you test on paper is literally the code that trades.
"""
from __future__ import annotations

import csv
import json
import os
import signal
import threading
import time
from typing import Callable, Optional

from .broker import PaperBroker
from .config import Config
from .engine import TradingEngine
from .execution import OrderExecutor
from .guards import SessionState, build_guardrails
from .notify import build_notifier
from .risk import RiskManager
from .strategies import build_strategy

CONFIRM_PHRASE = "I UNDERSTAND"
CONFIRM_ENV = "LLNX_CONFIRM"


# ── state on disk ────────────────────────────────────────────────
def load_state(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_state(path: str, broker, session: SessionState) -> None:
    data = {"cash": broker.cash, "position": broker.position,
            "avg_entry": broker.avg_entry, "last_buy_price": broker.last_buy_price,
            "session": session.to_dict()}
    inner = getattr(broker, "to_dict", None)
    if callable(inner):
        data.update(inner())          # paper broker: fee_rate, min_notional, ...
        data["session"] = session.to_dict()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


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


# ── going live ───────────────────────────────────────────────────
def confirm_live(log=print) -> bool:
    """Real money needs a deliberate yes -- typed, or set in the environment."""
    if os.environ.get(CONFIRM_ENV, "").strip().upper() == CONFIRM_PHRASE:
        return True
    log("\n" + "!" * 62)
    log("  LIVE MODE. Orders will spend the funds in your account.")
    log("  Only do this once paper and sandbox runs look right.")
    log("!" * 62)
    try:
        answer = input(f'  Type "{CONFIRM_PHRASE}" to continue: ').strip()
    except (EOFError, OSError):     # no terminal to ask on: treat it as a no
        return False
    return answer.upper() == CONFIRM_PHRASE


def build_broker(cfg: Config, state: dict, *, confirmed: bool = False, log=print):
    """The broker for this mode. Raises SystemExit if live was not confirmed."""
    if cfg.mode == "live" and not confirmed and not confirm_live(log):
        raise SystemExit("[stop] cancelled -- live mode was not confirmed.")

    if cfg.mode == "paper":
        if state:
            broker = PaperBroker.from_dict(state)
            log(f"[state] resuming: cash={broker.cash:.4f} "
                f"position={broker.position:.8f}")
            return broker
        return PaperBroker(fee_rate=cfg.fee_rate, min_notional=cfg.min_notional,
                           cash=cfg.starting_cash)

    if cfg.token_address:                      # DEX
        from .chains import get_chain
        chain = get_chain(cfg.chain)
        if chain.kind != "solana":
            raise SystemExit(
                f"[stop] real swaps on {chain.name} (EVM) are not supported yet "
                "-- stay on paper. Only Solana can execute for real.")
        from .jupiter_broker import JupiterBroker
        return JupiterBroker(cfg.token_address, dry_run=cfg.mode == "sandbox",
                             cash=cfg.starting_cash, fee_rate=cfg.fee_rate,
                             min_notional=cfg.min_notional,
                             slippage_bps=cfg.jupiter_slippage_bps, log=log)

    from .live_broker import CcxtBroker       # CEX
    return CcxtBroker(cfg.exchange, cfg.symbol, sandbox=cfg.mode == "sandbox",
                      fee_rate=cfg.fee_rate, min_notional=cfg.min_notional, log=log)


def restore_entry(broker, state: dict, log=print) -> None:
    """Give a live broker back its average entry price after a restart.

    The venue knows the balance but not what it was paid for, and without an
    average entry the stop-loss has nothing to measure against.
    """
    avg = float(state.get("avg_entry") or 0.0)
    if avg <= 0 or broker.position <= 0:
        return
    setter = getattr(broker, "restore_entry", None)
    if callable(setter):
        setter(avg, float(state.get("last_buy_price") or avg))
        log(f"[state] restored average entry {avg:.8g} for a position of "
            f"{broker.position:.8f}")


def mode_banner(cfg: Config, is_dex: bool) -> str:
    if cfg.mode == "paper":
        return "PAPER (simulated orders, no real money)"
    if cfg.mode == "sandbox":
        return ("SANDBOX - Solana dry run (real quotes, nothing is sent)" if is_dex
                else "SANDBOX - exchange testnet (fake money, real order flow)")
    return ("!!! LIVE - REAL SOLANA SWAPS !!!" if is_dex
            else "!!! LIVE - REAL MONEY ON THE EXCHANGE !!!")


def run_live(cfg: Config, *, confirmed: bool = False, log=print,
             should_run: Optional[Callable[[], bool]] = None,
             on_tick: Optional[Callable[[dict], None]] = None) -> None:
    from .feeds import build_feed

    state = load_state(cfg.state_file)
    session = SessionState.from_dict(state.get("session") or {})
    strategy = build_strategy(cfg.strategy, cfg)
    broker = build_broker(cfg, state, confirmed=confirmed, log=log)
    if cfg.mode != "paper":
        restore_entry(broker, state, log)

    feed, symbol = build_feed(cfg)
    guards = build_guardrails(cfg)
    executor = OrderExecutor(broker, guards, journal_path=cfg.orders_file,
                             symbol=symbol, mode=cfg.mode,
                             auto_execute=cfg.auto_execute, log=log, state=session)
    risk = RiskManager(cfg.stop_loss_pct, cfg.take_profit_pct)
    notifier = build_notifier(cfg)
    engine = TradingEngine(strategy, executor, cfg.starting_cash, risk=risk,
                           notifier=notifier, symbol=symbol)

    is_dex = bool(cfg.token_address)
    if is_dex:
        from .chains import get_chain
        source = f"{get_chain(cfg.chain).name} DEX (DexScreener/GeckoTerminal)"
    else:
        source = cfg.exchange
    mode = mode_banner(cfg, is_dex)

    log("=" * 62)
    log(f"  mode     : {mode}")
    log(f"  market   : {source} | {symbol} | {cfg.timeframe}")
    log(f"  strategy : {strategy.describe()}")
    log(f"  execute  : {'ON - orders are placed automatically' if cfg.auto_execute else 'OFF - signals only'}")
    log(f"  guards   : {guards.describe()}")
    log(f"  risk     : SL {cfg.stop_loss_pct*100:g}% | TP {cfg.take_profit_pct*100:g}%"
        + ("  (off)" if not risk.active else ""))
    log(f"  notify   : {'telegram on' if notifier.enabled else 'off'}")
    log(f"  journal  : {cfg.orders_file}")
    log(f"  polling every {cfg.poll_interval_sec}s. Ctrl+C to stop.")
    log("=" * 62)
    if notifier.enabled:
        notifier.notify(f"llnx started - {mode}\n{symbol} | {strategy.describe()}")

    if is_dex and cfg.safety_check:
        from .safety import check_token
        log("[safety] checking the token...")
        rep = check_token(cfg.chain, cfg.token_address)
        log(f"[safety] {rep.summary()} (source: {rep.source or '-'})")
        for lvl, msg in rep.flags[:8]:
            log(f"   - [{lvl}] {msg}")
        if rep.blocking and cfg.mode == "live":
            raise SystemExit("[stop] the token looks DANGEROUS - live trading cancelled.")
        if rep.blocking:
            log("   [safety] the token looks DANGEROUS - continuing without real money.")

    run = {"go": True}
    if should_run is None:
        should_run = lambda: run["go"]      # noqa: E731
        if threading.current_thread() is threading.main_thread():
            def _stop(signum, frame):
                run["go"] = False
                log("\n[stop] saving state...")
            signal.signal(signal.SIGINT, _stop)
            signal.signal(signal.SIGTERM, _stop)

    while should_run():
        if guards.kill_switch_on():
            log(f"[stop] kill switch: {guards.kill_switch_file} exists. "
                "Delete it to trade again.")
            if notifier.enabled:
                notifier.notify("llnx stopped: kill switch")
            run["go"] = False
            break
        try:
            closes = feed.fetch_closes(limit=strategy.warmup + 3)
            price = feed.fetch_price()
            res = engine.step(closes, price)
            if res.executed is not None:
                _append_trade(cfg, res.executed)
            save_state(cfg.state_file, broker, session)
            mark = ""
            if res.executed is not None:
                mark = (f">>> {res.executed.side} {res.executed.amount:.8g} @ "
                        f"{res.executed.price:.8g} ({res.executed.reason})")
            elif res.decision.action != "HOLD" and executor.last_block:
                mark = f"(held: {executor.last_block})"
            log(f"[{time.strftime('%H:%M:%S')}] price={price:.8g} "
                f"signal={res.decision.action:<4} equity={res.equity:.4f}  {mark}")
            if on_tick:
                on_tick({"price": price, "decision": res.decision, "equity": res.equity,
                         "executed": res.executed, "blocked": executor.last_block})
        except Exception as e:
            log(f"[warn] tick failed: {e!r} - will retry")

        for _ in range(cfg.poll_interval_sec):
            if not should_run():
                break
            time.sleep(1)

    save_state(cfg.state_file, broker, session)
    log("[stop] done.")
