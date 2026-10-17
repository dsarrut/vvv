"""save_image_async: files written in a thread, state updated on the main thread."""

import os
import time

import numpy as np
import SimpleITK as sitk

from vvv.core.controller import Controller


def _setup(tmp_path):
    c = Controller()
    c.use_history = False
    c.save_settings = lambda: None
    p = str(tmp_path / "a.nii")
    sitk.WriteImage(sitk.GetImageFromArray(np.full((4, 8, 8), 3, np.float32)), p)
    return c, c.file.load_image(p)


def _wait_for_commit(c):
    deadline = time.time() + 10
    while not c._main_commits and time.time() < deadline:
        time.sleep(0.005)


def test_save_success_updates_volume_on_commit(tmp_path):
    c, vs_id = _setup(tmp_path)
    out = str(tmp_path / "saved.nii.gz")
    c.save_image_async(vs_id, out)
    _wait_for_commit(c)
    assert os.path.exists(out)
    assert c.volumes[vs_id].name == "a.nii"  # not changed by the worker
    c.run_main_thread_commits()
    assert c.volumes[vs_id].name == "saved.nii.gz"
    assert c.status_message == "Saved: saved.nii.gz"


def test_save_failure_is_reported_and_changes_nothing(tmp_path):
    c, vs_id = _setup(tmp_path)
    c.save_image_async(vs_id, str(tmp_path / "missing_dir" / "x.nii"))
    _wait_for_commit(c)
    c.run_main_thread_commits()
    assert c.status_message.startswith("Save failed (x.nii)")
    assert c.volumes[vs_id].name == "a.nii"
