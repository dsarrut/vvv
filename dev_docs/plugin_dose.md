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

### A. Intensity & Dose Scaling Tools (Implemented in Step 2)
* **Physical Dose Scaling Factor ($S$)**:
  * Raw image voxels may represent absorbed dose directly ($S=1.0$) or require calibration scaling (e.g. Monte Carlo dose-per-simulated-particle, calibration factors, decay-to-fraction multiplication).
  * Interactive scaling multiplier input ($D_{\text{scaled}} = S \times D_{\text{raw}}$) with `x1`, `x0.001`, and `x1000` quick presets.
  * **"Apply to Voxels" (Bake)**: Permanently multiplies the voxel values in memory by $S$ and resets $S=1.0$, adapting window/level synchronously.
* **Min / Max Dose Range**:
  * Real-time readouts of volume dose range ($D_{\min}$ and $D_{\max}$) computed via cached `volume.get_data_range()`.
  * In absolute mode: displayed in physical units (e.g., `0.00 Gy` to `65.4 Gy`).
  * In relative modes: displays both physical dose and relative percentage (e.g., `[0.0 % - 130.8 %]`).

### B. Dose Normalization Modes (Implemented in Step 2)
Quick toggling between absolute dose and relative percentage representations:
1. **Absolute Dose**: $\text{Gy}$, $\text{mGy}$, or $\text{Gy/decay}$.
2. **% to Max Dose ($D_{\max}$)**: Normalized such that $100\% = \max(D)$.
3. **% to Prescription Dose ($D_{\text{rx}}$)**:
   * User-defined prescription dose target (e.g. $50.0\text{ Gy}$ or $60.0\text{ Gy}$), with quick presets (`2 Gy`, `50 Gy`, `60 Gy`, `Set to Max`).
   * $100\%$ corresponds to $D_{\text{rx}}$.
4. **% to ROI Mean / Target**:
   * Normalization based on the mean dose inside a selected target structure (e.g., PTV or tumor ROI).
   * Populated dynamically from available organ ROIs; computes and displays $\bar{D}_{\text{ROI}}$.

### C. Clinical Window/Level Presets & Colormaps (Implemented in Step 2)
* **Presets**:
  * `[0 - 100%]`: sets window range $[0, D_{\text{ref}}]$.
  * `[0 - 107%]`: sets window range $[0, 1.07 \times D_{\text{ref}}]$ (standard ICRU clinical target coverage).
  * `[Full Range]`: sets window range $[D_{\min}, D_{\max}]$.
* **Threshold Background (< 5% Ref)**:
  * Checkbox to hide low non-clinical dose below 5% of reference dose, preserving underlying anatomical CT/MRI visibility.
* **Colormaps**:
  * Dedicated radiotherapy colormaps: `Dosimetry`, `Jet`, `Turbo`, `Hot`.

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

## 4. Roadmap & Future Modules (Planned)

### E. Isodose Contours (Phase 2)
* Customizable isodose level presets:
  * Standard clinical levels: $107\%$, $100\%$, $95\%$, $90\%$, $80\%$, $50\%$, $20\%$ (or fixed Gy intervals).
* Individual isodose level toggles, colors, line widths, and fill shading.
* Sub-pixel isoline extraction built on top of the existing `marching_squares` contour engine.

### F. Dose-Volume Histograms (DVH) (Phase 3)
* Active when both a dose volume and organ ROIs / structure sets are loaded.
* Interactive cumulative and differential DVH plots ($V(D)$ vs. $D$):
  * Volume axis: $\%$ volume or $\text{cm}^3$.
  * Dose axis: $\text{Gy}$ or $\% D_{\text{rx}}$.
* Clinical dose-volume metrics table:
  * $D_{\text{mean}}$, $D_{\min}$, $D_{\max}$.
  * $D_{98\%}$, $D_{95\%}$, $D_{50\%}$, $D_{2\%}$ (near-minimum and near-maximum metrics).
  * $V_{x\text{Gy}}$ (volume receiving at least $x\text{ Gy}$).
* CSV export for DVH curves and clinical metrics.

---

## 5. Architecture & File Structure

```
src/vvv/plugins/dose/
├── __init__.py           # Package init
├── plugin_dose.py        # Lifecycle entry point, discovery, order
├── control_dose.py       # State, scaling logic, normalization math, callbacks
├── ui_dose.py            # Sidebar panel, requirement banner, preset buttons
└── test_dose.py          # Pytest unit tests
```

### State Storage & Workspace
* Dose settings (`scaling_factor`, `norm_mode`, `rx_dose`, `selected_roi_id`) will be serialized into workspace `.vvw` under `plugins.dose_plugin`.

