# Developer Guide: ROI Tool

## 1. Overview
The ROI Manager handles 3 types of Regions of Interest:
1. **Binary Masks:** Standard `.nii.gz` files where voxel values indicate foreground/background.
2. **Label Maps:** A single discrete file containing multiple numbered labels (e.g., TotalSegmentator outputs).
3. **RT-Structs:** DICOM files containing mathematical polygon contours.

For memory efficiency, ROIs are cropped to their tightest 3D bounding box (`roi_bbox`) on load. The renderer maps this tiny block back into the Base Image's coordinate space at draw time.

## 2. Core Modules
* **`ROIManager` (`core/roi_manager.py`):** Mathematical backend. Handles `sitk.ResampleImageFilter` for mismatched geometries, `get_roi_stats`, and the thread-safe dictionary lock.
* **`ROIState` (`core/roi_manager.py`):** Transient UI state for an ROI. Tracks `source_type` (Binary, Label Map, RT-Struct), visibility, colors, opacity, and caching for vector polygons.
* **`ContourManager` (`core/contour_manager.py`):** Lifecycle and memory management for `ContourROI` overlays derived from ROI masks.
* **`ContourROI` (`maths/contours.py`):** Data container for per-slice 2D polygon sets.
* **`RoiUI` (`ui/ui_roi.py`):** The view layer — ROI list table, filters, and sort orders.

## 3. Performance & Multithreading (Label Maps)
VVV uses a fast-path in `ui_sequences.py` to load 100+ label maps without freezing:
1. **Read Once:** The file is loaded into memory once.
2. **O(1) Bounding Boxes:** `sitk.LabelShapeStatisticsImageFilter` pre-calculates bounding boxes for all labels simultaneously in C++.
3. **Parallel Slicing:** A `ThreadPoolExecutor` (8 threads) uses pure NumPy slicing on the pre-calculated bounding boxes.

## 4. UI Architecture Notes
* **File Reloading:** ROIs track their modification time (`_is_outdated`). If the file changes externally, the ROI name turns orange and a "Reload" icon appears.
* **Memory Conversions:** ROIs extracted from Label Maps or RT-Structs live in RAM. Clicking "Save" writes to disk and converts `source_type` to Binary Mask.
* **Filtering & Sorting:** `RoiUI` maintains local filter/sort-order dicts per `image_id`, so switching between Base Images restores the correct ROI list state.

## 5. Vector Contours
Clicking the "Pen" icon switches an ROI from raster to vector mode:
1. `ROIManager.update_roi_contours()` intercepts the current 2D slice.
2. The boolean mask is fed into `skimage.measure.find_contours` (Marching Squares).
3. Resulting polygons are offset by `roi_bbox` to align over the base image.
4. Polygons are handed to `ContourManager` → `ContourROI` and rendered via DPG `draw_polyline`.
