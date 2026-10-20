from enum import Enum, auto
import numpy as np
import os
import sys
from pathlib import Path


class ViewMode(Enum):
    AXIAL = auto()
    SAGITTAL = auto()
    CORONAL = auto()


class ProfileInteractionMode(Enum):
    IDLE = auto()
    MANIPULATING = auto()


class RoiInteractionMode(Enum):
    IDLE = auto()
    MANIPULATING = auto()


class LandmarkInteractionMode(Enum):
    IDLE = auto()
    MANIPULATING = auto()



def fmt(values, precision=3):
    if isinstance(values, (int, float, np.number)):
        return f"{round(float(values), precision):g}"
    # If it's a 2D matrix (like the ITK direction matrix), flatten it first
    if isinstance(values, np.ndarray):
        items = values.flatten()
    else:
        items = values
    # Round to max precision, then convert to string to remove trailing zeros
    return " ".join([f"{round(float(x), precision):g}" for x in items])


def compute_adaptive_step_and_speed(ww, default_ww=1.0):
    """Computes (step_size, drag_speed, dpg_format) adapted to the intensity range (window width).

    Ensures that for large intensity ranges (e.g. CT: 400 HU), standard ranges (e.g. MRI: 1000),
    and very small ranges (e.g. Dose maps: 0.05 Gy or 2 Gy), the + / - buttons, drag speed,
    and number formatting scale seamlessly without coarse jumps or precision loss.
    """
    try:
        val = float(ww) if ww is not None else float(default_ww)
        if not np.isfinite(val) or val <= 0:
            safe_ww = float(default_ww)
        else:
            safe_ww = val
    except (TypeError, ValueError):
        safe_ww = float(default_ww)

    safe_ww = max(1e-12, safe_ww)
    step_size = safe_ww * 0.02
    drag_speed = safe_ww * 0.005

    if safe_ww >= 100.0:
        dpg_format = "%.1f"
    elif safe_ww >= 10.0:
        dpg_format = "%.2f"
    elif safe_ww >= 1.0:
        dpg_format = "%.3f"
    elif safe_ww >= 0.01:
        dpg_format = "%.4f"
    elif safe_ww >= 0.0001:
        dpg_format = "%.6f"
    else:
        dpg_format = "%.4e"

    return step_size, drag_speed, dpg_format


def format_pixel_value(val, vol, time_idx, dvf_precision=2):
    """Format a pixel/voxel value as a human-readable string.

    Handles scalar, RGB, and DVF volumes. Returns '-' for None values.
    """
    if val is None:
        return "-"
    sf = getattr(vol, "scale_factor", 1.0)
    if not isinstance(sf, (int, float)) or sf == 0.0 or np.isnan(sf):
        sf = 1.0
    if getattr(vol, "is_rgb", False):
        if sf != 1.0:
            return f"{val[0]*sf:g} {val[1]*sf:g} {val[2]*sf:g}"
        return f"{val[0]:g} {val[1]:g} {val[2]:g}"
    if getattr(vol, "is_dvf", False):
        mag = np.linalg.norm(val) * sf
        comps = [
            f"*{v*sf:.{dvf_precision}f}" if i == time_idx else f"{v*sf:.{dvf_precision}f}"
            for i, v in enumerate(val)
        ]
        return f"[{' '.join(comps)}] L:{mag:.{dvf_precision}f}"
    return f"{val * sf:g}"


def slice_to_voxel(slice_x, slice_y, slice_idx, orientation, shape):
    """Converts 2D screen coordinates [0, W] to 3D ITK continuous voxel array [-0.5, W-0.5]."""
    real_h, real_w = shape[0], shape[1]
    cx, cy = slice_x - 0.5, slice_y - 0.5

    if orientation == ViewMode.AXIAL:
        return np.array([cx, cy, float(slice_idx)])
    elif orientation == ViewMode.SAGITTAL:
        return np.array(
            [float(slice_idx), real_w - slice_x - 0.5, real_h - slice_y - 0.5]
        )
    elif orientation == ViewMode.CORONAL:
        return np.array([cx, float(slice_idx), real_h - slice_y - 0.5])
    return np.array([0.0, 0.0, 0.0])


def voxel_to_slice(vx, vy, vz, orientation, shape):
    """Converts 3D continuous voxel [-0.5, W-0.5] to 2D screen coordinates [0, W]."""
    real_h, real_w = shape[0], shape[1]
    if orientation == ViewMode.AXIAL:
        return vx + 0.5, vy + 0.5
    elif orientation == ViewMode.SAGITTAL:
        return real_w - vy - 0.5, real_h - vz - 0.5
    elif orientation == ViewMode.CORONAL:
        return vx + 0.5, real_h - vz - 0.5
    return 0.0, 0.0


def get_history_path_key(file_path):
    """Converts absolute path to ~/ path if it's inside the user's home directory."""
    abs_path = Path(file_path).resolve()
    home = Path.home().resolve()
    try:
        rel_path = abs_path.relative_to(home)
        return "~/" + str(rel_path.as_posix())
    except ValueError:
        return str(abs_path.as_posix())


def resolve_history_path_key(key):
    """Expands ~/ back to absolute path."""
    if key.startswith("~/"):
        return str((Path.home() / key[2:]).resolve())
    return str(Path(key).resolve())


def clean_string(val) -> str:
    """Sanitizes strings from DICOM or external headers by stripping null bytes and surrogate escapes."""
    if val is None:
        return ""
    try:
        val_str = str(val).replace("\x00", "")
        val_str = "".join(c for c in val_str if not (0xD800 <= ord(c) <= 0xDFFF))
        return val_str.encode("utf-8", "ignore").decode("utf-8")
    except Exception:
        return "Unknown"


def write_json_atomic(path, data, indent=4):
    """Write JSON so that `path` always holds either the old or the new content.

    The data goes to a temporary file in the same folder, which then replaces
    `path` (os.replace is atomic). A crash, or an error while serialising, can
    no longer leave a truncated settings / history / workspace file behind.
    """
    import json
    import tempfile

    path = os.fspath(path)
    fd, tmp = tempfile.mkstemp(
        dir=os.path.dirname(os.path.abspath(path)), prefix=".tmp_", suffix=".json"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=indent)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def get_config_dir() -> Path:
    """Gets the user configuration directory in a cross-platform way."""
    if "PYTEST_CURRENT_TEST" in os.environ:
        workspace_test_config = Path(__file__).resolve().parent.parent.parent / ".pytest_config"
        workspace_test_config.mkdir(exist_ok=True)
        return workspace_test_config

    appdata = os.getenv("APPDATA")
    if os.name == "nt" and appdata:
        return Path(appdata) / "VVV"
    return Path.home() / ".config" / "vvv"


def get_resource_path(rel_path):
    """Get absolute path to resource, works for dev and for PyInstaller/cx_Freeze"""
    # PyInstaller creates a temp folder and stores path in _MEIPASS
    base_path = getattr(sys, "_MEIPASS", os.path.abspath(os.path.dirname(__file__)))
    return os.path.join(base_path, rel_path)
