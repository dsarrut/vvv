Goal: Add a new fusion blending algorithm (e.g., "Difference" or "Maximum Intensity").

1. **Implement the Math:** In `image.py`, create a new `@staticmethod` inside the `SliceRenderer` class (e.g., `_blend_difference`). This should take two NumPy arrays as input and return a blended RGBA array.
2. **Update the Router:** In the `SliceRenderer.get_slice_rgba` method, add a new `elif` block for your mode name that calls your new blending function.
3. **Update the UI Options:** Open `src/vvv/ui/ui_fusion.py`. Locate the `combo_fusion_mode` definition within `build_tab_fusion` and add your new mode string to the `items` list.
4. **Handle UI Logic:** If your mode requires extra sliders (like the Checkerboard mode does), update the visibility logic in the `refresh_fusion_ui` method inside `ui_fusion.py` to show or hide the relevant UI groups when your mode is selected.