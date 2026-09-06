"""Notifications: NullNotifier (default, silent) and TelegramNotifier.

Telegram needs a bot token and a chat id: create the bot with @BotFather and
get the chat id from @userinfobot. Uses urllib, so no extra packages.
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
        except Exception as e:  # a network hiccup must not kill the bot
            print(f"[telegram] send failed: {e!r}")

    def notify(self, text: str) -> None:
        self.send(text)

    def notify_trade(self, trade, symbol: str) -> None:
        emoji = "🟢" if trade.side == "BUY" else "🔴"
        self.send(
            f"{emoji} <b>{trade.side}</b> {symbol}\n"
            f"price: {trade.price:.6g}\n"
            f"amount: {trade.amount:.8g}\n"
            f"reason: {trade.reason or '-'}\n"
            f"equity: {trade.equity_after:.4f}"
        )


def build_notifier(cfg):
    """TelegramNotifier when a token and chat id are set, NullNotifier otherwise."""
    import os
    token = os.environ.get("TELEGRAM_TOKEN") or getattr(cfg, "telegram_token", "")
    chat = os.environ.get("TELEGRAM_CHAT_ID") or getattr(cfg, "telegram_chat_id", "")
    if token and chat:
        return TelegramNotifier(token, chat)
    return NullNotifier()
