"""TUI full-screen ala opencode — bisa diklik (mouse) & keyboard.

Layout landscape ringkas biar nyaman di layar lebar / HP miring.
Butuh: pip install textual   |   Jalankan: python3 main.py
"""
from __future__ import annotations

from textual import on, work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import (Button, Footer, Header, Input, Label, RichLog,
                             Select, Static)

from .backtest import run_backtest, synthetic_prices
from .config import Config
from .strategies import AVAILABLE, build_strategy


class BotTUI(App):
    TITLE = "BOT TRADING"
    SUB_TITLE = "paper · sma · rsi · grid"

    CSS = """
    Screen { background: #14161b; layout: horizontal; }
    #sidebar {
        width: 42; padding: 0 1; background: #1b1e26; border: round #3b4252;
    }
    #title { color: #7aa2f7; text-style: bold; padding: 0 1; }
    .col { width: 1fr; height: auto; }
    .row { height: auto; }
    Label { color: #8b93a7; padding: 0 1; height: 1; }
    Input { border: round #3b4252; background: #10121a; height: 3; }
    Input:focus { border: round #7aa2f7; }
    Select { height: 3; }
    #btnrow { height: auto; padding: 1 0 0 0; align-horizontal: center; }
    Button { margin: 0 1; min-width: 12; }
    #backtest { background: #2e7d5b; color: #eafff3; text-style: bold; }
    #paper { background: #3d5a99; color: #eaf1ff; text-style: bold; }
    #stopbtn { background: #7a2e3a; color: #ffeaea; min-width: 6; }
    #main { width: 1fr; padding: 0 1; }
    #summary {
        height: auto; padding: 1 2; margin-bottom: 1;
        background: #1b1e26; border: round #3b4252; color: #c0caf5;
    }
    #log { background: #10121a; border: round #3b4252; padding: 0 1; }
    """

    BINDINGS = [
        ("b", "backtest", "Backtest"),
        ("p", "paper", "Paper"),
        ("s", "status", "Status"),
        ("x", "stop", "Stop"),
        ("q", "quit", "Keluar"),
    ]

    def __init__(self, cfg: Config) -> None:
        super().__init__()
        self.cfg = cfg
        self._paper_running = False
        self._app_ready = False

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with VerticalScroll(id="sidebar"):
            yield Static("◆ PENGATURAN", id="title")
            with Horizontal(classes="row"):
                with Vertical(classes="col"):
                    yield Label("Modal ($)")
                    yield Input(str(self.cfg.starting_cash), id="cash", type="number")
                with Vertical(classes="col"):
                    yield Label("Pasangan")
                    yield Input(self.cfg.symbol, id="symbol")
            yield Label("Timeframe")
            yield Select([(t, t) for t in ("1m", "5m", "15m", "1h", "4h")],
                         value=self.cfg.timeframe, id="timeframe", allow_blank=False)
            yield Label("Strategi")
            yield Select([(f"{n.upper()} — {d.split('—')[0].strip()}", n)
                          for n, d in AVAILABLE.items()],
                         value=self.cfg.strategy, id="strategy", allow_blank=False)
            yield Label("Mint Solana (opsional → mode paper Solana)")
            yield Input(self.cfg.solana_mint, id="mint")
            with Horizontal(classes="row"):
                with Vertical(classes="col"):
                    yield Label("Stop-loss")
                    yield Input(str(self.cfg.stop_loss_pct), id="sl", type="number")
                with Vertical(classes="col"):
                    yield Label("Take-profit")
                    yield Input(str(self.cfg.take_profit_pct), id="tp", type="number")
            with Horizontal(id="btnrow"):
                yield Button("▶ Backtest", id="backtest")
                yield Button("● Paper", id="paper")
                yield Button("■", id="stopbtn")
        with Vertical(id="main"):
            yield Static(self._summary(), id="summary")
            yield RichLog(id="log", markup=True, highlight=True, wrap=True)
        yield Footer()

    # ── util ────────────────────────────────────────────────────
    def _summary(self) -> str:
        c = self.cfg
        sl = f"{c.stop_loss_pct*100:g}%" if c.stop_loss_pct else "off"
        tp = f"{c.take_profit_pct*100:g}%" if c.take_profit_pct else "off"
        d = "  [#565f89]·[/]  "
        if c.solana_mint:
            pasar = f"[b #bb9af7]SOL {c.solana_mint[:4]}…{c.solana_mint[-4:]}[/]"
        else:
            pasar = f"[b]{c.symbol}[/]"
        return (f"[b #7aa2f7]◈ BOT TRADING[/]{d}modal [b]{c.starting_cash:g}[/]{d}"
                f"{pasar} [#565f89]·[/] {c.timeframe}{d}strategi [b #e0af68]{c.strategy.upper()}[/]"
                f"{d}SL [b]{sl}[/] · TP [b]{tp}[/]")

    def _refresh_summary(self) -> None:
        self.query_one("#summary", Static).update(self._summary())

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
            solana_mint=self.query_one("#mint", Input).value.strip())
        self._refresh_summary()

    @property
    def logbox(self) -> RichLog:
        return self.query_one("#log", RichLog)

    def on_mount(self) -> None:
        self.call_after_refresh(self._post_welcome)

    def _post_welcome(self) -> None:
        self._app_ready = True
        self.logbox.write("[#7aa2f7]Selamat datang![/] Atur di kiri, lalu klik "
                          "[b]▶ Backtest[/] (atau tekan [b]b[/]).")
        self.logbox.write("[#565f89]Backtest jalan offline. Paper trading butuh "
                          "koneksi + ccxt.[/]")

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
        self.logbox.write("")
        self.logbox.write(f"[b #9ece6a]▶ BACKTEST[/] · "
                          f"{build_strategy(self.cfg.strategy, self.cfg).describe()}")
        try:
            rep = run_backtest(synthetic_prices(n=500), self.cfg)
        except Exception as e:
            self.logbox.write(f"[b red]error:[/] {e}")
            return
        col = "#9ece6a" if rep.return_pct >= 0 else "#f7768e"
        bh = "#9ece6a" if rep.buy_hold_pct >= 0 else "#f7768e"
        self.logbox.write(f"  modal awal   : [b]{rep.starting_cash:.2f}[/]")
        self.logbox.write(f"  equity akhir : [b #e0af68]{rep.final_equity:.2f}[/]")
        self.logbox.write(f"  transaksi    : {rep.n_trades}   fee: {rep.total_fees:.4f}")
        self.logbox.write(f"  return       : [b {col}]{rep.return_pct:+.2f}%[/]   "
                          f"buy&hold: [{bh}]{rep.buy_hold_pct:+.2f}%[/]")
        self.logbox.write("[#565f89]  (backtest bukan jaminan hasil live)[/]")

    @on(Button.Pressed, "#paper")
    def action_paper(self) -> None:
        self._sync_cfg()
        if self._paper_running:
            self.logbox.write("[#e0af68]paper sudah berjalan.[/]")
            return
        if not self.cfg.solana_mint:
            try:
                import ccxt  # noqa: F401
            except ImportError:
                self.logbox.write("[b red]ccxt belum terpasang.[/] "
                                  "jalankan: pip install -r requirements.txt")
                return
        self._paper_running = True
        self.logbox.write("[b #7dcfff]● PAPER TRADING dimulai[/] "
                          "(tombol ■ / tekan x untuk stop)")
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
            self.call_from_thread(self.logbox.write, f"[b red]gagal start:[/] {e!r}")
            self._paper_running = False
            return
        while self._paper_running:
            try:
                closes = feed.fetch_closes(limit=strat.warmup + 3)
                price = feed.fetch_price()
                res = eng.step(closes, price)
                mark = (f"  [b #7dcfff]{res.executed.side} @ {price:.2f}[/] "
                        f"({res.executed.reason})" if res.executed else "")
                self.call_from_thread(
                    self.logbox.write,
                    f"[#565f89]{_t.strftime('%H:%M:%S')}[/] harga=[b]{price:.2f}[/] "
                    f"sinyal={res.decision.action} equity=[#e0af68]{res.equity:.4f}[/]{mark}")
            except Exception as e:
                self.call_from_thread(self.logbox.write, f"[red]tick error:[/] {e!r}")
            for _ in range(cfg.poll_interval_sec):
                if not self._paper_running:
                    break
                _t.sleep(1)

    @on(Button.Pressed, "#stopbtn")
    def action_stop(self) -> None:
        if self._paper_running:
            self._paper_running = False
            self.logbox.write("[#f7768e]■ paper dihentikan.[/]")

    def action_status(self) -> None:
        import json, os
        self._sync_cfg()
        self.logbox.write("[b]— status —[/]")
        if os.path.exists(self.cfg.state_file):
            with open(self.cfg.state_file) as fh:
                st = json.load(fh)
            self.logbox.write(f"  cash={st.get('cash',0):.4f} "
                              f"position={st.get('position',0):.8f}")
        else:
            self.logbox.write("  belum ada state.")


def run_tui(cfg: Config) -> None:
    BotTUI(cfg).run()
