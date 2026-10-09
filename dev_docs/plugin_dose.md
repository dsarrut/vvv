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

### A. Intensity & Dose Scaling Tools
* **Physical Dose Scaling Factor ($S$)**:
  * Raw image voxels may represent absorbed dose directly ($S=1.0$) or require calibration scaling (e.g. Monte Carlo dose-per-simulated-particle, calibration factors, decay-to-fraction multiplication).
  * Interactive scaling multiplier slider / input ($D_{\text{scaled}} = S \times D_{\text{raw}}$).
* **Min / Max Dose Range**:
  * Real-time readouts of true volume dose range: $D_{\min}$ and $D_{\max}$ (in Gy or relative %). Warning, if dose image is large, can be long. 
  * Excludes voxels below lower threshold (air / exterior).
NO. Unsure how to deal with that. Ignore for the moment. 
### B. Dose Normalization Modes
Quick toggling between absolute dose and relative percentage representations:
1. **Absolute Dose**: $\text{Gy}$, $\text{mGy}$, or $\text{Gy/decay}$. Can be maybe Gy.IA (injected activity), so we need an injected activity field (?)
2. **% to Max Dose ($D_{\max}$)**: Normalized such that $100\% = \max(D)$.
3. **% to Prescription Dose ($D_{\text{rx}}$)**:
   * User-defined prescription dose target (e.g. $50.0\text{ Gy}$ or $60.0\text{ Gy}$).
   * $100\%$ corresponds to $D_{\text{rx}}$.
4. **% to ROI Mean / Target**:
   * Normalization based on the mean dose inside a selected target structure (e.g., PTV or tumor ROI).
only if ROIs exists
### C. Colormap & Legend Integration
* Automatic binding to dedicated radiotherapy lookup tables (`Dosimetry`, `Jet`, `Hot`).
* The existing viewer color legend bar (<kbd>L</kbd>) automatically reflects the chosen normalization scale (Gy or %).

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

