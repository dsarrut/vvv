import numpy as np
import threading
from vvv.utils import ViewMode
from vvv.maths.contours import ContourROI, extract_2d_contours_from_slice
from vvv.maths.image import SliceRenderer


class ExtractionManager:
    """Core backend for progressive contour extraction and lazy evaluation."""

    def __init__(self, controller):
        self.controller = controller

    def _get_or_create_preview_rois(self, img_id, vs):
        """Retrieves or initializes the transient Draft ROIs inside the ViewState."""
        roi_min = next(
            (c for c in vs.contours.values() if getattr(c, "is_draft_min", False)), None
        )
        if not roi_min:
            roi_min = ContourROI(
                name="Draft Min",
                color=vs.extraction.preview_color_min,
                thickness=vs.extraction.preview_thickness,
            )
            roi_min.is_draft_min = True
            roi_min.last_computed_threshold_min = None
            roi_min.last_computed_threshold_max = None
            roi_min.last_computed_subpixel = None
            self.controller.contours.add_contour(img_id, roi_min)
        else:
            roi_min.color = vs.extraction.preview_color_min
            roi_min.thickness = vs.extraction.preview_thickness

        roi_max = next(
            (c for c in vs.contours.values() if getattr(c, "is_draft_max", False)), None
        )
        if not roi_max:
            roi_max = ContourROI(
                name="Draft Max",
                color=vs.extraction.preview_color_max,
                thickness=vs.extraction.preview_thickness,
            )
            roi_max.is_draft_max = True
            roi_max.last_computed_threshold_min = None
            roi_max.last_computed_threshold_max = None
            roi_max.last_computed_subpixel = None
            self.controller.contours.add_contour(img_id, roi_max)
        else:
            roi_max.color = vs.extraction.preview_color_max
            roi_max.thickness = vs.extraction.preview_thickness

        return roi_min, roi_max

    def clear_preview(self, img_id, vs):
        """Removes the draft ROIs from the image's state."""
        roi_min = next(
            (c for c in vs.contours.values() if getattr(c, "is_draft_min", False)), None
        )
        roi_max = next(
            (c for c in vs.contours.values() if getattr(c, "is_draft_max", False)), None
        )
        cleared = False
        if roi_min:
            self.controller.contours.remove_contour(img_id, roi_min.id)
            cleared = True
        if roi_max:
            self.controller.contours.remove_contour(img_id, roi_max.id)
            cleared = True
        return cleared

    def update_preview(
        self, img_id, vol, vs, threshold_min, threshold_max, visible_targets
    ):
        """The Lazy Engine: Computes missing slices on the fly."""
        roi_min, roi_max = self._get_or_create_preview_rois(img_id, vs)

        # Clear draft if the slider OR the subpixel flag moved
        if (
            getattr(roi_min, "last_computed_threshold_min", None) != threshold_min
            or getattr(roi_min, "last_computed_threshold_max", None) != threshold_max
            or getattr(roi_min, "last_computed_subpixel", None)
            != vs.extraction.subpixel_accurate
        ):

            for ori in roi_min.polygons:
                roi_min.polygons[ori].clear()
            for ori in roi_max.polygons:
                roi_max.polygons[ori].clear()

            roi_min.last_computed_threshold_min = threshold_min
            roi_min.last_computed_threshold_max = threshold_max
            roi_min.last_computed_subpixel = vs.extraction.subpixel_accurate
            roi_max.last_computed_threshold_min = threshold_min
            roi_max.last_computed_threshold_max = threshold_max
            roi_max.last_computed_subpixel = vs.extraction.subpixel_accurate

        extracted_any = False
        for ori, s_idx in visible_targets:
            if s_idx not in roi_min.polygons[ori]:
                sw, sh = vol.get_physical_aspect_ratio(ori)
                slice_data = SliceRenderer.get_raw_slice(vol.data, False, 0, s_idx, ori)

                if vs.extraction.subpixel_accurate:
                    c_min = np.min(slice_data)
                    c_max = np.max(slice_data)

                    if c_min <= threshold_min <= c_max:
                        roi_min.polygons[ori][s_idx] = extract_2d_contours_from_slice(
                            slice_data, threshold_min, sw, sh
                        )
                    else:
                        roi_min.polygons[ori][s_idx] = []

                    if c_min <= threshold_max <= c_max:
                        roi_max.polygons[ori][s_idx] = extract_2d_contours_from_slice(
                            slice_data, threshold_max, sw, sh
                        )
                    else:
                        roi_max.polygons[ori][s_idx] = []

                else:
                    mask_min = (slice_data >= threshold_min).astype(np.uint8)
                    mask_max = (slice_data >= threshold_max).astype(np.uint8)

                    if np.any(mask_min):
                        roi_min.polygons[ori][s_idx] = extract_2d_contours_from_slice(
                            mask_min, 0.5, sw, sh
                        )
                    else:
                        roi_min.polygons[ori][s_idx] = []

                    if np.any(mask_max):
                        roi_max.polygons[ori][s_idx] = extract_2d_contours_from_slice(
                            mask_max, 0.5, sw, sh
                        )
                    else:
                        roi_max.polygons[ori][s_idx] = []

                extracted_any = True

        if extracted_any:
            self.controller.ui_needs_refresh = True

    def create_image(self, img_id, vol, vs):
        """Extracts the threshold settings into a pure, in-memory generated image."""

        def _extract():
            import SimpleITK as sitk
            from vvv.maths.image import VolumeData
            from vvv.core.view_state import ViewState

            self.controller.status_message = "Generating thresholded image..."
            self.controller.ui_needs_refresh = True

            try:
                # 1. Generate Masks
                mask_fg = (vol.data >= vs.extraction.threshold_min) & (
                    vol.data <= vs.extraction.threshold_max
                )
                mask_bg = ~mask_fg

                new_data = np.zeros_like(vol.data)

                if vs.extraction.gen_fg_mode == "Constant":
                    new_data[mask_fg] = vs.extraction.gen_fg_val
                else:
                    new_data[mask_fg] = vol.data[mask_fg]

                if vs.extraction.gen_bg_mode == "Constant":
                    new_data[mask_bg] = vs.extraction.gen_bg_val
                else:
                    new_data[mask_bg] = vol.data[mask_bg]

                # 2. Build the ITK Image
                new_img = sitk.GetImageFromArray(new_data)
                new_img.SetSpacing(vol.sitk_image.GetSpacing())
                new_img.SetOrigin(vol.sitk_image.GetOrigin())
                new_img.SetDirection(vol.sitk_image.GetDirection())

                # 3. Bypass Disk I/O to Create VolumeData
                new_vol = VolumeData.__new__(VolumeData)
                new_vol.path = vol.path
                new_vol.file_paths = list(vol.file_paths)
                new_vol.name = f"Thr: {vol.name}"
                new_vol.sitk_image = new_img
                new_vol.data = new_data
                new_vol.matrix_display_str = vol.matrix_display_str
                new_vol.matrix_tooltip_str = vol.matrix_tooltip_str
                new_vol.read_image_metadata()
                new_vol.last_mtime = 0
                new_vol._last_check_time = 0
                new_vol._is_outdated = False

                # 4. Build ViewState and Mount it!
                new_vs = ViewState(new_vol)
                new_vs.camera.from_dict(
                    vs.camera.to_dict()
                )  # Inherit zoom, pan, and slices!

                new_id = str(self.controller.next_image_id)
                self.controller.next_image_id += 1

                self.controller.volumes[new_id] = new_vol
                self.controller.view_states[new_id] = new_vs

                # Swap the active viewer over to the new image
                if self.controller.gui and self.controller.gui.context_viewer:
                    target_tag = self.controller.gui.context_viewer.tag
                    self.controller.layout[target_tag] = new_id

                self.controller.status_message = (
                    "Threshold image generated successfully"
                )
                self.controller.ui_needs_refresh = True

            except Exception as e:
                self.controller.status_message = f"Failed to generate image: {e}"
                self.controller.ui_needs_refresh = True

        threading.Thread(target=_extract, daemon=True).start()
