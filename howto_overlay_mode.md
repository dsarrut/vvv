Goal: Add a new fusion blending algorithm (e.g., "Difference" or "Maximum Intensity").

1.  **Implement the Math:** In `src/vvv/math/image.py`, create a new `@staticmethod` inside the `SliceRenderer` class (e.g., `_blend_difference`). This function should accept the base and overlay image data as NumPy arrays and return a blended RGBA NumPy array.

2.  **Update the Router:** In the `SliceRenderer.get_slice_rgba` method, add a new `elif` block for your new mode. This block should call your new blending function.

3.  **Update the UI:** In `src/vvv/ui/ui_fusion.py`, find the `combo_fusion_mode` definition inside the `build_tab_fusion` function and add the name of your new mode to the `items` list.

4.  **Handle UI Logic (Optional):** If your new mode requires additional controls (like sliders), you'll also need to update the `refresh_fusion_ui` method in `src/vvv/ui/ui_fusion.py` to show or hide them based on the selected mode.
