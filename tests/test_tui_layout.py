"""Test layout responsif TUI (landscape ↔ portrait). Butuh textual."""
import asyncio

import pytest

pytest.importorskip("textual", reason="textual opsional, TUI tidak diuji")

from bot.config import Config
from bot.tui import BotTUI, NARROW_COLS, PANEL_ROWS


def run(coro):
    return asyncio.run(coro)


def classes_at(width, height):
    async def go():
        app = BotTUI(Config())
        async with app.run_test(size=(width, height)) as pilot:
            await pilot.pause()
            return set(app.screen.classes)
    return run(go())


def test_desktop_pakai_layout_landscape():
    assert classes_at(120, 40) == set()


def test_layar_sempit_menumpuk_ke_bawah():
    assert "-narrow" in classes_at(NARROW_COLS - 1, 50)
    assert "-narrow" not in classes_at(NARROW_COLS, 50)


def test_layar_pendek_dirapatkan():
    cls = classes_at(100, 20)
    assert "-narrow" not in cls          # masih berdampingan
    assert {"-compact", "-short"} <= cls  # tapi widget dipadatkan


def test_panel_pengaturan_tidak_makan_seluruh_layar_sempit():
    async def go():
        app = BotTUI(Config())
        async with app.run_test(size=(45, 50)) as pilot:
            await pilot.pause()
            sidebar = app.query_one("#sidebar")
            log = app.query_one("#log")
            return sidebar.size.height, log.size.height
    panel, log = run(go())
    assert panel <= PANEL_ROWS
    assert log > panel          # sisa layar buat log


def test_tombol_aksi_tetap_terlihat_saat_sempit():
    async def go():
        app = BotTUI(Config())
        async with app.run_test(size=(38, 24)) as pilot:
            await pilot.pause()
            return [b.region.height > 0 and b.region.y < app.size.height
                    for b in app.query("Button")]
    assert all(run(go()))


def test_log_dibungkus_ulang_saat_layar_diputar():
    async def go():
        app = BotTUI(Config())
        async with app.run_test(size=(40, 30)) as pilot:
            await pilot.pause(); await pilot.pause()
            app._log("x" * 200)
            await pilot.pause()
            sempit = len(app.logbox.lines)
            await pilot.resize_terminal(120, 30)
            await pilot.pause(); await pilot.pause()
            return sempit, len(app.logbox.lines), app.logbox._history[-1]
    sempit, lebar, terakhir = run(go())
    assert terakhir == "x" * 200
    assert lebar < sempit        # baris lama ikut dibungkus ulang, bukan kepotong


def test_toggle_pengaturan():
    async def go():
        app = BotTUI(Config())
        async with app.run_test(size=(45, 30)) as pilot:
            await pilot.pause(); await pilot.pause()
            await pilot.press("t"); await pilot.pause()
            hidden = app.query_one("#sidebar").has_class("hidden")
            await pilot.press("t"); await pilot.pause()
            return hidden, app.query_one("#sidebar").has_class("hidden")
    hidden, kembali = run(go())
    assert hidden and not kembali
