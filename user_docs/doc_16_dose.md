# Radiation Dose & Isodoses

The **Dose** tool provides quantitative radiotherapy, dosimetry, and nuclear medicine tools for radiation dose inspection, dose scaling, relative normalization, and interactive 2D isodose contour visualization.

---

## 1. Activation & Target Selection

The Dose plugin is strictly dedicated to volumes representing absorbed dose or dose rate.

### Activation Criteria

* The tool is automatically active when:
  * The active viewer's **Base image** has physical unit **`Gy`**, **`mGy`**, or **`Gy/decay`**.
  * **OR** the active viewer's **Fusion overlay** has unit **`Gy`**, **`mGy`**, or **`Gy/decay`**.
* **DICOM RTDOSE**: VVV automatically reads `DoseGridScaling` from DICOM RTDOSE series and sets `image.unit = "Gy"`. RTDOSE images therefore satisfy the activation requirement immediately upon loading.

### Inactive State (Dose Unit Required)

* When neither the base image nor the overlay has a Gy-compatible unit, the panel displays an informational banner:
  > *"Dose Unit Required: This tool is active when the base image or fused overlay has a Gy-compatible unit: Gy, mGy, or Gy/decay."*
* An **"Enable (Set unit to Gy)"** button is provided:
  * If an overlay is loaded: assigns unit `Gy` to the overlay volume.
  * Otherwise: assigns unit `Gy` to the base image volume.
  * Instantly activates the plugin controls.

### Automatic Dose Target

When active, the tool indicates its target dose volume (`Target: <Image Name>`):

* If a Fusion overlay represents a dose (e.g. anatomical CT base with RTDOSE overlay), the tool automatically targets the **overlay** layer.
* If the base image is a dose volume, it targets the **base** image.

---

## 2. Intensity Scaling & Normalization

The Dose tool features a comprehensive scaling and normalization engine shared with the Intensity component:

### Scaled Range Preview

* **Range**: Displays the real-time dynamic range `[min, max]` of the dose volume, taking into account the active user scale factor.

### User Scale Factor ($S$)

* **Scale factor**: Interactive numeric input (defaults to `1.0`). Allows applying an arbitrary physical multiplier $S$ to raw image values (e.g. converting between units, applying monitor units, or scaling Monte Carlo fractions).
* Works independently alongside prescription dose normalization.

### Normalization Controls

Easily switch between absolute physical dosimetry and relative clinical percentages:

| Mode | Control | Behavior |
| :--- | :--- | :--- |
| **Absolute** | **None** | Displays absolute dose values in Gy or mGy using the user scale factor. |
| **Max Normalization** | **Max** | Automatically sets the peak dose voxel across the volume to $100\%$ ($S_{\text{eff}} = 100 / D_{\max}$). Window/Level is adjusted to $[0, 100\%]$. |
| **Center on Max** | **⌖** | Jumps the 3D crosshair and camera view directly to the coordinates of the maximum dose voxel. |
| **Prescription** | **Prescription** | Relative normalization setting a specified prescription reference dose (e.g. $50.0\text{ Gy}$) to $100\%$. Opens an input field to configure the prescription value. |
| **ROI Mean** | **ROI Mean** | *(When an ROI structure is selected)* Normalizes the mean dose inside the chosen contour to $100\%$. |

---

## 3. Display Threshold

The **Display Threshold** section controls background dose transparency:

* **Min Thr**: Stepped slider with an enable/disable checkbox.
* Voxels with dose values below the threshold cutoff are rendered completely transparent.
* This removes low non-clinical background dose (e.g. $< 5\%$ of prescription) so that underlying anatomical structures (such as CT or MRI tissues) remain clearly visible.

---

## 4. Isodose Contours & Colorwash Shading

The **Isodose Contours** engine provides dual visualization modes standard in clinical radiation therapy planning systems (TPS):

### Visualization Modes

* **Lines**: Toggles visibility of sharp 2D isodose contour lines in the active viewports.
* **Shading (Colorwash)**: Toggles semi-transparent colorwash shading between isodose levels.
  * Dose voxels between adjacent isodose levels are filled with the corresponding level's color.
  * Dose voxels below the lowest enabled isodose level (e.g. $< 10\%$) remain completely transparent so underlying anatomy is never obscured.
  * Can be combined with **Lines** for simultaneous stepped colorwash and demarcated isodose boundaries.
* **Opacity**: Unified opacity slider controlling overlay and shader transparency. When dose is an overlay in Fusion mode, it directly controls the fusion overlay opacity (synchronized bidirectionally with the Fusion tab's opacity slider). When Shading (colorwash) is enabled, it defines the colorwash shader transparency. When dose is a base image and shading is turned off, the slider is disabled.
* **Sub-Pixel**: Uses marching squares linear interpolation for smooth, sub-voxel contour curves rather than jagged voxel edges.
* **↺ (Reset Defaults)**: Restores standard clinical radiotherapy isodose levels:
  * $107\%$ (Hot spot / overdose target)
  * $100\%$ (Prescription dose coverage)
  * $95\%$ (Target volume minimum coverage)
  * $90\%$, $80\%$, $70\%$, $50\%$, $20\%$, $10\%$

### Managing Individual Levels

Below the header, each isodose level is listed with individual controls:

* **Checkbox**: Toggle visibility of that specific isodose curve / colorwash band on and off.
* **Color Swatch**: Click the colored square to open the color picker and customize the contour line and shading color.
* **Value Input**: Edit the threshold value (in $\%$ for normalized dose, or in $\text{Gy}$ for absolute dose).
* **Unit Label**: Displays `%` or physical dose unit.
* **✕ (Delete)**: Removes the level.

---

## 5. Working with Multi-Modal Datasets (CT + RTDOSE)

In typical radiotherapy workflows (e.g. using data from the `data/head_neck` sample):

1. **Load Anatomy & Dose**:
   * Load the planning CT as the base image.
   * In the **Fusion** tab, select the RTDOSE volume as the **Target (Overlay)** with `Alpha` mode.
2. **Open the Dose Tab**:
   * The Dose tool automatically detects the dose overlay and targets it.
3. **Normalize to Prescription**:
   * Click **Prescription**, enter the prescribed dose (e.g., $50\text{ Gy}$), and watch the display and isodoses re-scale to percentages ($100\% = 50\text{ Gy}$).
4. **Inspect Isodoses & Hot Spots**:
   * Check **Lines** for contour isolines, and **Shading** for isodose colorwash.
   * Click **⌖** to immediately jump the crosshair to the location of maximum dose ($D_{\max}$).
5. **Inspect Metadata**:
   * In the **Active Viewer** panel, use the **⇄** toggle button next to the image name to toggle between viewing CT metadata and RTDOSE metadata.

---

## 6. Workspace Serialization (`.vvw`)

All Dose tool parameters are fully saved and restored in VVV workspace files (`.vvw`):

* **Scaling & Normalization**: User multiplier $S$, active normalization mode (`None`, `Max`, `Prescription`, `ROI Mean`), and reference prescription target dose.
* **Isodose Configuration**: All custom level values, colors, enabled states, line thickness, and sub-pixel interpolation setting.
* **Shading & Display**: `Lines` visibility, `Shading` colorwash toggle, and shading opacity.

Opening a saved workspace automatically reconstructs the exact clinical isodose display and scaling state without requiring manual re-configuration.
