# Intensities Tool

* **State**: W/L and colormaps belong to `ViewState.display`.
* **Render**: Normalizes `(val - min) / (max - min)` to index standard integer RGBA lookup arrays (`COLORMAPS`).
* **Auto-Window (W)**: Computes dynamic Min/Max based strictly on the viewport's currently visible pixels.
* **Mouse Drag**: `Shift + R-Click` uses an exponential curve for width adjustments and a linear curve for level translation.
