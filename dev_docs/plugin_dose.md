# Dose Plugin Developer & Design Specification (`plugin_dose.md`)

This document defines the functional scope, architecture, activation conditions, and roadmap for the **Dose Plugin** in VVV.

---

## 1. Overview & Purpose

The **Dose Plugin** provides radiotherapy, dosimetry, and nuclear medicine tools for quantitative radiation dose inspection, dose scaling, relative normalization, isodose visualization, and Dose-Volume Histograms (DVH).

---

## 2. Activation & Unit Requirements

The plugin is strictly scoped to images representing absorbed dose or dose rate.

### Activation Criteria
* The plugin panel is **enabled/active** when:
  * The active viewer's base image has physical unit **`Gy`**, **`mGy`**, or **`Gy/decay`**.
  * **OR** the active viewer's fused/overlay image has unit **`Gy`**, **`mGy`**, or **`Gy/decay`**.
* When active on an overlay dose image (e.g. CT base + Dose overlay), the plugin automatically targets the dose overlay layer for all measurements, isodoses, and normalization.

### Requirement UI State (When Inactive)
* When neither the base image nor the overlay has a Gy-compatible unit:
  * A clear informational banner is displayed:
    > *"Dose analysis requires an image with unit Gy, mGy, or Gy/decay."*
  * An **"Enable (Set unit to Gy)"** button is provided:
    * If an overlay is loaded: assigns unit `Gy` to the overlay volume.
    * Otherwise: assigns unit `Gy` to the base image volume.
    * Instantly unlocks the plugin tools.

### DICOM RTDOSE Default
* DICOM RTDOSE objects parsed by VVV automatically read `DoseGridScaling` and set `image.unit = "Gy"` with `unit_source = "DICOM (RTDOSE)"`.
* RTDOSE images therefore satisfy the requirement upon loading without user intervention.

---

## 3. Core Features & Functional Content

### A. Shared Intensity Scaling & Normalization Component (`src/vvv/ui/ui_scaling.py`)
Both the **Intensity Tool** and the **Dose Tool** share a unified component (`IntensityScalingComponent`):
* **Active Viewer Panel Hidden**: Switching to either `dose_plugin` or `intensity_plugin` hides the `Active Viewer` sidebar panel to maximize vertical tool space.
* **Two Operating Modes**:
  1. **Manual Scaling**: User specifies or adjusts the scaling factor $S$ directly (with quick multipliers `x1`, `x0.001`, `x1000`, `x0.1`, `x10`).
  2. **Normalization**: The scaling factor $S$ is **auto-set** from the chosen normalization target:
     - **Max**: $S = \text{target\_scale} / V_{\max}$ (normalizes max to 100% or 1.0).
     - **Target Value**: $S = \text{target\_scale} / V_{\text{target}}$ (e.g. prescription dose $D_{\text{rx}}$ or target intensity).
     - **ROI Mean**: $S = \text{target\_scale} / \bar{V}_{\text{ROI}}$ (normalizes mean inside selected ROI to 100% or 1.0).
* **Actions**:
  - **`Apply to Image`**: Permanently multiplies voxel values in memory by $S$, adjusts Window/Level proportionally, clears range/histogram caches, and resets $S = 1.0$.
  - **`Reset Original`**: Inverts cumulative scale $\prod S$ to safely restore original unscaled voxel values without duplicate memory allocation.
  - **Real-time Range Preview**: Displays `Current Range [min, max]` and `Scaled Range [min*S, max*S]`.

### C. Clinical Window/Level Presets & Colormaps (Implemented in Step 2)
* **Presets**:
  * `[0 - 100%]`: sets window range $[0, D_{\text{ref}}]$.
  * `[0 - 107%]`: sets window range $[0, 1.07 \times D_{\text{ref}}]$ (standard ICRU clinical target coverage).
  * `[Full Range]`: sets window range $[D_{\min}, D_{\max}]$.
* **Threshold Background (< 5% Ref)**:
  * Checkbox to hide low non-clinical dose below 5% of reference dose, preserving underlying anatomical CT/MRI visibility.
* **Colormaps**:
  * Dedicated radiotherapy colormaps: `Dosimetry`, `Jet`, `Hot`.

### D. Point Dose Sampling (Implemented in Step 2)
* Displays real-time dose at the crosshair position:
  * Absolute physical dose ($D_{\text{pt}}$ in Gy).
  * Relative dose percentage ($\% D_{\text{ref}}$).

### D. Point Dose & Profile Sampling (Adaptation)
* **Point Sampling**:
  * Crosshair tracker displays both absolute dose (e.g., $48.2\text{ Gy}$) and relative dose (e.g., $96.4\% D_{\text{rx}}$).
* **1D Dose Profiles**:
  * Connects with the existing Profile Plugin:
  * When sampling along a profile line, plots the dose curve with prescription dose reference lines ($100\%$, $95\%$, $107\%$).

---

### E. Isodose Contours (Implemented)
* Real-time 2D isodose curve extraction and rendering in physical space across orthogonal slice views.
* Customizable isodose level presets with standard clinical levels (10% to 107%).
* Individual isodose level visibility toggles, color swatch pickers, numeric threshold inputs, and deletion.
* Sub-pixel isoline extraction built on top of the marching squares contour engine.
* Compact toolbar with `Show`, `Sub-Pixel`, and reset defaults icon button (`↺`).

---

### F. Dose-Volume Histograms (DVH / HDV) (Implemented)
* Active when both a dose volume and organ ROIs / structure sets are loaded.
* Interactive cumulative ($c\text{DVH}$) and differential ($d\text{DVH}$) plots ($V(D)$ vs. $D$):
  * Volume axis: $\%$ volume or $\text{cm}^3$.
  * Dose axis: $\text{Gy}$ or $\% D_{\text{rx}}$.
  * Interactive plot legend positionable across any corner or outside.
* Structure checklist with real-time substring search, invert filter (`!`), and bidirectional color sync with the ROI plugin.
* Clinical dosimetric metrics table:
  * $D_{\text{mean}}$, $D_{\min}$, $D_{\max}$.
  * $D_{98\%}$, $D_{50\%}$, $D_{2\%}$ (near-minimum, median, and near-maximum metrics).
  * Interactive column sorting across all metrics (Structure, Vol, Min, Mean, Max, D98, D50, D2).
* CSV export for both summary metrics and full dose-volume curves, preserving active filters and sort orders.

---

## 4. Architecture & File Structure

```
src/vvv/plugins/dose/
├── __init__.py           # Package init
├── plugin_dose.py        # Lifecycle entry point, discovery, order
├── control_dose.py       # State, isodoses, normalization, callbacks
├── ui_dose.py            # Sidebar panel, requirement banner, preset buttons
├── dvh_calc.py           # High-performance dose-volume histogram calculation
├── ui_dvh.py             # Interactive DVH window (plots, metrics, sorting, CSV)
└── test_dose.py          # Pytest unit tests (40+ test cases)
```

### State Storage & Workspace
* Dose settings (`scaling_factor`, `norm_mode`, `norm_target_value`, `norm_roi_id`, isodose levels, colors, opacity) are fully serialized into workspace `.vvw` under `plugins.dose_plugin`.

