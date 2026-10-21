import pytest
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


def test_icon_font_has_custom_save_as_glyph():
    TTFont = pytest.importorskip("fontTools.ttLib").TTFont
    from vvv.utils import get_resource_path
    from vvv.ui.ui_components import ICON_SAVE_AS

    font_path = get_resource_path(
        os.path.join("fonts", "Font Awesome 7 Free-Solid-900.otf")
    )
    assert os.path.exists(font_path)
    font = TTFont(font_path)
    cmap = font.getBestCmap()
    save_as_cp = ord(ICON_SAVE_AS)
    assert save_as_cp in cmap
    assert cmap[save_as_cp] == "floppy-disk-arrow-down"


def test_ui_config_panel_heights_per_platform(monkeypatch):
    from unittest.mock import MagicMock

    controller = MagicMock()
    controller.settings.data = {
        "layout": {
            "side_panel_width": 380,
            "nav_panel_width": 80,
            "sidebar_gap": 5,
        }
    }

    # Darwin / macOS
    monkeypatch.setattr(ui_theme.sys, "platform", "darwin")
    cfg_mac = ui_theme.build_ui_config(controller)
    assert cfg_mac["layout"]["panel_av_h"] == 345
    assert cfg_mac["layout"]["panel_ch_h"] == 160
    assert cfg_mac["layout"]["nav_panel_w"] == 80

    # Linux / Windows
    for plat in ("linux", "win32"):
        monkeypatch.setattr(ui_theme.sys, "platform", plat)
        cfg_linux = ui_theme.build_ui_config(controller)
        assert cfg_linux["layout"]["panel_av_h"] == 395
        assert cfg_linux["layout"]["panel_ch_h"] == 185
        assert cfg_linux["layout"]["nav_panel_w"] >= 90

