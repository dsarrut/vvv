import numpy as np
import threading
from vvv.utils import ViewMode
from vvv.math.contours import ContourROI, extract_2d_contours_from_slice
from vvv.math.image import SliceRenderer


class ExtractionManager:
    """Core backend for progressive contour extraction and lazy evaluation."""

    def __init__(self, controller):
        self.controller = controller

    def _get_or_create_preview_roi(self, img_id, vs, color):
        """Retrieves or initializes the transient Draft ROI inside the ViewState."""
        roi = next(
            (c for c in vs.contours.values() if getattr(c, "is_draft", False)), None
        )

        if not roi:
            # Create with state thickness
            roi = ContourROI(
                name="Draft Preview",
                color=color,
                thickness=vs.extraction.preview_thickness,
            )
            roi.is_draft = True
            roi.last_computed_threshold = None
            roi.last_computed_subpixel = None
            self.controller.contours.add_contour(img_id, roi)
        else:
            # Update with state thickness
            roi.color = color
            roi.thickness = vs.extraction.preview_thickness
        return roi

    def clear_preview(self, img_id, vs):
        """Removes the draft ROI from the image's state."""
        roi = next(
            (c for c in vs.contours.values() if getattr(c, "is_draft", False)), None
        )
        if roi:
            self.controller.contours.remove_contour(img_id, roi.id)
            return True
        return False

    def update_preview(self, img_id, vol, vs, threshold_val, visible_targets, color):
        """The Lazy Engine: Computes missing slices on the fly."""
        roi = self._get_or_create_preview_roi(img_id, vs, color)

        # Clear draft if the slider OR the subpixel flag moved
        if (
            getattr(roi, "last_computed_threshold", None) != threshold_val
            or getattr(roi, "last_computed_subpixel", None)
            != vs.extraction.subpixel_accurate
        ):

            for ori in roi.polygons:
                roi.polygons[ori].clear()
            roi.last_computed_threshold = threshold_val
            roi.last_computed_subpixel = vs.extraction.subpixel_accurate

        extracted_any = False
        for ori, s_idx in visible_targets:
            if s_idx not in roi.polygons[ori]:
                sw, sh = vol.get_physical_aspect_ratio(ori)
                slice_data = SliceRenderer.get_raw_slice(vol.data, False, 0, s_idx, ori)

                if vs.extraction.subpixel_accurate:
                    # True Subpixel: Pass raw data and exact threshold
                    if np.any(slice_data >= threshold_val):
                        polys = extract_2d_contours_from_slice(
                            slice_data, threshold_val, sw, sh
                        )
                        roi.polygons[ori][s_idx] = polys
                    else:
                        roi.polygons[ori][s_idx] = []
                else:
                    # Voxel Aligned: Pre-binarize and pass 0.5 threshold
                    mask_2d = (slice_data >= threshold_val).astype(np.uint8)
                    if np.any(mask_2d):
                        polys = extract_2d_contours_from_slice(mask_2d, 0.5, sw, sh)
                        roi.polygons[ori][s_idx] = polys
                    else:
                        roi.polygons[ori][s_idx] = []

                extracted_any = True

        if extracted_any:
            self.controller.ui_needs_refresh = True
