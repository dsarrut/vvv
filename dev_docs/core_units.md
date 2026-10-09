# Image Units & Publication Legends

This document details VVV's image intensity unit architecture, detection pipeline, sidecar JSON persistence, clinical presets, and publication colorbar rendering.

---

## 1. Overview & Supported Units

Medical and scientific images represent physical quantities with specific physical units. Tracking intensity units enables:
* Appropriate Window/Level presets (e.g. standard clinical PET SUV scales).
* Noise/air suppression via minimum thresholding.
* Accurate colorbar legends and tracker readouts for scientific publications and diagnostic review.

### Standard Known Units

| Unit | Modality / Context | Description |
|------|--------------------|-------------|
| `HU` | CT | Hounsfield Units (water = 0, air = -1000) |
| `SUV` | PET | Standardized Uptake Value (normalized by body weight) |
| `SUL` | PET | Standardized Uptake Value normalized by Lean Body Mass (PERCIST standard) |
| `Bq/mL` | PET / SPECT | Becquerels per milliliter (activity concentration) |
| `kBq/mL` | PET / SPECT | Kilo-Becquerels per milliliter |
| `Gy` | RTDOSE | Gray (absorbed radiation dose) |
| `counts` | Nuclear / Optical | Raw detector event counts |
| `a.u.` | MRI / Microscopy | Arbitrary units (uncalibrated) |
| `?` | Generic | Unknown / unspecified unit |

Custom user-typed units (e.g. `mm/s`, `ppm`, `MBq/mL`) are also supported.

---

## 2. Auto-Detection Pipeline

When an image volume is loaded, VVV resolves its unit via the following priority cascade:

1. **Priority 1: Sidecar JSON (`<image>.json`)**
   * VVV looks for a JSON file in the same directory as the image: `<path_to_image>.json` or `<image_stem>.json` (e.g., `pet.json` alongside `pet.nii.gz`).
   * Keys parsed: `"unit"`, `"units"`, `"Unit"`, or `"Units"`.
   * Example sidecar JSON:
     ```json
     {
       "unit": "SUV",
       "patient_weight_kg": 72.5
     }
     ```
   * Case-insensitive matching automatically maps aliases (e.g. `"suv"` $\to$ `"SUV"`, `"sul"` $\to$ `"SUL"`, `"bq/ml"` $\to$ `"Bq/mL"`).

2. **Priority 2: DICOM Metadata**
   * If no sidecar JSON is found, VVV inspects the DICOM dataset header:
     * `Modality` tag `(0008,0060)`: `CT` $\to$ `HU`, `RTDOSE` $\to$ `Gy`.
     * `Units` tag `(0054,1001)` for Nuclear Medicine / PET:
       * `BQML` $\to$ `Bq/mL`
       * `CNTS` $\to$ `counts`
       * `GML` $\to$ `SUV` (g/mL uptake concentration)
     * If `Modality == "PT"` or `"PET"` and calibrated uptake values are detected $\to$ `SUV`.

3. **Fallback: `None` (`?`)**
   * If no metadata or sidecar is available, the unit defaults to `None`, displayed as `?` in the interface.

---

## 3. Interactive Editing & Sidecar Persistence

Units can be inspected and updated directly within the **Active Viewer Info** sidebar panel:

```text
Unit: [ SUV      ] [▾]  (pet.json)
```

* **Renamable Text Input**: Clicking the unit field allows direct typing of any standard or custom unit. Pressing `Enter` or clicking outside confirms the change.
* **Preset Dropdown `[▾]`**: Clicking the chevron opens a quick-pick popup menu listing standard presets (`HU`, `SUV`, `SUL`, `Bq/mL`, `kBq/mL`, `Gy`, `counts`, `a.u.`, `?`).
* **Change Tracking**:
  * Modifying the unit flags the volume as outdated/modified (visual indicator: volume title turns orange with an asterisk `*` and `[OUTDATED]`).
  * Changes immediately invalidate viewer legend caches and trigger real-time colorbar redrawing.
* **Saving to Sidecar**:
  * Quick-saving (`Ctrl+S` / top-bar Save button) automatically creates or updates the `<image>.json` sidecar on disk with the new unit:
    ```json
    {
      "unit": "SUL"
    }
    ```
  * Saving clears the dirty status and returns the volume status to normal.

---

## 4. Clinical Presets & Noise Thresholding

Images with known units automatically benefit from standard clinical display presets:

### Auto-Defaulting
* When an image with unit `SUV` or `SUL` is loaded, VVV automatically applies the standard clinical preset **`PET: [0 - 10]`** with:
  * `Window Width (WW) = 10.0`
  * `Window Level (WL) = 5.0`
  * `min_threshold = 0.0`

### PET Presets
Available in both the **Intensity** plugin panel and the **Fusion Image Intensity** tab:
* `PET: [0 - 10]` (`ww=10.0`, `wl=5.0`, `min_threshold=0.0`) — standard clinical oncology review
* `PET: [0 - 5]` (`ww=5.0`, `wl=2.5`, `min_threshold=0.0`) — low-uptake / brain PET
* `PET: [0 - 15]` (`ww=15.0`, `wl=7.5`, `min_threshold=0.0`) — high-uptake lesions
* `PET: [0 - 20]` (`ww=20.0`, `wl=10.0`, `min_threshold=0.0`) — intense avidity / radiotherapy planning

### Minimum Noise Threshold (`min_threshold = 0.0`)
* Voxels with values $\le 0.0$ are non-positive background noise or air.
* Setting `min_threshold = 0.0` renders these voxels completely transparent in the slice viewport, allowing fused CT anatomy to show through without a dark haze.

---

## 5. Colorbar Legend Display (`L` Shortcut)

Pressing **`L`** cycles through the three legend overlay states:
$$\text{Off} \longrightarrow \text{Mode 1 (Interactive)} \longrightarrow \text{Mode 2 (AQARA)} \longrightarrow \text{Off}$$

### Mode 1: Interactive / Diagnostic
* Displays **Min**, **Window Level (WL)**, and **Max** values.
* Interactive crosshair needle (horizontal line + pointer triangle) follows the mouse cursor and displays the exact value of the voxel under the cursor in real time.
* Unit is centered above the colorbar.

### Mode 2: AQARA Publication-Ready
* Designed for scientific articles, reports, and presentations.
* Uses clean, rounded tick marks (tics) at standard intervals ($1, 2, 5 \times 10^k$), e.g.:
  * `PET: [0 - 10]` $\to$ ticks at `0`, `2`, `4`, `6`, `8`, `10`.
  * `PET: [0 - 5]` $\to$ ticks at `0`, `1`, `2`, `3`, `4`, `5`.
* Suppresses the interactive crosshair needle indicator for an uncluttered export.
* Caches the rendered vector overlay to avoid unnecessary redraws on mouse movements.

### Dual Colorbar Layout (Fusion / Overlay)
* When an overlay image is fused on top of a base image (e.g. PET over CT):
  * Left colorbar displays base image `(1)` with its colormap and unit (e.g. `HU`).
  * Right colorbar displays overlay `(2)` with its colormap and unit (e.g. `SUV`).
  * Image numbers `(1)` and `(2)` are centered above their respective colorbars and units.

---

## 6. Threshold Cutoff Visualization on Colorbars

When `min_threshold` is active, the colorbar visually indicates which portion of the intensity spectrum is clipped:

1. **Sub-Threshold Dimming**:
   * Colorbar gradient levels corresponding to voxel values $\le \text{min\_threshold}$ are dimmed by 70% toward the background color (`dim_factor = 0.30`).
   * This provides an immediate visual clue that those values are transparent in the image.

2. **In-Range Cutoff Indicator Line**:
   * When $\text{val\_min} \le \text{min\_threshold} \le \text{val\_max}$, an amber indicator line (`thickness = 2`) is drawn across the colorbar at the exact threshold position, extending 3 pixels on each side beyond the colorbar border.

3. **Sub-Min Indicator Tag (`min_threshold < val_min`)**:
   * If the display window minimum is adjusted above the threshold (e.g. range $[2.0 - 10.0]$ with `min_threshold = 0.0`), the cutoff line is off-scale.
   * In this case, a downward amber triangle marker $\boldsymbol{\triangledown}$ is drawn at the bottom edge of the bar with a clean label **`thr: <value>`** (e.g. `thr: 0`) directly beneath it.

