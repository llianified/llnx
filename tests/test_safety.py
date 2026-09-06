from llnx.safety import parse_goplus, parse_rugcheck


def test_rugcheck_flags_authorities_and_risks():
    data = {"mintAuthority": "SomeAddr", "freezeAuthority": "Frz",
            "risks": [{"name": "Low liquidity", "level": "warn", "description": "thin book"}]}
    r = parse_rugcheck(data, "mint1")
    assert r.level == "danger"          # freeze authority = danger
    msgs = " ".join(m for _, m in r.flags)
    assert "mint authority" in msgs and "freeze authority" in msgs


def test_rugcheck_clean():
    r = parse_rugcheck({"mintAuthority": None, "freezeAuthority": None, "risks": []},
                       "mint2")
    assert r.level == "ok"


def test_goplus_detects_honeypot():
    addr = "0xabc"
    data = {"result": {addr: {"is_honeypot": "1", "buy_tax": "0", "sell_tax": "0"}}}
    r = parse_goplus(data, addr)
    assert r.blocking is True
    assert any("HONEYPOT" in m for _, m in r.flags)


def test_goplus_high_tax_and_lp():
    addr = "0xdef"
    data = {"result": {addr: {"is_honeypot": "0", "buy_tax": "0.02", "sell_tax": "0.12",
                              "is_open_source": "1",
                              "lp_holders": [{"is_locked": "1"}]}}}
    r = parse_goplus(data, addr)
    assert r.level == "warn"           # sell tax 12% -> warn
    assert any("locked" in m for _, m in r.flags)


def test_goplus_empty_is_unknown():
    r = parse_goplus({"result": {}}, "0x0")
    assert r.level == "unknown"
