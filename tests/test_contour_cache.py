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
