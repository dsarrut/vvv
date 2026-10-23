# Workspaces, Export & Screenshots

VVV allows saving and restoring complete multi-viewer visualization sessions using lightweight Workspace files (`.vvw`), as well as high-resolution image exports and automated screenshots.

![Workspace Interface](images/doc_04_workspace_layout.png)

---

## VVV Workspaces (`.vvw`)

A workspace file stores the entire state of your session in a clean, human-readable JSON format:
* **Loaded Datasets**: Base image paths, overlays, and ROI masks.
* **Viewer Configurations**: Multi-viewer layout (1, 2, 3, or 4 panels), assigned images, slice orientations (Axial, Coronal, Sagittal), zoom, and pan.
* **Synchronization Links**: Active synchronized viewer groups.
* **Radiometry & Visualization**: Window/Level settings, colormaps, opacity, and threshold bounds.
* **Analysis States**: Active landmarks and line profiles. Registration transforms are not stored: a transform saved next to its image (`ct.tfm`, a [side-car file](doc_17_side_car_files.md)) is applied again when the workspace is opened.

### Saving & Loading
* **Save Workspace**: In the **Images** or **File** menu, click **Save Workspace** (or press <kbd>Ctrl + S</kbd> / <kbd>Cmd + S</kbd>).
* **Load Workspace**: Open a `.vvw` file from the GUI or launch directly from the terminal:
  ```bash
  vvv data/dose.vvw
  ```
* **Dynamic Label Maps on Disk**: When a workspace referencing a multi-label segmentation map is reopened, VVV reads the actual label map image file currently on disk as the source of truth:
  * Any labels present in the file on disk are loaded.
  * Preferences saved in the workspace (custom names, colors, contours, visibility, and opacity) are reapplied to matching labels.
  * Labels removed from the file on disk since the workspace was saved are not loaded (preventing phantom or empty masks).
  * Newly added labels in the file on disk are automatically loaded with default colors and naming.

---

## Exporting High-Resolution Screenshots

VVV provides flexible tools for exporting clean, publication-ready figures:

### 1. Interactive Screenshot
* Click the **Screenshot** icon (camera icon in the top bar) or use the screenshot menu.
* **macOS & Windows**: Automatically copied directly to your system clipboard ready to paste into documents or presentation slides.
* **Linux**:
  * Copying directly to the clipboard uses `xclip` (on X11) or `wl-clipboard` (`wl-copy` on Wayland). These system utilities cannot be installed via `pip`:
    ```bash
    sudo apt install xclip         # X11
    sudo apt install wl-clipboard  # Wayland
    ```
  * If neither utility is installed, VVV gracefully falls back to automatically saving the captured image to `~/Pictures/vvv_screenshot_<timestamp>.png` (or `~/vvv_screenshot_<timestamp>.png`).

### 2. Automated Headless Screenshots via CLI
You can generate batch figures directly from scripts or CI pipelines without displaying an interactive window:
```bash
vvv --screenshot my_session.vvw --output figure1.png
```


---

## Shortcuts Summary

| Action | Shortcut |
| :--- | :--- |
| **Save Workspace** | <kbd>Ctrl + S</kbd> / <kbd>Cmd + S</kbd> |
| **Capture Screenshot** | <kbd>F12</kbd> |
| **Toggle Fullscreen Viewport** | <kbd>F11</kbd> |
| **Reset View / Zoom** | <kbd>Space</kbd> |

