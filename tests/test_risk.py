"""Risk management (stop-loss / take-profit) through the engine."""
from llnx.broker import PaperBroker
from llnx.engine import TradingEngine
from llnx.risk import RiskManager
from llnx.strategies.base import Context, Decision, Strategy


class _Hold(Strategy):
    warmup = 1
    def evaluate(self, closes, ctx):
        return Decision("HOLD")


def _engine(sl=0.0, tp=0.0, cash=100.0):
    b = PaperBroker(fee_rate=0.0, min_notional=0.0, cash=cash)
    return TradingEngine(_Hold(), b, cash, risk=RiskManager(sl, tp)), b


def test_stop_loss_triggers_sell():
    eng, b = _engine(sl=0.05)
    b.buy(100.0)                     # entry @100
    res = eng.step([100], 94.0)      # -6% < -5% -> stop loss
    assert res.executed is not None and res.executed.side == "SELL"
    assert "STOP-LOSS" in res.decision.reason


def test_take_profit_triggers_sell():
    eng, b = _engine(tp=0.10)
    b.buy(100.0)
    res = eng.step([100], 111.0)     # +11% > +10% -> take profit
    assert res.executed is not None and res.executed.side == "SELL"
    assert "TAKE-PROFIT" in res.decision.reason


def test_no_trigger_when_within_bounds():
    eng, b = _engine(sl=0.05, tp=0.10)
    b.buy(100.0)
    res = eng.step([100], 102.0)     # within bounds -> no sale
    assert res.executed is None
