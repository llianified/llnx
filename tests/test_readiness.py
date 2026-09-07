"""The setup checklist: what is still between a config and a real order."""
import json

from llnx.config import Config
from llnx.readiness import (DONE, TODO, UNKNOWN, Step, checklist, guardrail_steps,
                            solana_steps, traded_in)

FULL_ENV = {"SOLANA_PRIVATE_KEY": "abc", "SOLANA_RPC_URL": "https://rpc"}


def titles(steps):
    return [s.title for s in steps]


def state_of(steps, needle):
    return next(s.state for s in steps if needle in s.title)


def journal(tmp_path, rows):
    path = tmp_path / "orders.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return str(path)


def test_an_empty_environment_is_all_todo():
    steps = solana_steps(Config(token_address="MINT"), env={})
    assert state_of(steps, "SOLANA_PRIVATE_KEY") == TODO
    assert state_of(steps, "SOLANA_RPC_URL") == TODO
    assert state_of(steps, "wallet balance") == UNKNOWN     # nothing to read yet


def test_keys_in_the_environment_tick_off():
    steps = solana_steps(Config(token_address="MINT"), env=FULL_ENV)
    assert state_of(steps, "SOLANA_PRIVATE_KEY") == DONE
    assert state_of(steps, "SOLANA_RPC_URL") == DONE


def test_the_wallet_is_only_read_once_it_can_be():
    seen = []

    def probe():
        seen.append(True)
        return 0.05, 42.0
    steps = solana_steps(Config(token_address="MINT"), env=FULL_ENV, probe=probe)
    assert seen, "the probe should run when the key and the RPC are set"
    assert state_of(steps, "wallet funded") == DONE

    solana_steps(Config(token_address="MINT"), env={}, probe=probe)
    assert len(seen) == 1, "and never when they are not"


def test_an_unfunded_wallet_says_what_is_missing():
    steps = solana_steps(Config(token_address="MINT"), env=FULL_ENV,
                         probe=lambda: (0.0, 0.0))
    step = next(s for s in steps if "wallet" in s.title)
    assert step.state == TODO
    assert "SOL for fees" in step.detail and "no USDC" in step.detail


def test_a_wallet_that_cannot_be_read_is_not_a_failure():
    def boom():
        raise OSError("rpc down")
    steps = solana_steps(Config(token_address="MINT"), env=FULL_ENV, probe=boom)
    assert state_of(steps, "wallet balance") == UNKNOWN


def test_no_token_address_is_the_first_thing_to_fix():
    steps = solana_steps(Config(), env=FULL_ENV)
    assert state_of(steps, "no token address") == TODO


def test_the_brakes_have_to_be_on():
    loose = guardrail_steps(Config(max_order_pct=0, cooldown_sec=0))
    assert loose[0].state == TODO
    assert "max order" in loose[0].detail and "cooldown" in loose[0].detail
    tight = guardrail_steps(Config(max_order_pct=0.25, cooldown_sec=300,
                                   trailing_stop_pct=0.05))
    assert tight[0].state == DONE


def test_a_stop_of_either_kind_counts():
    with_trail = guardrail_steps(Config(max_order_pct=0.2, cooldown_sec=60,
                                        trailing_stop_pct=0.05))
    with_hard = guardrail_steps(Config(max_order_pct=0.2, cooldown_sec=60,
                                       stop_loss_pct=0.03))
    assert with_trail[0].state == DONE and with_hard[0].state == DONE


def test_practice_is_counted_from_the_order_journal(tmp_path):
    path = journal(tmp_path, [
        {"mode": "paper", "status": "filled"},
        {"mode": "paper", "status": "blocked"},      # not a fill
        {"mode": "sandbox", "status": "filled"},
        {"mode": "live", "status": "filled"},
    ])
    assert traded_in("paper", path) == 1
    assert traded_in("sandbox", path) == 1
    assert traded_in("nothing", path) == 0


def test_the_checklist_knows_whether_you_have_practised(tmp_path):
    cfg = Config(token_address="MINT",
                 orders_file=journal(tmp_path, [{"mode": "paper", "status": "filled"}]))
    steps = checklist(cfg, env=FULL_ENV)
    assert state_of(steps, "paper trading first") == DONE
    assert state_of(steps, "Solana dry run") == TODO       # sandbox still missing


def test_an_exchange_config_gets_exchange_steps():
    steps = checklist(Config(), env={})
    assert any("ccxt" in t for t in titles(steps))
    assert any("EXCHANGE_API_KEY" in t for t in titles(steps))
    assert not any("SOLANA" in t for t in titles(steps))


def test_the_last_word_is_always_how_to_arm_it():
    last = checklist(Config(token_address="MINT"), env=FULL_ENV)[-1]
    assert "live" in last.title and "type the phrase" in last.detail


def test_nothing_in_the_checklist_leaks_a_key():
    steps = checklist(Config(token_address="MINT"),
                      env={"SOLANA_PRIVATE_KEY": "SECRETKEY123",
                           "SOLANA_RPC_URL": "https://secret.rpc/abc"})
    rendered = " ".join(f"{s.title} {s.detail}" for s in steps)
    assert "SECRETKEY123" not in rendered and "secret.rpc" not in rendered
