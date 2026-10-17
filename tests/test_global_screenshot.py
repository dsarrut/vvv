import sys
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
    if sys.platform == "darwin":
        # On macOS with Cocoa, this should return True
        assert res is True
    else:
        # On headless Linux/Windows CI runners without clipboard tools installed
        assert isinstance(res, bool)


def test_copy_image_to_clipboard_windows():
    img = Image.new("RGBA", (10, 10), (0, 255, 0, 255))
    with patch("sys.platform", "win32"):
        mock_win32clipboard = MagicMock()
        with patch.dict("sys.modules", {"win32clipboard": mock_win32clipboard}):
            res = copy_image_to_clipboard(img)
            assert res is True
            mock_win32clipboard.OpenClipboard.assert_called_once()
            mock_win32clipboard.EmptyClipboard.assert_called_once()
            mock_win32clipboard.SetClipboardData.assert_called_once()
            mock_win32clipboard.CloseClipboard.assert_called_once()


def test_copy_image_to_clipboard_linux_xclip():
    img = Image.new("RGBA", (10, 10), (0, 255, 0, 255))
    with patch("sys.platform", "linux"):
        # Mock subprocess.Popen for xclip
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate.return_value = (b"", b"")

        def side_effect(cmd, *args, **kwargs):
            if "wl-copy" in cmd[0]:
                raise FileNotFoundError()
            if "xclip" in cmd[0]:
                # Verify that -i is present in the arguments
                assert "-i" in cmd
                return mock_proc
            raise FileNotFoundError()

        with patch("subprocess.Popen", side_effect=side_effect):
            res = copy_image_to_clipboard(img)
            assert res is True


def test_copy_image_to_clipboard_linux_failure_and_fallback(headless_gui_app, tmp_path):
    controller, gui, viewer, vs_id = headless_gui_app
    test_img = Image.new("RGBA", (100, 100), (0, 0, 255, 255))

    with patch("sys.platform", "linux"):
        with patch("subprocess.Popen", side_effect=FileNotFoundError):
            assert copy_image_to_clipboard(test_img) is False

    # Verify fallback in GUI saves file and updates status message
    with patch("vvv.ui.gui.capture_whole_window", return_value=test_img):
        with patch("vvv.ui.gui.copy_image_to_clipboard", return_value=False):
            with patch("vvv.utils.Path.home", return_value=tmp_path):
                with patch.object(gui, "show_status_message") as mock_status:
                    gui.on_copy_window_screenshot_clicked(None, None, None)
                    mock_status.assert_called_once()
                    status_text = mock_status.call_args[0][0]
                    assert "Saved screenshot to" in status_text
                    # Check file actually exists in tmp_path
                    saved_files = list(tmp_path.glob("vvv_screenshot_*.png"))
                    assert len(saved_files) == 1
