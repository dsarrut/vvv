import math
import random
import numpy as np
import threading
import dearpygui.dearpygui as dpg
from vvv.ui.ui_components import build_section_title
from vvv.utils import ViewMode


class ContoursUI:
    """Delegated UI handler for the Contours tab."""

    def __init__(self, gui, controller):
        self.gui = gui
        self.controller = controller

    @staticmethod
    def build_tab_contours(gui):
        cfg_c = gui.ui_cfg["colors"]
        with dpg.tab(label="Contours", tag="tab_contours"):
            dpg.add_spacer(height=5)
            build_section_title("Vector Engine", cfg_c["text_header"])

            dpg.add_checkbox(
                label="Show Contours",
                tag="check_show_contour",
                callback=gui.contours_ui.on_toggle_contour,
                default_value=True,
            )

            dpg.add_spacer(height=5)
            dpg.add_button(
                label="Add Random Contours",
                callback=gui.contours_ui.on_add_random_contours,
                width=-1,
            )

            dpg.add_spacer(height=10)
            build_section_title("Threshold Extraction", cfg_c["text_header"])

            with dpg.group(horizontal=True):
                dpg.add_text("Threshold:")
                dpg.add_drag_float(
                    tag="drag_contour_threshold", width=-1, default_value=0.0
                )

            dpg.add_spacer(height=5)
            dpg.add_button(
                label="Extract 3D Contours",
                callback=gui.contours_ui.on_extract_threshold_contours,
                width=-1,
            )

            # --- NEW: Progress UI Elements (Hidden by default) ---
            dpg.add_spacer(height=5)
            dpg.add_progress_bar(
                tag="progress_contour_extract", default_value=0.0, width=-1, show=False
            )
            dpg.add_text(
                "", tag="text_contour_progress", color=cfg_c["text_dim"], show=False
            )

    def refresh_contours_ui(self):
        viewer = self.gui.context_viewer
        has_image = (
            viewer is not None
            and getattr(viewer, "view_state", None) is not None
            and viewer.volume is not None
        )

        if dpg.does_item_exist("drag_contour_threshold"):
            dpg.configure_item("drag_contour_threshold", enabled=has_image)

            if has_image:
                dynamic_speed = max(0.1, viewer.view_state.display.ww * 0.005)
                dpg.configure_item("drag_contour_threshold", speed=dynamic_speed)

    def on_toggle_contour(self, sender, app_data, user_data):
        viewer = self.gui.context_viewer
        if viewer and viewer.view_state:
            viewer.view_state.camera.show_contour = app_data
            self.controller.ui_needs_refresh = True

    def on_add_random_contours(self, sender, app_data, user_data):
        viewer = self.gui.context_viewer
        if not viewer or not viewer.view_state or not viewer.volume:
            return

        vs = viewer.view_state
        vol = viewer.volume

        shape = vol.shape3d
        mask_3d = np.zeros(shape, dtype=np.uint8)

        cz = random.randint(shape[0] // 4, 3 * shape[0] // 4)
        cy = random.randint(shape[1] // 4, 3 * shape[1] // 4)
        cx = random.randint(shape[2] // 4, 3 * shape[2] // 4)
        r = random.randint(max(1, min(shape) // 10), max(2, min(shape) // 4))

        Z, Y, X = np.ogrid[: shape[0], : shape[1], : shape[2]]
        dist_sq = (Z - cz) ** 2 + (Y - cy) ** 2 + (X - cx) ** 2
        mask_3d[dist_sq <= r**2] = 1

        self.gui.show_status_message("Extracting 3D contours...")

        def _extract():
            from vvv.math.contours import extract_contours_from_mask

            roi = extract_contours_from_mask(mask_3d, vol)

            if roi.name == "Error":
                self.controller.status_message = (
                    "Extraction Failed: scikit-image missing!"
                )
                self.controller.ui_needs_refresh = True
                return

            roi.name = "Random Sphere"
            vs.contour_rois.append(roi)

            for v in self.controller.viewers.values():
                if v.image_id == viewer.image_id:
                    v.is_geometry_dirty = True
            self.controller.ui_needs_refresh = True
            self.controller.status_message = f"Added ContourROI: {roi.name}"

        threading.Thread(target=_extract, daemon=True).start()

    def on_extract_threshold_contours(self, sender, app_data, user_data):
        viewer = self.gui.context_viewer
        if not viewer or not viewer.view_state or not viewer.volume:
            return

        vs = viewer.view_state
        vol = viewer.volume
        threshold_val = dpg.get_value("drag_contour_threshold")

        mask_3d = (vol.data >= threshold_val).astype(np.uint8)
        if not np.any(mask_3d):
            self.gui.show_status_message(
                "Threshold resulted in empty mask.", color=[255, 100, 100]
            )
            return

        from vvv.math.contours import ContourROI, extract_2d_contours_from_slice
        from vvv.math.image import SliceRenderer

        roi = ContourROI(name=f"Thr: {threshold_val:g}", color=[255, 255, 0])

        for ori in [ViewMode.AXIAL, ViewMode.CORONAL, ViewMode.SAGITTAL]:
            if ori not in roi.polygons:
                roi.polygons[ori] = {}

        # --- PHASE 1: IMMEDIATE PASS (Visible Slices) ---
        visible_targets = []
        for v in self.controller.viewers.values():
            if v.image_id == viewer.image_id and v.is_image_orientation():
                visible_targets.append((v.orientation, v.slice_idx))

        for ori, s_idx in visible_targets:
            # FIX: Grab the physical aspect ratio to prevent offsets!
            sw, sh = vol.get_physical_aspect_ratio(ori)

            slice_mask = SliceRenderer.get_raw_slice(mask_3d, False, 0, s_idx, ori)

            if np.any(slice_mask):
                # FIX: Pass sw and sh into the extractor
                polys = extract_2d_contours_from_slice(slice_mask, sw, sh)
                roi.polygons[ori][s_idx] = polys

        vs.contour_rois.append(roi)
        for v in self.controller.viewers.values():
            if v.image_id == viewer.image_id:
                v.is_geometry_dirty = True

        self.controller.ui_needs_refresh = True
        self.gui.show_status_message(
            "Visible contours extracted. Processing background..."
        )

        # --- PHASE 2: BACKGROUND PASS ---
        shape = vol.shape3d
        ori_map = {
            ViewMode.AXIAL: shape[0],
            ViewMode.CORONAL: shape[1],
            ViewMode.SAGITTAL: shape[2],
        }

        total_slices = sum(ori_map.values())

        # Unhide the progress UI
        dpg.configure_item("progress_contour_extract", show=True, default_value=0.0)
        dpg.configure_item(
            "text_contour_progress", show=True, default_value="Starting extraction..."
        )

        def _background_extract():
            slices_processed = 0

            for ori, max_slices in ori_map.items():
                # FIX: Grab the physical aspect ratio for the background loop too!
                sw, sh = vol.get_physical_aspect_ratio(ori)

                for s_idx in range(max_slices):
                    if (ori, s_idx) in visible_targets:
                        slices_processed += 1
                        continue

                    slice_mask = SliceRenderer.get_raw_slice(
                        mask_3d, False, 0, s_idx, ori
                    )

                    if np.any(slice_mask):
                        # FIX: Pass sw and sh
                        polys = extract_2d_contours_from_slice(slice_mask, sw, sh)
                        roi.polygons[ori][s_idx] = polys

                    slices_processed += 1

                    # Update progress UI every 10 slices to avoid choking the DPG message queue
                    if slices_processed % 10 == 0:
                        dpg.set_value(
                            "progress_contour_extract", slices_processed / total_slices
                        )
                        dpg.set_value(
                            "text_contour_progress",
                            f"Processing: {slices_processed} / {total_slices}",
                        )

                        for v in self.controller.viewers.values():
                            if v.image_id == viewer.image_id:
                                v.is_geometry_dirty = True

            # Final cleanup
            for v in self.controller.viewers.values():
                if v.image_id == viewer.image_id:
                    v.is_geometry_dirty = True

            # Hide the progress UI when finished
            dpg.configure_item("progress_contour_extract", show=False)
            dpg.configure_item("text_contour_progress", show=False)

            self.controller.status_message = "Background contour extraction complete."
            self.controller.ui_needs_refresh = True

        threading.Thread(target=_background_extract, daemon=True).start()
