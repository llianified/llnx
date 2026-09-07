"""What is still missing before this config can trade for real.

A wall of setup instructions goes stale and nobody reads it twice. This looks
at the machine instead -- is the package installed, is the key in the
environment, has anything ever been paper traded, are the brakes on -- and
answers the only question worth asking: what is left to do.

Nothing here prints or needs a key. `probe` is optional and only called when
the wallet can actually be reached, so the checklist works offline.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable, List, Optional

from .execution import read_journal
from .guards import build_guardrails

DONE, TODO, UNKNOWN = "done", "todo", "unknown"


@dataclass
class Step:
    state: str          # done | todo | unknown
    title: str
    detail: str = ""    # what to do about it, when there is something to do


def installed(package: str) -> bool:
    import importlib.util
    return importlib.util.find_spec(package) is not None


def _env(name: str, env) -> bool:
    return bool((env or os.environ).get(name, "").strip())


def traded_in(mode: str, orders_file: str) -> int:
    """How many orders were actually filled in that mode, from the journal."""
    return sum(1 for row in read_journal(orders_file, limit=10_000)
               if row.get("mode") == mode and row.get("status") == "filled")


def guardrail_steps(cfg) -> List[Step]:
    guards = build_guardrails(cfg)
    loose = []
    if guards.max_order_pct <= 0:
        loose.append("max order")
    if guards.cooldown_sec <= 0:
        loose.append("cooldown")
    if cfg.stop_loss_pct <= 0 and cfg.trailing_stop_pct <= 0:
        loose.append("stop")
    if loose:
        return [Step(TODO, "the brakes are off",
                     "no " + ", no ".join(loose) + ". set them in `limits` and "
                     "`exits` before real money, not after")]
    return [Step(DONE, "brakes on", guards.describe())]


def solana_steps(cfg, env=None, probe: Optional[Callable] = None) -> List[Step]:
    steps = [
        Step(DONE if installed("solders") else TODO, "the solders package",
             "" if installed("solders") else "pip install solders"),
        Step(DONE if _env("SOLANA_PRIVATE_KEY", env) else TODO,
             "SOLANA_PRIVATE_KEY in the environment",
             "" if _env("SOLANA_PRIVATE_KEY", env) else
             'export SOLANA_PRIVATE_KEY="..." — or press w in the TUI and type '
             "it there. base58, and a burner wallet: put in only what you are "
             "trading"),
        Step(DONE if _env("SOLANA_RPC_URL", env) else TODO,
             "SOLANA_RPC_URL in the environment",
             "" if _env("SOLANA_RPC_URL", env) else
             'export SOLANA_RPC_URL="https://..." — or press w in the TUI. a '
             "private endpoint; public ones rate-limit and drop swaps"),
    ]
    # the wallet is readable once the key and the RPC are there; whether the
    # probe can actually derive the address is its own business, and it says so
    if probe is not None and _env("SOLANA_PRIVATE_KEY", env) \
            and _env("SOLANA_RPC_URL", env):
        steps.append(_wallet_step(probe))
    else:
        steps.append(Step(UNKNOWN, "wallet balance",
                          "checked once the key and the RPC are set"))
    if cfg.token_address:
        steps.append(Step(DONE, "token address", cfg.token_address))
        steps.append(Step(UNKNOWN, "token safety check",
                          "press c (or: llnx check) and read it before you buy"))
    else:
        steps.append(Step(TODO, "no token address",
                          "paste one in `market`, or find one with: llnx scan"))
    return steps


def _wallet_step(probe: Callable) -> Step:
    try:
        sol, usdc = probe()
    except Exception as e:
        return Step(UNKNOWN, "wallet balance", f"could not read it: {e!r}")
    problems = []
    if sol < 0.005:
        problems.append(f"only {sol:.4f} SOL for fees")
    if usdc <= 0:
        problems.append("no USDC to trade with")
    if problems:
        return Step(TODO, "wallet not funded yet",
                    " and ".join(problems) + " — swaps buy with USDC and pay gas in SOL")
    return Step(DONE, "wallet funded", f"{sol:.4f} SOL for gas, {usdc:.2f} USDC to trade")


def exchange_steps(cfg, env=None) -> List[Step]:
    have_keys = _env("EXCHANGE_API_KEY", env) and _env("EXCHANGE_API_SECRET", env)
    return [
        Step(DONE if installed("ccxt") else TODO, "the ccxt package",
             "" if installed("ccxt") else "pip install ccxt"),
        Step(DONE if have_keys else TODO,
             "EXCHANGE_API_KEY and EXCHANGE_API_SECRET",
             "" if have_keys else
             "spot trading only, withdrawals disabled, IP-allowlisted if the "
             "exchange offers it"),
    ]


def checklist(cfg, env=None, probe: Optional[Callable] = None) -> List[Step]:
    """Everything between this config and a real order, in order."""
    steps: List[Step] = []
    if cfg.token_address:
        steps += solana_steps(cfg, env, probe)
        practice = traded_in("sandbox", cfg.orders_file)
        practice_label = "a Solana dry run"
    else:
        steps += exchange_steps(cfg, env)
        practice = traded_in("sandbox", cfg.orders_file)
        practice_label = "a sandbox run"

    paper = traded_in("paper", cfg.orders_file)
    steps.append(Step(DONE if paper else TODO, "paper trading first",
                      f"{paper} orders filled on paper" if paper else
                      "run it on paper until you have seen it buy and sell"))
    steps.append(Step(DONE if practice else TODO, practice_label,
                      f"{practice} orders filled in sandbox" if practice else
                      "mode: sandbox — real quotes, nothing sent. do this before live"))
    steps += guardrail_steps(cfg)
    steps.append(Step(UNKNOWN, "then go live",
                      "mode: live, press r, and type the phrase. `llnx stop` "
                      "halts it from any terminal"))
    return steps


def solana_probe(env=None):
    """Read the wallet, if there is one to read. Returns (SOL, USDC)."""
    from . import wallet
    from .jupiter_broker import USDC
    from solders.keypair import Keypair

    env = env or os.environ
    rpc = env["SOLANA_RPC_URL"]
    owner = str(Keypair.from_base58_string(env["SOLANA_PRIVATE_KEY"]).pubkey())
    usdc, _ = wallet.token_balance(rpc, owner, USDC)
    return wallet.sol_balance(rpc, owner), usdc
