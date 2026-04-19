Goal: Add a new fusion blending algorithm (e.g., "Difference" or "Maximum Intensity").

1.  **Implement the Math:** In `src/vvv/math/image.py`, create a new `@staticmethod` inside the `SliceRenderer` class (e.g., `_blend_difference`). This function should accept the `RenderLayer` objects for the base and overlay, and return a blended 1D RGBA NumPy array and its 2D shape.

2.  **Update the Router:** In the same `src/vvv/math/image.py` file, locate the `SliceRenderer.get_slice_rgba` method. Add a new `elif` block for your new mode.
    ```python
    elif overlay_mode == "Difference":
        rgba_flat, shape = SliceRenderer._blend_difference(base, overlay, overlay_opacity)
    ```

3.  **Update the UI Dropdown:** In `src/vvv/ui/ui_fusion.py`, find the `combo_fusion_mode` definition inside the `build_tab_fusion` method. Add the exact name of your new mode to the `items` list:
    ```python
    dpg.add_combo(
        ["Alpha", "Registration", "Checkerboard", "Difference"],
        tag="combo_fusion_mode",
        # ...
    )
    ```

4.  **Handle UI State Logic (Optional):** If your new mode requires additional custom controls (like the square size slider used by Checkerboard), add those widgets to `build_tab_fusion`. Then, update `refresh_fusion_ui` in `src/vvv/ui/ui_fusion.py` to selectively `show=True` or `show=False` your new widgets when your mode is the currently active `viewer.view_state.display.overlay_mode`.
