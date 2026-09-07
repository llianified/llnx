"""llnx full-screen TUI: quiet colours, lowercase, no icons.

Three bands, always in the same place:

  status   what the bot is and what it holds -- mode, market, equity, position
  log      one row per poll, and every order in full
  settings the bar at the bottom; press t to fold it away

The run button drives the same loop as the CLI (`llnx.runner.run_live`), so
whatever mode is selected -- paper, sandbox or live -- the orders go through
the executor and its guardrails. Live mode asks you to type the phrase first.

The layout reflows to the terminal: four columns of settings on a desktop, two
on a phone, and shorter widgets when the screen is short.

Needs: pip install textual   |   run: llnx
"""
from __future__ import annotations

import math

from rich.markup import escape
from textual import events, on, work
from textual.app import App, ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import (Button, Footer, Header, Input, Label, RichLog,
                             Select, Static)

from .backtest import run_backtest, synthetic_prices
from .chains import CHAINS
from .config import MODES, Config
from .execution import read_journal
from .runner import CONFIRM_PHRASE, run_live
from .strategies import build_strategy

# muted palette: one accent, everything else greyed back
A = "#8fa6b2"      # accent (slate)
V = "#d3d7df"      # values
MUTED = "#8a8f99"  # values on a quiet row
DIM = "#6a6f7a"    # labels and chrome
POS = "#84a98c"    # muted green
NEG = "#b08a8a"    # muted red
WARN = "#c7b078"   # muted amber
MAUVE = "#9b93b0"  # chain marker

MODE_LABELS = {
    "paper": "paper · simulated",
    "sandbox": "sandbox · testnet",
    "live": "live · real money",
}
MODE_COLOURS = {"paper": DIM, "sandbox": WARN, "live": NEG}
STRATEGY_LABELS = {
    "sma": "sma · crossover",
    "ema": "ema · trend filter",
    "breakout": "breakout · donchian",
    "rsi": "rsi · oversold/overbought",
    "grid": "grid · dca",
}
TIMEFRAMES = ("1m", "5m", "15m", "1h", "4h")

# The settings are one screen per subject, not one long pile. A phone has no
# room for thirty fields, and a bar you have to scroll is a bar you misread.
SECTIONS = ("market", "trading", "strategy", "exits", "limits")
SECTION_TABS = {"market": "market", "trading": "trading", "strategy": "strategy",
                "exits": "exits", "limits": "limits"}
SECTION_NOTES = {
    "market": "one market at a time",
    "trading": "",
    "exits": "0 = off",
    "limits": "0 = off",
}

# Two markets, and only one is ever live. It is a choice you make here, not
# something inferred from whether another field happens to be filled in.
MARKET_LABELS = {"exchange": "exchange · a pair", "dex": "dex · a token address"}

# Every field says what it is in one line, shown while it has focus. A settings
# bar full of bare numbers -- 0.05, 60, 0.0 -- is a quiz, not an interface.
HINTS = {
    "market": "what you trade: a pair on an exchange, or one token on a chain.",
    "symbol": "the exchange pair. the left side is what you hold, the right is "
              "what you pay with.",
    "chain": "which network the token address below lives on.",
    "token_address": "paste the token's address. this is what gets traded.",
    "timeframe": "candle size the strategy reads. smaller = more signals, more "
                 "noise, more fees.",
    "mode": "paper: pretend money. sandbox: exchange testnet. live: real orders "
            "with real money.",
    "strategy": "when to buy and sell. `llnx optimize` searches its settings for "
                "you.",
    "cash": "capital to work with. in live mode your real exchange or wallet "
            "balance wins.",
    "poll": "seconds between price checks. the bot can never trade faster than "
            "this.",
    "sl": "sell if the price drops this far below your entry. 0 = off.",
    "tp": "sell once you are this far up. 0 = off — a trailing stop usually "
          "earns more.",
    "trail": "sell this far below the highest price since you bought. lets a "
             "winner keep running.",
    "max_order": "the largest single order, as a share of your equity. 0 = no cap.",
    "daily_loss": "stop buying for the rest of the day after losing this much. "
                  "selling still works.",
    "cooldown": "seconds the bot must wait after one order before the next.",
    "max_trades": "most orders it may place in one day. 0 = unlimited.",
    "sma_fast": "the quick average. it crosses the slow one to trigger a trade.",
    "sma_slow": "the slow average. further apart = fewer, later signals.",
    "ema_fast": "the quick average. reacts sooner than an sma of the same length.",
    "ema_slow": "the slow average it has to cross.",
    "ema_trend": "the filter: it only buys while the price is above this average.",
    "breakout_entry": "buy when the price closes above the high of this many candles.",
    "breakout_exit": "sell when it closes below the low of this many candles.",
    "breakout_atr_mult": "sell this many average moves below the peak. bigger = "
                         "more room to breathe.",
    "rsi_period": "how many candles the rsi looks back over.",
    "rsi_oversold": "buy when rsi falls under this. lower = rarer, deeper dips.",
    "rsi_overbought": "sell when rsi rises above this.",
    "grid_step_pct": "buy again each time the price falls this much below your "
                     "last buy.",
    "grid_take_profit_pct": "sell everything once the price is this far above your "
                            "average entry.",
    "grid_max_steps": "how many pieces the cash is split into.",
}

# Which knobs belong to which strategy. Only the chosen one is ever on screen:
# an rsi period sitting next to a grid step is how a settings bar stops making
# sense.
STRATEGY_FIELDS = {
    "sma": ("sma_fast", "sma_slow"),
    "ema": ("ema_fast", "ema_slow", "ema_trend"),
    "breakout": ("breakout_entry", "breakout_exit", "breakout_atr_mult"),
    "rsi": ("rsi_period", "rsi_oversold", "rsi_overbought"),
    "grid": ("grid_step_pct", "grid_take_profit_pct", "grid_max_steps"),
}
STRATEGY_CAPTIONS = {
    "sma": "sma · two averages crossing",
    "ema": "ema · two averages, plus a trend filter",
    "breakout": "breakout · a channel and a volatility stop",
    "rsi": "rsi · buy the dip, sell the rip",
    "grid": "grid · buy the way down, sell the bounce",
}
FIELD_LABELS = {
    "sma_fast": "fast average", "sma_slow": "slow average",
    "ema_fast": "fast ema", "ema_slow": "slow ema", "ema_trend": "trend filter ema",
    "breakout_entry": "buy above (candles)", "breakout_exit": "sell below (candles)",
    "breakout_atr_mult": "volatility stop (x)",
    "rsi_period": "rsi period", "rsi_oversold": "buy under", "rsi_overbought":
    "sell over",
    "grid_step_pct": "step down (%)", "grid_take_profit_pct": "target (+%)",
    "grid_max_steps": "steps",
}
# percentages are entered as percentages here, not as 0.05
SECTION_HINTS = {
    "market": "what you trade: a pair on an exchange, or one token on a chain.",
    "trading": "the money, the mode and the strategy it runs.",
    "strategy": "the numbers behind the strategy you picked in `trading`.",
    "exits": "how a position ends. these apply to every strategy.",
    "limits": "the brakes. they stop the bot buying, never selling.",
}
PERCENT_FIELDS = ("sl", "tp", "trail", "max_order", "daily_loss",
                  "grid_step_pct", "grid_take_profit_pct")
INTEGER_FIELDS = ("sma_fast", "sma_slow", "ema_fast", "ema_slow", "ema_trend",
                  "breakout_entry", "breakout_exit", "rsi_period", "grid_max_steps")

# from this width up the settings bar uses four columns instead of two
WIDE_COLS = 96
# below this width the footer drops the command-palette hint to save room
NARROW_COLS = 78
# below this height widgets lose their borders and shrink to one line
COMPACT_ROWS = 28
# below this height the status folds to one line and the frames are dropped
SHORT_ROWS = 22
# below this height the settings bar is hidden on its own (press t to show it)
TINY_ROWS = 16
# the settings bar never shrinks below this, it would hide the buttons
MIN_PANEL_ROWS = 6
# ...and never grows so far that the output has less than this left
MIN_LOG_ROWS = 10
# header, status band and footer, which the settings bar does not get either
CHROME_ROWS = 4
# log lines kept around so they can be re-wrapped when the terminal resizes
LOG_HISTORY = 500
# width of the price column in the log, so every row lines up
PRICE_WIDTH = 11
# below this many characters a reason is dropped rather than clipped to noise
MIN_REASON = 8


def format_price(price: float) -> str:
    """Prices readable at both ends of the market.

    A meme token trades at 0.0000182 and BTC at 68120.5; plain %g turns the
    first into 1.82e-05, which is unreadable in a scrolling log.
    """
    if price >= 1000:
        return f"{price:.2f}"
    if price >= 1:
        return f"{price:.4f}"
    if price >= 0.001:
        return f"{price:.6f}"
    if price <= 0:
        return "0"
    # keep three significant digits however small the token is
    decimals = min(12, -int(math.floor(math.log10(price))) + 2)
    return f"{price:.{decimals}f}"


def pct_in(fraction: float) -> str:
    """0.05 -> "5". Percentages are entered as percentages."""
    value = fraction * 100
    return f"{value:g}"


def pct_out(text: str, default: float = 0.0) -> float:
    """"5" or "5%" -> 0.05."""
    try:
        return float(text.strip().rstrip("%")) / 100
    except (AttributeError, ValueError):
        return default


def format_amount(amount: float) -> str:
    """Position sizes, from 0.00036 BTC to a million meme tokens."""
    if amount >= 1_000_000:
        return f"{amount / 1e6:.3g}M"
    if amount >= 1000:
        return f"{amount:,.0f}"
    return f"{amount:.6g}"


def clip(text: str, room: int) -> str:
    """Trim text to `room` characters so a log row never wraps."""
    if room < 4:
        return ""
    return text if len(text) <= room else text[:room - 1] + "…"


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

    def clear_all(self) -> None:
        """Empty the log for good: the history goes too, or a resize brings
        every cleared line back."""
        self._history.clear()
        self.clear()

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
    ConfirmLive { align: center middle; background: #131418 75%; }
    #confirm { width: 58; max-width: 90%; height: auto; padding: 1 2;
               background: #1a1b21; border: round #b08a8a; }
    #confirm Label { color: #c4b9b9; padding: 0; height: auto; }
    #confirm Input { margin-top: 1; background: #101115; color: #d3d7df;
                     border: none; height: 1; padding: 0 1; }
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
    SUB_TITLE = "auto-execute"

    CSS = """
    Screen { background: #131418; layout: vertical; color: #b9bec8; }
    * { scrollbar-size-vertical: 1; scrollbar-size-horizontal: 1;
        scrollbar-background: #131418; scrollbar-background-hover: #131418;
        scrollbar-background-active: #131418; scrollbar-color: #272932;
        scrollbar-color-hover: #363945; scrollbar-color-active: #454956; }
    HeaderIcon { visibility: hidden; }
    Header { background: #1a1b21; color: #8fa6b2; }
    Footer { background: #1a1b21; }
    FooterKey { background: #1a1b21; color: #6a6f7a; }
    FooterKey > .footer-key--key { color: #8fa6b2; background: #1a1b21; }
    FooterKey > .footer-key--description { color: #6a6f7a; background: #1a1b21; }

    /* ── status and output ──────────────────────────────────────── */
    #main { height: 1fr; }
    #status { height: auto; padding: 1 2 0 2; background: #131418;
              color: #b9bec8; }
    #log { background: #101115; border-top: solid #272932; padding: 1 2;
           height: 1fr; }

    /* ── settings bar at the bottom ─────────────────────────────── */
    #panel { height: auto; padding: 1 2 0 2; background: #1a1b21;
             border-top: solid #272932; }
    #panel.hidden { display: none; }
    #tabs { height: 1; layout: grid; grid-size: 5; grid-rows: 1;
            grid-gutter: 0 1; margin-bottom: 1; }
    .tab { height: 1; border: none; width: 1fr; min-width: 0;
           background: #1a1b21; color: #6a6f7a; text-style: none; }
    .tab:hover { background: #23252c; color: #b9bec8; }
    .tab.-on { background: #23252c; color: #d3d7df; }
    #fields { height: auto; max-height: 100%; padding-bottom: 1; }
    .section { height: auto; }
    .section.hidden { display: none; }
    .row { height: auto; layout: grid; grid-size: 2; grid-rows: auto;
           grid-gutter: 0 3; }
    .field { height: auto; }
    .field.hidden { display: none; }
    .caption { height: 1; color: #565a62; padding: 0 1; }
    #hint { height: auto; min-height: 1; color: #7a8089; padding: 0 1;
            border-top: solid #23252c; }
    Label { color: #6a6f7a; padding: 0 1; height: 1; }
    .field.-off Label { color: #4b4e56; }
    .field.-off Input { color: #565a62; }
    .field.-off Select > SelectCurrent { color: #565a62; }
    Input { height: 1; border: none; padding: 0 1;
            background: #101115; color: #b9bec8; }
    Input:focus { background: #23252c; color: #d3d7df; }
    Select { height: 1; }
    Select > SelectCurrent { border: none; height: 1; padding: 0 1;
                             background: #101115; color: #b9bec8; }
    Select:focus > SelectCurrent { background: #23252c; color: #d3d7df; }
    SelectOverlay { border: round #272932; background: #1a1b21; }

    #actions { height: auto; layout: grid; grid-size: 2; grid-rows: auto;
               grid-gutter: 1 3; padding: 1 0; }
    Button { border: none; width: 1fr; min-width: 0; height: 1;
             color: #b9bec8; background: #23252c; }
    Button:hover { background: #2c2f38; }
    #run { background: #26333a; color: #cfdde3; }
    #run.-live { background: #3a2a2b; color: #dcc5c5; }
    #stopbtn { color: #a89b9b; }

    /* ── wide terminal: four columns of fields, one row of buttons ─ */
    Screen.-wide .row { grid-size: 4; }
    Screen.-narrow #tabs { height: auto; grid-size: 3; grid-rows: 1;
                           grid-gutter: 1 1; }
    Screen.-wide #actions { grid-size: 5; }

    /* ── short terminal: tighter spacing ─────────────────────────── */
    Screen.-compact #panel { padding: 0 2; }
    Screen.-compact #actions { padding: 1 0 0 0; }
    Screen.-narrow FooterKey.-command-palette { display: none; }

    /* a short screen pays for every row: lose the gutters and the hint */
    Screen.-compact #tabs { margin-bottom: 0; grid-gutter: 0 1; }
    Screen.-compact #hint { display: none; }
    Screen.-compact #fields { padding-bottom: 0; }
    Screen.-compact #actions { grid-gutter: 0 2; padding: 0; }

    /* ── very short terminal: drop the padding ───────────────────── */
    Screen.-short #status { padding: 0 1; }
    Screen.-short #log { padding: 0 1; }
    Screen.-short #panel { padding: 0 1; }
    """

    BINDINGS = [
        ("b", "backtest", "backtest"),
        ("r", "run", "run"),
        ("c", "check", "check"),
        ("s", "status", "status"),
        ("x", "stop", "stop"),
        ("l", "clear", "clear"),
        ("t", "toggle_panel", "settings"),
        ("q", "quit", "quit"),
    ]

    def __init__(self, cfg: Config) -> None:
        super().__init__()
        self.cfg = cfg
        self._market = "dex" if cfg.token_address else "exchange"
        self._section = "market"          # which settings screen is showing
        self._saved_token = cfg.token_address   # kept while the pair is selected
        self._trading = False
        self._app_ready = False
        self._wide = None      # set on the first layout pass
        self._compact = None
        self._short = None
        self._narrow = None
        self._auto_hidden = False
        # live figures, filled in by the ticks
        self._equity = cfg.starting_cash
        self._cash = cfg.starting_cash
        self._position = 0.0
        self._entry = 0.0
        self._trades_today = 0

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical(id="main"):
            yield Static(self._status(), id="status")
            yield WrapLog(id="log", markup=True, highlight=False, wrap=True)
        with Vertical(id="panel"):
            with Vertical(id="tabs"):
                for name in SECTIONS:
                    yield Button(SECTION_TABS[name], id=f"tab_{name}",
                                 classes="tab")
            with VerticalScroll(id="fields"):
                with Vertical(id="section_market", classes="section"):
                    yield Static(SECTION_NOTES["market"], classes="caption")
                    with Vertical(classes="row"):
                        with Vertical(id="market_field", classes="field"):
                            yield Label("market")
                            yield Select([(MARKET_LABELS[m], m) for m in MARKET_LABELS],
                                         value=self._market, id="market",
                                         allow_blank=False)
                        with Vertical(id="pair_field", classes="field"):
                            yield Label("pair")
                            yield Input(self.cfg.symbol.lower(), id="symbol")
                        with Vertical(id="chain_field", classes="field"):
                            yield Label("chain")
                            yield Select([(CHAINS[c].name.lower(), c) for c in CHAINS],
                                         value=self.cfg.chain, id="chain",
                                         allow_blank=False)
                        with Vertical(classes="field"):
                            yield Label("candle size")
                            yield Select([(t, t) for t in TIMEFRAMES],
                                         value=self.cfg.timeframe, id="timeframe",
                                         allow_blank=False)
                    with Vertical(id="token", classes="field"):
                        yield Label("token address")
                        yield Input(self.cfg.token_address, id="token_address",
                                    placeholder="paste the mint / contract address")

                with Vertical(id="section_trading", classes="section"):
                    with Vertical(classes="row"):
                        with Vertical(classes="field"):
                            yield Label("mode")
                            yield Select([(MODE_LABELS[m], m) for m in MODES],
                                         value=self.cfg.mode, id="mode",
                                         allow_blank=False)
                        with Vertical(classes="field"):
                            yield Label("strategy")
                            yield Select([(STRATEGY_LABELS[n], n)
                                          for n in STRATEGY_LABELS],
                                         value=self.cfg.strategy, id="strategy",
                                         allow_blank=False)
                        with Vertical(id="cash_field", classes="field"):
                            yield Label("cash ($)")
                            yield Input(str(self.cfg.starting_cash), id="cash",
                                        type="number")
                        with Vertical(classes="field"):
                            yield Label("check every (s)")
                            yield Input(str(self.cfg.poll_interval_sec), id="poll",
                                        type="integer")

                with Vertical(id="section_strategy", classes="section"):
                    yield Static(STRATEGY_CAPTIONS[self.cfg.strategy],
                                 id="strategy_caption", classes="caption")
                    with Vertical(classes="row"):
                        for name in sum(STRATEGY_FIELDS.values(), ()):
                            with Vertical(id=f"{name}_field", classes="field"):
                                yield Label(FIELD_LABELS[name])
                                yield Input(self._strategy_value(name), id=name,
                                            type=("integer" if name in INTEGER_FIELDS
                                                  else "number"))

                with Vertical(id="section_exits", classes="section"):
                    yield Static(SECTION_NOTES["exits"], classes="caption")
                    with Vertical(classes="row"):
                        with Vertical(classes="field"):
                            yield Label("stop-loss (%)")
                            yield Input(pct_in(self.cfg.stop_loss_pct), id="sl",
                                        type="number")
                        with Vertical(classes="field"):
                            yield Label("take-profit (%)")
                            yield Input(pct_in(self.cfg.take_profit_pct), id="tp",
                                        type="number")
                        with Vertical(classes="field"):
                            yield Label("trailing stop (%)")
                            yield Input(pct_in(self.cfg.trailing_stop_pct), id="trail",
                                        type="number")

                with Vertical(id="section_limits", classes="section"):
                    yield Static(SECTION_NOTES["limits"], classes="caption")
                    with Vertical(classes="row"):
                        with Vertical(classes="field"):
                            yield Label("max order (%)")
                            yield Input(pct_in(self.cfg.max_order_pct), id="max_order",
                                        type="number")
                        with Vertical(classes="field"):
                            yield Label("daily loss (%)")
                            yield Input(pct_in(self.cfg.max_daily_loss_pct),
                                        id="daily_loss", type="number")
                        with Vertical(classes="field"):
                            yield Label("cooldown (s)")
                            yield Input(str(self.cfg.cooldown_sec), id="cooldown",
                                        type="integer")
                        with Vertical(classes="field"):
                            yield Label("trades / day")
                            yield Input(str(self.cfg.max_trades_per_day),
                                        id="max_trades", type="integer")
            yield Static(HINTS["market"], id="hint")
            with Vertical(id="actions"):
                yield Button("run", id="run")
                yield Button("backtest", id="backtest")
                yield Button("check", id="check")
                yield Button("stop", id="stopbtn")
                yield Button("clear", id="clearbtn")
        yield Footer()

    # ── responsive layout ───────────────────────────────────────
    def _apply_layout(self, width: int, height: int) -> None:
        wide = width >= WIDE_COLS        # four columns of fields
        narrow = width < NARROW_COLS     # phone width: trim the footer
        compact = height < COMPACT_ROWS  # one-line widgets
        short = height < SHORT_ROWS      # no padding, one-line status
        state = (wide, narrow, compact, short)
        changed = state != (self._wide, self._narrow, self._compact, self._short)
        if changed:
            self._wide, self._narrow, self._compact, self._short = state
            self.screen.set_class(wide, "-wide")
            self.screen.set_class(narrow, "-narrow")
            self.screen.set_class(compact, "-compact")
            self.screen.set_class(short, "-short")
            self._relabel()
            self._refresh_status()
        self._resize_panel(height)

    def _log_floor(self, height: int) -> int:
        """Rows the output keeps whatever the settings want. On a short screen
        it hands some of them back rather than leaving nothing readable."""
        return min(MIN_LOG_ROWS, max(4, height // 3))

    def _fit_panel(self, height: int) -> None:
        """The bar takes what this settings screen needs, and no more.

        Textual measures that -- the tab row wraps on a phone and the hint
        wraps with it, and arithmetic that tries to predict all of it ends up
        clipping the fields, which is the one thing it must not do. All we set
        is the ceiling, so the output always keeps its share of the screen.
        """
        panel = self.query("#panel")
        if panel:
            panel.first().styles.max_height = max(
                MIN_PANEL_ROWS, height - self._log_floor(height) - CHROME_ROWS)

    def _resize_panel(self, height: int) -> None:
        self._fit_panel(height)
        self._auto_hide_panel(height)

    def _relabel(self) -> None:
        """Shorten the wordy labels when the terminal is narrow."""
        self._apply_market()
        self._apply_strategy()
        self._apply_mode()
        self._apply_section()
        self._apply_section()
        self._relabel_select("#strategy", STRATEGY_LABELS)
        self._relabel_select("#mode", MODE_LABELS)
        self._relabel_select("#market", MARKET_LABELS)

    def _apply_section(self) -> None:
        """Only the settings screen you tapped is on show."""
        for name in SECTIONS:
            block = self.query(f"#section_{name}")
            if block:
                block.first().set_class(name != self._section, "hidden")
            tab = self.query(f"#tab_{name}")
            if tab:
                tab.first(Button).set_class(name == self._section, "-on")

    @on(Button.Pressed, ".tab")
    def _tab_pressed(self, event: Button.Pressed) -> None:
        self._section = (event.button.id or "tab_market")[len("tab_"):]
        self._apply_section()
        self._resize_panel(self.size.height)
        note = SECTION_HINTS.get(self._section, "")
        if note:
            self.query_one("#hint", Static).update(note)

    def _strategy_value(self, name: str) -> str:
        value = getattr(self.cfg, name)
        return pct_in(value) if name in PERCENT_FIELDS else f"{value:g}"

    def _apply_strategy(self) -> None:
        """Only the chosen strategy's knobs stay on screen."""
        wanted = STRATEGY_FIELDS[self.cfg.strategy]
        for name in sum(STRATEGY_FIELDS.values(), ()):
            field = self.query(f"#{name}_field")
            if field:
                field.first().set_class(name not in wanted, "hidden")
        caption = self.query("#strategy_caption")
        if caption:
            caption.first(Static).update(STRATEGY_CAPTIONS[self.cfg.strategy])

    def _apply_mode(self) -> None:
        """Hide the settings the chosen mode does not use.

        Cash is the bot's own money only while it keeps its own books. On a
        real exchange or a real wallet the balance is whatever the venue says
        it is, and a "cash" box you can type into would be a lie.
        """
        own_books = self.cfg.mode == "paper" or (self.cfg.mode == "sandbox"
                                                 and self._market == "dex")
        field = self.query("#cash_field")
        if field:
            field.first().set_class(not own_books, "hidden")

    def _apply_market(self) -> None:
        """Show the market you picked and hide the other one entirely.

        Dimming the unused half was not enough: a greyed-out `chain: solana`
        still looks like a setting that matters. Only one market can trade, so
        only one is on screen.
        """
        dex = self._market == "dex"
        for selector, hidden in (("#pair_field", dex),
                                 ("#chain_field", not dex),
                                 ("#token", not dex)):
            field = self.query(selector)
            if field:
                field.first().set_class(hidden, "hidden")

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

    def on_resize(self, event: events.Resize) -> None:
        self._apply_layout(event.size.width, event.size.height)

    def action_toggle_panel(self) -> None:
        panel = self.query_one("#panel")
        panel.toggle_class("hidden")
        self._auto_hidden = False
        if panel.has_class("hidden"):
            self._log(f"[{DIM}]settings hidden (press t to show them).[/]")
        else:
            self.query_one("#cash", Input).focus()

    # ── the status band ─────────────────────────────────────────
    def _market_text(self) -> str:
        """The market as the status band shows it: a pair, or a token on a chain."""
        c = self.cfg
        if self._market == "dex":
            if not c.token_address:
                return f"[{MAUVE}]{c.chain}[/] [{DIM}]· no token yet[/]"
            a = c.token_address
            short = f"{a[:4]}…{a[-4:]}" if len(a) > 10 else a
            return f"[{MAUVE}]{c.chain} {short}[/]"
        return f"[{V}]{c.symbol.lower()}[/]"

    def _mode_tag(self) -> str:
        colour = MODE_COLOURS[self.cfg.mode]
        auto = "" if self.cfg.auto_execute else " · signals only"
        return f"[{colour}]● {self.cfg.mode}{auto}[/]"

    def _pnl(self) -> str:
        start = self.cfg.starting_cash or 1.0
        pct = (self._equity / start - 1) * 100
        colour = POS if pct > 0 else (NEG if pct < 0 else DIM)
        return f"[{colour}]{pct:+.2f}%[/]"

    def _state_word(self) -> str:
        if self._trading:
            return f"[{A}]running[/]"
        return f"[{DIM}]idle[/]"

    def _status(self) -> str:
        c = self.cfg
        d = f" [{DIM}]·[/] "
        held = (f"[{DIM}]pos[/] [{V}]{format_amount(self._position)}[/]"
                if self._position else f"[{DIM}]flat[/]")
        if self._short:                      # one line, everything essential
            return (f"{self._mode_tag()}{d}{self._market_text()}{d}[{A}]{c.strategy}[/]"
                    f"{d}[{DIM}]equity[/] [{V}]{self._equity:.6g}[/] {self._pnl()}"
                    f"{d}{held}")
        first = (f"{self._mode_tag()}   {self._market_text()}{d}{c.timeframe}"
                 f"{d}[{A}]{c.strategy}[/]")
        money = (f"[{DIM}]equity[/] [{V}]{self._equity:.6g}[/] {self._pnl()}"
                 f"   [{DIM}]cash[/] [{V}]{self._cash:.6g}[/]   {held}")
        if self._wide:
            from .risk import RiskManager
            risk = RiskManager(c.stop_loss_pct, c.take_profit_pct,
                               c.trailing_stop_pct).describe().lower()
            first += f"   {self._state_word()}"
            money += (f"   [{DIM}]risk[/] {risk}"
                      f"   [{DIM}]today[/] {self._trades_today}")
        else:
            first += f"   {self._state_word()}"
        return f"{first}\n{money}"

    def _refresh_status(self) -> None:
        status = self.query("#status")   # not there yet during the first compose
        if status:
            status.first(Static).update(self._status())

    def _sync_cfg(self) -> None:
        def num(selector, default):
            try:
                return float(self.query_one(selector, Input).value)
            except (ValueError, Exception):
                return default

        def pct(selector, default=0.0):
            return pct_out(self.query_one(selector, Input).value, default)

        # the market select decides which half of the market group counts
        self._market = self.query_one("#market", Select).value
        token = self.query_one("#token_address", Input).value.strip()
        if self._market == "dex":
            self._saved_token = token
        else:
            token = ""            # the pair trades; the address is kept for later

        self.cfg = self.cfg.with_overrides(
            starting_cash=num("#cash", self.cfg.starting_cash),
            symbol=(self.query_one("#symbol", Input).value or self.cfg.symbol).upper(),
            timeframe=self.query_one("#timeframe", Select).value,
            strategy=self.query_one("#strategy", Select).value,
            mode=self.query_one("#mode", Select).value,
            poll_interval_sec=int(num("#poll", self.cfg.poll_interval_sec)),
            stop_loss_pct=pct("#sl"),
            take_profit_pct=pct("#tp"),
            trailing_stop_pct=pct("#trail"),
            max_order_pct=pct("#max_order"),
            max_daily_loss_pct=pct("#daily_loss"),
            cooldown_sec=int(num("#cooldown", self.cfg.cooldown_sec)),
            max_trades_per_day=int(num("#max_trades", self.cfg.max_trades_per_day)),
            chain=self.query_one("#chain", Select).value,
            token_address=token,
            **{name: (pct("#" + name) if name in PERCENT_FIELDS
                      else (int(num("#" + name, getattr(self.cfg, name)))
                            if name in INTEGER_FIELDS
                            else num("#" + name, getattr(self.cfg, name))))
               for name in sum(STRATEGY_FIELDS.values(), ())})
        if not self._trading:
            self._equity = self._cash = self.cfg.starting_cash
        self._refresh_status()
        self._mark_live()
        self._apply_market()
        self._apply_strategy()
        self._apply_mode()
        self._apply_section()

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
        self._log(f"[{A}]llnx[/] [{DIM}]· set up below, then run (r).[/]")
        self._log(f"[{DIM}]paper is simulated. live is not.[/]")
        self._log("")

    # ── actions ─────────────────────────────────────────────────
    @on(Select.Changed, "#market")
    def _market_changed(self, event: Select.Changed) -> None:
        """Switching back to dex puts the address you had typed back."""
        if not self._app_ready:
            return
        if event.value == "dex":
            field = self.query_one("#token_address", Input)
            if not field.value and self._saved_token:
                field.value = self._saved_token
        self._sync_cfg()
        self._resize_panel(self.size.height)

    @on(Select.Changed)
    @on(Input.Changed)
    def _on_change(self) -> None:
        if not self._app_ready:
            return
        self._sync_cfg()

    def on_descendant_focus(self, event: events.DescendantFocus) -> None:
        """One line under the settings, saying what the focused field does."""
        hint = HINTS.get(getattr(event.widget, "id", "") or "")
        box = self.query("#hint")
        if hint and box:
            box.first(Static).update(hint)

    @on(Button.Pressed, "#backtest")
    def action_backtest(self) -> None:
        self._sync_cfg()
        desc = build_strategy(self.cfg.strategy, self.cfg).describe().lower()
        self._log(f"[{A}]backtest[/] [{DIM}]· {desc}[/]")
        try:
            rep = run_backtest(synthetic_prices(n=500), self.cfg)
        except Exception as e:
            self._log(f"  [{NEG}]error[/] {escape(str(e))}")
            return
        col = POS if rep.return_pct >= 0 else NEG
        bh = POS if rep.buy_hold_pct >= 0 else NEG
        pf = "inf" if rep.profit_factor == float("inf") else f"{rep.profit_factor:.2f}"
        self._log(f"  [{DIM}]equity      [/] [{V}]{rep.starting_cash:.2f}[/] "
                  f"[{DIM}]→[/] [{V}]{rep.final_equity:.2f}[/]")
        self._log(f"  [{DIM}]return      [/] [{col}]{rep.return_pct:+.2f}%[/]   "
                  f"[{DIM}]buy&hold[/] [{bh}]{rep.buy_hold_pct:+.2f}%[/]")
        self._log(f"  [{DIM}]drawdown    [/] [{WARN}]{rep.max_drawdown_pct:.2f}%[/]   "
                  f"[{DIM}]exposure[/] {rep.exposure_pct:.0f}%")
        self._log(f"  [{DIM}]round trips [/] {rep.n_round_trips}   "
                  f"[{DIM}]win rate[/] {rep.win_rate_pct:.0f}%   "
                  f"[{DIM}]profit factor[/] {pf}")
        self._log(f"  [{DIM}]fees        [/] {rep.fees_pct:.2f}% of capital "
                  f"[{DIM}]({rep.n_trades} orders)[/]")
        self._log(f"  [{DIM}]synthetic data — fetch real candles before believing "
                  "it: llnx fetch[/]")
        self._log("")

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
            self._log(f"[{DIM}]live cancelled — nothing was sent.[/]")

    def _start_run(self, confirmed: bool = False) -> None:
        self._trading = True
        self._trades_today = 0
        colour = MODE_COLOURS[self.cfg.mode]
        self._log(f"[{colour}]{self.cfg.mode}[/] [{DIM}]· started "
                  "(stop button / press x)[/]")
        self._refresh_status()
        self._run_worker(confirmed)

    @work(thread=True, exclusive=True)
    def _run_worker(self, confirmed: bool = False) -> None:
        """One worker for every mode -- it drives the same loop as the CLI."""
        def log(line: str = "") -> None:
            # runner output is plain text and full of [tags], so it is escaped
            text = str(line).rstrip()
            if not text or set(text) <= {"=", " "}:      # its banner rules
                return
            self.call_from_thread(self._log, f"[{DIM}]{escape(text)}[/]")

        def tick(data: dict) -> None:
            self.call_from_thread(self._on_tick, data)

        try:
            run_live(self.cfg, confirmed=confirmed, log=log, on_tick=tick,
                     should_run=lambda: self._trading)
        except SystemExit as e:
            self.call_from_thread(self._log, f"[{NEG}]stopped[/] {escape(str(e))}")
        except Exception as e:
            self.call_from_thread(self._log, f"[{NEG}]run failed[/] {escape(repr(e))}")
        finally:
            self._trading = False
            self.call_from_thread(self._finished)

    def _finished(self) -> None:
        self._log(f"[{DIM}]run finished.[/]")
        self._refresh_status()

    def _on_tick(self, data: dict) -> None:
        """One poll: refresh the status band and add a row to the log."""
        import time as _t

        self._equity = data["equity"]
        self._cash = data["cash"]
        self._position = data["position"]
        self._entry = data.get("avg_entry", 0.0)
        self._trades_today = data.get("trades_today", 0)
        self._refresh_status()

        stamp = _t.strftime("%H:%M:%S", _t.localtime(data["ts"]))
        room = max(10, self._log_width() - len(stamp) - PRICE_WIDTH - 4)
        # a poll where nothing happened stays quiet, so the trades stand out
        quiet = data["executed"] is None and not data["blocked"]
        price = MUTED if quiet else V
        self._log(f"[{DIM}]{stamp}[/]  "
                  f"[{price}]{format_price(data['price']):>{PRICE_WIDTH}}[/]  "
                  + self._event(data, room))

    def _log_width(self) -> int:
        """Usable width inside the log: its padding and scrollbar do not count."""
        inner = self.logbox.scrollable_content_region.width
        return inner if inner > 0 else max(20, (self.size.width or 80) - 6)

    def _event(self, data: dict, room: int) -> str:
        """What happened on this poll, trimmed to the room the row has left."""
        trade = data["executed"]
        if trade is None:
            if not data["blocked"]:
                return f"[{DIM}]·[/]"
            return f"[{WARN}]held[/] [{DIM}]{escape(clip(data['blocked'], room - 5))}[/]"

        colour = POS if trade.side == "BUY" else NEG
        amount = format_amount(trade.amount)
        head = f"{trade.side.lower():<4} {amount}"
        row = f"[{colour}]{trade.side.lower():<4}[/] [{V}]{amount}[/]"
        if not self._narrow:      # a phone has no room for the fill price
            fill = format_price(trade.price)
            head += f" @ {fill}"
            row += f" [{DIM}]@[/] [{V}]{fill}[/]"
        # a couple of clipped letters say nothing: show the reason or drop it
        left = room - len(head) - 1
        if trade.reason and left >= MIN_REASON:
            row += f" [{DIM}]{escape(clip(trade.reason, left))}[/]"
        return row

    @on(Button.Pressed, "#check")
    def action_check(self) -> None:
        self._sync_cfg()
        if not self.cfg.token_address:
            self._log(f"[{DIM}]fill in a token address first to run a safety "
                      "check.[/]")
            return
        self._log(f"[{A}]safety check[/] [{DIM}]· {self.cfg.chain} · "
                  f"{self.cfg.token_address[:8]}…[/]")
        self._check_worker()

    @work(thread=True)
    def _check_worker(self) -> None:
        from .safety import check_token
        try:
            rep = check_token(self.cfg.chain, self.cfg.token_address)
        except Exception as e:
            self.call_from_thread(self._log, f"  [{NEG}]error[/] {escape(repr(e))}")
            return
        col = {"ok": POS, "warn": WARN, "danger": NEG, "unknown": DIM}.get(rep.level, DIM)
        self.call_from_thread(self._log,
                              f"  [{DIM}]status[/] [{col}]{rep.summary()}[/] "
                              f"[{DIM}]({rep.source or '-'})[/]")
        for lvl, msg in rep.flags[:8]:
            lc = {"ok": POS, "warn": WARN, "danger": NEG}.get(lvl, DIM)
            self.call_from_thread(self._log, f"  [{lc}]·[/] {escape(msg)}")

    @on(Button.Pressed, "#clearbtn")
    def action_clear(self) -> None:
        """Wipe the log. The run keeps going, and so do the journal and state."""
        self.logbox.clear_all()

    @on(Button.Pressed, "#stopbtn")
    def action_stop(self) -> None:
        if self._trading:
            self._trading = False
            self._log(f"[{NEG}]stopping[/] [{DIM}]after this tick...[/]")

    def action_status(self) -> None:
        import json
        import os
        self._sync_cfg()
        self._log(f"[{A}]status[/] [{DIM}]· {self.cfg.mode}[/]")
        if os.path.exists(self.cfg.state_file):
            with open(self.cfg.state_file) as fh:
                st = json.load(fh)
            self._log(f"  [{DIM}]cash[/] [{V}]{st.get('cash', 0):.4f}[/]   "
                      f"[{DIM}]position[/] "
                      f"[{V}]{format_amount(st.get('position', 0))}[/]   "
                      f"[{DIM}]entry[/] "
                      f"[{V}]{format_price(st.get('avg_entry', 0))}[/]")
            session = st.get("session") or {}
            if session.get("halt_reason"):
                self._log(f"  [{NEG}]halted[/] {escape(session['halt_reason'])}")
        else:
            self._log(f"  [{DIM}]no saved state yet.[/]")
        rows = read_journal(self.cfg.orders_file, limit=5)
        for r in rows:
            colour = {"filled": POS, "blocked": WARN, "failed": NEG}.get(
                r.get("status"), DIM)
            note = escape(r.get("signal") or r.get("reason") or r.get("error") or "")
            self._log(f"  [{colour}]{r.get('status', '?'):<8}[/] "
                      f"[{DIM}]{r.get('side', '?').lower():<4}[/] "
                      f"[{V}]{format_amount(r.get('amount', 0))}[/] [{DIM}]@[/] "
                      f"[{V}]{format_price(r.get('price', 0))}[/] [{DIM}]{note}[/]")
        self._log("")


def run_tui(cfg: Config) -> None:
    LlnxTUI(cfg).run()
