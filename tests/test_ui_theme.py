import os

from vvv.ui import ui_theme


def test_shipped_font_on_linux_and_windows(monkeypatch):
    for platform in ("linux", "win32"):
        monkeypatch.setattr(ui_theme.sys, "platform", platform)
        path, size, small = ui_theme._pick_ui_font()
        assert os.path.basename(path) == ui_theme.SHIPPED_UI_FONT[0]
        assert os.path.exists(path)
        assert (size, small) == ui_theme.SHIPPED_UI_FONT[1:]


def test_macos_uses_helvetica_when_present(monkeypatch):
    monkeypatch.setattr(ui_theme.sys, "platform", "darwin")
    real_exists = os.path.exists
    monkeypatch.setattr(
        ui_theme.os.path,
        "exists",
        lambda p: p == ui_theme.MACOS_UI_FONT[0] or real_exists(p),
    )
    assert ui_theme._pick_ui_font() == ui_theme.MACOS_UI_FONT
