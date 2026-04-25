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

    # Use the REAL threshold provided by the manager
    contours = measure.find_contours(slice2d, threshold)

    if not contours:
        return []

    # Add 0.5 to align skimage pixel centers with OpenGL top-left edges
    return [
        [[float((pt[1] + 0.5) * sw), float((pt[0] + 0.5) * sh)] for pt in contour]
        for contour in contours
    ]


def extract_contours_from_mask(mask_3d, volume):
    """
    Extracts 2D contours for all slices in all orientations from a 3D binary mask.
    mask_3d: 3D numpy array (z, y, x)
    volume: VolumeData instance to get aspect ratios and slice shapes.
    Returns a populated ContourROI.
    """
    import random

    color = [
        random.randint(50, 255),
        random.randint(50, 255),
        random.randint(50, 255),
        255,
    ]
    roi = ContourROI(name="Auto_Contour", color=color)

    for orient in [ViewMode.AXIAL, ViewMode.SAGITTAL, ViewMode.CORONAL]:
        sw, sh = volume.get_physical_aspect_ratio(orient)

        if orient == ViewMode.AXIAL:
            max_slice = volume.shape3d[0]
        elif orient == ViewMode.SAGITTAL:
            max_slice = volume.shape3d[2]
        else:
            max_slice = volume.shape3d[1]

        for slice_idx in range(max_slice):
            slice2d = SliceRenderer.get_raw_slice(mask_3d, False, 0, slice_idx, orient)
            if slice2d is None or not np.any(slice2d):
                continue

            polygons = extract_2d_contours_from_slice(slice2d, sw, sh)
            if polygons:
                roi.polygons[orient][slice_idx] = polygons

    return roi
