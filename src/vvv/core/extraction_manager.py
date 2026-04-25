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
        # Find existing draft in the image's own contours
        roi = next(
            (c for c in vs.contours.values() if getattr(c, "is_draft", False)), None
        )

        if not roi:
            roi = ContourROI(name="Draft Preview", color=color, thickness=2.0)
            roi.is_draft = True
            roi.last_computed_threshold = None
            # Add to the image's permanent dictionary via the manager
            self.controller.contours.add_contour(img_id, roi)
        else:
            roi.color = color
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
        """The Lazy Engine: Called by drawing.py to compute missing slices on the fly."""
        roi = self._get_or_create_preview_roi(img_id, vs, color)

        # Clear draft if the slider moved
        if getattr(roi, "last_computed_threshold", None) != threshold_val:
            for ori in roi.polygons:
                roi.polygons[ori].clear()
            roi.last_computed_threshold = threshold_val
            # Reset state counts
            vs.extraction.computed_counts = {
                k: 0 for k in vs.extraction.computed_counts
            }

        extracted_any = False
        for ori, s_idx in visible_targets:
            if s_idx not in roi.polygons[ori]:
                sw, sh = vol.get_physical_aspect_ratio(ori)
                slice_data = SliceRenderer.get_raw_slice(vol.data, False, 0, s_idx, ori)

                mask_2d = (slice_data >= threshold_val).astype(np.uint8)
                if np.any(mask_2d):
                    polys = extract_2d_contours_from_slice(mask_2d, sw, sh)
                    roi.polygons[ori][s_idx] = polys
                else:
                    roi.polygons[ori][s_idx] = []
                vs.extraction.computed_counts[ori] = len(roi.polygons[ori])
                extracted_any = True

        if extracted_any:
            self.controller.ui_needs_refresh = True

        return extracted_any

    def extract_full_volume(
        self, img_id, vol, vs, threshold_val, color, on_progress, on_complete, on_error
    ):
        """Hijacks the Draft ROI, completes the missing slices, and finalizes it."""

        # FIX: Find the draft ROI in the state, not a private dictionary
        draft_roi = next(
            (c for c in vs.contours.values() if getattr(c, "is_draft", False)), None
        )

        # If no draft exists or threshold changed, create/reset it
        if (
            not draft_roi
            or getattr(draft_roi, "last_computed_threshold", None) != threshold_val
        ):
            draft_roi = ContourROI(name="Processing...", color=color)
            draft_roi.is_draft = True
            draft_roi.last_computed_threshold = threshold_val
            draft_roi.id = self.controller.contours.add_contour(img_id, draft_roi)
            for ori in [ViewMode.AXIAL, ViewMode.CORONAL, ViewMode.SAGITTAL]:
                draft_roi.polygons[ori] = {}

        # Calculate how many slices are already done to adjust the progress bar
        initial_done = sum(
            len(vs.contours[draft_roi.id].polygons[o])
            for o in vs.extraction.computed_counts
        )

        def _background_extract():
            mask_3d = (vol.data >= threshold_val).astype(np.uint8)
            name_str = f"Iso [>= {threshold_val:g}]"

            if not np.any(mask_3d):
                self.controller.contours.remove_contour(img_id, draft_roi.id)
                on_error("Extraction Failed: Empty mask.")
                return

            shape = vol.shape3d
            ori_map = {
                ViewMode.AXIAL: shape[0],
                ViewMode.CORONAL: shape[1],
                ViewMode.SAGITTAL: shape[2],
            }

            total_slices = sum(ori_map.values())
            to_compute = total_slices - initial_done
            computed_now = 0

            for ori, max_slices in ori_map.items():
                sw, sh = vol.get_physical_aspect_ratio(ori)
                for s_idx in range(max_slices):
                    # PROGRESSIVE BAKE: Skip slices already computed during preview
                    if s_idx not in draft_roi.polygons[ori]:
                        slice_mask = SliceRenderer.get_raw_slice(
                            mask_3d, False, 0, s_idx, ori
                        )
                        if np.any(slice_mask):
                            polys = extract_2d_contours_from_slice(slice_mask, sw, sh)
                            draft_roi.polygons[ori][s_idx] = polys
                        else:
                            draft_roi.polygons[ori][s_idx] = []

                        computed_now += 1
                        # Progress bar reflects ONLY the remaining work
                        if computed_now % 10 == 0:
                            on_progress(computed_now, to_compute)

            # FINALIZE: Transition from Draft to permanent ROI
            draft_roi.name = name_str
            draft_roi.is_draft = False

            vs.is_geometry_dirty = True
            self.controller.update_all_viewers_of_image(img_id, data_dirty=False)
            on_complete(draft_roi.name)

        threading.Thread(target=_background_extract, daemon=True).start()
