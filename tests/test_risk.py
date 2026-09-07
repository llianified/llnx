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


# ── trailing stop ────────────────────────────────────────────────
def held(price, entry=100.0):
    from llnx.strategies.base import Context
    return Context(price=price, cash=0.0, position=1.0, avg_entry=entry,
                   last_buy_price=entry, starting_cash=100.0)


def test_the_trailing_stop_follows_the_peak_up():
    from llnx.risk import RiskManager
    risk = RiskManager(trailing_stop_pct=0.05)
    for price in (100.0, 110.0, 120.0, 116.0):
        assert risk.check(held(price)) is None       # 116 is only 3.3% off 120
    assert risk.peak == 120.0
    decision = risk.check(held(113.0))               # now 5.8% off the peak
    assert decision is not None and "TRAILING" in decision.reason


def test_the_trailing_stop_does_not_fire_before_the_position_is_ahead():
    from llnx.risk import RiskManager
    risk = RiskManager(trailing_stop_pct=0.05)
    assert risk.check(held(90.0)) is None            # under water, that is the SL's job


def test_the_peak_resets_when_the_position_closes():
    from llnx.risk import RiskManager
    from llnx.strategies.base import Context
    risk = RiskManager(trailing_stop_pct=0.10)
    risk.check(held(150.0))
    flat = Context(price=150.0, cash=100.0, position=0.0, avg_entry=0.0,
                   last_buy_price=0.0, starting_cash=100.0)
    assert risk.check(flat) is None and risk.peak == 0.0


def test_a_hard_stop_loss_wins_over_the_trailing_one():
    from llnx.risk import RiskManager
    risk = RiskManager(stop_loss_pct=0.05, trailing_stop_pct=0.20)
    risk.check(held(120.0))
    decision = risk.check(held(94.0))
    assert decision is not None and "STOP-LOSS" in decision.reason


def test_describe_names_what_is_switched_on():
    from llnx.risk import RiskManager
    assert RiskManager().describe() == "off"
    assert not RiskManager().active
    text = RiskManager(0.03, 0.10, 0.05).describe()
    assert "SL 3%" in text and "trail 5%" in text and "TP 10%" in text
