
This is VVV, a tentative successor to VV (https://github.com/open-vv)

VVV is a software to view 3D/4D (medical) images.

Goal
- fast, research-oriented, "minimalist"
- command line + keyboard driven

Help
- click on the bottom left "baby" icon to display additional helps in the ui


Features:
- 3D/4D image slice viewer (most file formats supported, mhd, nii, nrrd, etc.).
- Command line based: `vvv ct.nii.gz`.
- Multi-Planar slicing (MPR): instantly switch between Axial, Coronal, and Sagittal orientations (F1, F2, F3).
- Images synchronization, sub-pixel accuracy.
- Overlays: crosshairs, tracker, scalebar.
- Window/Level control, Colormap, auto-windowing.
- Fusion of two images: alpha blending, registration difference, checkerboard.
- ROI masks management (load binary mask images).
- (Basic) DICOM browser.
- Session management: save workspaces to file.
- History: automatically remembers last-viewed images.
- Interactive Profiles: draw lines on slices and plot intensity values (press `P`).
- Interactive Thresholding: preview contour lines and generate masks.
- Voxel units & publication legends: auto-detection from sidecar JSON / DICOM (HU, SUV, SUL, Bq/mL, Gy), interactive editing, and publication colorbars (press `L`).
- 6-DOF Registration: align images with manual sliders, fast 2D previews, and 3D resampling.
- DVF Visualization: render displacement vector fields as arrow overlays, component maps, or RGB channels.
- Radiation Dose & DVH: quantitative radiotherapy tools, relative normalization (% rx, % max), smooth 2D isodose contours/colorwash, and interactive Dose-Volume Histograms (DVH / HDV) with sortable metrics and CSV export.

VVV has been carefully "vibe-coded" (mostly Gemini, a bit of Claude) following the path of VV. We paid special attention to robustness, clear architecture and performance. 

## Installation

```bash
    pip install open-vvv
```

or for develop version

```
    git clone https://github.com/dsarrut/vvv
    cd vvv
    pip install -e .
```

> **Linux Note (Clipboard support for screenshots):**
> On Linux, copying screenshots directly to the system clipboard requires `xclip` (X11) or `wl-clipboard` (Wayland). These are system utilities and cannot be installed via `pip`:
> ```bash
> sudo apt install xclip         # Ubuntu / Debian (X11)
> # or: sudo apt install wl-clipboard   # Ubuntu / Debian (Wayland)
> # or: sudo dnf install xclip          # Fedora / RHEL
> ```
> If neither is installed, clicking the screenshot button automatically saves the image to `~/Pictures/vvv_screenshot_<timestamp>.png` (or `~/vvv_screenshot_...png`).

## Command line

```bash
    vvv ct.nii.gz spect.nii.gz -s    # load the two images, synchronize
    vvv ct.nii.gz, spect.nii.gz, jet  # load two images, fuse them with jet colormapping
    vvv ct.nii.gz + labels.nii.gz # load ct with labels overlay
    vvv my_session.vvw # restore the session for the file
    
```

## Screenshots

![Alt text](screenshots/ct.png?raw=true "vvv ct.nii.gz")

![Alt text](screenshots/ct_spect.png?raw=true "vvv ct.nii.gz, spect.nii.gz, jet")

![Alt text](screenshots/ct_4d.png?raw=true "vvv ct_4D.mha")

![Alt text](screenshots/rois.png?raw=true "vvv and open ROIs")

![Alt text](screenshots/dicom.png?raw=true "vvv and mini DICOM browser")

