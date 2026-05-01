# Developer Guide: Intensities Tool

## 1. Overview
The Intensities tool manages radiometric Window/Level (W/L) settings and Colormap transfer functions.

## 2. Core Mechanics
* **Data Storage:** W/L state is stored on the `ViewState.display` object (`vs.display.ww`, `vs.display.wl`).
* **The Render Math:** In `math/image.py`, the `SliceRenderer.normalize_wl()` method subtracts the Level and divides by the Width, clamping the result to a strict `[0.0, 1.0]` float array.
* **Colormaps:** The clamped array is multiplied by 255 and used as an index to sample the `COLORMAPS` dictionary (defined in `config.py`).

## 3. Auto-Windowing (FOV)
If the user presses `W` (or clicks the Auto-Window button), VVV calculates the optimal contrast.
Instead of calculating Min/Max over the entire 3D volume (which is often skewed by the scanner bed or background air), it uses the `SliceViewer`'s bounding boxes to calculate the Min/Max **exclusively** on the pixels currently visible inside the viewport.

## 4. Mouse Drag Sensitivity
When the user holds `Shift + Right Click` and drags to manually adjust W/L, the delta is processed in `ui_interaction.py`.

**The Exponential Width Curve:**
A linear slider for Window Width feels terrible—adjusting from 10 to 20 requires fine precision, but adjusting from 2000 to 4000 requires massive sweeps. 
To fix this, `dx` (mouse movement) is passed through an exponential multiplier (`math.exp(dx * base_sens)`). This ensures the window width expands smoothly regardless of the current scale.

**The Linear Level Curve:**
Window Level uses a linear translation, but its sensitivity is dynamically multiplied by the current Window Width. This ensures that when your Window is very narrow (high contrast), your Level mouse drags are automatically highly precise.