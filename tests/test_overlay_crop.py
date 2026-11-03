"""A small overlay on a large base is resampled on its box of the base grid
only (CroppedOverlay), and reads exactly as the full resampled grid."""

import numpy as np
import pytest
import SimpleITK as sitk

import vvv.core.overlay_resampler as R
from vvv.core.overlay_resampler import CroppedOverlay, resample_overlay
from vvv.maths.image import SliceRenderer, VolumeData
from vvv.utils import ViewMode


def _write(tmp_path, name, arr, spacing, origin):
    img = sitk.GetImageFromArray(arr)
    img.SetSpacing(spacing)
    img.SetOrigin(origin)
    p = str(tmp_path / name)
    sitk.WriteImage(img, p)
    return VolumeData(p)


@pytest.fixture
def base_and_overlay(tmp_path):
    base = _write(tmp_path, "ct.nii", np.zeros((60, 40, 50), np.int16), (1.0, 1.0, 1.0), (0, 0, 0))
    rng = np.random.default_rng(0)
    pet = rng.random((5, 4, 6)).astype(np.float32) + 1.0
    ov = _write(tmp_path, "pet.nii", pet, (2.5, 2.5, 2.5), (12.3, 8.1, 20.7))
    return base, ov


def _full(base, ov, tr, monkeypatch):
    """(ITK image, full array): the array is a view of the image, keep both."""
    with monkeypatch.context() as m:
        m.setattr(R, "_overlay_box", lambda *a: None)
        cache, data, _ = resample_overlay(base, ov, None, tr)
        return cache, data


@pytest.mark.parametrize("with_transform", [False, True])
def test_cropped_overlay_reads_as_the_full_grid(base_and_overlay, monkeypatch, with_transform):
    base, ov = base_and_overlay
    tr = None
    if with_transform:
        tr = sitk.Euler3DTransform()
        tr.SetRotation(0.2, -0.1, 0.3)
        tr.SetTranslation((3.0, -2.0, 4.0))
    _keep, full = _full(base, ov, tr, monkeypatch)
    _, crop, _ = resample_overlay(base, ov, None, tr)

    assert isinstance(crop, CroppedOverlay) and isinstance(full, np.ndarray)
    assert crop.shape == full.shape and crop.nbytes < full.nbytes / 10
    assert np.array_equal(np.asarray(crop), full)
    for ori, n in ((ViewMode.AXIAL, 60), (ViewMode.CORONAL, 40), (ViewMode.SAGITTAL, 50)):
        for s in range(n):
            a = SliceRenderer.extract_slice(crop, False, 0, s, ori)
            assert np.array_equal(a, SliceRenderer.extract_slice(full, False, 0, s, ori))
    assert SliceRenderer.extract_slice(crop, False, 0, 60, ViewMode.AXIAL) is None
    assert np.array_equal(crop[10:30, 5:25, 15:45], full[10:30, 5:25, 15:45])  # ROI bbox
    mask = np.zeros(full.shape, bool)
    mask[18:25, 9:20, 20:30] = True
    assert np.array_equal(crop[mask], full[mask])  # ROI mask
    assert crop[20, 10, 25] == full[20, 10, 25]


def test_an_overlay_covering_the_base_is_not_cropped(tmp_path, base_and_overlay):
    base, _ = base_and_overlay
    big = _write(tmp_path, "big.nii", np.ones((30, 20, 25), np.float32), (2.0, 2.0, 2.0), (0, 0, 0))
    _, data, _ = resample_overlay(base, big, None, None)
    assert isinstance(data, np.ndarray) and data.shape == (60, 40, 50)


def _render_all(controller):
    """The RGBA of the 3 base viewers for every render mode, zoom pixelated or not."""
    from vvv.ui.render_strategy import NNMode

    vs = controller.viewers["V1"].view_state
    out = []
    for mode in NNMode:
        controller.settings.data["rendering"] = {
            "gl_nearest": mode == NNMode.HW_GL_NEAREST,
            "single_texture": mode in (NNMode.SW_SINGLE_MERGED, NNMode.SW_SINGLE_NATIVE),
            "native_voxel": mode in (NNMode.SW_DUAL_NATIVE, NNMode.SW_SINGLE_NATIVE),
            "lazy_lin": False,
        }
        for pixelated in (False, True):
            vs.display.pixelated_zoom = pixelated
            for tag in ("V1", "V2", "V3"):
                v = controller.viewers[tag]
                v.resize(400, 300)
                v.is_geometry_dirty = True
                v.update_render(force_reblend=True)
                ov = v.last_overlay_rgba_flat
                out.append((np.array(v.last_rgba_flat), None if ov is None else np.array(ov)))
    return out


def test_views_are_the_same_with_a_cropped_overlay(tmp_path, monkeypatch):
    from vvv.app import build_app
    from vvv.utils import ViewMode

    rng = np.random.default_rng(1)
    _write(tmp_path, "ct.nii", (rng.random((60, 40, 50)) * 100).astype(np.int16), (1.0, 1.0, 1.0), (0, 0, 0))
    _write(tmp_path, "pet.nii", rng.random((5, 4, 6)).astype(np.float32) + 1.0, (2.5, 2.5, 2.5), (12.3, 8.1, 20.7))
    controller, gui = build_app(use_history=False)
    base_id = controller.file.load_image(str(tmp_path / "ct.nii"))
    ov_id = controller.file.load_image(str(tmp_path / "pet.nii"))
    for tag, ori in (("V1", ViewMode.AXIAL), ("V2", ViewMode.CORONAL), ("V3", ViewMode.SAGITTAL)):
        controller.viewers[tag].set_image(base_id)
        controller.viewers[tag].set_orientation(ori)
    vs, ovs = controller.view_states[base_id], controller.view_states[ov_id]
    vs.set_overlay(ov_id, controller.volumes[ov_id])
    vs.camera.crosshair_phys_coord = np.array([22.0, 14.0, 28.0])  # in the PET
    vs.update_crosshair_from_phys(vs.camera.crosshair_phys_coord)

    controller._apply_overlay_resample(vs, ovs)
    assert isinstance(vs.display.overlay_data, CroppedOverlay)
    crop = _render_all(controller)
    with monkeypatch.context() as m:
        m.setattr(R, "_overlay_box", lambda *a: None)
        controller._apply_overlay_resample(vs, ovs)
    assert isinstance(vs.display.overlay_data, np.ndarray)
    full = _render_all(controller)

    assert len(full) == len(crop)
    for (fb, fo), (cb, co) in zip(full, crop):
        assert np.array_equal(fb, cb)
        assert (fo is None) == (co is None) and (fo is None or np.array_equal(fo, co))


def test_a_rotated_base_is_resampled(base_and_overlay):
    """resample_base (rotation preview) is not touched by the overlay crop."""
    from vvv.core.overlay_resampler import resample_base

    base, _ = base_and_overlay
    rot = sitk.Euler3DTransform()
    rot.SetCenter((25.0, 20.0, 30.0))
    rot.SetRotation(0.0, 0.0, 0.3)
    _keep, data = resample_base(base, rot)
    assert isinstance(data, np.ndarray) and data.shape == (60, 40, 50)
