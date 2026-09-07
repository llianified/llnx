"""Downloading real candles: paging backwards, and what gets written out."""
import urllib.parse as urlparse

from llnx.history import COLUMNS, fetch_klines, klines_to_rows, write_csv

# 2500 candles of pretend history, oldest first
ALL = [[1_000_000 + i * 60_000, 1.0, 2.0, 0.5, 100.0 + i, 10.0] for i in range(2500)]


def fake_binance(url):
    """Answers like the real endpoint: the newest `limit` candles up to endTime."""
    query = urlparse.parse_qs(urlparse.urlparse(url).query)
    limit = int(query["limit"][0])
    end = int(query["endTime"][0]) if "endTime" in query else None
    rows = [k for k in ALL if end is None or k[0] <= end]
    return rows[-limit:]


def test_klines_are_parsed_and_junk_is_dropped():
    rows = klines_to_rows([[1, "1", "2", "0.5", "1.5", "10"], [], [2, "1"]])
    assert rows == [[1, 1.0, 2.0, 0.5, 1.5, 10.0]]


def test_a_long_history_is_paged_backwards():
    rows = fetch_klines("BTC/USDT", "1h", 1500, get=fake_binance, log=lambda *a: None)
    assert len(rows) == 1499                 # the forming candle is dropped
    assert rows[0][4] == 1100.0 and rows[-1][4] == 2598.0
    assert [r[0] for r in rows] == sorted(r[0] for r in rows)


def test_asking_for_more_than_exists_returns_what_there_is():
    rows = fetch_klines("BTC/USDT", "1h", 5000, get=fake_binance, log=lambda *a: None)
    assert len(rows) == len(ALL) - 1


def test_the_symbol_is_translated_for_the_exchange():
    seen = []
    fetch_klines("ETH/USDT", "15m", 10,
                 get=lambda url: (seen.append(url), fake_binance(url))[1],
                 log=lambda *a: None)
    assert "symbol=ETHUSDT" in seen[0] and "interval=15m" in seen[0]


def test_the_csv_is_what_the_backtest_reads(tmp_path):
    from llnx.backtest import read_closes
    path = tmp_path / "candles.csv"
    rows = fetch_klines("BTC/USDT", "1h", 100, get=fake_binance, log=lambda *a: None)
    write_csv(str(path), rows)
    assert path.read_text().splitlines()[0] == ",".join(COLUMNS)
    assert read_closes(str(path)) == [r[4] for r in rows]
