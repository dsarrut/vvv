# How to Generate Programmatic Screenshots

VVV provides a built-in programmatic screenshot utility called `vvv_screenshot`. It loads a saved workspace (`.vvw`) and generates PNG screenshots of specific slices.

The workspace provides all rendering state: intensity window/level, colormaps, fusion overlays, ROI contours. The JSON configuration specifies *what* to capture.

---

## 1. Configuration JSON

Create a JSON file (e.g., `screenshot_config.json`):

```json
{
  "defaults": {
    "image_id": "img_1",
    "fov_mm": [156, 148]
  },
  "screenshots": [
    {
      "position_mm": [-24.6, 68.6, 1776.2],
      "orientation": "XY",
      "output": "patient_axial.png"
    },
    {
      "position_mm": [-24.6, 68.6, 1776.2],
      "orientation": "XZ",
      "output": "patient_coronal.png"
    },
    {
      "position_mm": [10.0, 5.0, 30.0],
      "orientation": "YZ",
      "fov_mm": [100, 100],
      "output": "lesion_sagittal.png"
    }
  ]
}
```

### `defaults` (optional)

Shared settings applied to every entry unless overridden. Avoids repeating the same values.

### Per-entry fields

| Field | Required | Description |
|---|---|---|
| `position_mm` | **Yes** | `[x, y, z]` — 3D physical position in mm |
| `orientation` | **Yes** | Slice plane (see table below) |
| `output` | **Yes** | Output PNG file path (`.png` auto-appended if missing) |
| `image_id` | No | Image to use. Defaults to first loaded image |
| `fov_mm` | No | `[width, height]` in mm. Full slice if omitted |

### Orientation values

| Value | Alias | Plane |
|---|---|---|
| `XY` | `axial` | Axial — looking along Z |
| `XZ` | `coronal` | Coronal — looking along Y |
| `YZ` | `sagittal` | Sagittal — looking along X |

All values are case-insensitive.

---

## 2. Usage

```python
from vvv import vvv_screenshot

vvv_screenshot("my_workspace.vvw", "screenshot_config.json")
```

Each entry in `screenshots` produces exactly **one** PNG file.

### What is preserved from the workspace:
- Intensity window/level and colormaps
- Fusion overlays (with blending mode and opacity)
- ROI contours and visibility

---

## 3. Example

An example using `rois_fusion.vvw` is in `data/`:

```bash
python3 data/test_screenshot_rois_fusion.py
```
