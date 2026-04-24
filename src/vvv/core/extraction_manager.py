import numpy as np
import threading
from vvv.utils import ViewMode
from vvv.math.contours import ContourROI, extract_2d_contours_from_slice
from vvv.math.image import SliceRenderer


class ExtractionManager:
    """Core backend for contour extraction, caching, and background processing."""

    def __init__(self, controller):
        self.controller = controller
        # Smart Cache State
        self._preview_rois = {}
        self._last_threshold = None

    def _get_or_create_preview_roi(self, image_id, vs, color):
        """Retrieves or initializes the transient Live Preview ROI."""
        if image_id not in self._preview_rois:
            roi = ContourROI(name="Live Preview", color=color, thickness=2.0)
            self._preview_rois[image_id] = roi
            vs.contour_rois.append(roi)
        else:
            self._preview_rois[image_id].color = color
        return self._preview_rois[image_id]

    def clear_preview(self, image_id, vs):
        """Wipes the preview memory and polygons from the screen."""
        if image_id in self._preview_rois:
            roi = self._preview_rois[image_id]
            roi.polygons = {
                ViewMode.AXIAL: {},
                ViewMode.SAGITTAL: {},
                ViewMode.CORONAL: {},
            }
            self._last_threshold = None
            return True
        return False

    def update_preview(
        self, img_id, vol, vs, threshold_val, visible_targets, color, clear_cache=False
    ):
        """The Smart Engine: Extracts only the missing slices for the preview."""
        roi = self._get_or_create_preview_roi(img_id, vs, color)

        # Clear cache if slider moved
        if clear_cache or self._last_threshold != threshold_val:
            for ori in roi.polygons:
                roi.polygons[ori].clear()
            self._last_threshold = threshold_val

        extracted_any = False

        # Only process slices that aren't already in the dictionary
        for ori, s_idx in visible_targets:
            if s_idx not in roi.polygons[ori]:
                sw, sh = vol.get_physical_aspect_ratio(ori)
                slice_data = SliceRenderer.get_raw_slice(vol.data, False, 0, s_idx, ori)

                mask_2d = (slice_data >= threshold_val).astype(np.uint8)
                if np.any(mask_2d):
                    polys = extract_2d_contours_from_slice(mask_2d, sw, sh)
                    roi.polygons[ori][s_idx] = polys
                else:
                    roi.polygons[ori][s_idx] = []  # Cache empty state

                extracted_any = True

        return extracted_any

    def extract_full_volume(
        self, img_id, vol, vs, threshold_val, color, on_progress, on_complete, on_error
    ):
        """Spawns a background thread for full 3D extraction and reports back via callbacks."""

        def _background_extract():
            mask_3d = (vol.data >= threshold_val).astype(np.uint8)
            name_str = f"Iso [>= {threshold_val:g}]"

            if not np.any(mask_3d):
                on_error("Extraction Failed: Empty mask.")
                return

            baked_roi = ContourROI(name=name_str, color=color)
            for ori in [ViewMode.AXIAL, ViewMode.CORONAL, ViewMode.SAGITTAL]:
                baked_roi.polygons[ori] = {}

            shape = vol.shape3d
            ori_map = {
                ViewMode.AXIAL: shape[0],
                ViewMode.CORONAL: shape[1],
                ViewMode.SAGITTAL: shape[2],
            }

            total_slices = sum(ori_map.values())
            slices_processed = 0

            for ori, max_slices in ori_map.items():
                sw, sh = vol.get_physical_aspect_ratio(ori)
                for s_idx in range(max_slices):
                    slice_mask = SliceRenderer.get_raw_slice(
                        mask_3d, False, 0, s_idx, ori
                    )

                    if np.any(slice_mask):
                        polys = extract_2d_contours_from_slice(slice_mask, sw, sh)
                        baked_roi.polygons[ori][s_idx] = polys

                    slices_processed += 1

                    # Ping the UI safely through the callback
                    if slices_processed % 10 == 0:
                        on_progress(slices_processed, total_slices)

            # Finalize
            vs.contour_rois.append(baked_roi)
            on_complete(baked_roi.name)

        # Start thread
        threading.Thread(target=_background_extract, daemon=True).start()
