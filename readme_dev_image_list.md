# Developer Guide: Image List Tool

## 1. Overview
The Image List Tool manages file imports, active viewers, and workspace restoration.

## 2. Core Modules
* **`FileManager` (`core/file_manager.py`):** The disk I/O engine. Parses DICOM directories, falls back to XDR/Fabio if ITK fails, and handles `.vvw` Workspace serialization.
* **`ui_image_list.py`:** Renders the loaded files, handles closing files, and manages the Layout Checkboxes (`V1, V2, V3, V4`).
* **`ui_sequences.py`:** Contains the asynchronous python generators that actually execute the `FileManager` logic in background threads.

## 3. 4D Sequences & Stacking
VVV natively supports 4D viewing (Time). 
1. The CLI or `open_file_dialog` bundles a list of files into a single string prefixed with `4D:` (e.g., `"4D: slice1.nii slice2.nii"`).
2. The `VolumeData` object intercepts this prefix, uses `shlex` to safely split the string, and reads every file in the array.
3. It uses `sitk.JoinSeries` or NumPy `np.concatenate` to stack the 3D files along a 4th temporal axis `(Time, Z, Y, X)`.

## 4. The Viewers & Layout Dictionaries
VVV maintains exactly four `SliceViewer` instances in memory at all times (`V1`, `V2`, `V3`, `V4`). 

The `Controller.layout` dictionary maps which `VolumeData/ViewState` ID is currently mounted to which Viewer. 
```python
self.controller.layout = {"V1": "0", "V2": "1", "V3": None, "V4": None}
```
When the user clicks a checkbox in the Image List, the UI simply changes the `layout` dictionary and sets `ui_needs_refresh = True`. The Viewers will automatically unmount and remount the correct textures on the next render frame.

## 5. Workspaces (`.vvw`)
Workspaces are JSON files that capture the complete `ViewState` of every loaded image. 
Because image IDs are generated sequentially (`0`, `1`, `2`), loading a Workspace on top of an existing session would cause ID collisions. `ui_sequences.py` uses an `id_map` during Workspace loading to seamlessly translate the saved JSON IDs into fresh, collision-free memory IDs.