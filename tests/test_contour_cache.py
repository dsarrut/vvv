"""Contours are redrawn when an ROI's polygons change, even with the same count."""

import vvv.ui.drawing as drawing
from vvv.core.roi_manager import ROIState


def test_edited_contour_is_redrawn_with_same_polygon_count(headless_gui_app, monkeypatch):
    controller, gui, viewer, base_id = headless_gui_app
    vs = controller.view_states[base_id]
    roi = ROIState("roi_x", "lesion", [255, 0, 0])
    roi.is_contour = True
    vs.rois["roi_x"] = roi
    ori, s = viewer.orientation, viewer.slice_idx
    roi.polygons[ori][s] = [[[1.0, 1.0], [5.0, 1.0], [5.0, 5.0]]]

    drawn = []
    real = drawing.dpg.draw_polyline
    monkeypatch.setattr(
        drawing.dpg, "draw_polyline", lambda pts, **k: (drawn.append(pts), real(pts, **k))[1]
    )
    viewer.drawer.draw_contours()
    assert drawn[-1][0] == [1.0, 1.0]

    roi.invalidate()  # the mask was edited: polygons recomputed, same count
    roi.polygons[ori][s] = [[[2.0, 2.0], [6.0, 2.0], [6.0, 6.0]]]
    viewer.drawer.draw_contours()
    assert drawn[-1][0] == [2.0, 2.0]


def test_roi_contour_slice_extraction_equivalence():
    """Verify that SliceRenderer.extract_slice produces bit-for-bit identical
    slices to the original manual slicing and flipping logic used in update_roi_contours,
    for both 3D and 4D volumes across AXIAL, CORONAL, and SAGITTAL orientations.
    """
    import numpy as np
    from vvv.maths.image import SliceRenderer
    from vvv.utils import ViewMode

    # Asymmetric dimensions so axis transpositions or index swaps fail
    rng = np.random.default_rng(42)
    data_3d = rng.integers(1, 255, size=(10, 14, 18), dtype=np.uint8)
    data_4d = rng.integers(1, 255, size=(3, 10, 14, 18), dtype=np.uint8)

    # Manual logic previously in update_roi_contours:
    # AXIAL: 3D data[s, :, :], 4D data[t, s, :, :]
    # CORONAL: 3D np.flipud(data[:, s, :]), 4D np.flipud(data[t, :, s, :])
    # SAGITTAL: 3D np.flipud(np.fliplr(data[:, :, s])), 4D np.flipud(np.fliplr(data[t, :, :, s]))
    orientations = [
        (ViewMode.AXIAL, 10, lambda d, s: d[s, :, :], lambda d, t, s: d[t, s, :, :]),
        (
            ViewMode.CORONAL,
            14,
            lambda d, s: np.flipud(d[:, s, :]),
            lambda d, t, s: np.flipud(d[t, :, s, :]),
        ),
        (
            ViewMode.SAGITTAL,
            18,
            lambda d, s: np.flipud(np.fliplr(d[:, :, s])),
            lambda d, t, s: np.flipud(np.fliplr(d[t, :, :, s])),
        ),
    ]

    for ori, max_s, manual_3d, manual_4d in orientations:
        for s in [0, max_s // 2, max_s - 1]:
            # 3D
            expected_3d = manual_3d(data_3d, s)
            actual_3d = SliceRenderer.extract_slice(data_3d, False, 0, s, ori)
            assert actual_3d is not None
            np.testing.assert_array_equal(
                actual_3d, expected_3d, err_msg=f"Mismatch for 3D {ori} at slice {s}"
            )

            # 4D
            for t in [0, 1, 2]:
                expected_4d = manual_4d(data_4d, t, s)
                actual_4d = SliceRenderer.extract_slice(data_4d, False, t, s, ori)
                assert actual_4d is not None
                np.testing.assert_array_equal(
                    actual_4d,
                    expected_4d,
                    err_msg=f"Mismatch for 4D {ori} at t={t}, s={s}",
                )


def test_update_roi_contours_extraction(headless_gui_app, tmp_path):
    """End-to-end test verifying update_roi_contours computes polygons via
    the unified slice extraction across all three orientations.
    """
    import numpy as np
    import SimpleITK as sitk
    from vvv.utils import ViewMode

    controller, gui, viewer, base_id = headless_gui_app
    vs = controller.view_states[base_id]
    base_vol = controller.volumes[base_id]
    z, y, x = base_vol.shape3d

    # Create a small binary cube ROI in the center
    roi_data = np.zeros((z, y, x), dtype=np.uint8)
    cz, cy, cx = z // 2, y // 2, x // 2
    roi_data[cz - 1 : cz + 2, cy - 1 : cy + 2, cx - 1 : cx + 2] = 1

    mask_img = sitk.GetImageFromArray(roi_data)
    mask_img.SetSpacing(base_vol.spacing.tolist())
    mask_img.SetOrigin(base_vol.origin.tolist())
    mask_img.SetDirection(base_vol.matrix.flatten().tolist())

    mask_path = str(tmp_path / "test_cube_roi.nii.gz")
    sitk.WriteImage(mask_img, mask_path)

    roi_id = controller.roi.load_binary_mask(base_id, mask_path)
    roi_state = vs.rois[roi_id]
    roi_state.is_contour = True
    roi_state.visible = True

    # Verify contours are generated for each orientation at the center slice
    for ori, s_idx in [
        (ViewMode.AXIAL, cz),
        (ViewMode.CORONAL, cy),
        (ViewMode.SAGITTAL, cx),
    ]:
        roi_state.polygons[ori].clear()
        controller.roi.update_roi_contours(vs, ori, s_idx)
        assert s_idx in roi_state.polygons[ori]
        polys = roi_state.polygons[ori][s_idx]
        assert len(polys) > 0, f"Expected non-empty polygons for orientation {ori}"
        assert len(polys[0]) >= 3, f"Expected valid polygon with >=3 vertices for orientation {ori}"

