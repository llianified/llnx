"""Config loading, including the built-in YAML reader used without PyYAML."""
import textwrap

from llnx.config import Config, parse_simple_yaml


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


def test_mode_and_the_old_live_flags_stay_in_step():
    live = Config(mode="live")
    assert (live.live_real, live.live_sandbox) == (True, False)
    # an older config.yaml that only knows live_real/live_sandbox
    assert Config(live_real=True, live_sandbox=True).mode == "sandbox"
    assert Config(live_real=True, live_sandbox=False).mode == "live"
    assert Config().mode == "paper"
    # and switching back has to actually switch back
    back = live.with_overrides(mode="paper")
    assert (back.mode, back.live_real) == ("paper", False)


def test_a_mode_that_does_not_exist_is_refused():
    import pytest
    with pytest.raises(ValueError, match="unknown mode"):
        Config(mode="yolo")


def test_guardrail_ranges_are_checked():
    import pytest
    with pytest.raises(ValueError, match="max_daily_loss_pct"):
        Config(max_daily_loss_pct=1.5)
    with pytest.raises(ValueError, match="max_order_pct"):
        Config(max_order_pct=2.0)
