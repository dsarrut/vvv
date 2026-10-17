"""Image ids must stay unique when images are loaded in parallel."""

import threading
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import SimpleITK as sitk

from vvv.core.controller import Controller


def test_allocate_image_id_is_thread_safe():
    c = Controller()
    ids, barrier = [], threading.Barrier(8)

    def worker():
        barrier.wait()
        ids.extend(c.allocate_image_id() for _ in range(5000))

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(ids) == len(set(ids)) == 8 * 5000


def test_parallel_loads_get_distinct_ids(tmp_path):
    c = Controller()
    c.use_history = False
    c.save_settings = lambda: None
    paths = []
    for i in range(8):
        p = str(tmp_path / f"img{i}.nii")
        sitk.WriteImage(sitk.GetImageFromArray(np.full((4, 8, 8), i, np.float32)), p)
        paths.append(p)
    with ThreadPoolExecutor(max_workers=4) as ex:  # as the load sequences do
        ids = list(ex.map(c.file.load_image, paths))
    assert len(set(ids)) == 8
    assert sorted(c.view_states) == sorted(ids)
