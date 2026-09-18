# Landmarks Plugin Developer Guide

The **Landmarks Plugin** (`src/vvv/plugins/landmark/`) allows users to place, manage, visualize, and persist 3D physical point landmarks across medical image volumes.

---

## 1. Features & User Interactions

* **Add Landmark**:
  * Shortcut **`Space`** or clicking **"+ Add Landmark"** creates a new landmark at the current physical 3D crosshair position.
* **Voxel Grid Snapping**:
  * Snaps the physical coordinates to the exact center of the nearest voxel (`snap_to_voxel_grid`).
* **Interactive List & Navigation**:
  * Displays landmark name, physical coordinates $(X, Y, Z)$ in mm, and customizable color.
  * **Jump to Landmark**: Clicking on a landmark in the list instantly repositions the crosshair and navigates viewers to the landmark's physical coordinate.
* **Visibility & Label Toggles**:
  * Individual and global visibility toggles (`visible`, `show_name`).
* **Import & Export**:
  * **CSV Export/Import**: Compatible with standard spreadsheet and landmark tools (columns: `ID`, `Name`, `X_mm`, `Y_mm`, `Z_mm`, `Color_R`, `Color_G`, `Color_B`, `Color_A`, `Visible`, `ShowName`).
  * **Workspace / Session Persistence**: Landmarks serialize automatically into `.vvw` workspace sessions.

---

## 2. File Structure

* **`plugin_landmark.py`**: Plugin lifecycle entry point implementing `PluginProtocol`.
* **`landmark_state.py`**: `Landmark` data model representing a single 3D physical point, with serialization (`to_dict`, `from_dict`, `to_csv_row`, `from_csv_row`) and voxel-grid snapping.
* **`ui_landmark.py`**: Dear PyGui widget construction for the sidebar panel, color pickers, and landmark tables.
* **`control_landmark.py`**: State management, keyboard bindings (`Space`), CSV parsing/saving, and physical coordinate navigation.
* **`test_landmark.py`**: Unit tests for landmark lifecycle, snapping, serialization, and coordinate navigation.

---

## 3. Data Model & Coordinate Systems

```python
class Landmark:
    id: str
    name: str
    pt_phys: list[float]      # [x, y, z] in physical world millimeters
    color: list[int]          # [R, G, B, A] (0-255)
    visible: bool
    show_name: bool
```

### Physical Millimeter Space
Landmarks are stored in **physical world coordinates** (`pt_phys`), NOT voxel indices. This ensures:
1. Landmarks remain anatomically valid regardless of slice orientation (Axial, Coronal, Sagittal).
2. Landmarks can be shared and visualized accurately across multi-modality images with differing voxel grids or resolutions.
3. Extrinsic registration transforms are applied dynamically when projecting landmarks into overlay viewports.

---

## 4. Rendering Pipeline

Landmarks are projected onto 2D viewport slices in `OverlayDrawer` (`src/vvv/ui/drawing.py`):
1. **Coordinate Projection**: Transforms `pt_phys` into the viewer's 2D canvas coordinates.
2. **Slice Proximity**: Checks if the landmark's out-of-plane physical distance to the current slice is within the visible slice thickness.
3. **Drawing**: Renders a circle or crosshair symbol with an optional text label in the landmark's assigned color.

