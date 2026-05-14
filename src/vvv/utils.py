from enum import Enum, auto
import numpy as np
import os
from pathlib import Path


class ViewMode(Enum):
    AXIAL = auto()
    SAGITTAL = auto()
    CORONAL = auto()
    HISTOGRAM = auto()


def fmt(values, precision=3):
    if np.isscalar(values) or isinstance(values, (int, float)):
        return f"{round(float(values), precision):g}"
    # If it's a 2D matrix (like the ITK direction matrix), flatten it first
    if isinstance(values, np.ndarray):
        values = values.flatten()
    # Round to max precision, then convert to string to remove trailing zeros
    return " ".join([f"{round(float(x), precision):g}" for x in values])


def format_pixel_value(val, vol, time_idx):
    """Format a pixel/voxel value as a human-readable string.

    Handles scalar, RGB, and DVF volumes. Returns '-' for None values.
    """
    if val is None:
        return "-"
    if getattr(vol, "is_rgb", False):
        return f"{val[0]:g} {val[1]:g} {val[2]:g}"
    if getattr(vol, "is_dvf", False):
        mag = np.linalg.norm(val)
        comps = [f"*{v:g}" if i == time_idx else f"{v:g}" for i, v in enumerate(val)]
        return f"[{' '.join(comps)}] L:{mag:g}"
    return f"{val:g}"


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


def get_relative_path(target_path, base_dir):
    """Converts an absolute path to a relative path based on the workspace directory."""
    try:
        return os.path.relpath(os.path.abspath(target_path), os.path.abspath(base_dir))
    except ValueError:
        # Fallback for Windows if files are on different drives
        return os.path.abspath(target_path)


def resolve_relative_path(rel_path, base_dir):
    """Converts a relative path back to an absolute path."""
    if os.path.isabs(rel_path):
        return rel_path
    return os.path.normpath(os.path.join(os.path.abspath(base_dir), rel_path))
