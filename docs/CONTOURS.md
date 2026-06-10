# Contour Architecture

VVV has **two independent contour pipelines** that share the same math function and rendering path.

## 1. Vector Contours (Threshold Plugin)

Used by the threshold plugin to show a live preview of threshold boundaries.

| Layer | File | Role |
|-------|------|------|
| Data model | `maths/contours.py` → `ContourROI` | Stores polygons per orientation/slice, color, thickness, visibility |
| Math | `maths/contours.py` → `extract_2d_contours_from_slice()` | Marching squares on a 2D slice |
| Lifecycle | `core/contour_manager.py` → `ContourManager` | `add_contour`, `remove_contour`, `update_contour` |
| Storage | `vs.contours` dict | Keyed by contour id |
| Consumer | Threshold plugin only | Creates/removes `ContourROI` via `api.add_contour()` / `api.remove_contour()` |

## 2. ROI Contour Mode (ROI Plugin)

Each ROI can be displayed as a filled raster overlay **or** as an outline. The `is_contour` flag on `ROIState` controls this.

| Layer | File | Role |
|-------|------|------|
| Data model | `core/roi_manager.py` → `ROIState` | Has `is_contour` flag + `polygons` dict (same structure as `ContourROI`) |
| Math | `maths/contours.py` → `extract_2d_contours_from_slice()` | Same marching squares function |
| Extraction | `core/roi_manager.py` → `update_roi_contours()` | Extracts contours from the ROI binary mask, caches per slice |
| Storage | `vs.rois` dict | Each `ROIState` carries its own `polygons` |
| Consumer | ROI plugin UI | Toggle contour/raster per ROI |

## Rendering: Where They Merge

Both pipelines converge in `ui/drawing.py` → `draw_contours()`:

```python
# Collect vector contours (threshold plugin)
contour_dict = getattr(viewer.view_state, "contours", {})
contour_rois = list(contour_dict.values())

# Also collect ROIs in contour mode
for r_id, r_state in viewer.view_state.rois.items():
    if r_state.visible and getattr(r_state, "is_contour", False):
        contour_rois.append(r_state)

# Draw all with the same polyline loop
for roi in contour_rois:
    polys = roi.polygons[viewer.orientation].get(viewer.slice_idx, [])
    for poly in polys:
        dpg.draw_polyline(poly, color=roi.color, thickness=roi.thickness, ...)
```

This works because `ContourROI` and `ROIState` share the same duck-type interface: `.visible`, `.color`, `.thickness`, `.polygons[orientation][slice_idx]`.

## Call Graph

```
Viewer.render()
  │
  ├── controller.roi.update_roi_contours(viewer)   # lazy-extract ROI contour polygons
  │     └── extract_2d_contours_from_slice()        # from maths/contours.py
  │
  └── drawer.draw_contours()                        # in ui/drawing.py
        ├── vs.contours  ──→  ContourROI list       # threshold plugin contours
        ├── vs.rois (is_contour=True) ──→ append    # ROI contour-mode outlines
        └── draw all with dpg.draw_polyline()
```

## Key Point

The two systems **do not interact** with each other. They are independent pipelines that happen to:
- Use the same `extract_2d_contours_from_slice()` math function
- Store polygons in the same `{orientation: {slice_idx: [polyline, ...]}}` format
- Get drawn by the same `draw_contours()` renderer
