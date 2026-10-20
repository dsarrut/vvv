"""FileManager.read_image() (worker thread) / register_image() (main thread)."""

import threading

import numpy as np
import SimpleITK as sitk

from vvv.core.controller import Controller


def _write(path, value):
    sitk.WriteImage(sitk.GetImageFromArray(np.full((4, 8, 8), value, np.float32)), str(path))
    return str(path)


def test_read_image_registers_nothing(tmp_path):
    c = Controller()
    c.use_history = False
    loaded = c.file.read_image(_write(tmp_path / "a.nii", 1.0))
    assert not c.view_states and not c.volumes
    assert loaded["vol"] is not None and loaded["vs"] is not None


def test_history_overlay_is_read_in_the_worker_and_linked_on_register(tmp_path):
    base_path = _write(tmp_path / "base.nii", 1.0)
    ov_path = _write(tmp_path / "ov.nii", 2.0)
    c = Controller()
    c.save_settings = lambda: None
    # history remembers an overlay for the base image
    real = c.history.get_image_state
    c.history.get_image_state = lambda vol: (
        {"camera": {}, "display": {}, "overlay_path": ov_path}
        if vol.file_paths[0] == base_path else real(vol)
    )

    reads = []
    original_read = c.file.read_image

    def spy_read(*a, **k):
        reads.append(threading.current_thread() is threading.main_thread())
        return original_read(*a, **k)

    c.file.read_image = spy_read
    result = {}
    worker = threading.Thread(target=lambda: result.update(loaded=c.file.read_image(base_path)))
    worker.start()
    worker.join()
    assert reads == [False, False]  # base + its overlay, both in the worker
    assert result["loaded"]["overlay"] is not None  # overlay already read there
    assert not c.view_states

    base_id = c.file.register_image(result["loaded"])  # main thread
    assert len(c.view_states) == 2
    ov_id = c.view_states[base_id].display.overlay.image_id
    assert ov_id is not None and ov_id != base_id
    assert float(c.volumes[ov_id].data.max()) == 2.0
