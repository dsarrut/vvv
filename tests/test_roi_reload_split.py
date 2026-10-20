"""ROI reload: core closes the ROIs of a label map, the plugin API starts the
UI loading sequence (D1: core does not touch gui.tasks)."""

import numpy as np
import SimpleITK as sitk


def _load_two_labels(controller, vs_id, tmp_path):
    base = controller.volumes[vs_id]
    lab = np.zeros(base.shape3d, dtype=np.uint8)
    lab[2:5, 2:5, 2:5] = 1
    lab[8:12, 8:12, 8:12] = 2
    img = sitk.GetImageFromArray(lab)
    img.CopyInformation(base.sitk_image)
    path = str(tmp_path / "labels.nii.gz")
    sitk.WriteImage(img, path)
    data = sitk.GetArrayViewFromImage(img)
    return [
        controller.roi.extract_label_from_image(
            vs_id, path, img, data, v, f"L{v}", [255, 0, 0], None
        )
        for v in (1, 2)
    ]


def test_label_map_reload_goes_through_plugin_api(headless_gui_app, tmp_path):
    controller, gui, viewer, vs_id = headless_gui_app
    vs = controller.view_states[vs_id]
    roi_ids = _load_two_labels(controller, vs_id, tmp_path)
    vs.rois[roi_ids[1]].opacity = 0.25
    n_tasks = len(gui.tasks)

    gui.plugin_api.reload_roi(vs_id, roi_ids[0])

    assert not any(r in vs.rois for r in roi_ids)  # whole file closed
    assert len(gui.tasks) == n_tasks + 1  # one label map sequence queued


def test_take_file_rois_for_reload_keeps_preferences(headless_gui_app, tmp_path):
    controller, gui, viewer, vs_id = headless_gui_app
    vs = controller.view_states[vs_id]
    roi_ids = _load_two_labels(controller, vs_id, tmp_path)
    vs.rois[roi_ids[1]].opacity = 0.25

    source_type, path, prefs = controller.roi.take_file_rois_for_reload(vs_id, roi_ids[0])

    assert source_type == "Label Map" and path.endswith("labels.nii.gz")
    assert set(prefs) == {1, 2}
    assert prefs[2]["opacity"] == 0.25
    assert controller.roi.take_file_rois_for_reload(vs_id, roi_ids[0]) is None  # closed


def _run(gen, timeout=30.0):
    """Step a GUI sequence to its end (workers run in real time)."""
    import time

    t_end = time.perf_counter() + timeout
    while time.perf_counter() < t_end:
        try:
            next(gen)
        except StopIteration:
            return
    raise AssertionError("sequence did not finish")


def test_label_map_reload_end_to_end(headless_gui_app, tmp_path, monkeypatch):
    import time
    import vvv.ui.ui_sequences as seq

    monkeypatch.setattr(time, "sleep", lambda s: None)
    controller, gui, viewer, vs_id = headless_gui_app
    vs = controller.view_states[vs_id]
    base = controller.volumes[vs_id]
    lab = np.zeros(base.shape3d, dtype=np.uint8)
    lab[2:5, 2:5, 2:5] = 1
    lab[8:12, 8:12, 8:12] = 2
    img = sitk.GetImageFromArray(lab)
    img.CopyInformation(base.sitk_image)
    path = str(tmp_path / "labels.nii.gz")
    sitk.WriteImage(img, path)

    _run(seq.load_label_map_sequence(gui, controller, vs_id, path))
    by_val = {int(r.source_val): r for r in vs.rois.values()}
    assert set(by_val) == {1, 2}
    by_val[2].opacity = 0.25
    by_val[2].visible = False

    gui.tasks.clear()
    gui.plugin_api.reload_roi(vs_id, next(iter(vs.rois)))
    assert len(gui.tasks) == 1
    _run(gui.tasks.pop())

    by_val = {int(r.source_val): r for r in vs.rois.values()}
    assert set(by_val) == {1, 2}  # each label once, none duplicated or lost
    assert by_val[2].opacity == 0.25
    assert by_val[2].visible is False
    assert by_val[1].visible is True
