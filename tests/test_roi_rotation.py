"""ROIs follow their image's registration transform: a translation moves the
drawn slice (ROIs included), a rotation shows a resampled image, and the ROI
masks are rotated the same way (ROIManager.display_mask)."""

import time

import numpy as np
import pytest
import SimpleITK as sitk

from vvv.app import build_app
from vvv.utils import ViewMode

VIEWERS = (("V1", ViewMode.AXIAL), ("V2", ViewMode.CORONAL), ("V3", ViewMode.SAGITTAL))


def _settle(c):
    assert c.wait_for_jobs(timeout=10)
    for _ in range(5):
        c.tick()
        time.sleep(0.01)


@pytest.fixture
def cube_with_roi(tmp_path):
    arr = np.zeros((40, 128, 128), np.float32)
    arr[12:28, 30:60, 70:110] = 1000.0  # z y x, asymmetric
    sitk.WriteImage(sitk.GetImageFromArray(arr), str(tmp_path / "ct.nii"))
    sitk.WriteImage(sitk.GetImageFromArray((arr > 0).astype(np.uint8)), str(tmp_path / "roi.nii"))
    c, gui = build_app(use_history=False)
    bid = c.file.load_image(str(tmp_path / "ct.nii"))
    for tag, ori in VIEWERS:
        c.layout[tag] = bid
        c.viewers[tag].set_image(bid)
        c.viewers[tag].set_orientation(ori)
        c.viewers[tag].resize(400, 400)
    vs = c.view_states[bid]
    vs.display.ww, vs.display.wl = 1000.0, 500.0
    rid = c.roi.load_binary_mask(bid, str(tmp_path / "roi.nii"), color=[255, 0, 0])
    vs.rois[rid].opacity = 1.0
    vs.camera.crosshair_phys_coord = np.array([90.0, 45.0, 20.0])  # in the cube
    vs.update_crosshair_from_phys(vs.camera.crosshair_phys_coord)
    return c, bid, rid


def _set_transform(c, bid, tx=0.0, ty=0.0, tz=0.0, rx=0.0, ry=0.0, rz=0.0):
    vs = c.view_states[bid]
    c.update_transform_manual(bid, tx, ty, tz, rx, ry, rz)
    vs.space.is_active = True
    vs.needs_resample = True
    c.resample_image(bid)
    _settle(c)


def _iou_on_screen(c, bid, rid, tag):
    """IoU of the bright cube and of the red ROI in the viewer's slice image."""
    vs, v = c.view_states[bid], c.viewers[tag]

    def render(roi_on):
        vs.rois[rid].visible = roi_on
        v.is_geometry_dirty = True
        vs.is_data_dirty = True
        v.update_render(force_reblend=True)
        h, w = v.last_rgba_shape[:2]
        return np.asarray(v.last_rgba_flat).reshape(h, w, 4)

    cube = render(False)[..., 0] > 0.5
    roi = render(True)
    red = (roi[..., 0] > 0.5) & (roi[..., 1] < 0.3)
    assert cube.sum() > 50
    return (cube & red).sum() / (cube | red).sum()


@pytest.mark.parametrize(
    "transform",
    [{"tx": 6.0, "ty": -4.0, "tz": 3.0}, {"rz": 30.0}, {"rx": 10.0, "ry": -15.0, "rz": 25.0, "tx": 4.0}],
    ids=["translation", "rotation_z", "rotation_xyz"],
)
def test_roi_drawn_on_its_rotated_or_moved_image(cube_with_roi, transform):
    c, bid, rid = cube_with_roi
    _set_transform(c, bid, **transform)
    for tag, _ in VIEWERS:
        assert _iou_on_screen(c, bid, rid, tag) > 0.9, tag


@pytest.mark.parametrize(
    "transform",
    [{"tz": -1900.0, "tx": 15.0}, {"rx": 10.0, "ry": -15.0, "rz": 25.0, "tx": 4.0}],
    ids=["large_translation", "rotation_xyz"],
)
def test_roi_goto_lands_on_the_roi_of_a_moved_image(cube_with_roi, transform):
    """Issue 49: the goto went to the ROI's centre in its image's native
    space; with the image's transform (here as large as a registered time
    point, ~2 m in z) the crosshair ended outside the image."""
    c, bid, rid = cube_with_roi
    _set_transform(c, bid, **transform)
    vs = c.view_states[bid]
    c.roi.center_on_roi(bid, rid)

    # In the native voxels of the image: the centre of the cube
    x, y, z = vs.camera.crosshair_voxel[:3]
    assert np.allclose([z, y, x], [19.5, 44.5, 89.5], atol=0.6)
    # In world space: where the image's transform moves it
    native = vs.volume.voxel_coord_to_physic_coord(np.array([89.5, 44.5, 19.5]))
    world = vs.space.transform.TransformPoint([float(v) for v in native])
    assert np.allclose(vs.camera.crosshair_phys_coord, world, atol=0.6)


def test_roi_contours_follow_the_rotation(cube_with_roi):
    c, bid, rid = cube_with_roi
    vs, roi = c.view_states[bid], c.view_states[bid].rois[rid]
    roi.is_contour = True

    def polygons():
        c.roi.update_roi_contours(vs, ViewMode.AXIAL, c.viewers["V1"].slice_idx)
        polys = roi.polygons[ViewMode.AXIAL][c.viewers["V1"].slice_idx]
        assert polys
        return np.concatenate([np.asarray(p) for p in polys])

    read = polygons()
    _set_transform(c, bid, rz=30.0)
    rotated = polygons()
    assert roi.polygons_rotation == c.roi.display_rotation_key(vs) is not None
    assert not np.allclose(read.mean(axis=0), rotated.mean(axis=0), atol=1.0)

    # The rotated mask is where the rotated image's cube is
    mask, (z0, z1, y0, y1, x0, x1) = c.roi.display_mask(vs, rid, c.volumes[rid])
    full = np.zeros(vs.volume.shape3d, bool)
    full[z0:z1, y0:y1, x0:x1] = mask > 0
    cube = np.asarray(vs.base_display_data) > 500
    assert (full & cube).sum() / (full | cube).sum() > 0.9

    _set_transform(c, bid)  # no rotation: the polygons as read again
    c.view_states[bid].space.is_active = False
    assert np.allclose(polygons().mean(axis=0), read.mean(axis=0))
