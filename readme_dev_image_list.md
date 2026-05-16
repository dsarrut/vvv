# Image List Tool

* **File Manager**: Handles Disk I/O. Supports SimpleITK, fallback XDR/Fabio, and DICOM dir parsing.
* **4D Stacking**: `4D: file1.nii file2.nii` triggers `sitk.JoinSeries` to stack images across time into `(Time, Z, Y, X)`.
* **Viewers Layout**: Assigns `Image IDs` to viewports `V1`–`V4` via the `Controller.layout` dictionary.
* **Workspaces (.vvw)**: Serializes layout, display, and camera config to JSON. 
* **Generators**: `ui_sequences.py` handles background loading while yielding to the DPG render loop.
