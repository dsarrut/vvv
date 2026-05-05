"""Tests for OS drag-and-drop support (vvv.ui.ui_drop and MainGUI.on_file_drop).

What IS tested here
-------------------
- on_file_drop routing: image files → batch loader, .vvw → workspace loader,
  mixed input, empty / None input, multi-workspace truncation.
- install_os_drop platform dispatch (mocked platform functions).
- cleanup_os_drop clears module globals and calls the right teardown.

What is NOT tested
------------------
- Actual OS drag events (Finder / Nautilus / Explorer) — those require a
  real desktop session and human interaction.
- GLFW / Win32 / NSView internals — they wrap OS APIs that can't be driven
  from a headless test environment.
"""

import sys
from unittest.mock import MagicMock, call, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_gui(gui):
    """Attach a fresh task list so we can inspect what on_file_drop queued."""
    gui.tasks = []
    return gui


# ---------------------------------------------------------------------------
# on_file_drop routing
# ---------------------------------------------------------------------------

class TestOnFileDrop:
    @patch("vvv.ui.gui.load_batch_images_sequence", return_value=iter([]))
    @patch("vvv.ui.gui.load_workspace_sequence",    return_value=iter([]))
    def test_single_image_file(self, mock_ws, mock_batch, headless_gui_app):
        _, gui, *_ = headless_gui_app
        _make_mock_gui(gui)
        gui.on_file_drop(None, ["/data/scan.nii.gz"], None)
        mock_batch.assert_called_once()
        mock_ws.assert_not_called()
        assert len(gui.tasks) == 1

    @patch("vvv.ui.gui.load_batch_images_sequence", return_value=iter([]))
    @patch("vvv.ui.gui.load_workspace_sequence",    return_value=iter([]))
    def test_multiple_image_files(self, mock_ws, mock_batch, headless_gui_app):
        _, gui, *_ = headless_gui_app
        _make_mock_gui(gui)
        gui.on_file_drop(None, ["/a.nii", "/b.mha", "/c.nrrd"], None)
        mock_batch.assert_called_once()
        # all three paths forwarded together
        passed_paths = mock_batch.call_args[0][2]
        assert passed_paths == ["/a.nii", "/b.mha", "/c.nrrd"]
        mock_ws.assert_not_called()

    @patch("vvv.ui.gui.load_batch_images_sequence", return_value=iter([]))
    @patch("vvv.ui.gui.load_workspace_sequence",    return_value=iter([]))
    def test_workspace_file(self, mock_ws, mock_batch, headless_gui_app):
        _, gui, *_ = headless_gui_app
        _make_mock_gui(gui)
        gui.on_file_drop(None, ["/path/session.vvw"], None)
        mock_ws.assert_called_once()
        assert mock_ws.call_args[0][2] == "/path/session.vvw"
        assert gui.current_workspace_path == "/path/session.vvw"
        mock_batch.assert_not_called()

    @patch("vvv.ui.gui.load_batch_images_sequence", return_value=iter([]))
    @patch("vvv.ui.gui.load_workspace_sequence",    return_value=iter([]))
    def test_mixed_workspace_and_images(self, mock_ws, mock_batch, headless_gui_app):
        _, gui, *_ = headless_gui_app
        _make_mock_gui(gui)
        gui.on_file_drop(None, ["/scan.nii", "/session.vvw", "/other.mha"], None)
        mock_ws.assert_called_once()
        mock_batch.assert_called_once()
        image_paths = mock_batch.call_args[0][2]
        assert "/scan.nii" in image_paths
        assert "/other.mha" in image_paths
        assert "/session.vvw" not in image_paths

    @patch("vvv.ui.gui.load_batch_images_sequence", return_value=iter([]))
    @patch("vvv.ui.gui.load_workspace_sequence",    return_value=iter([]))
    def test_multiple_workspace_files_uses_first_only(self, mock_ws, mock_batch, headless_gui_app):
        _, gui, *_ = headless_gui_app
        _make_mock_gui(gui)
        gui.on_file_drop(None, ["/first.vvw", "/second.vvw"], None)
        mock_ws.assert_called_once()
        assert mock_ws.call_args[0][2] == "/first.vvw"

    @patch("vvv.ui.gui.load_batch_images_sequence", return_value=iter([]))
    @patch("vvv.ui.gui.load_workspace_sequence",    return_value=iter([]))
    def test_empty_list_does_nothing(self, mock_ws, mock_batch, headless_gui_app):
        _, gui, *_ = headless_gui_app
        _make_mock_gui(gui)
        gui.on_file_drop(None, [], None)
        mock_batch.assert_not_called()
        mock_ws.assert_not_called()
        assert gui.tasks == []

    @patch("vvv.ui.gui.load_batch_images_sequence", return_value=iter([]))
    @patch("vvv.ui.gui.load_workspace_sequence",    return_value=iter([]))
    def test_none_app_data_does_nothing(self, mock_ws, mock_batch, headless_gui_app):
        _, gui, *_ = headless_gui_app
        _make_mock_gui(gui)
        gui.on_file_drop(None, None, None)
        mock_batch.assert_not_called()
        mock_ws.assert_not_called()


# ---------------------------------------------------------------------------
# install_os_drop platform dispatch
# ---------------------------------------------------------------------------

class TestInstallOsDropDispatch:
    def test_dispatches_to_macos(self):
        import vvv.ui.ui_drop as m
        cb = MagicMock()
        with patch.object(sys, "platform", "darwin"), \
             patch.object(m, "_install_macos_drop") as mock_mac:
            m.install_os_drop(cb)
            mock_mac.assert_called_once_with(cb)

    def test_dispatches_to_linux(self):
        import vvv.ui.ui_drop as m
        cb = MagicMock()
        with patch.object(sys, "platform", "linux"), \
             patch.object(m, "_install_linux_drop") as mock_linux:
            m.install_os_drop(cb)
            mock_linux.assert_called_once_with(cb)

    def test_dispatches_to_windows(self):
        import vvv.ui.ui_drop as m
        cb = MagicMock()
        with patch.object(sys, "platform", "win32"), \
             patch.object(m, "_install_windows_drop") as mock_win:
            m.install_os_drop(cb)
            mock_win.assert_called_once_with(cb)

    def test_unknown_platform_does_nothing(self):
        import vvv.ui.ui_drop as m
        cb = MagicMock()
        with patch.object(sys, "platform", "freebsd"), \
             patch.object(m, "_install_macos_drop")   as mock_mac, \
             patch.object(m, "_install_linux_drop")   as mock_linux, \
             patch.object(m, "_install_windows_drop") as mock_win:
            m.install_os_drop(cb)
            mock_mac.assert_not_called()
            mock_linux.assert_not_called()
            mock_win.assert_not_called()


# ---------------------------------------------------------------------------
# cleanup_os_drop
# ---------------------------------------------------------------------------

class TestCleanupOsDrop:
    def test_clears_linux_globals_and_nulls_callback(self):
        import vvv.ui.ui_drop as m

        mock_glfw = MagicMock()
        m._linux_glfw        = mock_glfw
        m._linux_window      = 0xDEAD_BEEF
        m._linux_filter_ref  = MagicMock()

        m.cleanup_os_drop()

        mock_glfw.glfwSetDropCallback.assert_called_once()
        assert m._linux_glfw       is None
        assert m._linux_window     is None
        assert m._linux_filter_ref is None

    def test_clears_windows_globals(self):
        import vvv.ui.ui_drop as m

        fake_proc    = MagicMock()
        fake_hwnd    = 0x1234
        fake_origptr = 0x5678
        m._windows_drop_refs = (fake_proc, fake_hwnd, fake_origptr)

        # Patch away the actual Win32 calls so the test runs on any platform
        with patch("vvv.ui.ui_drop.getattr", create=True):
            try:
                m.cleanup_os_drop()
            except Exception:
                pass  # Win32 calls will fail on non-Windows; globals still cleared

        assert m._windows_drop_refs is None

    def test_safe_when_nothing_installed(self):
        import vvv.ui.ui_drop as m
        m._linux_glfw       = None
        m._linux_window     = None
        m._linux_filter_ref = None
        m._windows_drop_refs = None
        # Must not raise
        m.cleanup_os_drop()

    def test_swallows_errors_during_cleanup(self):
        import vvv.ui.ui_drop as m

        bad_glfw = MagicMock()
        bad_glfw.glfwSetDropCallback.side_effect = RuntimeError("boom")
        m._linux_glfw   = bad_glfw
        m._linux_window = 0x1

        m.cleanup_os_drop()  # must not propagate the RuntimeError

        assert m._linux_glfw is None
