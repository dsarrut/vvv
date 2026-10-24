# Manual Rigid Image Registration

The **Transform** tool aligns an image by hand with a rigid transform (6 degrees of freedom: 3 translations, 3 rotations), e.g. a moving image on a fixed reference.

![Registration Interface](images/doc_12_registration_layout.png)

---

## Aligning Images

1. Load the reference and the moving image, either in separate viewers or in one viewer with the moving image as Fusion overlay (see [Fusion](doc_06_fusion_and_overlays.md)).
2. Open the **Transform** tab of the nav column.
3. If the active viewer has a Fusion overlay, the **Target** switch (`Base` / `Fusion`) chooses which image you move. A summary line shows both transforms (`Base: <file or Identity> | Fusion: <file or Identity>`).

The screen stays fixed in space: with Target **Base**, the base image (and its ROIs) moves on screen and the overlay stays; with Target **Fusion**, the overlay moves. The crosshair stays at the same place in space.

---

## The Transform Panel

### File toolbar
**Load**, **Save**, **Save As**, **Reload**, **Unload** (<kbd>×</kbd>), then the name of the transform file (`patient.tfm (side-car)` for a side-car file; hover it for its full path).

### Rigid Adjustment (Euler R = Rz Ry Rx)
* **Step**: **Coarse** (1 mm / 1° per step) or **Fine** (0.1).
* **Tx**, **Ty**, **Tz** (mm): the translations; **Rx**, **Ry**, **Rz** (degrees): the rotations. Drag a value or use its <kbd>−</kbd> / <kbd>+</kbd> buttons.
* **CoR**: the center of rotation (mm). The icons next to it move the crosshair to the CoR, or snap the CoR to the crosshair.
* **Reset to Identity**: all translations and rotations back to zero.
* **Invert Transform**: replaces the transform by its inverse ($T \leftrightarrow T^{-1}$).

### Preview and resampling
While you drag, rotations are previewed quickly; the full resample (ITK) is done:
* when you stop dragging, if **Auto-Update Preview** is on;
* with the **Update Preview** button (orange when the preview is out of date).

**Resample Image** applies the transform to the voxels of the image for good (the image is resampled on its own grid) and resets the sliders to zero.

### Affine Matrix
The 4×4 matrix of the current transform.

---

## Checking the Alignment

Use the fusion modes of the **Fusion** tab (see [Fusion](doc_06_fusion_and_overlays.md)):
* **Registration**: a red / green difference map of the two images;
* **Checkerboard**: alternating tiles of the two images (tile size, **Swap**); edges that break at the tile borders show a misalignment;
* **Alpha** with a colormap on the overlay.

---

## Saving & Loading Transformations

* **File Formats**: Load reads ITK transforms (`.tfm`), `.txt`, `.mat`, `.xfm`, and Elastix Euler parameter files (`TransformParameters` + `CenterOfRotationPoint`, read only). Save writes `.tfm` (default), `.txt` or `.mat`.
* **Literature & ITK Coordinate Convention**: Files saved to and loaded from disk adhere to the standard ITK / literature convention ($T_{\text{disk}} = T_{\text{ITK}} = T_{\text{fixed} \to \text{moving}}$). In VVV's interactive viewport, forward spatial display coordinates ($T_{\text{moving} \to \text{world}}$) are used, ensuring intuitive forward slider movement while guaranteeing interoperability with SimpleITK (`sitk.Resample`), Plastimatch, Elastix, and 3D Slicer without manual coordinate inversion.
* **Default Name**: Save As proposes the name of the current transform file, else the image name (`patient.tfm`), which makes it a side-car file.
* **Automatic Transform Loading (side-car)**: When an image is loaded, VVV checks for a transform file with the same name in the same folder: `patient.tfm`, else `patient.mat` (also `patient.nii.gz.tfm`; for a DICOM series, the folder's `.tfm`). If found, it is loaded and applied, also when the image comes from a workspace (workspaces do not store transforms). The <kbd>×</kbd> icon unloads the transform (the file is kept, and applied again at the next load). See [Side-Car Files](doc_17_side_car_files.md).
