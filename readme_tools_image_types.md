# Tools × Image Types — Expected Behavior

This document defines the expected behavior of each VVV tool for every supported image type.
It serves as a specification reference for development and testing.

## Image Type Definitions

| Type  | Description                                                                 |
|-------|-----------------------------------------------------------------------------|
| 2D    | Single-slice image (PNG, JPG, TIFF, or any 3D image with Z=1)              |
| 3D    | Standard volumetric image (Physical XYZ coordinates, NumPy array shape ZYX)|
| 4D    | Time-series volume (Physical XYZ coordinates, NumPy array shape T, Z, Y, X), loaded via `4D:` prefix or CLI |
| DVF   | Displacement Vector Field — multi-component float image (3 components). 4D time-sequences of DVFs are currently out-of-scope and not supported. |
| RGB   | Color image — 3 or 4 integer components (uint8); no Window/Level concept   |

## Summary Matrix

Legend: ✅ Full support · ⚠️ Partial / with caveats · ❌ Not supported

|                   | 2D | 3D | 4D | DVF | RGB |
|-------------------|:--:|:--:|:--:|:---:|:---:|
| tracker, etc      | ✅ | ✅ | ✅ |  ✅ |  ✅ |
| Image List.       | ✅ | ✅ | ✅ |  ✅ |  ✅ |
| Sync              | ✅ | ✅ | ✅ |  ❌ |  ⚠️ |
| Fusion            | ✅ | ✅ | ✅ |  ⚠️ |  ⚠️ |
| Intensity         | ✅ | ✅ | ✅ |  ✅ |  ❌ |
| ROI               | ✅ | ✅ | ⚠️ |  ❌ |  ⚠️ |
| Reg               | ⚠️ | ✅ | ⚠️ |  ❌ |  ⚠️ |
| Threshold         | ✅ | ✅ | ⚠️ |  ❌ |  ❌ |

## Implementation Check Matrix

Use this matrix to track the actual implementation status of the rules defined in this document.
Legend: ⬜ Not checked yet · 🔄 In progress · ✅ Checked and implemented correctly · ❌ Needs fixing

|                   | 2D | 3D | 4D | DVF | RGB |
|-------------------|:--:|:--:|:--:|:---:|:---:|
| tracker, etc.     | ⬜ | ⬜ | ⬜ |  ⬜ |  ⬜ |
| Image List        | ✅ | ✅ | ✅ |  ✅ |  ✅ |
| Sync              | ✅ | ✅ | ✅ |  ✅ |  ✅ |
| Fusion            | ✅ | ✅ | ✅ |  ✅ |  ✅ |
| Intensity         | ⬜ | ⬜ | ⬜ |  ⬜ |  ⬜ |
| ROI               | ⬜ | ⬜ | ⬜ |  ⬜ |  ⬜ |
| Reg               | ⬜ | ⬜ | ⬜ |  ⬜ |  ⬜ |
| Threshold         | ⬜ | ⬜ | ⬜ |  ⬜ |  ⬜ |

---

## Tracker / Crosshair / Navigation

TrackerFunction: 
- Displays real-time information about the image voxel currently under the mouse cursor.  
- Information Displayed:
    - Coordinates: Physical coordinates in millimeters (mm) and integer voxel indices.  
    - Pixel Values: The raw value of the base image and any active overlay.  
    - DVF Support: For Displacement Vector Fields, it displays the three vector components $[dx, dy, dz]$ and the calculated vector length (L2 norm) in mm.  
    - Sync Behavior: If images are in a sync group, the tracker propagates to other viewers, showing the values of linked images at the same physical world position.  
    - ROI Detection: Lists the names of all ROIs present at the current mouse position.  
- Control: Can be toggled via the "Show Tracker" checkbox in the UI or via the shortcut defined in config.py.  

Crosshair
- Function: Vertical and horizontal lines representing the intersection of the current slices in other orientations (e.g., the Axial viewer shows where the Sagittal and Coronal planes intersect).  
- Panel Information:
    - Spatial Data: Voxel indices, physical coordinates (mm), and the current Window/Level.  
    - Optical Data: Current Pixels Per Millimeter (PPM) and the Field of View (FOV) size.  
    - ROI Data: Displays names of ROIs intersecting the crosshair center.  
    
Zoom & Pan
- Mouse Tracking: When zooming, the application automatically adjusts the pan offset to ensure the transformation pivots around the current mouse position.  
- View Consistency: All viewers displaying the same VolumeData share the same ViewState (zoom, pan, and PPM).  
- Synchronization: Viewers in the same sync group share identical PPM and physical target centers to ensure anatomical alignment across different modalities.  

Interpolation
- Default: Uses Linear interpolation for smooth visualization.  
- Nearest Neighbor (NN): Can be toggled (default key: K) for "pixelated" zoom.  
- Performance Note: At extreme zoom levels, the system may switch to Voxel Strips (geometric primitives) to maintain 60 FPS while bypassing standard texture mapping.

---

## Image List

**Purpose:** Load, display, arrange, and close images. Manage layout (V1–V4).

| Type | Expected behavior |
|------|-------------------|
| 2D   | Load and display in a viewer. The single slice is the only navigable plane. |
| 3D   | Load and display. Spatial navigation is done through keys or mouse (no slice slider appears). |
| 4D   | Load and display. Navigation across both spatial and temporal dimensions is done through keys or mouse (no sliders appear). |
| DVF  | Load and display. The 3 displacement components (Dx, Dy, Dz) are exposed via temporal navigation keys/mouse (one component per "frame" via internal array axis swapping). No temporal meaning — navigation changes the "Component" rather than "Time". |
| RGB  | Load and display in full color. No grayscale conversion. |

---

## Sync

**Purpose:** Broadcast camera geometry (zoom, pan, slice depth) and radiometry (W/L) across multiple viewers belonging to the same sync group.

| Type | Expected behavior |
|------|-------------------|
| 2D   | Sync zoom and pan. No slice-depth sync (single slice). W/L is synced if the image is grayscale. |
| 3D   | Full sync: zoom, pan, slice depth (in physical mm), and W/L. |
| 4D   | Sync zoom, pan, and slice depth identically to 3D. The time/frame index is **also** synced when two 4D images share a group, so scrubbing one advances the other. When a 3D is synced to a 4D, full sync except the last dimension is ignored for the 3D image. W/L synced. |
| DVF  | **Not allowed in any sync group.** DVF images must remain isolated (Group 0). Adding a DVF to a group is silently ignored or blocked in the UI. |
| RGB  | Camera sync (zoom, pan, slice depth) is allowed. W/L sync is **skipped for the RGB base image** itself (no W/L concept), but still propagated to any grayscale overlay loaded on top of that viewer. |

---

## Fusion

**Purpose:** Blend a secondary (overlay) image on top of the current base image. Modes: Alpha, Registration (red/green diff), Checkerboard.

The overlay image must be a grayscale scalar image. The base image can be any type.

| Type (as **base**) | Expected behavior |
|--------------------|-------------------|
| 2D  | Any overlay can be fused. All three blend modes work. |
| 3D  | Any overlay can be fused. All three blend modes work. |
| 4D  | Fusion operates on the currently displayed timepoint. The overlay is a static 3D image unless the overlay is also 4D, in which case both time indices are synchronized. All three blend modes work. If the number of time slices does not correspond, the time index is clamped to `min(base_time, overlay_max_time)`. |
| DVF | DVF as base is allowed for visual inspection. Only Alpha blend makes sense; Registration and Checkerboard modes are disabled because the per-component display does not produce a meaningful difference image. |
| RGB | RGB as base: only Alpha blend is supported. Registration (red/green) and Checkerboard modes are disabled because those modes require a normalized scalar base. |

| Type (as **overlay**) | Expected behavior |
|-----------------------|-------------------|
| 2D  | Allowed as overlay over any base type. |
| 3D  | Allowed as overlay over any base type. |
| 4D  | Allowed as overlay; the displayed timepoint follows the base image's time index (clamped if the overlay is shorter). |
| DVF | **Not allowed as an overlay.** Displacement fields are multi-component and have no meaningful single-scalar rendering as a blended overlay. |
| RGB | **Not allowed as an overlay.** Overlays must be grayscale scalar images so they can be colormapped and alpha-blended. |

---

## Intensity (Window/Level + Colormap)

**Purpose:** Adjust Window/Level contrast and apply a colormap transfer function.

| Type | Expected behavior |
|------|-------------------|
| 2D   | Full W/L and colormap support. Auto-window (key `W`) computes Min/Max from the visible viewport pixels. |
| 3D   | Full W/L and colormap support. Auto-window uses pixels in the current slice viewport. |
| 4D   | Full W/L and colormap support. The same W/L and colormap applies uniformly to all timepoints. Auto-window uses the currently visible slice regardless of which timepoint is active. |
| DVF  | Each component is treated as an independent scalar image. W/L applies to the currently visible component. Auto-window is useful here because component ranges (e.g., ±10 mm) differ from typical HU ranges. Colormap can be applied (diverging colormaps such as "cold-hot" are appropriate). |
| RGB  | **W/L controls are disabled and hidden.** Colormaps do not apply. The image is always displayed using its raw RGB(A) channel values. |

---

## ROI

**Purpose:** Load and display binary masks, label maps, and RT-Structs as overlays on a base image.

| Type (base image) | Expected behavior |
|-------------------|-------------------|
| 2D   | ROI overlay is restricted to the single slice. Binary masks with Z=1 load normally. RT-Structs that have only 1 contour plane are accepted. |
| 3D   | Full support: binary masks, label maps (parallel extraction), RT-Structs. Bounding-box crop optimization applies. Raster and vector (marching squares) rendering both work. |
| 4D   | The ROI geometry is static in 3D space and is displayed on every timepoint. There is no per-timepoint ROI. The ROI is linked to the base image's spatial geometry, not its temporal dimension. |
| DVF  | **Not supported.** ROIs are spatial masks over anatomical data; applying them over a displacement field has no meaningful interpretation. |
| RGB  | ROI overlay is displayed on top of the RGB base. Raster blending works visually. Vector (contour) mode works. W/L-dependent opacity formulas are bypassed; a fixed opacity is used instead. |

---

## Reg (Registration)

**Purpose:** Apply a manual 6-DOF rigid transform (Tx, Ty, Tz, Rx, Ry, Rz) to an image. Read/write `.tfm` / `.mat` / `.txt` transform files.

| Type | Expected behavior |
|------|-------------------|
| 2D   | Registration is allowed but limited. In-plane translation (Tx, Ty) and in-plane rotation (Rz) are meaningful. Out-of-plane rotations (Rx, Ry) and out-of-plane translation (Tz) produce no visible change on a single-slice image and should be hidden or disabled to avoid confusion. |
| 3D   | Full 6-DOF support. "Straighten on Load" normalizes oblique images. Transform I/O, dynamic pivot (CoR), world-fixed anchoring, and the debounced background resampler all apply. |
| 4D   | A single rigid transform applies globally to all timepoints simultaneously. Per-timepoint registration is not supported. The transform is stored once and resampled on each displayed timepoint. "Straighten on Load" applies to the spatial geometry only. |
| DVF  | **Not supported.** Applying a rigid transform on top of a displacement field has ambiguous semantics. DVF images are displayed as-is; registration controls are hidden when a DVF is the active image. |
| RGB  | 6-DOF transform applies normally. "Straighten on Load" works. Transform I/O works. The Registration fusion mode (red/green diff) cannot be used to visually assess alignment since W/L does not apply to RGB images; Alpha blend or Checkerboard should be used instead. |

---

## Threshold (Extraction)

**Purpose:** Interactively define a scalar threshold range, preview it as a live overlay, and bake the result into a new in-memory grayscale mask image.

| Type | Expected behavior |
|------|-------------------|
| 2D   | Full support. The generated mask has the same single-slice geometry as the source. |
| 3D   | Full support. The generated mask is a full 3D binary or intensity volume. |
| 4D   | The threshold is applied to the **currently visible timepoint only** and produces a single 3D mask. Applying the threshold across all timepoints simultaneously is not supported. The UI should clearly state which timepoint is being processed. The resulting mask will behave as a static 3D ROI moving forward. |
| DVF  | **Not supported.** Threshold requires a scalar grayscale image. DVF components are floats but lack an anatomical intensity interpretation. The tool is disabled when a DVF is the active image. |
| RGB  | **Not supported.** Threshold requires a scalar grayscale image. The tool is disabled when an RGB image is the active image. |