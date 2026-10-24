# Getting Started & Concepts

**VVV** is a lightweight, fast viewer for 2D, 3D and 4D medical images and scientific volumes (CT, MRI, PET, SPECT, radiation dose, DVF vector fields, label maps).

---

## Core Concepts

### 1. Viewers vs. Images
* **Images (Volumes)**: the images loaded in memory; you can load many at once. Each gets a number, shown as `(1)`, `(2)` ... before its name: it never changes while the image is open.
* **Viewers**: the display panes, in a layout of **1**, **2** (side by side) or **4** viewers (layout icons at the right of the menu bar).
* **Active Viewer**: the viewer you clicked last (highlighted border); the side panels show its image. Keyboard shortcuts and the mouse wheel act on the viewer under the mouse, or on the active viewer when the mouse is elsewhere.
* **Base Image vs. Overlay**:
  * Each viewer displays one **Base Image**.
  * A second image can be fused on top as an **Overlay** (e.g. PET on CT, dose on CT, or a registered follow-up MRI).

### 2. Coordinate Spaces
* **Physical Space (mm)**: real-world millimeter coordinates. Synchronization, the crosshair and registration work in physical space, whatever the resolution, voxel size or orientation of the images.
* **Voxel Space**: the integer grid indices `(i, j, k)`.

### 3. Synchronization
* Images can be linked: moving the crosshair, panning / zooming, changing Window/Level or the 4D frame in one viewer updates the linked ones (see [Synchronization](doc_05_synchronisation.md)).

---

## Interface Layout

* **Menu bar** (top): the **File**, **Workspace** and **System** menus; the status messages and the path of the active image; at the right, the screenshot and layout icons.
* **Viewers** (main area): 2D slices (Axial, Coronal, Sagittal), or a MIP projection.
* **Nav column** (left): one button per tool: **Images**, **Sync**, **Fusion**, then **Intensity**, **ROIs**, **Threshold**, **Profiles**, **Landmarks**, **Transform**, **MIP**, **DVF**, **Dose**, ... The button of a tool that does not apply to the current image (e.g. Dose without a dose image) is muted, but still opens its panel. Below: the **Workspace** icons (open, save, save as, reload) and, at the bottom, **Settings**, **Beginner mode** and **Help**.
* **Side panels** (next to the nav column): the panel of the selected tool, then the **Active Viewer** panel (the image metadata and display options) and the **Crosshair** panel (position, voxel value). Click the title of the Active Viewer or Crosshair panel (or its arrow) to fold it, leaving more room for the tool panel; the Crosshair panel folds by itself when the window is less than 800 px high, and unfolds when it grows back. Some tools (ROIs, Transform, Dose, Intensity) hide the Active Viewer panel to get more room.

The first time, the window opens at 85 % of the screen; then it keeps its last size.

---

## Essential Controls

### Mouse

| Action | Mouse |
| :--- | :--- |
| **Move the crosshair** | **Left click** on the image |
| **Change slice** | **Mouse wheel** |
| **Zoom** | <kbd>Ctrl</kbd> (<kbd>Cmd</kbd> on macOS) + **wheel** |
| **Pan** | <kbd>Ctrl</kbd> (<kbd>Cmd</kbd>) + **left drag**, or **middle drag** |
| **Window / Level** | **Right drag**, or <kbd>Shift</kbd> + **mouse move** (horizontal: window, vertical: level) |

### Keyboard

| Key | Action |
| :--- | :--- |
| <kbd>F1</kbd> / <kbd>F2</kbd> / <kbd>F3</kbd> | Axial / Sagittal / Coronal view |
| <kbd>↑</kbd> / <kbd>↓</kbd>, <kbd>Page Up</kbd> / <kbd>Page Down</kbd> | Previous / next slice, fast |
| <kbd>←</kbd> / <kbd>→</kbd> | Previous / next frame of a 4D image |
| <kbd>I</kbd> / <kbd>O</kbd> | Zoom in / out |
| <kbd>R</kbd> / <kbd>Shift</kbd>+<kbd>R</kbd> | Reset zoom & pan / also reset Window/Level and the defaults |
| <kbd>C</kbd> | Center the view on the crosshair |
| <kbd>W</kbd> / <kbd>X</kbd> | Auto Window/Level of the base image / of the overlay |
| <kbd>N</kbd> | Next image of the list in the viewer |
| <kbd>S</kbd> / <kbd>Shift</kbd>+<kbd>S</kbd> | Link (or unlink) all images, spatially / for Window/Level |
| <kbd>K</kbd> | Pixelated zoom (nearest neighbor) on / off |
| <kbd>L</kbd> / <kbd>G</kbd> / <kbd>A</kbd> / <kbd>B</kbd> | Color legend / voxel grid / axis guide / scalebar |
| <kbd>H</kbd> | Hide / show the annotations (crosshair, axis, scalebar, file name, profiles, contours) |
| <kbd>M</kbd> | MIP on / off |
| <kbd>P</kbd> | Add a profile line |
| <kbd>Space</kbd> | Add a landmark at the crosshair |
| <kbd>Ctrl</kbd> (<kbd>Cmd</kbd>) + <kbd>O</kbd> | Open image(s) |

The keys can be changed in **Settings**. The **Help** window lists them as they are set.

---

## Command-Line Interface (CLI)

VVV is usually launched from a terminal, with its images:
* Open several images: `vvv ct.nii.gz pet.nii.gz`
* Fuse an overlay, with a colormap and an opacity: `vvv ct.nii.gz,pet.nii.gz,hot,0.6`
* Open a workspace: `vvv session.vvw`

See [doc_03_command_line.md](doc_03_command_line.md) for the complete syntax.

---

## Help & Guidance in the Interface

At the bottom of the nav column:

![Help and Beginner Mode Buttons (OFF on left, ON in reverse video on right)](images/doc_01_help_buttons_states.png)

* ⚙ **Settings**: all the preferences (colors, shortcuts, behavior, ...).
* 👶 **Beginner Mode**: shows help tooltips and help buttons (`?`) on the controls. Shown in reverse video (white background) when on.
* ❓ **Help**: the reference window: mouse controls, keyboard shortcuts (as set), MIP keys and command-line examples.
