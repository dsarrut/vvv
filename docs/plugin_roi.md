# ROI Tool

* **Supported Types**: Binary Masks, Label Maps, RT-Structs.
* **Memory Optimization**: All ROIs are cropped to their tightest `roi_bbox` on load.
* **Fast Loading**: `sitk.LabelShapeStatisticsImageFilter` computes bounds for all labels simultaneously. Multithreading slices individual ROIs.
* **Rendering Modes**:
  * **Raster**: RGBA blended onto the base image inside `SliceRenderer`.
  * **Vector (Contours)**: `skimage.measure.find_contours` extracts marching squares geometry; DPG `draw_polyline` draws it natively.
* **File Watching**: Detects external modifications to ROI files and prompts for reload.
* **Memory Conversion**: Temporary RAM extraction (e.g. from Label Maps) converts to persistent Binary Mask source type upon saving.
