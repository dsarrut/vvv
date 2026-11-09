"""ROIs outside the image FOV: a status bar warning, no dialog to close
(the loading goes on); a label map can have many: 3 names shown."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from vvv.ui.ui_sequences import _warn_rois_outside_fov


def _run(n_outside, n_inside=2):
    gui = MagicMock()
    rois, volumes = {}, {}
    for i in range(n_outside + n_inside):
        rid = f"r{i}"
        rois[rid] = SimpleNamespace(name=f"roi_{i}")
        volumes[rid] = SimpleNamespace(is_outside=i < n_outside)
    list(_warn_rois_outside_fov(gui, SimpleNamespace(volumes=volumes), rois))
    return gui


def test_no_roi_outside_no_message():
    gui = _run(0)
    gui.show_status_message.assert_not_called()
    gui.show_message.assert_not_called()


def test_many_rois_outside_in_the_status_bar():
    gui = _run(5)
    gui.show_message.assert_not_called()
    (msg,), kwargs = gui.show_status_message.call_args
    assert msg == (
        "5 ROIs lie partially or fully outside the image FOV: "
        "'roi_0', 'roi_1', 'roi_2' (+2 more)"
    )
    assert kwargs["duration"] == 10.0
