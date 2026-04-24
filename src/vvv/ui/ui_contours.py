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
            )

    def refresh_contours_ui(self):
        # State is entirely controlled via `gui.bindings` and `gui.update_sidebar_info`
        pass

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

            vs.contour_rois.append(roi)

            for v in self.controller.viewers.values():
                if v.image_id == viewer.image_id:
                    v.is_geometry_dirty = True
            self.controller.ui_needs_refresh = True
            self.controller.status_message = f"Added ContourROI: {roi.name}"

        threading.Thread(target=_extract, daemon=True).start()
