import os
import sys
import json
import time
import numpy as np
import dearpygui.dearpygui as dpg
from PIL import Image

from vvv.core.controller import Controller
from vvv.ui.viewer import SliceViewer, ViewMode
from vvv.ui.gui import MainGUI


# Orientation mapping: user-facing names → internal ViewMode
_ORIENTATION_ALIASES = {
    "xy": ViewMode.AXIAL,
    "axial": ViewMode.AXIAL,
    "xz": ViewMode.CORONAL,
    "coronal": ViewMode.CORONAL,
    "yz": ViewMode.SAGITTAL,
    "sagittal": ViewMode.SAGITTAL,
}


def _resolve_orientation(name: str) -> ViewMode:
    """Resolve a user-facing orientation string to a ViewMode enum."""
    mode = _ORIENTATION_ALIASES.get(name.lower().strip())
    if mode is None:
        valid = ", ".join(sorted(_ORIENTATION_ALIASES.keys()))
        raise ValueError(f"Unknown orientation '{name}'. Valid values: {valid}")
    return mode


def vvv_screenshot(vvw_path: str, sc_json_path: str):
    """
    Loads VVV with a workspace and generates screenshots based on a JSON configuration.

    The workspace (.vvw) provides all rendering state: intensity window/level,
    colormaps, fusion overlays, ROI contours, etc.

    JSON format:
    {
      "defaults": {                        // optional shared defaults
        "image_id": "img_1",
        "fov_mm": [156, 148]
      },
      "screenshots": [
        {
          "position_mm": [x, y, z],        // required
          "orientation": "XY",             // required: XY, XZ, YZ, axial, coronal, sagittal
          "output": "my_screenshot.png",   // required
          "image_id": "img_1",             // optional (overrides defaults)
          "fov_mm": [w, h]                 // optional (overrides defaults)
        }
      ]
    }
    """
    # 1. Read and validate the JSON config
    if not os.path.exists(sc_json_path):
        raise FileNotFoundError(f"JSON configuration file not found: {sc_json_path}")
    with open(sc_json_path, "r") as f:
        config = json.load(f)

    defaults = config.get("defaults", {})
    screenshots = config.get("screenshots", [])
    if not screenshots:
        raise ValueError("JSON must contain a 'screenshots' list with at least one entry.")

    # Validate and merge defaults into each entry
    entries = []
    for i, entry in enumerate(screenshots):
        merged = {**defaults, **entry}  # entry values override defaults
        pos = merged.get("position_mm")
        if not pos or len(pos) != 3:
            raise ValueError(f"Screenshot [{i}]: 'position_mm' must be [x, y, z].")
        if "orientation" not in merged:
            raise ValueError(f"Screenshot [{i}]: 'orientation' is required.")
        if "output" not in merged:
            raise ValueError(f"Screenshot [{i}]: 'output' is required.")
        # Resolve orientation now to catch errors early
        merged["_orientation"] = _resolve_orientation(merged["orientation"])
        # Auto-append .png if missing
        if not merged["output"].lower().endswith(".png"):
            merged["output"] += ".png"
        entries.append(merged)

    # 2. Setup DPG context and VVV
    try:
        dpg.create_context()
    except Exception:
        pass

    controller = Controller()
    controller.use_history = False

    win_w = controller.settings.data["layout"]["window_width"]
    win_h = controller.settings.data["layout"]["window_height"]

    if not dpg.is_dearpygui_running() and not dpg.is_viewport_ok():
        try:
            dpg.create_viewport(title="VVV Screenshot Session", width=win_w, height=win_h)
            dpg.setup_dearpygui()
        except Exception:
            pass

    for tag in ["V1", "V2", "V3", "V4"]:
        controller.viewers[tag] = SliceViewer(tag, controller)

    gui = MainGUI(controller)
    controller.gui = gui

    if not dpg.does_item_exist("global_texture_registry"):
        with dpg.texture_registry(show=False, tag="global_texture_registry"):
            pass

    dpg.set_primary_window("PrimaryWindow", True)
    gui.on_window_resize()

    # 3. Load workspace — sets up everything:
    #    images, overlays, ROIs, viewer assignments, orientations, colormaps, window/level
    boot_gen = gui.load_workspace_sequence(vvw_path)
    if boot_gen:
        for _ in boot_gen:
            if dpg.is_viewport_ok():
                try:
                    dpg.render_dearpygui_frame()
                except Exception:
                    pass

    # Wait for background tasks (ROI loading, overlay resampling, etc.)
    while len(gui.tasks) > 0:
        try:
            next(gui.tasks[0])
        except StopIteration:
            gui.tasks.pop(0)
        if dpg.is_viewport_ok():
            try:
                dpg.render_dearpygui_frame()
            except Exception:
                pass

    # Stabilization frames
    for _ in range(20):
        if dpg.is_viewport_ok():
            try:
                dpg.render_dearpygui_frame()
            except Exception:
                pass
        time.sleep(0.02)

    # 4. Process each screenshot entry
    for entry in entries:
        _process_entry(controller, entry)

    # Clean up controller resources & background threads
    if hasattr(gui, "plugins") and gui.plugins:
        for plugin in gui.plugins:
            try:
                plugin.destroy()
            except Exception:
                pass
    if hasattr(controller, "destroy"):
        try:
            controller.destroy()
        except Exception:
            pass

    # Only destroy DPG context if not running inside a pytest test session
    if "pytest" not in sys.modules:
        try:
            dpg.stop_dearpygui()
        except Exception:
            pass
        from vvv.ui.ui_drop import cleanup_os_drop
        cleanup_os_drop()
        try:
            dpg.destroy_context()
        except Exception:
            pass


def _process_entry(controller, entry):
    """Process a single screenshot entry: set crosshair, render ALL viewers, capture one."""
    position_mm = entry["position_mm"]
    orientation = entry["_orientation"]
    output_path = entry["output"]
    image_id = entry.get("image_id")
    fov_mm = entry.get("fov_mm")

    # Resolve image_id
    target_vs_id = image_id
    if not target_vs_id or target_vs_id not in controller.view_states:
        if controller.view_states:
            target_vs_id = list(controller.view_states.keys())[0]

    if target_vs_id not in controller.view_states:
        print(f"Warning: No view state for image_id='{image_id}', skipping '{output_path}'.")
        return

    # Set crosshair on target image and propagate to all synced viewers
    vs = controller.view_states[target_vs_id]
    vs.update_crosshair_from_phys(position_mm)
    controller.sync.propagate_sync(target_vs_id)

    # Update ALL viewers — the full rendering pipeline (base + overlay + ROIs)
    # depends on all viewers being in sync. This replicates the exact flow that
    # produces correct output (base + fusion + ROIs).
    for tag in ["V1", "V2", "V3", "V4"]:
        viewer = controller.viewers[tag]
        if viewer.image_id and viewer.image_id in controller.view_states:
            viewer.set_current_slice_to_crosshair()
            viewer.center_on_physical_coord(position_mm)
            viewer.update_render(force_reblend=True)

    # No DPG GPU frame pass needed — CPU slice rendering pipeline update_render() is synchronous

    # Now find the viewer with the matching orientation and capture it
    viewer = None
    for tag in ["V1", "V2", "V3", "V4"]:
        v = controller.viewers[tag]
        if v.image_id == target_vs_id and v.orientation == orientation:
            viewer = v
            break

    if viewer is None:
        # No viewer with exact match — try any viewer with the target orientation
        for tag in ["V1", "V2", "V3", "V4"]:
            v = controller.viewers[tag]
            if v.orientation == orientation and v.image_id:
                viewer = v
                break

    if viewer is None:
        print(f"Warning: No viewer with orientation {orientation.name} for '{output_path}'.")
        return

    _capture_and_save(viewer, output_path, fov_mm)


def _capture_and_save(viewer, output_path, fov_mm):
    """Capture a viewer's rendered texture and save to a single PNG file."""

    if viewer.last_rgba_flat is None:
        print(f"Warning: No render data for '{output_path}', skipping.")
        return

    tex_h, tex_w = viewer.last_rgba_shape[0], viewer.last_rgba_shape[1]
    if len(viewer.last_rgba_flat) != tex_w * tex_h * 4:
        print(f"Warning: Texture mismatch for '{output_path}', skipping.")
        return

    # Base texture (includes base + ROIs; for non-Alpha modes also includes overlay)
    arr = np.array(viewer.last_rgba_flat, dtype=np.float32).reshape((tex_h, tex_w, 4))

    # For Alpha overlay mode: manually composite the separate overlay texture
    if viewer.last_overlay_rgba_flat is not None:
        vs = viewer.view_state
        if vs:
            ov_h, ov_w = viewer.last_overlay_rgba_shape
            if len(viewer.last_overlay_rgba_flat) == ov_w * ov_h * 4:
                ov_arr = np.array(viewer.last_overlay_rgba_flat, dtype=np.float32).reshape((ov_h, ov_w, 4))
                opacity = vs.display.overlay.opacity

                if ov_arr.shape[:2] != arr.shape[:2]:
                    ov_img = Image.fromarray((np.clip(ov_arr, 0, 1) * 255).astype(np.uint8), "RGBA")
                    resample = getattr(getattr(Image, "Resampling", Image), "NEAREST", getattr(Image, "NEAREST", None))
                    ov_img = ov_img.resize((tex_w, tex_h), resample)
                    ov_arr = np.array(ov_img, dtype=np.float32) / 255.0

                ov_alpha = ov_arr[:, :, 3:4] * opacity
                arr[:, :, :3] = arr[:, :, :3] * (1.0 - ov_alpha) + ov_arr[:, :, :3] * ov_alpha
                arr[:, :, 3] = np.maximum(arr[:, :, 3], ov_arr[:, :, 3] * opacity)

    # Spacing parameters
    spacing = viewer.volume.spacing  # [dx, dy, dz]
    _SPACING_MAP = {
        ViewMode.AXIAL:    (1, 0),  # row=dy, col=dx
        ViewMode.SAGITTAL: (2, 1),  # row=dz, col=dy
        ViewMode.CORONAL:  (2, 0),  # row=dz, col=dx
    }
    sp_idx = _SPACING_MAP.get(viewer.orientation)
    row_sp = abs(spacing[sp_idx[0]]) if sp_idx else 1.0
    col_sp = abs(spacing[sp_idx[1]]) if sp_idx else 1.0

    # FOV-based cropping
    if fov_mm and len(fov_mm) == 2 and viewer.volume:
        arr = _crop_to_fov(arr, viewer, fov_mm, tex_h, tex_w)
        # Update dimensions after crop
        tex_h, tex_w = arr.shape[0], arr.shape[1]
        phys_w_mm, phys_h_mm = fov_mm[0], fov_mm[1]
    else:
        phys_w_mm = tex_w * col_sp
        phys_h_mm = tex_h * row_sp

    # Resample the image to respect physical spacing (isotropic pixels)
    # We use the higher resolution (smaller spacing) as the pixel scale base
    target_sp = min(row_sp, col_sp)
    new_w = int(round(phys_w_mm / target_sp))
    new_h = int(round(phys_h_mm / target_sp))

    arr = np.clip(arr, 0.0, 1.0)
    arr = (arr * 255.0).astype(np.uint8)
    img = Image.fromarray(arr, "RGBA")

    # Rescale to final isotropic dimensions using bilinear filtering
    if (new_w, new_h) != (tex_w, tex_h) and new_w > 0 and new_h > 0:
        resample_mode = getattr(getattr(Image, "Resampling", Image), "BILINEAR", getattr(Image, "BILINEAR", None))
        img = img.resize((new_w, new_h), resample_mode)

    # Ensure output directory exists
    out_dir = os.path.dirname(output_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    img.save(output_path)
    print(f"Saved: {output_path}")


def _crop_to_fov(arr, viewer, fov_mm, tex_h, tex_w):
    """Crop the 2D slice array to a physical FOV centered on the crosshair."""
    spacing = viewer.volume.spacing  # [dx, dy, dz]

    # Texture axes → physical spacing index
    _SPACING_MAP = {
        ViewMode.AXIAL:    (1, 0),  # row=dy, col=dx
        ViewMode.SAGITTAL: (2, 1),  # row=dz, col=dy
        ViewMode.CORONAL:  (2, 0),  # row=dz, col=dx
    }
    sp_idx = _SPACING_MAP.get(viewer.orientation)
    if sp_idx is None:
        return arr

    row_sp = abs(spacing[sp_idx[0]])
    col_sp = abs(spacing[sp_idx[1]])

    fov_cols = int(round(fov_mm[0] / col_sp))
    fov_rows = int(round(fov_mm[1] / row_sp))

    vs = viewer.view_state
    if not vs or vs.camera.crosshair_phys_coord is None:
        return arr

    display_voxel = vs.world_to_display(
        vs.camera.crosshair_phys_coord,
        is_buffered=viewer._is_buffered()
    )
    if display_voxel is None:
        return arr

    cr, cc = _crosshair_tex_rc(display_voxel, viewer.orientation,
                                viewer._get_current_image_shape())
    if cr is None or cc is None:
        return arr

    cr, cc = int(round(cr)), int(round(cc))

    r0 = cr - fov_rows // 2
    r1 = r0 + fov_rows
    c0 = cc - fov_cols // 2
    c1 = c0 + fov_cols

    pad_top    = max(0, -r0)
    pad_bot    = max(0, r1 - tex_h)
    pad_left   = max(0, -c0)
    pad_right  = max(0, c1 - tex_w)

    r0c, r1c = max(0, r0), min(tex_h, r1)
    c0c, c1c = max(0, c0), min(tex_w, c1)

    cropped = np.zeros((fov_rows, fov_cols, 4), dtype=np.float32)
    cropped[pad_top:fov_rows - pad_bot, pad_left:fov_cols - pad_right] = arr[r0c:r1c, c0c:c1c]
    return cropped


def _crosshair_tex_rc(display_voxel, orientation, shape_3d):
    """
    Map 3D display-voxel → 2D texture (row, col).

    extract_slice flips:
      AXIAL:    data[t, z, Y, X]           → row=y, col=x
      SAGITTAL: data[t, Z::-1, Y::-1, x]   → row=(nz-1-z), col=(ny-1-y)
      CORONAL:  data[t, Z::-1, y, X]       → row=(nz-1-z), col=x
    """
    vx, vy, vz = display_voxel[0], display_voxel[1], display_voxel[2]
    nz, ny, nx = shape_3d

    if orientation == ViewMode.AXIAL:
        return vy, vx
    elif orientation == ViewMode.SAGITTAL:
        return (nz - 1 - vz), (ny - 1 - vy)
    elif orientation == ViewMode.CORONAL:
        return (nz - 1 - vz), vx
    return None, None
