"""Keys typed into the app: where they go, and where they must never go."""
import os
import stat

from llnx.credentials import (ENV_FILE, fingerprint, ignore, load, parse_env,
                              render_env, save, short)


def test_parsing_a_saved_file():
    values = parse_env('# a comment\n'
                       'SOLANA_RPC_URL="https://rpc"\n'
                       "SOLANA_PRIVATE_KEY='abc123'\n"
                       "\n"
                       "BARE=value\n"
                       "nonsense line\n")
    assert values == {"SOLANA_RPC_URL": "https://rpc",
                      "SOLANA_PRIVATE_KEY": "abc123", "BARE": "value"}


def test_empty_values_are_not_written():
    text = render_env({"A": "1", "B": ""})
    assert 'A="1"' in text and "B=" not in text


def test_saving_is_readable_only_by_its_owner(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = save({"SOLANA_PRIVATE_KEY": "secret", "SOLANA_RPC_URL": "https://rpc"})
    mode = stat.S_IMODE(os.stat(path).st_mode)
    assert mode == 0o600, f"the key file is {oct(mode)}, it must be 0600"


def test_saving_tells_git_to_ignore_it(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    save({"SOLANA_PRIVATE_KEY": "secret"})
    assert ENV_FILE in (tmp_path / ".gitignore").read_text()
    save({"SOLANA_RPC_URL": "https://rpc"})          # twice, not duplicated
    assert (tmp_path / ".gitignore").read_text().count(ENV_FILE) == 1


def test_saving_again_keeps_what_was_there(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    save({"SOLANA_PRIVATE_KEY": "secret"})
    save({"SOLANA_RPC_URL": "https://rpc"})
    values = parse_env((tmp_path / ENV_FILE).read_text())
    assert values["SOLANA_PRIVATE_KEY"] == "secret"
    assert values["SOLANA_RPC_URL"] == "https://rpc"


def test_the_environment_beats_the_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    save({"SOLANA_PRIVATE_KEY": "from-the-file", "SOLANA_RPC_URL": "https://file"})
    env = {"SOLANA_PRIVATE_KEY": "exported"}
    assert load(ENV_FILE, env) == 1                  # only the missing one
    assert env["SOLANA_PRIVATE_KEY"] == "exported"
    assert env["SOLANA_RPC_URL"] == "https://file"


def test_loading_nothing_is_not_an_error(tmp_path):
    assert load(str(tmp_path / "nope.env"), {}) == 0


def test_a_key_never_becomes_an_address_by_accident():
    assert fingerprint("") is None
    assert fingerprint("not-a-real-key") is None     # and it does not raise


def test_addresses_are_shortened_for_the_screen():
    assert short("DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263") == "DezX…B263"
    assert short("short") == "short"


def test_the_config_file_is_never_where_a_key_lands(tmp_path, monkeypatch):
    """config.yaml is meant to be shared; the key file is not."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.yaml").write_text("symbol: BTC/USDT\n", encoding="utf-8")
    save({"SOLANA_PRIVATE_KEY": "secret"})
    assert "secret" not in (tmp_path / "config.yaml").read_text()
    assert "secret" in (tmp_path / ENV_FILE).read_text()
