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

    def refresh_contours_ui(self):
        viewer = self.gui.context_viewer
        has_image = (
            viewer is not None
            and getattr(viewer, "view_state", None) is not None
            and viewer.volume is not None
        )

        if dpg.does_item_exist("drag_contour_threshold"):
            dpg.configure_item("drag_contour_threshold", enabled=has_image)

            # Dynamically scale the slider drag speed based on the current window width
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

        # 1. Create a 3D binary mask with a random sphere
        shape = vol.shape3d  # (z, y, x)
        mask_3d = np.zeros(shape, dtype=np.uint8)

        # Center and radius
        cz = random.randint(shape[0] // 4, 3 * shape[0] // 4)
        cy = random.randint(shape[1] // 4, 3 * shape[1] // 4)
        cx = random.randint(shape[2] // 4, 3 * shape[2] // 4)
        r = random.randint(max(1, min(shape) // 10), max(2, min(shape) // 4))

        # Draw sphere
        Z, Y, X = np.ogrid[: shape[0], : shape[1], : shape[2]]
        dist_sq = (Z - cz) ** 2 + (Y - cy) ** 2 + (X - cx) ** 2
        mask_3d[dist_sq <= r**2] = 1

        # 2. Extract contours in a background thread
        self.gui.show_status_message("Extracting 3D contours...")

        def _extract():
            from vvv.math.contours import extract_contours_from_mask

            roi = extract_contours_from_mask(mask_3d, vol)

            if roi.name == "Error":
                self.controller.status_message = (
                    "Extraction Failed: scikit-image is missing!"
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

        self.gui.show_status_message(f"Thresholding at {threshold_val:g}...")

        def _extract():
            # 1. Create the binary mask by evaluating the numpy array against the threshold
            mask_3d = (vol.data >= threshold_val).astype(np.uint8)

            # Check if mask is completely empty before passing to the extractor
            if not np.any(mask_3d):
                self.controller.status_message = (
                    "Extraction Failed: Threshold resulted in empty mask."
                )
                self.controller.ui_needs_refresh = True
                return

            self.controller.status_message = "Extracting contours..."

            # 2. Extract contours
            from vvv.math.contours import extract_contours_from_mask

            roi = extract_contours_from_mask(mask_3d, vol)

            if roi.name == "Error":
                self.controller.status_message = (
                    "Extraction Failed: scikit-image is missing!"
                )
                self.controller.ui_needs_refresh = True
                return

            # Give it a procedural name based on the threshold
            roi.name = f"Thr: {threshold_val:g}"
            vs.contour_rois.append(roi)

            # Trigger a redraw on all viewers currently looking at this image
            for v in self.controller.viewers.values():
                if v.image_id == viewer.image_id:
                    v.is_geometry_dirty = True

            self.controller.ui_needs_refresh = True
            self.controller.status_message = f"Added ContourROI: {roi.name}"

        threading.Thread(target=_extract, daemon=True).start()
