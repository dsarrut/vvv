"""Issue 49: a workspace's crosshair is restored from its saved native voxel
(the image's anatomy), the world point recomputed with the image's transform.
The saved world point is right only if written with that same transform."""

import json
from unittest.mock import MagicMock

import numpy as np
import pytest
import SimpleITK as sitk

from vvv.core.controller import Controller
from vvv.ui.ui_sequences import load_workspace_sequence

TZ = -1900.0  # a registered time point: ~2 m in z
SHIFT = np.array([5.0, 0.0, TZ])  # translation of the .tfm


def _world(native):
    """World point of a native one: vvv reads a .tfm as world -> native."""
    return np.asarray(native) - SHIFT


def _ct(tmp_path, with_tfm):
    img = sitk.Image(64, 64, 40, sitk.sitkInt16)
    img.SetSpacing((1.0, 1.0, 1.5))
    img.SetOrigin((-30.0, -20.0, -1900.0))
    path = tmp_path / "ct.nii.gz"
    sitk.WriteImage(img, str(path))
    if with_tfm:
        t = sitk.Euler3DTransform()
        t.SetTranslation(tuple(SHIFT))
        sitk.WriteTransform(t, str(tmp_path / "ct.tfm"))
    return path, img


def _load(tmp_path, ct_path, camera):
    ws = {
        "version": 1.0,
        "viewers": {},
        "images": {"1": {"path": str(ct_path), "display": {}, "camera": camera,
                         "extraction": {}, "dvf": {}, "rois": [], "profiles": []}},
    }
    ws_path = tmp_path / "ws.vvw"
    ws_path.write_text(json.dumps(ws))
    gui = MagicMock()
    gui.plugins = []
    c = Controller()
    list(load_workspace_sequence(gui, c, str(ws_path)))
    return c.view_states[next(iter(c.view_states))]


def test_crosshair_from_the_voxel_with_a_transform(tmp_path):
    """A script wrote the world point in the image's native mm: the voxel wins."""
    ct_path, img = _ct(tmp_path, with_tfm=True)
    voxel = [40.0, 30.0, 20.0]
    native = list(img.TransformContinuousIndexToPhysicalPoint(voxel))
    vs = _load(tmp_path, ct_path, {"crosshair_voxel": voxel + [0.0], "crosshair_phys_coord": native})
    assert vs.space.is_active and vs.space.transform is not None
    np.testing.assert_allclose(vs.camera.crosshair_voxel[:3], voxel, atol=1e-6)
    np.testing.assert_allclose(vs.camera.crosshair_phys_coord, _world(native), atol=1e-6)


@pytest.mark.parametrize("with_tfm", [False, True], ids=["no_transform", "transform"])
def test_a_workspace_saved_by_vvv_restores_as_saved(tmp_path, with_tfm):
    """Voxel and world point agree (vvv saves both): the same crosshair."""
    ct_path, img = _ct(tmp_path, with_tfm)
    voxel = [12.3, 45.6, 7.8]
    native = img.TransformContinuousIndexToPhysicalPoint(voxel)
    world = _world(native) if with_tfm else np.asarray(native)
    vs = _load(tmp_path, ct_path, {"crosshair_voxel": voxel + [0.0], "crosshair_phys_coord": world.tolist()})
    np.testing.assert_allclose(vs.camera.crosshair_voxel[:3], voxel, atol=1e-6)
    np.testing.assert_allclose(vs.camera.crosshair_phys_coord, world, atol=1e-6)


@pytest.mark.parametrize("voxel", [None, [500.0, 30.0, 20.0, 0.0]], ids=["no_voxel", "voxel_outside"])
def test_the_world_point_is_kept_without_a_usable_voxel(tmp_path, voxel):
    ct_path, img = _ct(tmp_path, with_tfm=False)
    world = list(img.TransformContinuousIndexToPhysicalPoint([10.0, 11.0, 12.0]))
    camera = {"crosshair_phys_coord": world}
    if voxel is not None:
        camera["crosshair_voxel"] = voxel
    vs = _load(tmp_path, ct_path, camera)
    np.testing.assert_allclose(vs.camera.crosshair_phys_coord, world, atol=1e-6)


def test_every_viewer_of_a_workspace_is_centred_on_the_crosshair(tmp_path):
    """needs_recenter on 4 viewers of one image, with other zooms: the first
    drawn sets the image's ppm (zoom sync); the others took it and dropped
    their recenter (pan left at 0: off screen for a moved image)."""
    import time

    from vvv.app import build_app
    from vvv.ui.drawing import world_to_screen_pos
    from vvv.utils import ViewMode

    ct_path, img = _ct(tmp_path, with_tfm=True)
    c, gui = build_app(use_history=False)
    bid = c.file.load_image(str(ct_path))
    vs = c.view_states[bid]
    vs.update_crosshair_from_phys(_world(img.TransformContinuousIndexToPhysicalPoint([50.0, 15.0, 30.0])))
    views = (("V1", ViewMode.CORONAL, 6.0), ("V2", ViewMode.SAGITTAL, 6.0),
             ("V3", ViewMode.CORONAL, 6.0), ("V4", ViewMode.AXIAL, 2.0))
    for tag, ori, zoom in views:
        c.layout[tag] = bid
        c.viewers[tag].resize(400, 300)
        c.viewers[tag].restore_view(bid, orientation=ori, zoom=zoom, pan_offset=[0.0, 0.0], needs_recenter=True)
    assert c.wait_for_jobs(timeout=10)
    for _ in range(10):
        c.tick()
        time.sleep(0.01)
    for tag, _, _ in views:
        v = c.viewers[tag]
        cw, ch = v._get_canvas_size()
        x, y = world_to_screen_pos(v, vs.camera.crosshair_phys_coord)
        assert abs(x - cw / 2) < 0.1 * cw and abs(y - ch / 2) < 0.1 * ch, (tag, x, y, cw, ch)
