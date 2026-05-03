# Developer Guide: Image List Tool

## 1. Overview
Manages file imports, active viewers, workspace restoration, and DICOM browsing.

## 2. Core Modules
* **`FileManager` (`core/file_manager.py`):** Disk I/O engine. Parses DICOM directories, falls back to XDR/Fabio if ITK fails, and handles `.vvw` workspace serialization.
* **`ui_image_list.py`:** Renders the loaded files, handles closing, and manages layout checkboxes (`V1, V2, V3, V4`).
* **`ui_dicom.py` (`DicomBrowserWindow`):** Async DICOM series browser with folder scanning and series preview.
* **`ui_sequences.py`:** Python generators that execute `FileManager` logic in background threads.

## 3. 4D Sequences & Stacking
VVV natively supports 4D (Time) viewing.
1. The CLI or file dialog bundles files into a string prefixed with `4D:` (e.g., `"4D: slice1.nii slice2.nii"`).
2. `VolumeData` intercepts this prefix, splits with `shlex`, and reads every file.
3. `sitk.JoinSeries` or `np.concatenate` stacks 3D files along a 4th temporal axis `(Time, Z, Y, X)`.

## 4. Viewers & Layout
VVV maintains exactly four `SliceViewer` instances at all times (`V1`–`V4`).

`Controller.layout` maps viewer slots to image IDs:
```python
self.controller.layout = {"V1": "0", "V2": "1", "V3": None, "V4": None}
```
Clicking a checkbox updates `layout` and sets `ui_needs_refresh = True`. Viewers automatically unmount/remount textures on the next frame.

## 5. Workspaces (`.vvw`)
JSON files capturing the full `ViewState` of every loaded image. Because image IDs are sequential (`0`, `1`, `2`…), `ui_sequences.py` uses an `id_map` during loading to translate saved IDs into fresh, collision-free memory IDs.
