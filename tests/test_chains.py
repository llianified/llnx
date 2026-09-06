import pytest
from llnx.chains import CHAINS, get_chain


def test_registry_has_solana_and_evm():
    assert get_chain("solana").kind == "solana"
    assert get_chain("bsc").kind == "evm"
    assert get_chain("base").goplus == "8453"


def test_unknown_chain_raises():
    with pytest.raises(ValueError):
        get_chain("dogechain")


def test_case_insensitive():
    assert get_chain("SOLANA").id == "solana"
