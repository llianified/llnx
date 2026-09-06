"""llnx full-screen TUI: minimal, lowercase, no icons, muted colours.

The output pane fills the top of the screen and the settings sit in a bar at
the bottom, so the layout works the same in landscape and portrait. The bar
reflows to the terminal size: four columns of fields on wide screens, two on
phones, and shorter widgets when the terminal is short.

The run button drives the same loop as the CLI (`llnx.runner.run_live`), so
whatever mode is selected -- paper, sandbox or live -- the orders go through
the executor and its guardrails. Live mode asks you to type the phrase first.

Needs: pip install textual   |   run: llnx
"""
from __future__ import annotations

from textual import events, on, work
from textual.app import App, ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from rich.markup import escape
from textual.widgets import (Button, Footer, Header, Input, Label, RichLog,
                             Select, Static)

from .backtest import run_backtest, synthetic_prices
from .chains import CHAINS
from .config import Config, MODES
from .execution import read_journal
from .runner import CONFIRM_PHRASE, run_live
from .strategies import build_strategy

# muted palette (little colour, low saturation)
A = "#8a9aa0"     # slate accent
V = "#c9cdd6"     # values (soft)
DIM = "#6b6f78"   # dimmed
POS = "#86a789"   # muted green
NEG = "#b08a8a"   # muted red
MAUVE = "#9b93b0" # chain marker
WARN = "#c9b273"  # muted amber

STRATEGY_LABELS = {
    "sma": "sma · crossover",
    "rsi": "rsi · oversold/overbought",
    "grid": "grid · dca",
}
MODE_LABELS = {
    "paper": "paper · simulated",
    "sandbox": "sandbox · testnet",
    "live": "live · real money",
}
TIMEFRAMES = ("1m", "5m", "15m", "1h", "4h")
TOKEN_LABEL = "token address (optional → dex mode)"
TOKEN_LABEL_SHORT = "token address (optional)"

# from this width up the settings bar uses four columns instead of two
WIDE_COLS = 96
# below this width the footer drops the command-palette hint to save room
NARROW_COLS = 78
# below this height widgets lose their borders and shrink to one line
COMPACT_ROWS = 28
# below this height the summary line and frames are dropped as well
SHORT_ROWS = 22
# below this height the settings bar is hidden on its own (press t to show it)
TINY_ROWS = 16
# fields in the settings grid (the token address gets its own row below them)
FIELD_COUNT = 8
# the settings bar never shrinks below this, it would hide the buttons
MIN_PANEL_ROWS = 6
# log lines kept around so they can be re-wrapped when the terminal resizes
LOG_HISTORY = 500


class WrapLog(RichLog):
    """A log that remembers its lines and re-wraps them when the width changes.

    RichLog wraps text once, when it is written, so rotating a phone would
    otherwise leave every old line clipped at the previous width.
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        # RichLog wraps at 78 columns by default, which clips on a phone.
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


class ConfirmLive(ModalScreen[bool]):
    """Live mode is one typed phrase away, never one stray click."""

    CSS = """
    ConfirmLive { align: center middle; background: #17181c 70%; }
    #confirm { width: 60; max-width: 90%; height: auto; padding: 1 2;
               background: #1d1e24; border: round #b08a8a; }
    #confirm Label { color: #c4b9b9; padding: 0; height: auto; }
    #confirm Input { margin-top: 1; }
    """

    BINDINGS = [("escape", "cancel", "cancel")]

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm"):
            yield Label("live mode places real orders with real money.\n"
                        f"type {CONFIRM_PHRASE} to continue, or press esc.")
            yield Input(placeholder=CONFIRM_PHRASE, id="phrase")

    def on_mount(self) -> None:
        self.query_one("#phrase", Input).focus()

    @on(Input.Submitted, "#phrase")
    def _submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value.strip().upper() == CONFIRM_PHRASE)

    def action_cancel(self) -> None:
        self.dismiss(False)


class LlnxTUI(App):
    TITLE = "llnx"
    SUB_TITLE = "auto-execute · paper · sandbox · live"

    CSS = """
    Screen { background: #17181c; layout: vertical; }
    * { scrollbar-size-vertical: 1; scrollbar-size-horizontal: 1;
        scrollbar-background: #17181c; scrollbar-background-hover: #17181c;
        scrollbar-background-active: #17181c; scrollbar-color: #2c2e36;
        scrollbar-color-hover: #3a3d47; scrollbar-color-active: #4a4e59; }
    HeaderIcon { visibility: hidden; }
    Header { background: #1d1e24; color: #8a9aa0; }
    Footer { background: #1d1e24; }
    FooterKey { background: #1d1e24; color: #6b6f78; }
    FooterKey > .footer-key--key { color: #8a9aa0; background: #1d1e24; }
    FooterKey > .footer-key--description { color: #6b6f78; background: #1d1e24; }

    /* ── output on top ──────────────────────────────────────────── */
    #main { height: 1fr; padding: 0 1; }
    #summary { height: auto; padding: 0 2; margin-bottom: 1;
               background: #1d1e24; border: round #2c2e36; color: #b4b8c0; }
    #log { background: #14151a; border: round #2c2e36; padding: 0 1; }

    /* ── settings bar at the bottom ─────────────────────────────── */
    #panel { padding: 1 2 0 2; background: #1d1e24; border-top: solid #2c2e36; }
    #panel.hidden { display: none; }
    #fields { height: 1fr; layout: grid; grid-size: 2; grid-rows: auto;
              grid-gutter: 0 3; }
    .field { height: auto; }
    Label { color: #6b6f78; padding: 0 1; height: 1; }
    Input { height: 1; border: none; padding: 0 1;
            background: #14151a; color: #b4b8c0; }
    Input:focus { background: #23252c; color: #d7dbe2; }
    Select { height: 1; }
    Select > SelectCurrent { border: none; height: 1; padding: 0 1;
                             background: #14151a; color: #b4b8c0; }
    Select:focus > SelectCurrent { background: #23252c; }

    #actions { height: auto; layout: grid; grid-size: 2; grid-rows: auto;
               grid-gutter: 1 3; padding: 1 0; }
    Button { border: none; width: 1fr; min-width: 0; height: 1;
             color: #b4b8c0; background: #23252c; }
    Button:hover { background: #2b2e37; }
    #backtest { background: #263029; color: #c6d2c8; }
    #run { background: #24272e; color: #bcc1c9; }
    #run.-live { background: #3a2a2b; color: #d8c3c3; }
    #check { background: #24262d; color: #bcc1c9; }
    #stopbtn { background: #2c2526; color: #c4b9b9; }

    /* ── wide terminal: four columns of fields, one row of buttons ─ */
    Screen.-wide #fields { grid-size: 4; }
    Screen.-wide #actions { grid-size: 4; }

    /* ── short terminal: tighter spacing ─────────────────────────── */
    Screen.-compact #panel { padding: 0 2; }
    Screen.-compact #actions { padding: 1 0 0 0; }
    Screen.-narrow FooterKey.-command-palette { display: none; }

    /* ── very short terminal: drop the frames ────────────────────── */
    Screen.-short #main { padding: 0; }
    Screen.-short #log { border: none; padding: 0 1; }
    Screen.-short #panel { padding: 0 1; }
    """

    BINDINGS = [
        ("b", "backtest", "backtest"),
        ("r", "run", "run"),
        ("c", "check", "check"),
        ("s", "status", "status"),
        ("x", "stop", "stop"),
        ("t", "toggle_panel", "settings"),
        ("q", "quit", "quit"),
    ]

    def __init__(self, cfg: Config) -> None:
        super().__init__()
        self.cfg = cfg
        self._trading = False
        self._app_ready = False
        self._wide = None      # set on the first layout pass
        self._compact = None
        self._short = None
        self._narrow = None
        self._auto_hidden = False

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical(id="main"):
            yield Static(self._summary(), id="summary")
            yield WrapLog(id="log", markup=True, highlight=False, wrap=True)
        with Vertical(id="panel"):
            with VerticalScroll(id="fields"):
                with Vertical(classes="field"):
                    yield Label("mode")
                    yield Select([(MODE_LABELS[m], m) for m in MODES],
                                 value=self.cfg.mode, id="mode", allow_blank=False)
                with Vertical(classes="field"):
                    yield Label("cash ($)")
                    yield Input(str(self.cfg.starting_cash), id="cash", type="number")
                with Vertical(classes="field"):
                    yield Label("pair")
                    yield Input(self.cfg.symbol.lower(), id="symbol")
                with Vertical(classes="field"):
                    yield Label("timeframe")
                    yield Select([(t, t) for t in TIMEFRAMES], value=self.cfg.timeframe,
                                 id="timeframe", allow_blank=False)
                with Vertical(classes="field"):
                    yield Label("strategy")
                    yield Select([(STRATEGY_LABELS[n], n) for n in STRATEGY_LABELS],
                                 value=self.cfg.strategy, id="strategy",
                                 allow_blank=False)
                with Vertical(classes="field"):
                    yield Label("chain")
                    yield Select([(CHAINS[c].name.lower(), c) for c in CHAINS],
                                 value=self.cfg.chain, id="chain", allow_blank=False)
                with Vertical(classes="field"):
                    yield Label("stop-loss")
                    yield Input(str(self.cfg.stop_loss_pct), id="sl", type="number")
                with Vertical(classes="field"):
                    yield Label("take-profit")
                    yield Input(str(self.cfg.take_profit_pct), id="tp", type="number")
            with Vertical(id="token", classes="field"):
                yield Label(TOKEN_LABEL, id="token_label")
                yield Input(self.cfg.token_address, id="token_address")
            with Vertical(id="actions"):
                yield Button("backtest", id="backtest")
                yield Button("run", id="run")
                yield Button("check", id="check")
                yield Button("stop", id="stopbtn")
        yield Footer()

    # ── responsive layout ───────────────────────────────────────
    def _apply_layout(self, width: int, height: int) -> None:
        wide = width >= WIDE_COLS        # four columns of fields
        narrow = width < NARROW_COLS     # phone width: trim the footer
        compact = height < COMPACT_ROWS  # one-line widgets
        short = height < SHORT_ROWS      # no frames around the output
        state = (wide, narrow, compact, short)
        changed = state != (self._wide, self._narrow, self._compact, self._short)
        if changed:
            self._wide, self._narrow, self._compact, self._short = state
            self.screen.set_class(wide, "-wide")
            self.screen.set_class(narrow, "-narrow")
            self.screen.set_class(compact, "-compact")
            self.screen.set_class(short, "-short")
            self._relabel()
            self._refresh_summary()
        self._resize_panel(height)

    def _panel_rows(self, height: int) -> int:
        """How tall the settings bar may be, in rows.

        It asks for what its fields need and never takes more than half the
        screen; if capped, the fields scroll and the buttons stay put.
        """
        columns = 4 if self._wide else 2
        field_rows = -(-FIELD_COUNT // columns) + 1  # ceil, +1 = token address
        buttons = 1 if self._wide else 3             # one row, or two + gutter
        chrome = 4 if self._compact else 5           # border, padding, spare
        wanted = field_rows * 2 + buttons + chrome   # each field: label + value
        return max(MIN_PANEL_ROWS, min(wanted, height // 2))

    def _resize_panel(self, height: int) -> None:
        panel = self.query("#panel")
        if panel:
            panel.first().styles.height = self._panel_rows(height)
        self._auto_hide_panel(height)

    def _relabel(self) -> None:
        """Shorten the wordy labels when the terminal is narrow."""
        label = self.query("#token_label")
        if label:
            label.first(Label).update(TOKEN_LABEL if self._wide else TOKEN_LABEL_SHORT)
        self._relabel_select("#strategy", STRATEGY_LABELS)
        self._relabel_select("#mode", MODE_LABELS)

    def _relabel_select(self, selector: str, labels: dict) -> None:
        node = self.query(selector)
        if not node:
            return
        select = node.first(Select)
        names = list(labels)
        current = select.value if select.value in names else names[0]
        select.set_options([(labels[n] if self._wide else n, n) for n in names])
        # set_options keeps the old text on screen when the value does not
        # change, so move the value away and back to redraw it
        select.value = next(n for n in names if n != current)
        select.value = current

    def _auto_hide_panel(self, height: int) -> None:
        """On a very short terminal the bar would leave no room for output."""
        panel = self.query("#panel")
        if not panel:
            return
        panel = panel.first()
        if height < TINY_ROWS and not panel.has_class("hidden"):
            panel.add_class("hidden")
            self._auto_hidden = True
            if self._app_ready:
                self._log(f"[{DIM}]screen is very short — settings hidden, "
                          "press t to show them.[/]")
        elif height >= TINY_ROWS and self._auto_hidden:
            panel.remove_class("hidden")
            self._auto_hidden = False
        self._sync_summary()

    def _sync_summary(self) -> None:
        """The summary only earns its row while the settings bar is hidden."""
        summary, panel = self.query("#summary"), self.query("#panel")
        if summary and panel:
            summary.first(Static).display = panel.first().has_class("hidden")

    def on_resize(self, event: events.Resize) -> None:
        self._apply_layout(event.size.width, event.size.height)

    def action_toggle_panel(self) -> None:
        panel = self.query_one("#panel")
        panel.toggle_class("hidden")
        self._auto_hidden = False
        self._sync_summary()
        if panel.has_class("hidden"):
            self._log(f"[{DIM}]settings hidden (press t to show them).[/]")
        else:
            self.query_one("#cash", Input).focus()

    # ── helpers ─────────────────────────────────────────────────
    def _market(self) -> str:
        c = self.cfg
        if c.token_address:
            a = c.token_address
            short = f"{a[:4]}…{a[-4:]}" if len(a) > 10 else a
            return f"[{MAUVE}]{c.chain} {short}[/]"
        return f"[{V}]{c.symbol.lower()}[/]"

    def _mode_tag(self) -> str:
        colour = {"paper": DIM, "sandbox": WARN, "live": NEG}[self.cfg.mode]
        auto = "" if self.cfg.auto_execute else " (signals only)"
        return f"[{colour}]{self.cfg.mode}{auto}[/]"

    def _summary(self) -> str:
        c = self.cfg
        sl = f"{c.stop_loss_pct*100:g}%" if c.stop_loss_pct else "off"
        tp = f"{c.take_profit_pct*100:g}%" if c.take_profit_pct else "off"
        d = f"  [{DIM}]·[/]  "
        if not self._wide:  # two short lines instead of one long, wrapped one
            return (f"{self._mode_tag()} [{DIM}]·[/] {self._market()} [{DIM}]·[/] "
                    f"{c.timeframe} [{DIM}]·[/] [{A}]{c.strategy}[/]\n"
                    f"[{DIM}]cash[/] [{V}]{c.starting_cash:g}[/] [{DIM}]·[/] "
                    f"sl [{V}]{sl}[/] [{DIM}]·[/] tp [{V}]{tp}[/]")
        return (f"[{A}]llnx[/]{d}{self._mode_tag()}{d}cash [{V}]{c.starting_cash:g}[/]{d}"
                f"{self._market()} [{DIM}]·[/] {c.timeframe}{d}strategy "
                f"[{A}]{c.strategy}[/]{d}sl [{V}]{sl}[/] · tp [{V}]{tp}[/]")

    def _refresh_summary(self) -> None:
        summary = self.query("#summary")   # not there yet during the first compose
        if summary:
            summary.first(Static).update(self._summary())

    def _sync_cfg(self) -> None:
        def num(selector, default):
            try:
                return float(self.query_one(selector, Input).value)
            except (ValueError, Exception):
                return default
        self.cfg = self.cfg.with_overrides(
            starting_cash=num("#cash", self.cfg.starting_cash),
            symbol=(self.query_one("#symbol", Input).value or self.cfg.symbol).upper(),
            timeframe=self.query_one("#timeframe", Select).value,
            strategy=self.query_one("#strategy", Select).value,
            mode=self.query_one("#mode", Select).value,
            stop_loss_pct=num("#sl", 0.0),
            take_profit_pct=num("#tp", 0.0),
            chain=self.query_one("#chain", Select).value,
            token_address=self.query_one("#token_address", Input).value.strip())
        self._refresh_summary()
        self._mark_live()

    def _mark_live(self) -> None:
        """The run button wears the mode, so live never looks like paper."""
        button = self.query("#run")
        if button:
            button.first(Button).set_class(self.cfg.mode == "live", "-live")

    @property
    def logbox(self) -> WrapLog:
        return self.query_one("#log", WrapLog)

    def _log(self, line: str = "") -> None:
        self.logbox.log_line(line)

    def on_mount(self) -> None:
        self._apply_layout(self.size.width, self.size.height)
        self._mark_live()
        self.call_after_refresh(self._post_welcome)

    def _post_welcome(self) -> None:
        self._app_ready = True
        self._log(f"[{A}]llnx.[/] set things up below, then backtest (b) or "
                  "run (r).")
        self._log(f"[{DIM}]run executes orders for real in the selected mode. "
                  "paper is simulated, live is not.[/]")

    # ── actions ─────────────────────────────────────────────────
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
        self._log(f"  [{DIM}]start cash  [/] [{V}]{rep.starting_cash:.2f}[/]")
        self._log(f"  [{DIM}]final equity[/] [{V}]{rep.final_equity:.2f}[/]")
        self._log(f"  [{DIM}]trades      [/] {rep.n_trades}   "
                  f"[{DIM}]fees[/] {rep.total_fees:.4f}")
        self._log(f"  [{DIM}]return      [/] [{col}]{rep.return_pct:+.2f}%[/]   "
                  f"[{DIM}]buy&hold[/] [{bh}]{rep.buy_hold_pct:+.2f}%[/]")
        self._log(f"[{DIM}]  (a backtest is no promise of live results)[/]")

    @on(Button.Pressed, "#run")
    def action_run(self) -> None:
        self._sync_cfg()
        if self._trading:
            self._log(f"[{DIM}]already running (stop button / press x).[/]")
            return
        if self.cfg.mode == "live":
            self.push_screen(ConfirmLive(), self._live_confirmed)
        else:
            self._start_run()

    def _live_confirmed(self, ok: bool) -> None:
        if ok:
            self._start_run(confirmed=True)
        else:
            self._log(f"[{DIM}]live mode cancelled — nothing was sent.[/]")

    def _start_run(self, confirmed: bool = False) -> None:
        self._trading = True
        colour = NEG if self.cfg.mode == "live" else A
        self._log("")
        self._log(f"[{colour}]{self.cfg.mode} run started[/] "
                  f"[{DIM}](stop button / press x)[/]")
        self._run_worker(confirmed)

    @work(thread=True, exclusive=True)
    def _run_worker(self, confirmed: bool = False) -> None:
        """One worker for every mode -- it drives the same loop as the CLI."""
        def log(line: str = "") -> None:
            # runner output is plain text and full of [tags], so it is escaped
            self.call_from_thread(self._log, escape(str(line)))

        try:
            run_live(self.cfg, confirmed=confirmed, log=log,
                     should_run=lambda: self._trading)
        except SystemExit as e:
            log(f"stopped: {e}")
        except Exception as e:
            self.call_from_thread(self._log, f"[{NEG}]run failed:[/] {e!r}")
        finally:
            self._trading = False
            self.call_from_thread(self._log, f"[{DIM}]run finished.[/]")

    @on(Button.Pressed, "#check")
    def action_check(self) -> None:
        self._sync_cfg()
        if not self.cfg.token_address:
            self._log(f"[{DIM}]fill in a token address first to run a safety "
                      "check.[/]")
            return
        self._log("")
        self._log(f"[{A}]safety check[/] · {self.cfg.chain} · "
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
        if self._trading:
            self._trading = False
            self._log(f"[{NEG}]stopping after this tick...[/]")

    def action_status(self) -> None:
        import json, os
        self._sync_cfg()
        self._log("")
        self._log(f"[{A}]status[/] · {self._mode_tag()}")
        if os.path.exists(self.cfg.state_file):
            with open(self.cfg.state_file) as fh:
                st = json.load(fh)
            self._log(f"  [{DIM}]cash[/] {st.get('cash',0):.4f}   "
                      f"[{DIM}]position[/] {st.get('position',0):.8f}   "
                      f"[{DIM}]entry[/] {st.get('avg_entry',0):.6g}")
            session = st.get("session") or {}
            if session.get("trades_today"):
                self._log(f"  [{DIM}]today[/] {session['trades_today']} trades")
            if session.get("halt_reason"):
                self._log(f"  [{NEG}]halted:[/] {escape(session['halt_reason'])}")
        else:
            self._log(f"  [{DIM}]no saved state yet.[/]")
        rows = read_journal(self.cfg.orders_file, limit=5)
        if rows:
            self._log(f"  [{DIM}]last orders[/]")
        for r in rows:
            colour = {"filled": POS, "blocked": WARN, "failed": NEG}.get(
                r.get("status"), DIM)
            note = escape(r.get("reason") or r.get("error") or "")
            self._log(f"   [{colour}]{r.get('status','?'):<8}[/] "
                      f"{r.get('side','?').lower()} {r.get('amount',0):.6g} @ "
                      f"{r.get('price',0):.6g} [{DIM}]{note}[/]")


def run_tui(cfg: Config) -> None:
    LlnxTUI(cfg).run()
