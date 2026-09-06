"""Solana swaps: priced off the real quote, booked only once confirmed."""
import pytest

from llnx import jupiter_broker, wallet
from llnx.config import Config
from llnx.jupiter_broker import API_URL, TOKENS_URL, USDC, JupiterBroker


def quoting(rate):
    """A Jupiter stand-in: `rate` output units per input unit."""
    def _quote(in_mint, out_mint, atomic):
        if in_mint == USDC:                     # 6 in, `decimals` out
            return {"outAmount": str(int(atomic / 10 ** 6 * rate * 10 ** 6))}
        return {"outAmount": str(int(atomic / 10 ** 6 * rate * 10 ** 6))}
    return _quote


def dry(cash=100.0, rate=0.98, min_notional=1.0):
    b = JupiterBroker("MINT", dry_run=True, cash=cash, min_notional=min_notional,
                      log=lambda *a: None)
    b._decimals = 6
    b._quote = quoting(rate)
    return b


def test_the_quote_sets_the_price_not_the_screen():
    b = dry()
    trade = b.buy(1.0, 50.0)                     # 2% goes to impact and fees
    assert trade.amount == pytest.approx(49.0)
    assert trade.price == pytest.approx(50 / 49)
    assert trade.fee == pytest.approx(1.0)       # what the route cost, vs 1.0
    assert "dry-run" in trade.reason
    assert b.cash == 50.0 and b.position == pytest.approx(49.0)


def test_a_round_trip_loses_only_the_quoted_slippage():
    b = dry()
    b.buy(1.0, 50.0)
    b.sell(1.0)
    assert b.position == 0.0
    assert b.cash == pytest.approx(50 + 49 * 0.98)


def test_small_orders_are_refused_and_empty_positions_do_not_sell():
    b = dry(cash=0.5, min_notional=1.0)
    assert b.buy(1.0) is None
    assert dry().sell(1.0) is None


def test_a_route_that_does_not_exist_is_an_error(monkeypatch):
    monkeypatch.setattr(jupiter_broker, "get_json", lambda url: {"outAmount": None})
    b = dry()
    with pytest.raises(RuntimeError, match="no route"):
        JupiterBroker._quote(b, USDC, "MINT", 1000)


# ── live path ────────────────────────────────────────────────────
def live(monkeypatch, cash=100.0, position=0.0, raw=0):
    """A live broker with a stubbed wallet -- no keys, no network."""
    b = object.__new__(JupiterBroker)
    b.token, b.dry_run, b.slippage_bps = "MINT", False, 100
    b.min_notional, b.log, b.trades = 1.0, lambda *a: None, []
    b._decimals, b._paper = 6, None
    b._live_cash, b._live_position, b._live_position_raw = cash, position, raw
    b._avg_entry = b._last_buy_price = 0.0
    b.rpc_url, b.owner, b.keypair = "rpc", "OWNER", object()
    b._quote = quoting(0.98)
    balances = {USDC: (cash, int(cash * 10 ** 6)), "MINT": (position, raw)}
    monkeypatch.setattr(wallet, "token_balance",
                        lambda url, owner, mint: balances[mint])
    return b, balances


def test_a_live_buy_is_booked_from_the_chain_after_confirmation(monkeypatch):
    b, balances = live(monkeypatch)
    sent = []
    b._swap = lambda quote: (sent.append(quote), "SIGNATURE1234")[1]
    # the swap goes through, so the wallet now holds the token
    def settle(url, owner, mint):
        return {USDC: (50.0, 50_000_000), "MINT": (49.0, 49_000_000)}[mint]
    monkeypatch.setattr(wallet, "token_balance", settle)

    trade = b.buy(1.0, 50.0)
    assert len(sent) == 1
    assert trade.price == pytest.approx(50 / 49) and trade.amount == pytest.approx(49.0)
    assert trade.cash_after == 50.0 and trade.position_after == 49.0
    assert b.avg_entry == pytest.approx(50 / 49)
    assert "LIVE SIGNATU" in trade.reason


def test_a_swap_that_does_not_confirm_books_nothing(monkeypatch):
    b, _ = live(monkeypatch)
    def boom(quote):
        raise wallet.RpcError("the swap was not confirmed within 90s")
    b._swap = boom
    with pytest.raises(wallet.RpcError):
        b.buy(1.0, 50.0)
    assert b.trades == [] and b.position == 0.0 and b.avg_entry == 0.0


def test_selling_everything_live_spends_the_exact_base_units(monkeypatch):
    # a float uiAmount can round above what the chain holds; the raw amount cannot
    b, _ = live(monkeypatch, cash=0.0, position=49.000000001, raw=49_000_000)
    quoted = []
    b._quote = lambda i, o, a: (quoted.append(a),
                                {"outAmount": str(int(a * 0.98))})[1]
    b._swap = lambda quote: "SIG"
    monkeypatch.setattr(wallet, "token_balance",
                        lambda url, owner, mint: (0.0, 0) if mint == "MINT"
                        else (48.02, 48_020_000))
    trade = b.sell(1.0)
    assert quoted == [49_000_000]
    assert trade.amount == pytest.approx(49.0)
    assert b.position == 0.0 and b.avg_entry == 0.0


# ── endpoints ────────────────────────────────────────────────────
def test_the_endpoints_can_be_pointed_somewhere_else(monkeypatch):
    seen = []
    monkeypatch.setattr(jupiter_broker, "get_json",
                        lambda url: (seen.append(url), {"outAmount": "5"})[1])
    b = JupiterBroker("MINT", dry_run=True, api_url="https://quote-api.jup.ag/v6/",
                      tokens_url="https://tokens.jup.ag/token/")
    b._quote(USDC, "MINT", 1_000_000)
    assert seen[0].startswith("https://quote-api.jup.ag/v6/quote?inputMint=")
    assert "slippageBps=100" in seen[0]
    assert b.tokens_url == "https://tokens.jup.ag/token"     # trailing slash trimmed
    assert JupiterBroker("MINT", dry_run=True).api_url == API_URL


def test_an_unreachable_api_names_the_setting_to_change(monkeypatch):
    def boom(url):
        raise OSError("no route to host")
    monkeypatch.setattr(jupiter_broker, "get_json", boom)
    b = JupiterBroker("MINT", dry_run=True)
    with pytest.raises(RuntimeError, match="jupiter_api_url"):
        b._quote(USDC, "MINT", 1_000_000)


def test_the_config_carries_the_endpoints():
    cfg = Config(jupiter_api_url="https://example.test/v7")
    assert cfg.jupiter_api_url == "https://example.test/v7"
    assert Config().jupiter_api_url == ""      # empty = use the built-in default


def test_decimals_come_from_the_configured_token_endpoint(monkeypatch):
    monkeypatch.setattr(jupiter_broker, "get_json", lambda url: {"decimals": 8}
                        if url == f"{TOKENS_URL}/MINT" else None)
    b = JupiterBroker("MINT", dry_run=True)
    assert b.decimals == 8
