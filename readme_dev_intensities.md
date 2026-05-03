# Developer Guide: Intensities Tool

## 1. Overview
Manages Window/Level (W/L) settings and Colormap transfer functions via `ui_intensities.py`.

## 2. Core Mechanics
* **Data Storage:** W/L state lives on `ViewState.display` (`vs.display.ww`, `vs.display.wl`).
* **Render Math:** `SliceRenderer.normalize_wl()` in `maths/image.py` subtracts Level and divides by Width, clamping to `[0.0, 1.0]`. The result indexes into the `COLORMAPS` lookup table from `config.py`.

## 3. Auto-Windowing (FOV)
Pressing `W` or clicking Auto-Window calculates Min/Max **exclusively on pixels currently visible in the viewport** (using `SliceViewer`'s bounding boxes), avoiding bias from the scanner bed or background air.

## 4. Mouse Drag Sensitivity
`Shift + Right Click` drag adjusts W/L in `ui_interaction.py`:

* **Exponential Width Curve:** `dx` is passed through `math.exp(dx * base_sens)` so that the window width expands smoothly regardless of current scale (avoids the precision/sweep dilemma of a linear slider).
* **Linear Level Curve:** `dy` is a linear translation, but sensitivity is multiplied by the current Window Width — narrow windows get automatic fine precision.
