# Developer Guide: Extraction Tool

## 1. Overview
Allows users to interactively define a radiometric threshold window, visualize it as a live overlay, and bake the result into a new, independent `VolumeData` mask in memory.

## 2. Core Modules
* **`ExtractionManager` (`core/extraction_manager.py`):** Threading lock and volume generation logic.
* **`ui_extraction.py`:** Visual UI state. When active, hijacks the viewer's `fusion` overlay system for a real-time threshold preview.

## 3. Extraction Pipeline
When the user clicks "Create new Image":
1. A background thread in `ExtractionManager.create_image` prevents UI freeze.
2. A blank NumPy array matching the base image dimensions is allocated.
3. Populated via `np.where((data >= min) & (data <= max))`.
4. **Foreground/Background Modes:** If "Constant", the output gets a static `gen_fg_val`. If "Original Value", raw intensities are preserved from the source.
5. A new `VolumeData` is instantiated and appended to `Controller.volumes`.

When generation finishes, the new mask is automatically activated as an Overlay, transitioning the user from preview to the final product. Saving defaults to `.nii.gz`.
