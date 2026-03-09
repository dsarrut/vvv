from enum import Enum, auto
import numpy as np


class ViewMode(Enum):
    AXIAL = auto()
    SAGITTAL = auto()
    CORONAL = auto()
    HISTOGRAM = auto()


def fmt(values, precision=3):
    # Round to max precision, then convert to string to remove trailing zeros
    return " ".join([f"{round(x, precision):g}" for x in values])


def slice_to_voxel(slice_x, slice_y, slice_idx, orientation, shape):
    """Converts 2D slice coordinates to a 3D voxel array [x, y, z]."""
    real_h, real_w = shape[0], shape[1]
    if orientation == ViewMode.AXIAL:
        return np.array([slice_x, slice_y, slice_idx])
    elif orientation == ViewMode.SAGITTAL:
        return np.array([slice_idx, real_w - slice_x, real_h - slice_y])
    elif orientation == ViewMode.CORONAL:
        return np.array([slice_x, slice_idx, real_h - slice_y])
    return np.array([0, 0, 0])


def voxel_to_slice(vx, vy, vz, orientation, shape):
    """Converts a 3D voxel [x, y, z] to 2D slice coordinates [x, y]."""
    real_h, real_w = shape[0], shape[1]
    if orientation == ViewMode.AXIAL:
        return vx, vy
    elif orientation == ViewMode.SAGITTAL:
        return real_w - vy, real_h - vz
    elif orientation == ViewMode.CORONAL:
        return vx, real_h - vz
    return 0, 0
