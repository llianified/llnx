# Bot Trading Crypto — Paper / Real (SMA · RSI · Grid/DCA)

Bot trading crypto untuk **belajar & uji strategi**, dengan **menu interaktif**
supaya gampang dipakai tanpa hafal perintah. Default berjalan di **mode paper
(simulasi)**: harga real-time dari exchange, order **bohongan** pakai saldo
virtual. **Nol risiko, tanpa uang sungguhan, tanpa API key.**

> ⚠️ **Soal modal kecil.** Modal recehan ($5–$20) itu **buat latihan, bukan
> mesin uang.** Fee (~0.1%/sisi), spread, dan minimum order exchange (~$5–10)
> memakan untung yang memang recehan. Uji di paper dulu; jangan pakai uang yang
> tak siap kamu relakan.

## Fitur
1. **Stop-loss & take-profit** global — jual otomatis saat rugi/untung X%.
2. **3 strategi**: `sma` (crossover), `rsi` (oversold/overbought), `grid` (DCA).
3. **Notifikasi Telegram** — kabar tiap transaksi (opsional).
4. **Jembatan uang real** — order asli via `ccxt`, default **sandbox/testnet**.
- **Menu interaktif** + **backtest** offline + **persistensi state** + **unit test**.

## Tampilan (TUI)
Jalankan `python3 main.py` untuk antarmuka **TUI full-screen** (bisa diklik pakai
mouse & keyboard, layout landscape yang enak di layar lebar/HP):

![TUI](docs/tui.png)

## Mulai cepat (paling gampang)
```bash
python3 main.py            # TUI full-screen (butuh: pip install textual)
python3 main.py menu       # menu teks sederhana (fallback tanpa textual)
```
Dari menu kamu bisa: ubah modal & pasar, pilih strategi + parameternya, atur
stop-loss/take-profit, jalankan backtest, mulai paper trading, lihat riwayat.

## Pakai lewat perintah (power user)
```bash
# Backtest (tanpa internet, tanpa install apa pun)
python3 main.py backtest --strategy sma  --cash 20
python3 main.py backtest --strategy rsi  --cash 20
python3 main.py backtest --strategy grid --cash 20
python3 main.py backtest --strategy sma  --sl 0.03 --tp 0.10   # + stop-loss/take-profit
python3 main.py backtest --csv harga.csv                       # data sendiri

# Paper trading live (harga real-time, order simulasi) — butuh ccxt
pip install -r requirements.txt
python3 main.py paper --strategy grid --symbol ETH/USDT --cash 10

# Lihat state & riwayat transaksi
python3 main.py status
```
Berhenti dengan `Ctrl+C` — state tersimpan (`state.json`), lanjut kapan saja.

## Trading token Solana / micin (paper) 🟣
Selain CEX, bot bisa pantau **token Solana DEX** (Raydium/Orca/pump.fun) untuk
**paper trading** — cukup tempel **mint address** token-nya. Tanpa wallet, tanpa
API key, nol risiko. Harga real-time dari **DexScreener** (USD), candle historis
dari **GeckoTerminal** (USD), lalu diproses engine & strategi yang sama.

```bash
# di TUI: isi kolom "Mint Solana", atau lewat CLI:
python3 main.py paper --mint <MINT_ADDRESS_TOKEN> --cash 20 --strategy rsi
# contoh BONK:
python3 main.py paper --mint DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263 --cash 20
```

> ⚠️ **Micin = judi.** Mayoritas meme coin menuju nol; banyak **rug pull /
> honeypot** (bisa beli, tak bisa jual), likuiditas tipis (slippage besar), dan
> **sniper/MEV bot** yang front-run. Indikator teknikal sering tak berarti pada
> koin baru. Paper-kan dulu; jangan taruh uang yang tak siap hilang.
>
> **Uang real Solana (swap Jupiter) BELUM didukung** — perlu wallet, RPC, dan
> **cek honeypot** dulu. Saat ini Solana = paper saja.

## Strategi singkat
| Strategi | Kapan beli | Kapan jual | Cocok untuk |
|---|---|---|---|
| `sma`  | golden cross (SMA cepat > lambat) | death cross | pasar tren |
| `rsi`  | RSI < oversold (mis. 30) | RSI > overbought (mis. 70) | pasar bolak-balik |
| `grid` | turun tiap `step_pct`, DCA bertahap | naik `take_profit_pct` dari entry rata-rata | pasar sideways/turun |

Semua parameter ada di `config.yaml` atau bisa diatur lewat menu.

## Notifikasi Telegram (opsional)
1. Buat bot via **@BotFather**, salin token. Ambil chat id dari **@userinfobot**.
2. Set lewat environment (lebih aman daripada di file):
```bash
export TELEGRAM_TOKEN="123456:abc..."
export TELEGRAM_CHAT_ID="123456789"
```
Kalau keduanya ada, bot kirim pesan tiap transaksi otomatis.

## Mode uang REAL (lanjutan) ⚠️
Order pakai dana asli. **Uji di paper & sandbox dulu.**
```bash
export EXCHANGE_API_KEY="..."         # JANGAN pernah commit key
export EXCHANGE_API_SECRET="..."
python3 main.py paper --real          # default: SANDBOX/testnet (uang bohongan)
python3 main.py paper --real --mainnet  # uang SUNGGUHAN (butuh ketik konfirmasi)
```
Mode mainnet minta ketik `SAYA PAHAM` sebelum jalan. `CcxtBroker` sifatnya
eksperimental — mulai dari sandbox.

## Struktur
```
main.py                    # entry point (menu default + subcommand)
config.yaml                # semua pengaturan
bot/
  config.py                # loader konfigurasi
  strategies/              # indikator + strategi (sma, rsi, grid) + registry
  broker.py                # paper broker (order bertahap, entry rata-rata)
  live_broker.py           # broker uang real via ccxt (sandbox default)
  risk.py                  # stop-loss / take-profit
  engine.py                # risk + strategi + broker + notifier
  notify.py                # NullNotifier / TelegramNotifier
  datafeed.py              # harga live via ccxt (CEX, tanpa API key)
  solana_feed.py           # harga token Solana DEX (DexScreener + GeckoTerminal)
  feeds.py                 # pemilih sumber data (CEX / Solana)
  runner.py                # loop live + persistensi
  backtest.py              # mesin backtest + data sintetis
  menu.py                  # menu teks sederhana
  tui.py                   # TUI full-screen (Textual)
tests/                     # unit test (pytest) — 23 test
```

## Test
```bash
pip install pytest
python3 -m pytest -q
```

## Peringatan
Alat **edukasi**, bukan nasihat finansial. Trading crypto berisiko tinggi.
Hasil backtest **bukan** jaminan hasil live. Uji di paper dulu.
