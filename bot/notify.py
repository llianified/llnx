"""Notifikasi. NullNotifier (default, diam) & TelegramNotifier (opsional).

Telegram butuh bot token + chat id. Buat bot lewat @BotFather, ambil chat id
dari @userinfobot. Pakai urllib standar — tanpa dependency tambahan.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request


class NullNotifier:
    enabled = False

    def send(self, text: str) -> None:
        pass

    def notify_trade(self, trade, symbol: str) -> None:
        pass

    def notify(self, text: str) -> None:
        pass


class TelegramNotifier:
    enabled = True

    def __init__(self, token: str, chat_id: str, timeout: int = 10) -> None:
        self.token = token
        self.chat_id = str(chat_id)
        self.timeout = timeout

    def send(self, text: str) -> None:
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        data = urllib.parse.urlencode({
            "chat_id": self.chat_id, "text": text, "parse_mode": "HTML",
        }).encode()
        try:
            with urllib.request.urlopen(url, data=data, timeout=self.timeout) as r:
                json.loads(r.read().decode())
        except Exception as e:  # jaringan gagal jangan menjatuhkan bot
            print(f"[telegram] gagal kirim: {e!r}")

    def notify(self, text: str) -> None:
        self.send(text)

    def notify_trade(self, trade, symbol: str) -> None:
        emoji = "🟢" if trade.side == "BUY" else "🔴"
        self.send(
            f"{emoji} <b>{trade.side}</b> {symbol}\n"
            f"harga: {trade.price:.6g}\n"
            f"jumlah: {trade.amount:.8g}\n"
            f"alasan: {trade.reason or '-'}\n"
            f"equity: {trade.equity_after:.4f}"
        )


def build_notifier(cfg):
    """Kembalikan TelegramNotifier bila token+chat id ada, else NullNotifier."""
    import os
    token = os.environ.get("TELEGRAM_TOKEN") or getattr(cfg, "telegram_token", "")
    chat = os.environ.get("TELEGRAM_CHAT_ID") or getattr(cfg, "telegram_chat_id", "")
    if token and chat:
        return TelegramNotifier(token, chat)
    return NullNotifier()
