import pytest
from unittest.mock import MagicMock, patch
from PIL import Image
import dearpygui.dearpygui as dpg

from vvv.core.controller import Controller
from vvv.ui.gui import MainGUI
from vvv.ui.viewer import SliceViewer
from vvv.utils import copy_image_to_clipboard


def test_top_menu_screenshot_button_exists(headless_gui_app):
    controller, gui, viewer, vs_id = headless_gui_app

    assert dpg.does_item_exist("btn_screenshot"), "btn_screenshot should exist in top menu"
    assert dpg.does_item_exist("btn_layout_4")
    assert dpg.does_item_exist("btn_layout_2")
    assert dpg.does_item_exist("btn_layout_1")

    # Simulate click with mocks
    test_img = Image.new("RGBA", (800, 600), (200, 100, 50, 255))
    with patch("vvv.ui.gui.capture_whole_window", return_value=test_img) as mock_capture:
        with patch("vvv.ui.gui.copy_image_to_clipboard", return_value=True) as mock_copy:
            with patch.object(gui, "show_status_message") as mock_status:
                gui.on_copy_window_screenshot_clicked(None, None, None)
                mock_capture.assert_called_once()
                mock_copy.assert_called_once_with(test_img)
                mock_status.assert_called_once()
                assert "copied to clipboard" in mock_status.call_args[0][0].lower()


def test_copy_image_to_clipboard():
    img = Image.new("RGBA", (50, 50), (255, 0, 0, 255))
    res = copy_image_to_clipboard(img)
    # On macOS with Cocoa, this should return True
    assert res is True
