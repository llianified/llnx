"""Keys the app can be given directly, without an `export` in every session.

Typing a private key into a program is a real risk, so the rules here are
narrow and worth stating:

  * a key is never written to config.yaml -- that file is meant to be shared
    and committed, and this one must not be
  * saving to disk is a separate, explicit choice, and lands in a file only
    the owner can read (0600) that git is told to ignore
  * nothing here ever returns a key for display. `fingerprint` gives the
    public address, which is what you actually want to check anyway
  * the environment always wins: an exported key beats a saved one, so the
    safest way to run stays the default way

A wallet you paste into a trading bot should be a burner holding what you are
willing to trade, and nothing else.
"""
from __future__ import annotations

import os
from typing import Dict, Optional

ENV_FILE = ".llnx.env"
SOLANA_KEYS = ("SOLANA_PRIVATE_KEY", "SOLANA_RPC_URL")
EXCHANGE_KEYS = ("EXCHANGE_API_KEY", "EXCHANGE_API_SECRET")
SECRET_NAMES = ("SOLANA_PRIVATE_KEY", "EXCHANGE_API_KEY", "EXCHANGE_API_SECRET")


def parse_env(text: str) -> Dict[str, str]:
    """`KEY=value` lines. Quotes are stripped, blanks and comments ignored."""
    out: Dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        out[name.strip()] = value
    return out


def render_env(values: Dict[str, str]) -> str:
    lines = ["# llnx credentials. Never commit this file.",
             "# The environment wins over it, so `export` still overrides."]
    for name, value in values.items():
        if value:
            lines.append(f'{name}="{value}"')
    return "\n".join(lines) + "\n"


def load(path: str = ENV_FILE, env=None) -> int:
    """Put a saved file into the environment. Returns how many it set.

    Anything already exported is left alone: the environment is the safer
    place, so it stays the winner.
    """
    env = os.environ if env is None else env
    if not os.path.exists(path):
        return 0
    try:
        with open(path, encoding="utf-8") as f:
            values = parse_env(f.read())
    except OSError:
        return 0
    set_count = 0
    for name, value in values.items():
        if value and not env.get(name):
            env[name] = value
            set_count += 1
    return set_count


def save(values: Dict[str, str], path: str = ENV_FILE) -> str:
    """Write the file so only its owner can read it, and tell git to skip it."""
    existing = {}
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                existing = parse_env(f.read())
        except OSError:
            existing = {}
    existing.update({k: v for k, v in values.items() if v})

    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(render_env(existing))
    os.chmod(path, 0o600)          # in case the file already existed
    ignore(path)
    return path


def ignore(path: str, gitignore: str = ".gitignore") -> None:
    """Make sure the credentials file cannot be committed by accident."""
    name = os.path.basename(path)
    try:
        lines = []
        if os.path.exists(gitignore):
            with open(gitignore, encoding="utf-8") as f:
                lines = f.read().splitlines()
        if name in (line.strip() for line in lines):
            return
        with open(gitignore, "a", encoding="utf-8") as f:
            f.write(f"\n# llnx credentials\n{name}\n")
    except OSError:
        pass                        # not being able to write it is not fatal


def fingerprint(private_key: str) -> Optional[str]:
    """The public address a key belongs to -- never the key itself."""
    if not private_key:
        return None
    try:
        from solders.keypair import Keypair
        return str(Keypair.from_base58_string(private_key).pubkey())
    except Exception:
        return None


def short(address: str) -> str:
    return f"{address[:4]}…{address[-4:]}" if len(address) > 10 else address
