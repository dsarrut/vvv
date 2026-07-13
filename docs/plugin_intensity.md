# Intensity Plugin Developer Guide

This plugin controls the window/level (W/L) presets, sliders, colormaps, minimum thresholding, and the histogram visualization. 

## File Structure

- **[plugin_intensity.py](../src/vvv/plugins/intensity/plugin_intensity.py)**: Registers the plugin entry point and coordinates lifecycle events.
- **[ui_intensity.py](../src/vvv/plugins/intensity/ui_intensity.py)**: Defines the Dear PyGui (DPG) layouts for the sidebar panel and the external histogram window.
- **[control_intensity.py](../src/vvv/plugins/intensity/control_intensity.py)**: Contains the controller that manages interactions, coordinates histogram rendering, and syncs UI inputs with the active viewer state.

---

## 1. Frame-by-Frame Update Loop
The plugin controller implements `update(self, api: PluginAPI)`, which is called on **every frame** of the core application render loop.
- **State Check**: It queries the active viewer's `ViewState.display` to see if the active image, W/L values, colormap, or threshold parameters have changed.
- **Sync Direction**: Any external change (from mouse drags or keyboard shortcuts in the core viewer) is instantly read from `ViewState.display` and pushed to the plugin's DPG sliders, combos, and plot elements.

## 2. Dynamic Slider Speed Principle
To allow precise control over both high-contrast (e.g., CT bone windows) and low-contrast (e.g., MRI) images:
- The drag speed of the W/L and threshold sliders (`drag_ww`, `drag_wl`, and `drag_min_threshold`) is dynamically reconfigured on every frame.
- **Formula**: `speed = max(0.1, ww_val * 0.005)`, where `ww_val` is the active image's current window width.
- This prevents "dead zones" or overly sensitive jumps when working with small window ranges, and enables fast navigation across huge ranges.
- Similarly, the speed of the histogram X-axis sliders is scaled dynamically using `hist_x_range * 0.005`.

## 3. Histogram Computation: Fast vs. Slow
Calculating a high-resolution histogram on large 3D/4D volumes can block the main rendering thread and cause UI stutter. The plugin avoids this using a dual-phase calculation pipeline:
1. **Fast Approximation (Synchronous)**: When the active image or bin count changes, the controller immediately computes a low-resolution histogram by subsampling the data (`subsample_step = data_size // 100_000`). This takes less than 2 milliseconds and is rendered instantly.
2. **Accurate Computation (Asynchronous)**: Simultaneously, the controller spawns a background daemon thread to compute the full-resolution histogram (`subsample_step = 1`).
3. **UI Indicator**: While the background thread is running, a bright orange "computing full histogram" label is displayed in the UI. Once finished, the thread flags `full_hist_ready = True` and requests a UI refresh to render the exact distribution.

## 4. External Window Synchronization
The histogram can be expanded into a dedicated external popup window:
- Both the sidebar panel and the external popup display are driven by the same active `ViewState.display` state.
- Controls (such as Bar/Line toggles, Lin/Log toggles, and bin counts) are bi-directionally synchronized. Modifying a control in the external window updates the sidebar controls and vice-versa.

## 5. Minimum Background Threshold Concept
- **Purpose**: Used to mask out background noise or uninteresting voxel values (common in PET/SPECT functional imaging or CT scans) so underlying fused base images show through.
- **Implementation**: Voxel values below the active image's `base_threshold` are rendered as fully transparent in the shader. 
- **Sync**: The slider triggers window/level synchronization updates to ensure multi-viewer layouts (e.g. axial, sagittal, coronal views) apply the threshold simultaneously.

## 6. Histogram Drag and Update Lines
- The histogram plot displays three interactive vertical lines representing the lower window bound (`wl - ww / 2`), the upper window bound (`wl + ww / 2`), and the center level (`wl`).
- **Callbacks**: Dragging these lines in the plot triggers `on_hist_drag_lower`, `on_hist_drag_upper`, or `on_hist_drag_level` which recalculate the `DisplayState.ww` and `DisplayState.wl` parameters and propagate the window/level to the core viewers.

## 7. Histogram Colorscale Preview
- The external popup window renders a horizontal color bar beneath the histogram plot to visually represent how colors map to intensity values.
- **Texture Generation**: It calls `compute_colorscale_gradient` (defined in `src/vvv/maths/image_utils.py` or similar) to generate a 1D NumPy array representing the color spectrum between the lower and upper window bounds.
- **Rendering**: This gradient is uploaded to DPG as a dynamic texture and mapped onto a rectangle beneath the plot.

## 8. Histogram View Limits (X and Y Axes)
- **X-Axis Viewport**: The visible X-range is controlled by `DisplayState.hist_x_center` and `DisplayState.hist_x_range`. The axis limits are locked to `[center - range / 2, center + range / 2]`. 
- **Y-Axis Auto-Scale**: When the user switches between linear and log mode, or when a new image is loaded, `DisplayState.hist_y_max` is set to `None`. This tells the update loop to automatically adapt the Y-axis limit to the maximum count of the visible histogram data, ensuring the entire curve is always visible.
