import numpy as np
from vvv.utils import ViewMode
from vvv.math.image import SliceRenderer


class ContourROI:
    """Manages a set of 2D polygons representing an anatomical structure."""

    def __init__(self, name, color, thickness=1.5):
        self.name = name
        self.color = color
        self.visible = True
        self.thickness = thickness

        # Mapping: Orientation -> Slice Index -> List of Polygons
        # A Polygon is a list of 2D points [[x, y], [x, y], ...] in physical millimeters relative to the slice.
        self.polygons = {
            ViewMode.AXIAL: {},
            ViewMode.SAGITTAL: {},
            ViewMode.CORONAL: {},
        }


def extract_contours_from_mask(mask_3d, volume):
    """
    Extracts 2D contours for all slices in all orientations from a 3D binary mask.
    mask_3d: 3D numpy array (z, y, x)
    volume: VolumeData instance to get aspect ratios and slice shapes.
    Returns a populated ContourROI.
    """
    import random

    try:
        from skimage import measure
    except ImportError:
        print(
            "scikit-image is required for contour extraction. Install with: pip install scikit-image"
        )
        return ContourROI(name="Error", color=[255, 0, 0, 255])

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

            contours = measure.find_contours(slice2d, 0.5)
            if contours:
                roi.polygons[orient][slice_idx] = [
                    [[float(pt[1] * sw), float(pt[0] * sh)] for pt in contour]
                    for contour in contours
                ]

    return roi
