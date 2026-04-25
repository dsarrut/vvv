import numpy as np
import dearpygui.dearpygui as dpg
from vvv.ui.ui_components import build_section_title, build_stepped_slider
from vvv.core.view_state import ViewMode


class ExtractionUI:
    """Handles the Interactive Thresholding UI elements and user input."""

    def __init__(self, gui, controller):
        self.gui = gui
        self.controller = controller
        self._current_image_id = None

    def build_tab_extraction(self, gui):
        cfg_c = gui.ui_cfg["colors"]

        with dpg.tab(label="Extract", tag="tab_extraction"):
            dpg.add_spacer(height=5)
            build_section_title("Interactive Threshold", cfg_c["text_header"])

            dpg.add_checkbox(
                label="Enable Thresholding",
                tag="check_ext_enable",
                callback=self.on_enable_toggle,
            )
            dpg.add_spacer(height=5)

            build_stepped_slider(
                "Threshold:",
                "drag_ext_threshold",
                callback=self.on_threshold_drag,
                step_callback=self.on_step_button_clicked,
                min_val=-100000.0,
                max_val=100000.0,
            )

            dpg.add_spacer(height=5)

            with dpg.group(horizontal=True):
                dpg.add_checkbox(
                    label="Live Preview",
                    tag="check_ext_preview",
                    callback=self.on_threshold_drag,
                )

                dpg.add_checkbox(
                    label="Sub-Pixel",
                    tag="check_ext_subpixel",
                    callback=self.on_threshold_drag,
                )

                dpg.add_color_edit(
                    (255, 255, 0, 255),
                    tag="color_ext_preview",
                    no_inputs=True,
                    no_label=True,
                    no_alpha=True,
                    width=20,
                    height=20,
                    callback=self.on_threshold_drag,
                )

            # --- NEW: Thickness Slider ---
            dpg.add_spacer(height=5)
            with dpg.group(horizontal=True):
                dpg.add_text("Thickness:")
                dpg.add_slider_float(
                    tag="drag_ext_thickness",
                    width=-1,
                    min_value=0.5,
                    max_value=10.0,
                    default_value=2.0,
                    callback=self.on_threshold_drag,
                )

    def refresh_extraction_ui(self):
        viewer = self.gui.context_viewer
        has_image = (
            viewer is not None
            and getattr(viewer, "view_state", None) is not None
            and getattr(viewer.view_state, "extraction", None) is not None
            and viewer.volume is not None
        )

        if not has_image:
            tags_to_disable = [
                "check_ext_enable",
                "drag_ext_threshold",
                "check_ext_preview",
                "color_ext_preview",
                "check_ext_subpixel",
                "drag_ext_thickness",
            ]
            for tag in tags_to_disable:
                if dpg.does_item_exist(tag):
                    dpg.configure_item(tag, enabled=False)

            self._current_image_id = None
            return

        vol = viewer.volume
        ext_state = viewer.view_state.extraction
        img_id = viewer.image_id

        # Constraints
        current_data_id = id(vol.data)
        if (
            not hasattr(vol, "_cached_min_val")
            or getattr(vol, "_cached_data_id", None) != current_data_id
        ):
            vol._cached_min_val = float(np.min(vol.data))
            vol._cached_max_val = float(np.max(vol.data))
            vol._cached_data_id = current_data_id

        safe_min = min(0.0, vol._cached_min_val)
        dpg.configure_item(
            "drag_ext_threshold", min_value=safe_min, max_value=vol._cached_max_val
        )
        dpg.configure_item(
            "drag_ext_threshold", speed=max(0.1, viewer.view_state.display.ww * 0.005)
        )

        # Context Switch Snap
        if self._current_image_id != img_id:
            self._current_image_id = img_id
            dpg.set_value("check_ext_enable", ext_state.is_enabled)
            dpg.set_value("drag_ext_threshold", ext_state.threshold)
            dpg.set_value("check_ext_preview", ext_state.show_preview)
            dpg.set_value("check_ext_subpixel", ext_state.subpixel_accurate)
            dpg.set_value("color_ext_preview", list(ext_state.preview_color))
            dpg.set_value("drag_ext_thickness", ext_state.preview_thickness)

        # 4. CONTINUOUS SYNC
        else:
            if dpg.get_value("check_ext_enable") != ext_state.is_enabled:
                dpg.set_value("check_ext_enable", ext_state.is_enabled)

            if not dpg.is_item_active("drag_ext_threshold"):
                dpg.set_value("drag_ext_threshold", ext_state.threshold)

            if not dpg.is_item_active("drag_ext_thickness"):
                dpg.set_value("drag_ext_thickness", ext_state.preview_thickness)

            if dpg.get_value("check_ext_preview") != ext_state.show_preview:
                dpg.set_value("check_ext_preview", ext_state.show_preview)

            if dpg.get_value("check_ext_subpixel") != ext_state.subpixel_accurate:
                dpg.set_value("check_ext_subpixel", ext_state.subpixel_accurate)

            # --- FIX: Safe Float/Int Color Syncing ---
            raw_ui_col = dpg.get_value("color_ext_preview")[:4]
            ui_scale = 255.0 if all(c <= 1.0 for c in raw_ui_col) else 1.0
            ui_col = [int(c * ui_scale) for c in raw_ui_col]

            if ui_col != list(ext_state.preview_color):
                dpg.set_value("color_ext_preview", list(ext_state.preview_color))

        # 5. UI LOCKING RULES
        dpg.configure_item("check_ext_enable", enabled=True)

        # Actionable controls that require the Master Switch to be ON
        locked_when_disabled = [
            "drag_ext_threshold",
            "btn_drag_ext_threshold_minus",
            "btn_drag_ext_threshold_plus",
        ]

        # Preferences that can be configured at any time
        always_enabled = [
            "check_ext_preview",
            "check_ext_subpixel",
            "color_ext_preview",
            "drag_ext_thickness",  # (If you added the thickness slider)
        ]

        for tag in locked_when_disabled:
            if dpg.does_item_exist(tag):
                dpg.configure_item(tag, enabled=ext_state.is_enabled)

        for tag in always_enabled:
            if dpg.does_item_exist(tag):
                dpg.configure_item(tag, enabled=True)

    # --- Callbacks ---

    def on_enable_toggle(self, sender, app_data, user_data):
        viewer = self.gui.context_viewer
        if not viewer or not viewer.view_state:
            return
        viewer.view_state.extraction.is_enabled = app_data
        if not app_data:
            self.controller.extraction.clear_preview(viewer.image_id, viewer.view_state)
        self.controller.ui_needs_refresh = True

    def on_threshold_drag(self, sender, app_data, user_data):
        viewer = self.gui.context_viewer
        if not viewer or not viewer.view_state:
            return

        if sender == "color_ext_preview":
            scale = 255.0 if all(c <= 1.0 for c in app_data) else 1.0
            viewer.view_state.extraction.preview_color = [
                int(c * scale) for c in app_data[:4]
            ]

        elif sender == "check_ext_preview":
            viewer.view_state.extraction.show_preview = app_data
            if not app_data:
                self.controller.extraction.clear_preview(
                    viewer.image_id, viewer.view_state
                )

        elif sender == "check_ext_subpixel":
            viewer.view_state.extraction.subpixel_accurate = app_data

        elif sender == "drag_ext_thickness":
            viewer.view_state.extraction.preview_thickness = app_data

        else:
            viewer.view_state.extraction.threshold = dpg.get_value("drag_ext_threshold")

        self.controller.ui_needs_refresh = True

    def on_step_button_clicked(self, sender, app_data, user_data):
        viewer = self.gui.context_viewer
        if not viewer or not viewer.view_state:
            return

        direction = user_data["dir"]
        current_val = viewer.view_state.extraction.threshold
        step_size = (
            max(0.1, viewer.view_state.display.ww * 0.02) if viewer.view_state else 1.0
        )
        new_val = current_val + (step_size * direction)

        if hasattr(viewer.volume, "_cached_min_val"):
            new_val = np.clip(
                new_val, viewer.volume._cached_min_val, viewer.volume._cached_max_val
            )

        viewer.view_state.extraction.threshold = new_val
        self.controller.ui_needs_refresh = True
