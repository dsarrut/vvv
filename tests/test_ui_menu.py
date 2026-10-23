import json
import shlex

import dearpygui.dearpygui as dpg

from vvv.ui.ui_menu import _describe_recent


def test_describe_recent_file(tmp_path):
    f = tmp_path / "ct.nii.gz"
    f.write_bytes(b"")
    assert _describe_recent(str(f)) == ("ct.nii.gz", str(f), True)
    assert _describe_recent(str(tmp_path / "gone.mhd"))[2] is False


def test_describe_recent_dicom_series(tmp_path):
    d = tmp_path / "series_a"
    d.mkdir()
    files = [str(d / "1.dcm"), str(d / "2.dcm")]
    open(files[0], "w").close()
    label, tooltip, exists = _describe_recent(files)
    assert label == "series_a (DICOM Series)"
    assert tooltip == "\n".join(files)
    assert exists
    assert _describe_recent([])[2] is False


def test_describe_recent_4d(tmp_path):
    frame = tmp_path / "frame 0.nii"  # space: needs shell quoting
    frame.write_bytes(b"")
    entry = "4D:" + shlex.join([str(frame), str(tmp_path / "frame1.nii")])
    assert _describe_recent(entry) == ("4D: frame 0.nii...", entry, True)
    assert _describe_recent('4D:"unclosed')[0:3:2] == ("4D Sequence", False)


def test_recent_menu_shares_one_missing_theme(headless_gui_app, tmp_path):
    controller, gui, _, _ = headless_gui_app
    present = tmp_path / "here.nii.gz"
    present.write_bytes(b"")
    controller.settings.data.setdefault("behavior", {})["recent_files"] = [
        str(present),
        str(tmp_path / "gone1.nii.gz"),
        json.dumps([str(tmp_path / "gone_dir" / "1.dcm")]),
    ]
    n_items = None
    for _ in range(3):
        gui.refresh_recent_menu()
        items = dpg.get_item_children("menu_recent_files", 1)
        n_items = n_items or len(items)
        assert len(items) == n_items  # rebuilt, not appended

    labels = [dpg.get_item_label(i) for i in items]
    assert "here.nii.gz" in labels
    assert "gone1.nii.gz (Missing)" in labels
    assert "gone_dir (DICOM Series) (Missing)" in labels
    missing = [i for i in items if "(Missing)" in (dpg.get_item_label(i) or "")]
    assert {dpg.get_item_theme(i) for i in missing} == {"missing_recent_theme"}
