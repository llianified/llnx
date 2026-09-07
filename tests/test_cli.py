"""The command line: every subcommand parses, and every help page renders."""
import pytest

from llnx.cli import build_parser
from llnx.config import Config

SUBCOMMANDS = ["tui", "menu", "backtest", "optimize", "fetch", "run", "paper",
               "status", "stop", "resume", "scan", "check"]


@pytest.mark.parametrize("command", SUBCOMMANDS)
def test_every_help_page_renders(command, capsys):
    """argparse %-formats help text, so a stray % in it breaks --help."""
    with pytest.raises(SystemExit) as exit_info:
        build_parser().parse_args([command, "--help"])
    assert exit_info.value.code == 0
    assert capsys.readouterr().out


def test_the_top_level_help_renders(capsys):
    with pytest.raises(SystemExit):
        build_parser().parse_args(["--help"])
    assert "llnx" in capsys.readouterr().out


def test_risk_flags_reach_the_config():
    from llnx.cli import _apply_overrides
    args = build_parser().parse_args(
        ["run", "--sl", "0.03", "--tp", "0.1", "--trail", "0.05", "--mode", "sandbox"])
    cfg = _apply_overrides(Config(), args)
    assert cfg.stop_loss_pct == 0.03
    assert cfg.take_profit_pct == 0.1
    assert cfg.trailing_stop_pct == 0.05
    assert cfg.mode == "sandbox"


def test_guardrail_flags_reach_the_config():
    from llnx.cli import _apply_overrides
    args = build_parser().parse_args(
        ["run", "--max-order", "0.25", "--cooldown", "300", "--max-trades", "3",
         "--max-daily-loss", "0.08", "--signals-only"])
    cfg = _apply_overrides(Config(), args)
    assert cfg.max_order_pct == 0.25 and cfg.cooldown_sec == 300
    assert cfg.max_trades_per_day == 3 and cfg.max_daily_loss_pct == 0.08
    assert cfg.auto_execute is False


def test_the_sweep_flag_is_separate_from_the_trailing_stop():
    args = build_parser().parse_args(["optimize", "--sweep-trail", "--trail", "0.05"])
    assert args.sweep_trail is True and args.trail == 0.05


def test_paper_is_an_alias_that_keeps_the_mode():
    args = build_parser().parse_args(["paper"])
    assert args.cmd == "paper" and args.mode is None


def test_every_strategy_is_accepted():
    from llnx.strategies import AVAILABLE
    for name in AVAILABLE:
        args = build_parser().parse_args(["backtest", "--strategy", name])
        assert args.strategy == name
