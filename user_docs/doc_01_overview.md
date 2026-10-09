# Getting Started & Concepts

**VVV** is a lightweight, high-performance viewer designed for 2D, 3D, and 4D medical images and scientific volumes (CT, MRI, PET, SPECT, radiation dose, DVF vector fields, label maps).

---

## Core Concepts

### 1. Viewers vs. Images
* **Images (Volumes)**: Loaded volumes stored in memory. You can load dozens of images simultaneously.
* **Viewers (Viewports)**: Independent 2D display panes arranged in a grid (1×1, 1×2, 2×2, 1×3, etc.).
* **Active Viewer**: The viewer currently focused (highlighted border). Mouse and shortcut interactions apply to the active viewer.
* **Base Image vs. Overlay**:
  * Each viewer displays one **Base Image**.
  * A second image can be fused on top as an **Overlay** (e.g. PET on CT, dose on CT, or registered follow-up MRI).

### 2. Coordinate Spaces
* **Physical Space (mm)**: Real-world millimeter coordinates. Multi-viewer synchronization, crosshairs, distance measurements, and registrations always operate in physical space regardless of image resolution, voxel size, or orientation.
* **Voxel Space**: Discrete integer grid indices `(i, j, k)`.

### 3. Synchronization
* Viewers can link dynamically: moving the crosshair, panning/zooming, adjusting Window/Level, or scrolling timeframes in one viewer automatically updates linked viewers in real-time.

---

## Interface Layout

* **Top Menu Bar**: File loading, layouts, synchronizations, view resets, help/preferences.
* **Main Area (Grid)**: Viewports displaying 2D orthogonal slices (Axial, Coronal, Sagittal) or 3D projections (MIP).
* **Left Sidebar**: Collapsible tool panels organized by tabs:
  * **Images**: Manage loaded volumes, assign images to viewports, inspect metadata.
  * **Intensity**: Window/Level, colormaps, units (HU, SUV, Gy), histograms.
  * **Plugins**: Feature tools (ROIs, Threshold, Profiles, Landmarks, Registration, DVF, DICOM).
* **Bottom Status Bar**: Active image name, voxel index, physical $(X, Y, Z)$ position in mm, and voxel intensity at crosshair.

---

## Essential Controls

### Mouse Interactions
| Action | Mouse |
| :--- | :--- |
| **Slice navigation** | **Mouse Wheel** scroll |
| **Pan** | **Middle Mouse Button** drag (or **Left Click + Shift**) |
| **Zoom** | **Right Click** drag up/down |
| **Window / Level (W/L)** | **Left Click** drag (horizontal: width, vertical: level) |
| **Move Crosshair** | **Left Click** on image |

### Common Keyboard Shortcuts
| Key | Action |
| :--- | :--- |
| <kbd>F1</kbd> / <kbd>F2</kbd> / <kbd>F3</kbd> | Switch slice orientation (**Axial** / **Sagittal** / **Coronal**) |
| <kbd>W</kbd> | Auto Window/Level for base image |
| <kbd>X</kbd> | Auto Window/Level for overlay |
| <kbd>R</kbd> | Reset view (pan & zoom to fit window) |
| <kbd>C</kbd> | Center view on crosshair |
| <kbd>S</kbd> | Sync all viewports to active viewer |
| <kbd>H</kbd> | Toggle overlays visibility (crosshair, scalebar, annotations) |
| <kbd>K</kbd> | Toggle Nearest-Neighbor vs Bilinear interpolation |
| <kbd>Esc</kbd> | Clear ROI / tool selection |

---

## Command-Line Interface (CLI)

VVV is designed to be launched directly from the terminal with images, overlays, layouts, and label maps pre-configured:
* Open single or multiple images: `vvv ct.nii.gz pet.nii.gz`
* Fuse an overlay with colormap: `vvv ct.nii.gz,pet.nii.gz:cmap=hot:opacity=0.6`
* Auto-arrange grid layouts, MIPs, or ROI masks on launch.

See [doc_03_command_line.md](doc_03_command_line.md) for the complete CLI syntax and reference.

---

## Help & Guidance in the Interface

At the bottom-left of the sidebar, two quick-access help buttons are always available:

* 🎓 **Beginner Mode** (Academic cap icon): Toggles interactive hover tooltips across buttons, sliders, and plugin controls. Enable this when learning the interface.
* ❓ **Shortcuts & Controls** (Question mark icon): Opens the full in-app reference window listing mouse bindings, keyboard shortcuts, MIP navigation, and CLI quick examples.


