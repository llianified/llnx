"""Notifier: default Null, dan build dari env."""
import os

from bot.config import Config
from bot.notify import NullNotifier, TelegramNotifier, build_notifier


def test_null_notifier_is_quiet():
    n = NullNotifier()
    assert n.enabled is False
    n.send("halo"); n.notify("x")  # tidak boleh error


def test_build_notifier_default_null():
    for k in ("TELEGRAM_TOKEN", "TELEGRAM_CHAT_ID"):
        os.environ.pop(k, None)
    assert isinstance(build_notifier(Config()), NullNotifier)


def test_build_notifier_from_env(monkeypatch):
    monkeypatch.setenv("TELEGRAM_TOKEN", "abc")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123")
    assert isinstance(build_notifier(Config()), TelegramNotifier)
