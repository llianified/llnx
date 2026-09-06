"""tui minimalis — huruf kecil, tanpa ikon, warna kalem. bisa diklik & keyboard.

layout landscape-first: di layar lebar (desktop / hp diputar) pengaturan ada di
kiri dan log di kanan. di layar sempit (termux portrait) layout otomatis
menumpuk ke bawah, dan bisa dipadatkan lagi kalau tinggi layar mepet.

butuh: pip install textual   |   jalankan: python3 main.py
"""
from __future__ import annotations

from textual import events, on, work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import (Button, Footer, Header, Input, Label, RichLog,
                             Select, Static)

from .backtest import run_backtest, synthetic_prices
from .chains import CHAINS
from .config import Config
from .strategies import build_strategy

# palet kalem (sedikit warna, low-saturation)
A = "#8a9aa0"     # aksen slate
V = "#c9cdd6"     # nilai (soft)
DIM = "#6b6f78"   # redup
POS = "#86a789"   # hijau kalem
NEG = "#b08a8a"   # merah kalem
MAUVE = "#9b93b0" # penanda chain
WARN = "#c9b273"  # amber kalem

STRAT_LABELS = {
    "sma": "sma · crossover",
    "rsi": "rsi · oversold/overbought",
    "grid": "grid · dca",
}
TFS = ("1m", "5m", "15m", "1h", "4h")

# ambang layout: di bawah ini pengaturan pindah ke atas (menumpuk), bukan ke kiri
NARROW_COLS = 78
# di bawah ini widget dirapatkan (border input dilepas) biar muat
COMPACT_ROWS = 28
# layar benar-benar pendek (hp landscape): buang ringkasan & bingkai
SHORT_ROWS = 22
# baris log yang disimpan untuk digambar ulang saat ukuran layar berubah
LOG_HISTORY = 500
# tinggi panel pengaturan saat menumpuk (baris) — sisanya buat log
PANEL_ROWS = 16


class WrapLog(RichLog):
    """log yang mengingat isinya, lalu membungkus ulang saat lebar layar berubah.

    RichLog membungkus teks sekali saat ditulis, jadi kalau hp diputar
    baris lama harus digambar ulang biar tidak kepotong.
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        # RichLog default membungkus di 78 kolom; di layar hp itu bikin kepotong.
        self.min_width = 10
        self._history: list[str] = []
        self._width = 0

    def log_line(self, line: str = "") -> None:
        self._history.append(line)
        del self._history[:-LOG_HISTORY]
        self.write(line)

    def on_resize(self) -> None:
        self.call_after_refresh(self._rewrap)

    def _rewrap(self) -> None:
        width = self.scrollable_content_region.width
        if width <= 0 or width == self._width:
            return
        self._width = width
        self.clear()
        for line in self._history:
            self.write(line)


class BotTUI(App):
    TITLE = "bot trading"
    SUB_TITLE = "paper · solana · sma · rsi · grid"

    CSS = """
    Screen { background: #17181c; layout: horizontal; }
    HeaderIcon { visibility: hidden; }
    Header { background: #1d1e24; color: #8a9aa0; }
    Footer { background: #1d1e24; }
    FooterKey { background: #1d1e24; color: #6b6f78; }
    FooterKey > .footer-key--key { color: #8a9aa0; background: #1d1e24; }
    FooterKey > .footer-key--description { color: #6b6f78; background: #1d1e24; }

    #sidebar { width: 42; height: 1fr; padding: 0 1;
               background: #1d1e24; border: round #2c2e36; }
    #sidebar.hidden { display: none; }
    #settings { height: auto; }
    #title { color: #8a9aa0; padding: 0 1; }
    .col { width: 1fr; height: auto; }
    .row { height: auto; }
    Label { color: #6b6f78; padding: 0 1; height: 1; }
    Input { border: round #2c2e36; background: #14151a; color: #b4b8c0; height: 3; }
    Input:focus { border: round #5f767c; }
    Select { height: 3; }
    Select > SelectCurrent { color: #b4b8c0; }
    #btnbox { height: auto; padding: 1 0 0 0; }
    Button { margin: 0 1 1 0; border: none; width: 1fr; min-width: 0;
             color: #b4b8c0; background: #23252c; }
    Button:hover { background: #2b2e37; }
    #backtest { background: #263029; color: #c6d2c8; }
    #paper { background: #24272e; color: #bcc1c9; }
    #check { background: #24262d; color: #bcc1c9; }
    #stopbtn { background: #2c2526; color: #c4b9b9; }
    #main { width: 1fr; padding: 0 1; }
    #summary { height: auto; padding: 1 2; margin-bottom: 1;
               background: #1d1e24; border: round #2c2e36; color: #b4b8c0; }
    #log { background: #14151a; border: round #2c2e36; padding: 0 1; }

    /* ── layar sempit (termux portrait): tumpuk ke bawah ─────────── */
    Screen.-narrow { layout: vertical; }
    Screen.-narrow #sidebar { width: 1fr; }   /* tinggi diatur di _apply_layout */
    Screen.-narrow #main { width: 1fr; height: 1fr; padding: 0; }
    Screen.-narrow #summary { padding: 0 1; margin-bottom: 0; }
    Screen.-narrow FooterKey.-command-palette { display: none; }

    /* ── ruang mepet: rapatkan widget, tombol tetap kelihatan ────── */
    Screen.-compact #settings { height: 1fr; }
    Screen.-compact Input { height: 1; border: none; padding: 0 1; }
    Screen.-compact Input:focus { border: none; background: #1b1d23; }
    Screen.-compact Select { height: 1; }
    Screen.-compact Select > SelectCurrent { border: none; height: 1; padding: 0 1; }
    Screen.-compact Button { height: 1; }
    Screen.-compact #btnbox { padding: 1 0 0 0; }

    /* ── layar benar-benar pendek (hp landscape): buang hiasan ───── */
    Screen.-short #summary { display: none; }
    Screen.-short #sidebar { border: none; }
    Screen.-short #log { border: none; }
    """

    BINDINGS = [
        ("b", "backtest", "backtest"),
        ("p", "paper", "paper"),
        ("c", "check", "check"),
        ("s", "status", "status"),
        ("x", "stop", "stop"),
        ("t", "toggle_settings", "atur"),
        ("q", "quit", "keluar"),
    ]

    def __init__(self, cfg: Config) -> None:
        super().__init__()
        self.cfg = cfg
        self._paper_running = False
        self._app_ready = False
        self._narrow = False
        self._compact = False
        self._short = False
        self._hinted_narrow = False

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical(id="sidebar"):
            with VerticalScroll(id="settings"):
                yield Static("pengaturan", id="title")
                with Horizontal(classes="row"):
                    with Vertical(classes="col"):
                        yield Label("modal ($)")
                        yield Input(str(self.cfg.starting_cash), id="cash", type="number")
                    with Vertical(classes="col"):
                        yield Label("pasangan")
                        yield Input(self.cfg.symbol.lower(), id="symbol")
                with Horizontal(classes="row"):
                    with Vertical(classes="col"):
                        yield Label("timeframe")
                        yield Select([(t, t) for t in TFS], value=self.cfg.timeframe,
                                     id="timeframe", allow_blank=False)
                    with Vertical(classes="col"):
                        yield Label("chain")
                        yield Select([(CHAINS[c].name.lower(), c) for c in CHAINS],
                                     value=self.cfg.chain, id="chain", allow_blank=False)
                yield Label("strategi")
                yield Select([(STRAT_LABELS[n], n) for n in STRAT_LABELS],
                             value=self.cfg.strategy, id="strategy", allow_blank=False)
                yield Label("token address (opsional → mode dex)")
                yield Input(self.cfg.token_address, id="token")
                with Horizontal(classes="row"):
                    with Vertical(classes="col"):
                        yield Label("stop-loss")
                        yield Input(str(self.cfg.stop_loss_pct), id="sl", type="number")
                    with Vertical(classes="col"):
                        yield Label("take-profit")
                        yield Input(str(self.cfg.take_profit_pct), id="tp", type="number")
            with Vertical(id="btnbox"):
                with Horizontal(classes="row"):
                    yield Button("backtest", id="backtest")
                    yield Button("paper", id="paper")
                with Horizontal(classes="row"):
                    yield Button("check", id="check")
                    yield Button("stop", id="stopbtn")
        with Vertical(id="main"):
            yield Static(self._summary(), id="summary")
            yield WrapLog(id="log", markup=True, highlight=False, wrap=True)
        yield Footer()

    # ── layout responsif ────────────────────────────────────────
    def _apply_layout(self, width: int, height: int) -> None:
        """pilih layout dari ukuran terminal (landscape = layout utama)."""
        narrow = width < NARROW_COLS               # tumpuk ke bawah
        compact = narrow or height < COMPACT_ROWS  # rapatkan widget
        short = height < SHORT_ROWS                # buang ringkasan & bingkai
        sidebar = self.query("#sidebar")
        if sidebar:
            # menumpuk: panel secukupnya (maks separuh layar), sisanya buat log.
            # berdampingan: biarkan CSS yang atur (setinggi layar).
            sidebar.first().styles.height = (
                min(PANEL_ROWS, max(7, height // 2)) if narrow else None)
        if (narrow, compact, short) == (self._narrow, self._compact, self._short):
            return
        self._narrow, self._compact, self._short = narrow, compact, short
        self.screen.set_class(narrow, "-narrow")
        self.screen.set_class(compact, "-compact")
        self.screen.set_class(short, "-short")
        self._refresh_summary()
        if self._app_ready and narrow and not self._hinted_narrow:
            self._hinted_narrow = True
            self._log(f"[{DIM}]layar sempit ({width} kolom). putar hp ke landscape "
                      "untuk tampilan penuh, atau tekan t untuk sembunyikan "
                      "pengaturan.[/]")

    def on_resize(self, event: events.Resize) -> None:
        self._apply_layout(event.size.width, event.size.height)

    def action_toggle_settings(self) -> None:
        sidebar = self.query_one("#sidebar")
        sidebar.toggle_class("hidden")
        if sidebar.has_class("hidden"):
            self._log(f"[{DIM}]pengaturan disembunyikan (tekan t "
                      "untuk memunculkan).[/]")
        else:
            self.query_one("#cash", Input).focus()

    # ── util ────────────────────────────────────────────────────
    def _market(self) -> str:
        c = self.cfg
        if c.token_address:
            a = c.token_address
            short = f"{a[:4]}…{a[-4:]}" if len(a) > 10 else a
            return f"[{MAUVE}]{c.chain} {short}[/]"
        return f"[{V}]{c.symbol.lower()}[/]"

    def _summary(self) -> str:
        c = self.cfg
        sl = f"{c.stop_loss_pct*100:g}%" if c.stop_loss_pct else "off"
        tp = f"{c.take_profit_pct*100:g}%" if c.take_profit_pct else "off"
        d = f"  [{DIM}]·[/]  "
        if self._narrow:  # dua baris pendek biar tak jadi kolom cacing
            return (f"{self._market()} [{DIM}]·[/] {c.timeframe} [{DIM}]·[/] "
                    f"[{A}]{c.strategy}[/]\n"
                    f"[{DIM}]modal[/] [{V}]{c.starting_cash:g}[/] [{DIM}]·[/] "
                    f"sl [{V}]{sl}[/] [{DIM}]·[/] tp [{V}]{tp}[/]")
        return (f"[{A}]bot trading[/]{d}modal [{V}]{c.starting_cash:g}[/]{d}"
                f"{self._market()} [{DIM}]·[/] {c.timeframe}{d}strategi "
                f"[{A}]{c.strategy}[/]{d}sl [{V}]{sl}[/] · tp [{V}]{tp}[/]")

    def _refresh_summary(self) -> None:
        summary = self.query("#summary")   # belum ada saat compose pertama
        if summary:
            summary.first(Static).update(self._summary())

    def _sync_cfg(self) -> None:
        def num(sel, default):
            try:
                return float(self.query_one(sel, Input).value)
            except (ValueError, Exception):
                return default
        self.cfg = self.cfg.with_overrides(
            starting_cash=num("#cash", self.cfg.starting_cash),
            symbol=(self.query_one("#symbol", Input).value or self.cfg.symbol).upper(),
            timeframe=self.query_one("#timeframe", Select).value,
            strategy=self.query_one("#strategy", Select).value,
            stop_loss_pct=num("#sl", 0.0),
            take_profit_pct=num("#tp", 0.0),
            chain=self.query_one("#chain", Select).value,
            token_address=self.query_one("#token", Input).value.strip())
        self._refresh_summary()

    @property
    def logbox(self) -> WrapLog:
        return self.query_one("#log", WrapLog)

    def _log(self, line: str = "") -> None:
        self.logbox.log_line(line)

    def on_mount(self) -> None:
        self._apply_layout(self.size.width, self.size.height)
        self.call_after_refresh(self._post_welcome)

    def _post_welcome(self) -> None:
        self._app_ready = True
        where = "di atas" if self._narrow else "di kiri"
        self._log(f"[{A}]selamat datang.[/] atur {where}, lalu klik "
                  "backtest (atau tekan b).")
        self._log(f"[{DIM}]backtest jalan offline. "
                  "paper trading butuh koneksi.[/]")
        if self._narrow:
            self._hinted_narrow = True
            self._log(f"[{DIM}]layar sempit: putar hp ke landscape untuk "
                      "tampilan penuh, atau tekan t untuk menyembunyikan "
                      "pengaturan.[/]")

    # ── aksi ────────────────────────────────────────────────────
    @on(Select.Changed)
    @on(Input.Changed)
    def _on_change(self) -> None:
        if not self._app_ready:
            return
        self._sync_cfg()

    @on(Button.Pressed, "#backtest")
    def action_backtest(self) -> None:
        self._sync_cfg()
        self._log("")
        desc = build_strategy(self.cfg.strategy, self.cfg).describe().lower()
        self._log(f"[{A}]backtest[/] · {desc}")
        try:
            rep = run_backtest(synthetic_prices(n=500), self.cfg)
        except Exception as e:
            self._log(f"[{NEG}]error:[/] {e}")
            return
        col = POS if rep.return_pct >= 0 else NEG
        bh = POS if rep.buy_hold_pct >= 0 else NEG
        self._log(f"  [{DIM}]modal awal  [/] [{V}]{rep.starting_cash:.2f}[/]")
        self._log(f"  [{DIM}]equity akhir[/] [{V}]{rep.final_equity:.2f}[/]")
        self._log(f"  [{DIM}]transaksi   [/] {rep.n_trades}   "
                  f"[{DIM}]fee[/] {rep.total_fees:.4f}")
        self._log(f"  [{DIM}]return      [/] [{col}]{rep.return_pct:+.2f}%[/]   "
                  f"[{DIM}]buy&hold[/] [{bh}]{rep.buy_hold_pct:+.2f}%[/]")
        self._log(f"[{DIM}]  (backtest bukan jaminan hasil live)[/]")

    @on(Button.Pressed, "#paper")
    def action_paper(self) -> None:
        self._sync_cfg()
        if self._paper_running:
            self._log(f"[{DIM}]paper sudah berjalan.[/]")
            return
        if not self.cfg.token_address:
            try:
                import ccxt  # noqa: F401
            except ImportError:
                self._log(f"[{NEG}]ccxt belum terpasang.[/] "
                          "pip install -r requirements.txt")
                return
        self._paper_running = True
        self._log(f"[{A}]paper trading dimulai[/] "
                  f"[{DIM}](tombol stop / tekan x)[/]")
        self._paper_worker()

    @work(thread=True, exclusive=True)
    def _paper_worker(self) -> None:
        from .broker import PaperBroker
        from .engine import TradingEngine
        from .feeds import build_feed
        from .risk import RiskManager
        import time as _t
        cfg = self.cfg
        try:
            strat = build_strategy(cfg.strategy, cfg)
            broker = PaperBroker(fee_rate=cfg.fee_rate, min_notional=cfg.min_notional,
                                 cash=cfg.starting_cash)
            feed, symbol = build_feed(cfg)
            eng = TradingEngine(strat, broker, cfg.starting_cash,
                                risk=RiskManager(cfg.stop_loss_pct, cfg.take_profit_pct),
                                symbol=symbol)
        except Exception as e:
            self.call_from_thread(self._log, f"[{NEG}]gagal start:[/] {e!r}")
            self._paper_running = False
            return
        while self._paper_running:
            try:
                closes = feed.fetch_closes(limit=strat.warmup + 3)
                price = feed.fetch_price()
                res = eng.step(closes, price)
                mark = (f"  [{A}]{res.executed.side.lower()} @ {price:.4g}[/] "
                        f"[{DIM}]({res.executed.reason})[/]" if res.executed else "")
                self.call_from_thread(
                    self._log,
                    f"[{DIM}]{_t.strftime('%H:%M:%S')}[/] harga={price:.4g} "
                    f"sinyal={res.decision.action.lower()} "
                    f"equity=[{V}]{res.equity:.4f}[/]{mark}")
            except Exception as e:
                self.call_from_thread(self._log, f"[{NEG}]tick error:[/] {e!r}")
            for _ in range(cfg.poll_interval_sec):
                if not self._paper_running:
                    break
                _t.sleep(1)

    @on(Button.Pressed, "#check")
    def action_check(self) -> None:
        self._sync_cfg()
        if not self.cfg.token_address:
            self._log(f"[{DIM}]isi token address dulu untuk cek keamanan.[/]")
            return
        self._log("")
        self._log(f"[{A}]cek keamanan[/] · {self.cfg.chain} · "
                  f"{self.cfg.token_address[:8]}…")
        self._check_worker()

    @work(thread=True)
    def _check_worker(self) -> None:
        from .safety import check_token
        rep = check_token(self.cfg.chain, self.cfg.token_address)
        col = {"ok": POS, "warn": WARN, "danger": NEG, "unknown": DIM}.get(rep.level, DIM)
        self.call_from_thread(self._log,
                              f"  status: [{col}]{rep.summary()}[/] "
                              f"[{DIM}]({rep.source or '-'})[/]")
        for lvl, msg in rep.flags[:8]:
            lc = {"ok": POS, "warn": WARN, "danger": NEG}.get(lvl, DIM)
            self.call_from_thread(self._log, f"  [{lc}]·[/] {msg}")

    @on(Button.Pressed, "#stopbtn")
    def action_stop(self) -> None:
        if self._paper_running:
            self._paper_running = False
            self._log(f"[{NEG}]paper dihentikan.[/]")

    def action_status(self) -> None:
        import json, os
        self._sync_cfg()
        self._log(f"[{A}]status[/]")
        if os.path.exists(self.cfg.state_file):
            with open(self.cfg.state_file) as fh:
                st = json.load(fh)
            self._log(f"  [{DIM}]cash[/] {st.get('cash',0):.4f}   "
                      f"[{DIM}]position[/] {st.get('position',0):.8f}")
        else:
            self._log(f"  [{DIM}]belum ada state.[/]")


def run_tui(cfg: Config) -> None:
    BotTUI(cfg).run()
