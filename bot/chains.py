"""Registry of supported networks (Solana + EVM)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Chain:
    id: str            # used on the CLI and in config.yaml
    name: str
    kind: str          # "solana" | "evm"
    dexscreener: str   # chainId on DexScreener
    gecko: str         # network id on GeckoTerminal
    goplus: str        # GoPlus id (a number for EVM, "solana" for Solana)
    native: str        # gas coin symbol
    rpc_env: str       # name of the RPC env var


CHAINS = {
    "solana":   Chain("solana",   "Solana",    "solana", "solana", "solana",      "solana", "SOL", "SOLANA_RPC_URL"),
    "ethereum": Chain("ethereum", "Ethereum",  "evm",    "ethereum", "eth",        "1",      "ETH", "EVM_RPC_URL"),
    "bsc":      Chain("bsc",      "BNB Chain", "evm",    "bsc",    "bsc",          "56",     "BNB", "EVM_RPC_URL"),
    "base":     Chain("base",     "Base",      "evm",    "base",   "base",         "8453",   "ETH", "EVM_RPC_URL"),
    "arbitrum": Chain("arbitrum", "Arbitrum",  "evm",    "arbitrum", "arbitrum",   "42161",  "ETH", "EVM_RPC_URL"),
    "polygon":  Chain("polygon",  "Polygon",   "evm",    "polygon", "polygon_pos", "137",    "POL", "EVM_RPC_URL"),
}


def get_chain(chain_id: str) -> Chain:
    key = (chain_id or "solana").lower()
    if key not in CHAINS:
        raise ValueError(f"unknown chain '{chain_id}'. Options: {', '.join(CHAINS)}")
    return CHAINS[key]
