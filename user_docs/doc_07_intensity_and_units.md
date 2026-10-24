# Window/Level, Colormaps, Physical Units & Histograms

VVV provides precise control over image contrast (Window/Level), color lookup tables, intensity thresholds, real-time histograms, and physical calibrated units.

![Intensity & Histogram Interface](images/doc_07_intensity_layout.png)

---

## The Intensity Tab

Select the **Intensity** tab on the sidebar to adjust radiometry for the active base image:

![Intensity Tab Panel](images/doc_07_intensity_panel.png)

### 1. Contrast Controls
* **Preset**: statistical presets (`Optimal`, `Min/Max`), `Binary Mask`, CT presets (`CT: Soft Tissue`, `CT: Bone`, `CT: Lung`, `CT: Brain`) and PET presets (`PET: [0 - 5]`, `[0 - 10]`, `[0 - 15]`, `[0 - 20]`, which also set the threshold at 0); `Custom` once you change the values.
* **Window (WW)**: Range of displayed intensity values. Lower values increase contrast across narrow dynamic ranges.
* **Level (WL)**: Midpoint of the displayed window range.
* **Map**: Colormap lookup table (`Grayscale`, `Hot`, `Cold`, `Jet`, `Dosimetry`, `Segmentation`).
* **Min Thr**: a checkbox and a value with <kbd>−</kbd> / <kbd>+</kbd> buttons: voxels below this value are rendered completely transparent. A click on <kbd>−</kbd> / <kbd>+</kbd> also turns the threshold on.
* **Image Range**: Displays true minimum and maximum voxel intensities across the volume.

---

## Interactive Histogram

Below the W/L controls, an interactive real-time histogram plots the voxel intensity distribution:
* **Blue Draggable Lines**: Drag the lower and upper window bounds directly on the plot.
* **Orange Draggable Line**: Drag the window center level ($WL$).
* **Shaded Region**: Highlights the active window width visible on screen.

### Histogram Tools
* **Ctr**: Centers the histogram zoom around the active Window/Level range.
* **Bar / Line**: Shows the current histogram style (bars or line); click to switch.
* **Lin / Log**: Shows the current frequency scale (linear or logarithmic); click to switch.
* **X center / X width / Y max**: the histogram view (center and width of the X axis, height of the Y axis): drag or type a value to change it. <kbd>Ctrl</kbd> + wheel on the plot zooms it.
* **Popout ()**: Opens the histogram in an enlarged standalone window for high-precision inspection.

---

## Physical Units & Presets

VVV tracks physical calibrated units attached to image metadata:

| Unit | Modality | Common Range / Notes |
| :--- | :--- | :--- |
| **HU** | CT | Hounsfield Units (air: $-1000$, water: $0$, bone: $+1000$) |
| **SUV** | PET | Standardized Uptake Value |
| **SUL** | PET | SUV normalized by Lean Body Mass |
| **Gy** | Radiotherapy | Absorbed radiation dose in Gray |
| **Bq/mL**, **kBq/mL** | Nuclear Medicine | Absolute radioactivity concentration |
| **counts** | SPECT / PET | Raw acquisition counts |
| **a.u.** | MRI / Other | Arbitrary / relative units |

> [!TIP]
> You can assign or modify the unit anytime in the **Active Viewer** panel using the dropdown arrow <kbd>▾</kbd> beside the **Unit** field. The unit is kept in a `.json` [side-car file](doc_17_side_car_files.md) next to the image (`ct.json` for `ct.nii.gz`): use the save icon next to the unit to write it without saving the image.

---

## Shortcuts Summary

| Action | Shortcut |
| :--- | :--- |
| **Adjust Window/Level** | <kbd>Right drag</kbd> (or <kbd>Shift</kbd> + mouse move) on the image (horizontal: Window, vertical: Level) |
| **Auto Window/Level** | <kbd>W</kbd> |
| **Auto Overlay Window/Level** | <kbd>X</kbd> |
| **Nearest-Neighbor / Linear Interpolation** | <kbd>K</kbd> |
| **Color Legend Bar** (off / two styles) | <kbd>L</kbd> |

