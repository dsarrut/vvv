# Developer Guide: ROI Tool

## 1. Overview
The ROI Manager handles 3 types of Regions of Interest:
1. **Binary Masks:** Standard `.nii.gz` files where voxel values indicate foreground/background.
2. **Label Maps:** A single discrete file containing multiple numbered labels (e.g., TotalSegmentator outputs).
3. **RT-Structs:** DICOM files containing mathematical polygon contours.

The system is highly optimized for memory. When an ROI is loaded, it is instantly cropped down to its tightest 3D bounding box (`roi_bbox`). The rendering engine then mathematically maps this tiny 3D block back into the Base Image's coordinate space during rendering, saving gigabytes of RAM.

## 2. Core Modules
* **`ROIManager` (`core/roi_manager.py`):** The mathematical backend. Handles `sitk.ResampleImageFilter` for mismatched geometries, executes `get_roi_stats`, and manages the thread-safe dictionary lock.
* **`ROIState` (`core/roi_manager.py`):** The transient UI state for an ROI. Tracks `source_type` (Binary vs Label Map), visibility, colors, opacity, and caching for extracted Vector Polygons.
* **`RoiUI` (`ui/ui_roi.py`):** The view layer. Responsible for the ROI List Table.

## 3. Performance & Multithreading (Label Maps)
Loading a Label Map with 100+ labels sequentially would freeze the app. VVV uses a highly optimized fast-path in `ui_sequences.py`:
1. **Read Once:** The file is read into memory once.
2. **O(1) Bounding Boxes:** It uses `sitk.LabelShapeStatisticsImageFilter` to pre-calculate the bounding boxes for all 100 labels simultaneously in C++.
3. **Parallel Slicing:** A `ThreadPoolExecutor` spins up 8 threads, bypassing SimpleITK entirely, and uses pure NumPy slicing `cropped_data = data[y0:y1, x0:x1]` to instantly extract the binary masks based on the pre-calculated bounding boxes.

## 4. UI Architecture Notes
* **File Reloading:** ROIs track their modification time (`_is_outdated`). If a user edits a binary mask in another program (like ITK-SNAP) and saves it, the ROI's name turns Orange and a "Reload" icon appears.
* **Memory Conversions:** When a user extracts an ROI from a Label Map or RT-Struct, it lives entirely in RAM. Clicking the "Save" icon writes it to disk and permanently converts its `ROIState.source_type` to a standard "Binary Mask" going forward.
* **Filtering & Sorting:** The `RoiUI` maintains local dictionaries (`roi_filters` and `roi_sort_orders`) mapped by the `viewer.image_id`. This ensures that when you swap between Base Images, your specific ROI list filters are cleanly restored.

## 5. Vector Contours (Marching Squares)
If the user clicks the "Pen" icon, the ROI switches from Raster to Vector mode.
1. `ROIManager.update_roi_contours()` intercepts the current 2D slice.
2. It feeds the boolean mask into `skimage.measure.find_contours`.
3. It offsets the resulting polygons by the pre-calculated `roi_bbox` so they align perfectly over the base image.
4. The polylines are handed to DearPyGui's primitive `draw_polyline` system.