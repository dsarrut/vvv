
Goal: Add a new fusion blending algorithm (e.g., "Difference" or "Maximum Intensity").

Implement the Math: In image.py, create a new @staticmethod inside the SliceRenderer class (e.g., _blend_difference). This should take NumPy arrays as input and return a blended RGBA array.

Update the Router: In the SliceRenderer.get_slice_rgba method, add a new elif block for your mode name that calls your new blending function.

Update the UI Options: In gui.py, locate the combo_overlay_mode definition within build_tab_fusion and add your new mode string to the list of items.

Handle UI Logic: If your mode requires extra sliders (like the Checkerboard mode does), update on_overlay_mode_changed in gui.py to show or hide the relevant UI groups.


