"""Registry jaringan yang didukung (Solana + EVM)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Chain:
    id: str            # dipakai di CLI/config
    name: str
    kind: str          # "solana" | "evm"
    dexscreener: str   # chainId di DexScreener
    gecko: str         # network id di GeckoTerminal
    goplus: str        # id GoPlus (nomor utk EVM, "solana" utk solana)
    native: str        # simbol koin gas
    rpc_env: str       # nama env var RPC


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
        raise ValueError(f"chain '{chain_id}' tidak dikenal. Pilihan: {', '.join(CHAINS)}")
    return CHAINS[key]
