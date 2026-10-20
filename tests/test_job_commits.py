"""Background jobs compute on a worker; their results are applied on the main
thread only (Controller.run_main_thread_commits, called by tick())."""

import time

import numpy as np
import SimpleITK as sitk

from vvv.core.controller import Controller


def _make(tmp_path):
    c = Controller()
    c.use_history = False
    c.save_settings = lambda: None
    ids = []
    for name, value, spacing in [("base", 1.0, 1.0), ("ov", 7.0, 2.0)]:
        img = sitk.GetImageFromArray(np.full((10, 20, 20), value, np.float32))
        img.SetSpacing((spacing,) * 3)
        path = str(tmp_path / f"{name}.nii")
        sitk.WriteImage(img, path)
        ids.append(c.file.load_image(path))
    base, ov = ids
    c.view_states[base].set_overlay(ov, c.volumes[ov])
    return c, base, ov


def _wait_worker(c, image_id):
    deadline = time.time() + 10
    while not c._get_job_runner(image_id).is_idle() and time.time() < deadline:
        time.sleep(0.005)


def test_resample_result_is_applied_only_by_the_main_thread_commit(tmp_path):
    c, base, _ = _make(tmp_path)
    vs = c.view_states[base]
    c.resample_image(base)
    _wait_worker(c, base)
    assert vs.display.overlay_data is None  # computed, not applied yet
    c.run_main_thread_commits()
    assert vs.display.overlay_data is not None
    assert float(vs.display.overlay_data.max()) == 7.0


def test_superseded_resample_is_discarded_at_commit(tmp_path):
    c, base, _ = _make(tmp_path)
    vs = c.view_states[base]
    c.resample_image(base)
    _wait_worker(c, base)
    c.update_transform_manual(base, 5, 0, 0, 0, 0, 0)  # invalidates the job
    c.run_main_thread_commits()
    assert vs.display.overlay_data is None
    assert "discarded" in c.status_message


def test_invalidate_resample_discards_job_at_commit(tmp_path):
    c, base, _ = _make(tmp_path)
    vs = c.view_states[base]
    c.resample_image(base)
    _wait_worker(c, base)
    c.invalidate_resample(base)
    c.run_main_thread_commits()
    assert vs.display.overlay_data is None
    assert "discarded" in c.status_message


def test_bake_commits_on_main_thread_and_relinks_overlay(tmp_path):
    c, base, ov = _make(tmp_path)
    vs = c.view_states[base]
    tx = sitk.Euler3DTransform()
    tx.SetTranslation((3.0, 0.0, 0.0))
    vs.space.transform = tx
    vs.space.is_active = True
    old_sitk = c.volumes[base].sitk_image

    c.bake_transform_to_volume(base)
    assert c.wait_for_jobs(timeout=10)
    assert c.volumes[base].sitk_image is not old_sitk
    assert vs.space.transform is None and not vs.space.is_active
    assert vs.display.overlay.image_id == ov and vs.display.overlay_data is not None
    assert c.status_message == "Transform baked into image" or "Resampling" in c.status_message


def test_save_image_async_callbacks_run_on_main_thread(tmp_path):
    c, base, _ = _make(tmp_path)
    save_path = str(tmp_path / "saved_base.nii")
    done_called = False
    error_called = False

    def on_done():
        nonlocal done_called
        done_called = True

    def on_error(err):
        nonlocal error_called
        error_called = True

    c.save_image_async(base, save_path, on_done=on_done, on_error=on_error)
    # Background thread writes the file; main thread commit queue receives callback
    deadline = time.time() + 5
    while not c._main_commits and time.time() < deadline:
        time.sleep(0.01)

    assert not done_called  # Not called until run_main_thread_commits
    c.run_main_thread_commits()
    assert done_called
    assert not error_called
    assert c.volumes[base].path == save_path

