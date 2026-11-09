"""Side-car badge (issue 54): the image list shows when an image uses side-car
files, the side-car transform can be turned off and on, the viewer marks a
side-car transform, and label-map ROIs show their names/colors json."""

import json
from types import SimpleNamespace

import dearpygui.dearpygui as dpg
import numpy as np
import SimpleITK as sitk

from vvv.app import build_app
from vvv.core.roi_manager import ROIState
from vvv.ui import ui_sidecar as sc
from vvv.ui.ui_image_list import refresh_image_list_ui, sync_image_list_ui
from vvv.ui.viewer import SliceViewer

SHIFT = (5.0, 0.0, -10.0)


def _ct(tmp_path, tfm=True, unit=None):
    sitk.WriteImage(sitk.GetImageFromArray(np.zeros((8, 8, 8), np.float32)), str(tmp_path / "ct.nii.gz"))
    if tfm:
        sitk.WriteTransform(sitk.TranslationTransform(3, SHIFT), str(tmp_path / "ct.tfm"))
    if unit:
        (tmp_path / "ct.json").write_text(json.dumps({"unit": unit, "1": "liver", "2": "kidney"}))
    c, _ = build_app(use_history=False)
    return c, c.file.load_image(str(tmp_path / "ct.nii.gz"))


def test_badge_state(tmp_path):
    c, vid = _ct(tmp_path, tfm=False)
    vs = c.view_states[vid]
    assert sc.badge_state(vs.volume, vs.space) is None

    vs.volume.sidecar_json_path = str(tmp_path / "ct.json")
    assert sc.badge_state(vs.volume, vs.space) == sc.BADGE_MUTED


def test_transform_toggle_keeps_it_and_the_crosshair(tmp_path):
    c, vid = _ct(tmp_path)
    vs = c.view_states[vid]
    assert sc.badge_state(vs.volume, vs.space) == sc.BADGE_APPLIED
    world = np.array(vs.camera.crosshair_phys_coord, dtype=float)
    t = vs.space.transform

    assert c.set_transform_active(vid, False)
    assert not vs.space.is_active and vs.space.transform is t and vs.space.from_sidecar
    np.testing.assert_allclose(vs.camera.crosshair_phys_coord, world)
    assert sc.badge_state(vs.volume, vs.space) == sc.BADGE_MUTED
    assert "transform, off" in sc.image_sidecar_lines(vs.volume, vs.space)[0]["text"]

    assert c.set_transform_active(vid, True)
    assert vs.space.is_active and vs.space.transform is t
    assert sc.badge_state(vs.volume, vs.space) == sc.BADGE_APPLIED


def test_unloaded_sidecar_can_be_applied_again(tmp_path):
    c, vid = _ct(tmp_path)
    vs = c.view_states[vid]
    c.unload_transform(vid)
    assert vs.space.transform is None and vs.space.sidecar_file
    lines = sc.image_sidecar_lines(vs.volume, vs.space)
    assert lines[0]["text"] == "transform, unloaded" and not lines[0]["applied"]

    assert c.set_transform_active(vid, True)
    assert vs.space.from_sidecar and vs.space.is_active
    np.testing.assert_allclose(vs.space.transform.TransformPoint((0, 0, 0)), -np.array(SHIFT), atol=1e-9)


def test_json_summary_and_lines(tmp_path):
    c, vid = _ct(tmp_path, unit="bqml")
    vs = c.view_states[vid]
    lines = sc.image_sidecar_lines(vs.volume, vs.space)
    assert [l["kind"] for l in lines] == ["json", "tfm"]
    assert lines[0]["text"] == "unit bqml, 2 labels"
    assert lines[1]["text"] == "transform, applied"
    tip = sc.tooltip_text(lines)
    assert "ct.json: unit bqml, 2 labels" in tip and "ct.tfm: transform, applied" in tip


def test_viewer_marks_the_sidecar_transform(tmp_path):
    c, vid = _ct(tmp_path)
    vs = c.view_states[vid]
    assert SliceViewer._sidecar_tfm_suffix(vs) == " ·tfm"
    c.set_transform_active(vid, False)
    assert SliceViewer._sidecar_tfm_suffix(vs) == ""
    # A transform loaded from another file is not marked
    vs.space.from_sidecar, vs.space.is_active = False, True
    assert SliceViewer._sidecar_tfm_suffix(vs) == ""


def test_image_list_badge(headless_gui_app, tmp_path):
    c, gui, viewer, vid = headless_gui_app
    refresh_image_list_ui(gui)
    sync_image_list_ui(gui)
    tag = f"btn_sidecar_{vid}"
    assert dpg.does_item_exist(tag)
    assert not dpg.is_item_shown(tag)  # no side-car

    tfm = tmp_path / "synthetic_1.tfm"
    sitk.WriteTransform(sitk.TranslationTransform(3, SHIFT), str(tfm))
    assert c.apply_transform_sidecar(vid)
    sync_image_list_ui(gui)
    assert dpg.is_item_shown(tag)
    assert dpg.get_item_theme(tag) == "sidecar_badge_applied_theme"
    assert "synthetic_1.tfm: transform, applied" in dpg.get_value(f"text_sidecar_tip_{vid}")

    c.set_transform_active(vid, False)
    sync_image_list_ui(gui)
    assert dpg.get_item_theme(tag) == "sidecar_badge_muted_theme"

    sc.open_image_popup(gui, vid)  # builds without error
    assert dpg.does_item_exist("sidecar_popup")


def _label_rois(tmp_path):
    lm = str(tmp_path / "labels.nii.gz")
    js = tmp_path / "labels.json"
    js.write_text(json.dumps({"1": {"name": "liver", "color": [255, 0, 0]}, "2": "kidney"}))
    vols, rois = {}, {}
    for i, (name, val) in enumerate((("liver", 1), ("kidney", 2))):
        rois[f"r{i}"] = ROIState(f"r{i}", name, [255, 0, 0] if val == 1 else [0, 255, 0],
                                 source_val=val, source_type="Label Map")
        vols[f"r{i}"] = SimpleNamespace(file_paths=[lm, str(js)], name=name)
    rois["x"] = ROIState("x", "drawn", [0, 0, 255], source_type="Created")
    vols["x"] = SimpleNamespace(file_paths=[], name="drawn")
    return lm, str(js), rois, vols


def test_label_map_sidecar_modified_and_read_again(tmp_path):
    lm, js, rois, vols = _label_rois(tmp_path)
    assert sc.roi_label_sidecars(rois, vols) == {lm: js}
    assert sc.roi_label_sidecars(rois, vols, source_filter="other.nii.gz") == {}
    assert not sc.label_sidecar_modified(rois, vols, lm)

    rois["r0"].name = "Liver (edited)"
    rois["r1"].color = [1, 2, 3]  # kidney has no color in the json: not a change
    assert sc.label_sidecar_modified(rois, vols, lm)

    assert sc.reload_label_names(rois, vols, lm) == 1
    assert rois["r0"].name == "liver" and vols["r0"].name == "liver"
    assert rois["r1"].color[:3] == [1, 2, 3]
    assert not sc.label_sidecar_modified(rois, vols, lm)
    assert rois["x"].name == "drawn"


def test_roi_panel_badge(headless_gui_app, tmp_path):
    c, gui, viewer, vid = headless_gui_app
    lm, js, rois, vols = _label_rois(tmp_path)
    ui = gui.get_plugin("roi_plugin")._ui
    tag = ui._t("btn_roi_sidecar")
    assert dpg.does_item_exist(tag)

    ui._update_sidecar_badge(rois, vols, None)
    assert dpg.is_item_shown(tag)
    assert not dpg.is_item_shown(ui._t("text_roi_sidecar_modified"))
    assert "labels.json: names and colors" in dpg.get_value(ui._t("text_roi_sidecar_tip"))

    rois["r0"].name = "edited"
    ui._update_sidecar_badge(rois, vols, None)
    assert dpg.is_item_shown(ui._t("text_roi_sidecar_modified"))
    assert "(modified in vvv, unsaved)" in dpg.get_value(ui._t("text_roi_sidecar_tip"))
    ui.on_roi_sidecar_clicked()
    assert dpg.does_item_exist(ui._t("roi_sidecar_popup"))

    ui._update_sidecar_badge({"x": rois["x"]}, vols, None)  # no label map
    assert not dpg.is_item_shown(tag)


def test_json_text_load_and_save(tmp_path):
    p = tmp_path / "ct.json"
    p.write_text('{"unit":"hu","1":"liver"}')
    text, err = sc.load_json_text(str(p))
    assert err is None and '"unit": "hu"' in text and "\n" in text  # pretty

    assert "not valid JSON" in sc.save_json_text(str(p), '{"unit": ')
    assert json.loads(p.read_text()) == {"unit": "hu", "1": "liver"}  # unchanged

    assert sc.save_json_text(str(p), '{"unit": "Gy"}') is None
    assert json.loads(p.read_text()) == {"unit": "Gy"}

    p.write_text(json.dumps({"1": {"name": "liver", "color": [200, 80, 60]}}))
    text, _ = sc.load_json_text(str(p))
    assert '"color": [200, 80, 60]' in text
    assert sc.save_json_text(str(p), text) is None
    assert p.read_text() == text + "\n"  # as typed

    p.write_text("{broken")
    text, err = sc.load_json_text(str(p))
    assert text == "{broken" and "not valid JSON" in err


def test_json_window_save_reads_the_unit_again(headless_gui_app, tmp_path):
    c, gui, viewer, vid = headless_gui_app
    js = tmp_path / "synthetic_1.json"
    js.write_text(json.dumps({"unit": "hu"}))
    vol = c.volumes[vid]
    vol._detect_unit_and_source()
    assert vol.unit == "HU" and vol.sidecar_json_path

    sc._on_open_json(gui, vid, str(js))
    box = f"{sc.JSON_WINDOW}_text"
    assert dpg.does_item_exist(box) and '"unit": "hu"' in dpg.get_value(box)

    dpg.set_value(box, '{"unit": ')  # invalid: refused, file kept
    save = dpg.get_item_children(dpg.get_item_children(sc.JSON_WINDOW, 1)[-1], 1)[0]
    dpg.get_item_callback(save)()
    assert "not valid JSON" in dpg.get_value(f"{sc.JSON_WINDOW}_status")
    assert json.loads(js.read_text()) == {"unit": "hu"}

    dpg.set_value(box, '{"unit": "gy"}')
    dpg.get_item_callback(save)()
    assert json.loads(js.read_text()) == {"unit": "gy"}
    assert vol.unit == "Gy"  # read again after the save
