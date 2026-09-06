"""Solana RPC helpers: parsing balances and waiting for a real confirmation."""
import pytest

from llnx import wallet
from llnx.wallet import RpcError, signature_state, sum_token_accounts


def account(ui, raw):
    return {"account": {"data": {"parsed": {"info": {
        "tokenAmount": {"uiAmount": ui, "amount": raw}}}}}}


def test_token_accounts_are_added_up_in_both_units():
    result = {"value": [account(12.5, "12500000"), account(2.5, "2500000")]}
    assert sum_token_accounts(result) == (15.0, 15_000_000)
    assert sum_token_accounts({}) == (0.0, 0)
    assert sum_token_accounts({"value": [{}]}) == (0.0, 0)


def test_signature_state_reads_the_first_entry():
    assert signature_state({"value": [{"confirmationStatus": "finalized"}]}) == (
        "finalized", None)
    assert signature_state({"value": [None]}) == ("pending", None)
    assert signature_state({}) == ("pending", None)
    status, err = signature_state({"value": [{"err": {"InstructionError": 1}}]})
    assert status == "processed" and err


def test_confirmation_waits_until_the_chain_agrees(monkeypatch):
    replies = iter([{"value": [None]},
                    {"value": [{"confirmationStatus": "processed"}]},
                    {"value": [{"confirmationStatus": "confirmed"}]}])
    monkeypatch.setattr(wallet, "rpc", lambda *a, **k: next(replies))
    assert wallet.confirm_signature("rpc", "SIG", sleep=lambda s: None) == "confirmed"


def test_a_swap_that_failed_on_chain_raises(monkeypatch):
    monkeypatch.setattr(wallet, "rpc",
                        lambda *a, **k: {"value": [{"err": "InsufficientFunds"}]})
    with pytest.raises(RpcError, match="failed on chain"):
        wallet.confirm_signature("rpc", "SIG", sleep=lambda s: None)


def test_a_swap_that_never_confirms_raises(monkeypatch):
    monkeypatch.setattr(wallet, "rpc", lambda *a, **k: {"value": [None]})
    with pytest.raises(RpcError, match="not confirmed"):
        wallet.confirm_signature("rpc", "SIG", timeout=0, sleep=lambda s: None)


def test_rpc_turns_a_node_error_into_an_exception(monkeypatch):
    monkeypatch.setattr(wallet, "post_json",
                        lambda url, payload, timeout=20: {"error": {"message": "nope"}})
    with pytest.raises(RpcError, match="getBalance"):
        wallet.rpc("url", "getBalance", ["key"])


def test_balances_come_back_in_human_units(monkeypatch):
    monkeypatch.setattr(wallet, "post_json",
                        lambda url, payload, timeout=20: {"result": {"value": 2_500_000_000}})
    assert wallet.sol_balance("url", "key") == 2.5
