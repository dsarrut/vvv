# Developer Guide: Extraction Tool

## 1. Overview
The Extraction (Threshold) tool allows users to interactively define a radiometric Window, visualize it instantly as a live overlay, and bake the result into a completely new, independent `VolumeData` mask in memory.

## 2. Core Mechanics
* **`ExtractionManager` (`core/extraction_manager.py`):** Houses the threading lock and the generation logic.
* **`ui_extraction.py`:** Manages the visual UI state. When active, it hijacks the active Viewer's `fusion` overlay system to display a real-time preview of the threshold bounds.

## 3. The Extraction Pipeline
When the user clicks "Create new Image":
1. A background thread is spawned in `ExtractionManager.create_image` to prevent the UI from freezing.
2. A blank NumPy array matching the Base Image's dimensions is allocated.
3. The array is populated using `np.where( (data >= min) & (data <= max) )`.
4. **Foreground/Background Modes:** The math respects the UI dropdowns. If "Constant" is selected, the output receives the static `gen_fg_val`. If "Original Value" is selected, the mathematical slice pulls the raw HU/Intensity values from the source image.
5. A new `VolumeData` object is instantiated, the NumPy array is bound to it, and it is appended to the `Controller.volumes` dictionary.

## 4. UI Architecture Notes
* The new generated mask is entirely synthetic. If the user clicks "Save", it will default to a standard `.nii.gz` file export.
* When generation finishes, the `ExtractionManager` automatically activates the new image as an Overlay on top of the Base Image, seamlessly transitioning the user from the "Interactive Preview" to the final generated product.