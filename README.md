# Crypto Trading Bot — paper / real (SMA · RSI · Grid/DCA)

A crypto trading bot for **learning and testing strategies**, with a TUI and a
text menu so you never have to memorise flags. It runs in **paper mode** by
default: real-time prices from the exchange, fake orders against a virtual
balance. **No risk, no real money, no API key.**

> **About tiny accounts.** $5–$20 is practice money, not a money machine. Fees
> (~0.1% per side), spread and exchange minimums (~$5–10) eat most of the
> profit at that size. Test on paper first, and never trade money you cannot
> afford to lose.

## Features
1. **Global stop-loss and take-profit** — sell automatically at ±X%.
2. **Three strategies**: `sma` (crossover), `rsi` (oversold/overbought), `grid` (DCA).
3. **Telegram notifications** on every trade (optional).
4. **Real-money bridge** through `ccxt`, sandbox/testnet by default.
- Text menu, offline backtests, state persistence, unit tests.

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
| `solders` | real Solana swaps through Jupiter (experimental) |

### Termux (Android)

```bash
pkg install python git
git clone <this repo> && cd no-name-yet
pip install textual        # ~20 MB, no compiler needed
python3 main.py
```

That is the whole install. Notes for Termux specifically:

- **Do not install ccxt** unless you need a non-Binance exchange. It drags in
  aiohttp and cryptography, which build from source on Android and take ages.
  Binance price data goes through plain HTTPS from the standard library.
- **PyYAML is not required** either. Without it the bot reads `config.yaml`
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

Press `t` to hide the settings bar and give the output the whole screen.
Rotating the phone re-wraps the log instead of leaving old lines clipped.

## Quick start
```bash
python3 main.py            # full-screen TUI (needs: pip install textual)
python3 main.py menu       # plain text menu (works without textual)
```
Both let you set the cash and market, pick a strategy and its parameters, set
stop-loss/take-profit, run a backtest, start paper trading and read the history.

## Command line
```bash
# Backtest (no internet, no packages)
python3 main.py backtest --strategy sma  --cash 20
python3 main.py backtest --strategy rsi  --cash 20
python3 main.py backtest --strategy grid --cash 20
python3 main.py backtest --strategy sma  --sl 0.03 --tp 0.10   # with SL/TP
python3 main.py backtest --csv prices.csv                      # your own data

# Paper trading (live prices, simulated orders)
python3 main.py paper --strategy grid --symbol ETH/USDT --cash 10

# State and trade history
python3 main.py status
```
Stop with `Ctrl+C`; the state is saved to `state.json` and picked up next time.

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

**Paper-trade a DEX token** on any chain — paste the token address:
```bash
python3 main.py paper --chain bsc --token <CONTRACT> --cash 20 --strategy rsi
```
Before going live the bot runs the safety check itself (when `safety_check: true`).

**Real Solana swaps through Jupiter** — experimental, dry-run by default:
```bash
# dry run: real Jupiter quotes (real slippage), nothing is sent
python3 main.py paper --token <MINT> --real
# actually send transactions (needs env vars + solders, asks for confirmation):
export SOLANA_PRIVATE_KEY="..."   # base58, never commit this
export SOLANA_RPC_URL="https://..."
pip install solders
python3 main.py paper --token <MINT> --real --mainnet
```

## Solana / meme tokens (paper)
Besides exchanges, the bot can watch **Solana DEX tokens** (Raydium, Orca,
pump.fun) for paper trading — paste the mint address and go. No wallet, no API
key. Prices come from **DexScreener** (USD) and candles from **GeckoTerminal**
(USD), then run through the same engine and strategies.

```bash
# in the TUI: fill in the token address field, or from the CLI:
python3 main.py paper --mint <TOKEN_MINT_ADDRESS> --cash 20 --strategy rsi
# BONK, for example:
python3 main.py paper --mint DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263 --cash 20
```

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

## Telegram notifications (optional)
1. Create a bot with **@BotFather** and copy the token. Get your chat id from
   **@userinfobot**.
2. Set them in the environment (safer than writing them to a file):
```bash
export TELEGRAM_TOKEN="123456:abc..."
export TELEGRAM_CHAT_ID="123456789"
```
With both set, every trade is sent to you automatically.

## Real-money mode (advanced)
Orders spend real funds. **Run paper and sandbox first.**
```bash
pip install ccxt
export EXCHANGE_API_KEY="..."           # never commit your keys
export EXCHANGE_API_SECRET="..."
python3 main.py paper --real            # sandbox/testnet (fake money)
python3 main.py paper --real --mainnet  # real money, asks for confirmation
```
Mainnet makes you type `I UNDERSTAND` before it starts. `CcxtBroker` is
experimental; start in the sandbox.

## Layout of the code
```
main.py                    # entry point (TUI by default, plus subcommands)
config.yaml                # every setting
bot/
  config.py                # config loader (PyYAML optional)
  strategies/              # indicators + strategies (sma, rsi, grid) + registry
  broker.py                # paper broker (partial orders, average entry)
  live_broker.py           # real-money broker via ccxt (sandbox by default)
  risk.py                  # stop-loss / take-profit
  engine.py                # risk + strategy + broker + notifier
  notify.py                # NullNotifier / TelegramNotifier
  datafeed.py              # exchange prices: Binance over stdlib HTTPS, or ccxt
  dexfeed.py               # DEX token prices (DexScreener + GeckoTerminal)
  solana_feed.py           # compatibility shim: Solana-only DexFeed
  chains.py                # network registry (solana + evm)
  safety.py                # token safety checks (RugCheck / GoPlus)
  scan.py                  # trending token scan per chain
  jupiter_broker.py        # real Solana swaps via Jupiter (dry run by default)
  feeds.py                 # picks the price source (exchange / DEX)
  runner.py                # live loop + persistence
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
This is an **educational tool**, not financial advice. Crypto trading is risky.
Backtest results are **not** a promise of live results. Paper-trade first.
