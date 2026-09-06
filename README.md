# llnx — a crypto bot that places its own orders

**llnx** watches a market, decides, and then actually sends the order. Paper,
exchange sandbox or real money — same loop, same code, one setting apart. It
ships with a TUI, a text menu and a CLI, and the core runs on the Python
standard library alone.

```bash
pip install textual
python3 main.py                     # TUI: pick a mode, press run
```

> **About tiny accounts.** $5–$20 is practice money, not a money machine. Fees
> (~0.1% per side), spread and exchange minimums (~$5–10) eat most of the
> profit at that size. Test on paper first, and never trade money you cannot
> afford to lose.

## The three modes

| mode | what happens | what you need |
|---|---|---|
| `paper` | real prices, simulated orders against a virtual balance | nothing |
| `sandbox` | exchange testnet orders, or a Solana dry run on real Jupiter quotes | testnet keys (CEX) |
| `live` | **real orders, real money** | API keys / a funded wallet |

```bash
python3 main.py run --mode paper
python3 main.py run --mode sandbox
python3 main.py run --mode live            # asks you to type I UNDERSTAND
```

Nothing goes out until you pick a non-paper mode, and live mode always asks
for the phrase — in the TUI, the menu and the CLI alike.

## How an order actually gets placed

```
feed → strategy → decision → risk (SL/TP) → guardrails → broker → venue
                                                 │           │
                                                 │           └─ real fill: amount,
                                                 │              price and fee come
                                                 │              back from the venue
                                                 └─ orders.jsonl: every attempt,
                                                    filled, blocked or failed
```

* **The fill is read back, never assumed.** On an exchange the order is polled
  until it is closed and the booked price is the average fill price, with the
  fee converted to the quote currency. On Solana the price comes from the
  Jupiter quote itself, and the swap is **confirmed on chain** before it is
  booked as a trade — an unconfirmed swap is not a trade.
* **Balances come from the venue.** After every live order — and after every
  failure — llnx re-reads the balance instead of guessing. A restart hands the
  average entry price back to the broker so the stop-loss still has something
  to measure against.
* **A failed order is never blindly retried.** A market order that errored may
  still have reached the venue; the next tick decides again with fresh prices.

## Guardrails

An auto-executing bot needs a hand on the brake. All of these live in
`config.yaml` and are checked before every order (0 = off):

| setting | what it does |
|---|---|
| `max_daily_loss_pct` | stops **buying** after -X% on the day; exits still work |
| `max_trades_per_day` | caps how many trades a day it may make |
| `cooldown_sec` | minimum seconds between orders |
| `max_order_pct` | shrinks any order bigger than X% of equity |
| `max_consecutive_failures` | stands the bot down after N failed orders in a row |
| `kill_switch_file` | the file that stops everything |

Exits are deliberately not blocked by the risk limits: after a bad day the
stop-loss is the last thing you want disabled. The kill switch and the failure
halt stop everything, because at that point the venue or your intent says so.

### The kill switch

```bash
python3 main.py stop      # creates STOP; a running bot quits within one tick
python3 main.py resume    # removes it
```

Works from any terminal, over SSH, from your phone — the running bot checks the
file every tick.

### Signals only

Want the old behaviour back for a while? `auto_execute: false`, or:

```bash
python3 main.py run --signals-only
```
Everything runs and gets journalled, nothing is sent.

## What it did while you were away

Every order attempt is appended to `orders.jsonl` — filled, blocked, rejected
or failed, with the signal that caused it:

```bash
python3 main.py status --orders 20
```
```
last 3 order attempts:
  2026-01-04T09:15:02+00:00  filled   BUY  0.00043 @ 68120.5  golden cross 9/21
  2026-01-04T09:41:02+00:00  filled   SELL 0.00043 @ 67980.0  STOP-LOSS -2%
  2026-01-04T10:02:03+00:00  blocked  BUY  0 @ 67990.0        cooldown: 44s to go
```

## Install

Backtests, the text menu and the tests need **nothing but Python**. The TUI
needs one package:

```bash
pip install textual        # that's it
python3 main.py
```

Everything else is optional and only pulled in if you actually use it:

| package  | needed for |
|---|---|
| `textual` | the full-screen TUI (`python3 main.py`) |
| `ccxt`    | exchanges other than Binance, and real CEX orders |
| `PyYAML`  | stricter `config.yaml` parsing (a built-in reader is used otherwise) |
| `solders` | real Solana swaps through Jupiter |

Installing it as a package gives you the `llnx` command:

```bash
pip install -e ".[tui]"
llnx run --mode paper
```

### Termux (Android)

```bash
pkg install python git
git clone <this repo> && cd llnx
pip install textual        # ~20 MB, no compiler needed
python3 main.py
```

That is the whole install. Notes for Termux specifically:

- **Do not install ccxt** unless you need a non-Binance exchange. It drags in
  aiohttp and cryptography, which build from source on Android and take ages.
  Binance price data goes through plain HTTPS from the standard library.
- **PyYAML is not required** either. Without it llnx reads `config.yaml`
  with a small built-in parser.
- Prefer `pkg install python` over pyenv or a venv; the system Python is fine.
- No textual? `python3 main.py menu` gives the same features as plain text.

## Layout (TUI)

The output pane fills the top of the screen and the settings live in a bar at
the bottom, so the same layout works in landscape and portrait. It reflows to
the terminal size:

| terminal | layout |
|---|---|
| ≥ 96 columns | four columns of fields, buttons on one row |
| < 96 columns | two columns of fields, buttons on two rows |
| < 28 rows | tighter spacing, the fields scroll if they do not fit |
| < 22 rows | frames dropped, all remaining space goes to the output |
| < 16 rows | settings bar hides itself; press `t` to bring it back |

Desktop (120x38):

![TUI desktop](docs/tui.png)

Phone landscape (96x20):

![TUI phone landscape](docs/tui_hp_landscape.png)

Termux portrait (45x55):

![TUI Termux portrait](docs/tui_termux_portrait.png)

Keys: `b` backtest · `r` run · `c` safety check · `s` status · `x` stop ·
`t` settings · `q` quit. The run button turns red in live mode, and the mode
sits in the header the whole time.

## Command line

```bash
# Backtest (no internet, no packages)
python3 main.py backtest --strategy sma  --cash 20
python3 main.py backtest --strategy rsi  --sl 0.03 --tp 0.10
python3 main.py backtest --csv prices.csv                      # your own data

# Trade
python3 main.py run --mode paper --strategy grid --symbol ETH/USDT --cash 10
python3 main.py run --mode live --yes --max-order 0.25 --cooldown 300
python3 main.py run --signals-only                             # decide, send nothing

# Control and history
python3 main.py stop / resume
python3 main.py status --orders 20
```

Guardrails have flags too: `--max-daily-loss`, `--max-trades`, `--cooldown`,
`--max-order`. Stop with `Ctrl+C`; state goes to `state.json` and is picked up
next time, daily counters included.

## Multi-chain (Solana + EVM), scanning and safety checks

Supported networks: `solana`, `ethereum`, `bsc`, `base`, `arbitrum`, `polygon`.
Paper trading, scanning and safety checks work on all of them. **Real swaps**
only work on **Solana (Jupiter)** — EVM swaps would need web3 plus a router.

**Token safety check** (honeypot, mint/freeze authority, tax, locked LP):
```bash
python3 main.py check --chain solana --token <MINT>      # source: RugCheck
python3 main.py check --chain bsc    --token <CONTRACT>  # source: GoPlus
```

**Scan trending tokens** per chain (GeckoTerminal), optionally with the check:
```bash
python3 main.py scan --chain solana --limit 10
python3 main.py scan --chain base --limit 10 --safety
```

**Trade a DEX token** on any chain — paste the token address:
```bash
python3 main.py run --chain bsc --token <CONTRACT> --cash 20 --strategy rsi
```
Before trading a token llnx runs the safety check itself (`safety_check: true`),
and a token that looks dangerous cancels live mode outright.

**Real Solana swaps through Jupiter:**
```bash
# sandbox: real Jupiter quotes (real slippage), nothing is signed or sent
python3 main.py run --token <MINT> --mode sandbox

# live: signs, sends and waits for on-chain confirmation
pip install solders
export SOLANA_PRIVATE_KEY="..."   # base58, never commit this
export SOLANA_RPC_URL="https://..."
python3 main.py run --token <MINT> --mode live
```
The wallet's USDC and token balances are read straight from the chain, and
"sell everything" spends the exact base units the wallet holds.

> **Meme coins are gambling.** Most go to zero, many are rug pulls or
> honeypots (you can buy, you cannot sell), liquidity is thin (heavy slippage)
> and sniper/MEV bots front-run you. Technical indicators mean very little on a
> brand-new coin. Paper-trade first.

## The strategies
| strategy | buys | sells | suits |
|---|---|---|---|
| `sma`  | golden cross (fast SMA > slow) | death cross | trending markets |
| `rsi`  | RSI < oversold (e.g. 30) | RSI > overbought (e.g. 70) | choppy markets |
| `grid` | every `step_pct` down, in chunks | `take_profit_pct` above the average entry | sideways or falling markets |

All parameters live in `config.yaml`, or can be set from the menu and the TUI.

## Keys

Keys never live in `config.yaml`. They come from the environment:

```bash
export EXCHANGE_API_KEY="..."          # exchange orders (ccxt)
export EXCHANGE_API_SECRET="..."
export SOLANA_PRIVATE_KEY="..."        # solana swaps (base58)
export SOLANA_RPC_URL="https://..."
export TELEGRAM_TOKEN="123456:abc..."  # optional notifications
export TELEGRAM_CHAT_ID="123456789"
```

With Telegram set, every trade is sent to you as it happens — handy when the
bot is the one pressing the buttons.

## Layout of the code
```
main.py                    # entry point (`python3 main.py`, or `llnx` installed)
config.yaml                # every setting
llnx/
  cli.py                   # subcommands: run, backtest, status, stop, resume, scan
  config.py                # config loader (PyYAML optional)
  strategies/              # indicators + strategies (sma, rsi, grid) + registry
  engine.py                # risk + strategy + broker + notifier
  risk.py                  # stop-loss / take-profit
  guards.py                # guardrails: daily loss, trade cap, cooldown, kill switch
  execution.py             # the executor: guards, order journal, reconciliation
  broker.py                # paper broker (partial orders, average entry)
  live_broker.py           # real CEX orders via ccxt, booked from the real fill
  jupiter_broker.py        # real Solana swaps, confirmed on chain
  wallet.py                # solana RPC: balances, decimals, confirmation
  datafeed.py              # exchange prices: Binance over stdlib HTTPS, or ccxt
  dexfeed.py               # DEX token prices (DexScreener + GeckoTerminal)
  solana_feed.py           # compatibility shim: Solana-only DexFeed
  chains.py                # network registry (solana + evm)
  safety.py                # token safety checks (RugCheck / GoPlus)
  scan.py                  # trending token scan per chain
  feeds.py                 # picks the price source (exchange / DEX)
  runner.py                # the live loop + persistence (used by CLI, menu, TUI)
  notify.py                # NullNotifier / TelegramNotifier
  backtest.py              # backtest engine + synthetic data
  menu.py                  # plain text menu
  tui.py                   # full-screen TUI (Textual)
tests/                     # unit tests (pytest)
```

## Tests
```bash
pip install pytest
python3 -m pytest -q
```

## Warning
This is an **educational tool**, not financial advice. Crypto trading is risky,
and a bot that trades by itself can lose money by itself, faster than you can
watch it. Backtest results are **not** a promise of live results. Start on
paper, move to sandbox, and only then risk an amount you can afford to lose.
