import numpy as np
from vvv.utils import ViewMode
from vvv.math.image import SliceRenderer


class ContourROI:
    """Manages a set of 2D polygons representing an anatomical structure."""

    def __init__(self, name, color, thickness=1, linked_roi_id=None):
        self.id = None  # Will be assigned by the ContourManager
        self.linked_roi_id = linked_roi_id

        self.name = name
        self.color = color
        self.visible = True
        self.thickness = thickness

        self.polygons = {
            ViewMode.AXIAL: {},
            ViewMode.SAGITTAL: {},
            ViewMode.CORONAL: {},
        }


def extract_2d_contours_from_slice(slice2d, threshold, sw=1.0, sh=1.0):
    """
    Extracts 2D contours using marching squares.
    Accepts the exact threshold to allow for true sub-pixel linear interpolation.
    """
    try:
        from skimage import measure
    except ImportError:
        print("scikit-image is required for contour extraction...")
        return []

    # Pad the slice to ensure contours touching the image borders form closed loops
    pad_val = slice2d.min()
    if pad_val >= threshold:
        pad_val = threshold - 1.0  # Force a background value below the threshold

    padded_slice = np.pad(
        slice2d, pad_width=1, mode="constant", constant_values=pad_val
    )
    contours = measure.find_contours(padded_slice, threshold)

    if not contours:
        return []

    # Offset by -0.5 (-1.0 for the padding + 0.5 for OpenGL alignment)
    return [
        [[float((pt[1] - 0.5) * sw), float((pt[0] - 0.5) * sh)] for pt in contour]
        for contour in contours
    ]
