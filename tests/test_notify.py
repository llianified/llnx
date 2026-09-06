"""Notifiers: the default null one, and building from the environment."""
import os

from bot.config import Config
from bot.notify import NullNotifier, TelegramNotifier, build_notifier


def test_null_notifier_is_quiet():
    n = NullNotifier()
    assert n.enabled is False
    n.send("hello"); n.notify("x")  # must not raise


def test_build_notifier_default_null():
    for k in ("TELEGRAM_TOKEN", "TELEGRAM_CHAT_ID"):
        os.environ.pop(k, None)
    assert isinstance(build_notifier(Config()), NullNotifier)


def test_build_notifier_from_env(monkeypatch):
    monkeypatch.setenv("TELEGRAM_TOKEN", "abc")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123")
    assert isinstance(build_notifier(Config()), TelegramNotifier)
