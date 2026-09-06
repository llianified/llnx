# Bot Trading Paper (Simulasi) — SMA Crossover

Bot trading crypto sederhana untuk **belajar & uji strategi**. Default-nya berjalan
di **mode paper (simulasi)**: pakai harga real-time dari exchange, tapi order-nya
**bohongan** dengan saldo virtual. **Nol risiko, tanpa uang sungguhan, tanpa API key.**

> ⚠️ **Baca dulu soal modal kecil.** Modal recehan ($5–$20) itu **buat belajar, bukan
> cari penghasilan.** Fee (~0.1% per sisi), spread, dan minimum order exchange
> (Binance spot biasanya ~$5–10 per order) akan memakan untung yang recehan. Naik 10%
> dari $5 cuma $0.50. Anggap ini simulator latihan, bukan mesin uang.

## Fitur
- **Paper trading live** — harga real-time (via `ccxt`), order disimulasikan lokal.
- **Backtest** — uji strategi ke data historis (CSV) atau data sintetis bawaan.
- **Strategi SMA crossover** — beli saat SMA cepat memotong naik SMA lambat, jual saat memotong turun.
- **Simpan state** — saldo & posisi tersimpan, bisa lanjut setelah restart (`state.json`).
- **Riwayat transaksi** — dicatat ke `trades.csv`.
- **Modal & parameter gampang diubah** — lewat `config.yaml` atau flag CLI.

## Struktur
```
main.py            # entry point (CLI)
config.yaml        # konfigurasi (modal, symbol, timeframe, periode SMA, fee, dst.)
requirements.txt   # dependency untuk mode live
bot/
  config.py        # loader konfigurasi
  strategy.py      # strategi SMA crossover (murni, teruji)
  broker.py        # paper broker: saldo virtual, fee, min notional
  engine.py        # gabungan strategi + broker (tanpa IO, mudah dites)
  datafeed.py      # ambil harga live via ccxt (mode live saja)
  runner.py        # loop paper trading live + persistensi
  backtest.py      # mesin backtest + generator data sintetis
tests/             # unit test (pytest)
```

## Cara Pakai

### 1) Coba backtest dulu (tanpa internet, tanpa install apa pun)
```bash
python3 main.py backtest                 # data sintetis bawaan
python3 main.py backtest --cash 20       # ganti modal
python3 main.py backtest --fast 5 --slow 20
python3 main.py backtest --csv harga.csv # pakai data sendiri (kolom terakhir = harga close)
```

### 2) Paper trading live (harga real-time, order simulasi)
```bash
pip install -r requirements.txt          # butuh ccxt (data publik, tanpa API key)
python3 main.py paper                     # pakai config.yaml
python3 main.py paper --cash 10 --symbol ETH/USDT --timeframe 5m
```
Berhenti dengan `Ctrl+C` — state tersimpan otomatis, lanjut lagi kapan saja.

### 3) Ganti modal / parameter
Edit `config.yaml` (baris `starting_cash`, `symbol`, `sma_fast`, `sma_slow`, dst.),
atau override sesaat lewat flag CLI seperti contoh di atas.

## Menjalankan test
```bash
pip install pytest
python3 -m pytest -q
```

## Roadmap kalau mau lanjut
- **Ke uang real:** tambah kelas broker baru yang memanggil API order ccxt (butuh API
  key + saldo real). Simpan key di `.env`, **jangan pernah** di-commit.
- Strategi lain: RSI, grid/DCA, trailing stop, stop-loss / take-profit.
- Notifikasi (Telegram) & dashboard.
- Backtest dengan data OHLCV historis asli dari exchange.

## Peringatan
Ini alat **edukasi**, bukan nasihat finansial. Trading crypto berisiko tinggi dan
bisa membuat modalmu habis. Uji di mode paper dulu, dan jangan pakai uang yang tidak
siap kamu relakan.
