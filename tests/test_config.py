"""Config loading, including the built-in YAML reader used without PyYAML."""
import textwrap

from bot.config import Config, parse_simple_yaml


def test_parses_the_scalar_types_it_needs():
    data = parse_simple_yaml(textwrap.dedent("""
        # a comment
        symbol: ETH/USDT
        starting_cash: 12.5
        sma_fast: 7
        live_real: false
        safety_check: true
        telegram_token: ""
        timeframe: 5m           # trailing comment
    """))
    assert data == {"symbol": "ETH/USDT", "starting_cash": 12.5, "sma_fast": 7,
                    "live_real": False, "safety_check": True,
                    "telegram_token": "", "timeframe": "5m"}


def test_matches_pyyaml_on_the_shipped_config():
    yaml = __import__("importlib").util.find_spec("yaml")
    text = open("config.yaml", encoding="utf-8").read()
    ours = parse_simple_yaml(text)
    if yaml is None:            # PyYAML is optional, skip the comparison
        assert ours["symbol"] == "BTC/USDT"
        return
    import yaml as pyyaml
    theirs = {k: ("" if v is None else v) for k, v in pyyaml.safe_load(text).items()}
    assert ours == theirs


def test_unknown_keys_are_ignored(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("symbol: SOL/USDT\nsomething_else: 1\n", encoding="utf-8")
    cfg = Config.from_yaml(str(path))
    assert cfg.symbol == "SOL/USDT"
