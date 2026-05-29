# ROI Plugin Developer Guide

The ROI plugin provides comprehensive Region of Interest (ROI) management, supporting loading binary masks, DICOM RT-Struct structures, and integer label maps. It manages individual color mappings, visibility toggles (raster vs. contour), alphabetical sorting, live statistics calculations via SimpleITK, settings persistence, and workspace serialization.

## File Structure

- **[plugin_roi.py](plugin_roi.py)**: Plugin entry point conforming to `PluginProtocol`. Registers lifecycle events, and delegates to the controller and UI.
- **[control_roi.py](control_roi.py)**: Controller. Coordinates selection updates, caches filter text and sort orders, and manages workspace serialization/restoration hooks.
- **[ui_roi_plugin.py](ui_roi_plugin.py)**: UI. Renders the ROI list window, load options (Rule/Val), global slider overrides, selected ROI properties, and the interactive RT-Struct selection modal.
- **[test_roi_plugin.py](test_roi_plugin.py)**: Unit tests covering loader options, table rebuilding, properties changes, stats, modal selections, and settings persistence.

---

## 1. Core Model Ownership & Workspace Serialization

ROIs belong to the base volume view state under `ViewState.rois` (mapping unique string IDs to `RoiState` objects).

- **State Persistence**: In [control_roi.py](control_roi.py), `serialize_image_state` and `restore_image_state` save and restore `roi_filter` and `roi_sort_order` properties per-image.
- **Backward Compatibility**: The sequence loader ([ui_sequences.py](../../ui/ui_sequences.py)) and save manager ([file_manager.py](../../core/file_manager.py)) bridge these values from older workspaces directly into the plugin's controller state cache.

---

## 2. RT-Struct Selection Modal

When loading a DICOM RT-Struct file, a popup modal allows users to selectively load individual structures:

- **Image Title Integration**: The modal window title (label) dynamically includes the name of the active base image (e.g. `Select ROIs to Load - image.nii.gz`).
- **Modal Lifecycle Safety**: To comply with the plugin implementation checklist, the modal window is completely deleted (not just hidden) via `close_rtstruct_modal` during image removal (`on_image_removed`) and plugin destruction (`destroy()`) events to avoid dangling DPG tags.

---

## 3. Dynamic Color Theme Binding

To provide a premium visual experience:
- The slider grab color of the active ROI's opacity/thickness slider is dynamically updated to match the RGB color of the selected ROI.
- On every selection update, a namespaced `dpg.theme` component (`dynamic_roi_slider_theme`) is generated with color styles matching the active ROI color and bound to the slider widget.

---

## 4. Live Volume & Intensity Statistics

Voxel stats are calculated dynamically using SimpleITK filters:
- **Filters Used**: `LabelShapeStatisticsImageFilter` (for volume/size statistics) and `LabelIntensityStatisticsImageFilter` (for intensity metrics like mean, max, min, standard deviation, peak, and mass).
- **Target Analysis Selector**: The analysis target combo box enables selecting between the base image and any active fused overlay layer to compute stats against different modalities.

---

## 5. Recomputation Optimization & Focus Preservation

Rebuilding DearPyGui tables or sliders on every frame tick causes active widgets to lose grab/focus state (e.g. disrupting active opacity slider drags or text renaming inputs).

- **Cache-Optimized Updates**: In [control_roi.py](control_roi.py), the `update` loop tracks the active image ID (`_last_image_id`) and the set of ROI IDs (`_last_roi_ids`).
- **Conditional Refresh**: Re-rendering `refresh_rois_ui()` is only triggered when these IDs change or if `ui_needs_refresh` is explicitly set, preserving focus states and ensuring smooth slider dragging.

---

## 6. Beginner Mode & Settings Persistence

- **Beginner Mode Tooltips**: Explanatory tooltips (`build_beginner_tooltip`) are attached to the load button, rule combo box, global opacity and thickness sliders, and search filter input.
- **Settings Persistence**: Implemented `save_settings` and `load_settings` in [ui_roi_plugin.py](ui_roi_plugin.py) to save and load default loading settings (mode and default values) into the main settings database.
