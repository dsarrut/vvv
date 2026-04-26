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

        with dpg.group(tag="tab_extraction", show=False):
            build_section_title("Interactive Threshold", cfg_c["text_header"])

            dpg.add_checkbox(
                label="Enable Thresholding",
                tag="check_ext_enable",
                callback=self.on_enable_toggle,
            )
            dpg.add_spacer(height=5)

            build_stepped_slider(
                "Min:",
                "drag_ext_threshold_min",
                callback=self.on_threshold_drag,
                step_callback=self.on_step_button_clicked,
                min_val=-100000.0,
                max_val=100000.0,
                has_color=True,
                color_tag="color_ext_preview_min",
                color_cb=self.on_threshold_drag,
            )

            build_stepped_slider(
                "Max:",
                "drag_ext_threshold_max",
                callback=self.on_threshold_drag,
                step_callback=self.on_step_button_clicked,
                min_val=-100000.0,
                max_val=100000.0,
                has_color=True,
                color_tag="color_ext_preview_max",
                color_cb=self.on_threshold_drag,
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

            # --- NEW: Image Generation ---
            dpg.add_spacer(height=10)
            build_section_title("Image Generation", cfg_c["text_header"])

            with dpg.group(horizontal=True):
                dpg.add_text("BG Range:", color=cfg_c["text_dim"])
                dpg.add_text("---", tag="text_ext_bg_range")

            with dpg.group(horizontal=True):
                dpg.add_text("FG Range:", color=cfg_c["text_dim"])
                dpg.add_text("---", tag="text_ext_fg_range")

            dpg.add_spacer(height=5)
            with dpg.group(horizontal=True):
                dpg.add_text("BG:")
                dpg.add_combo(
                    ["Constant", "Image"],
                    default_value="Constant",
                    width=95,
                    tag="combo_ext_bg_mode",
                    callback=self.on_gen_mode_changed,
                )
                dpg.add_input_float(
                    default_value=0.0,
                    width=95,
                    tag="input_ext_bg_val",
                    step=0,
                    callback=self.on_gen_mode_changed,
                )

            with dpg.group(horizontal=True):
                dpg.add_text("FG:")
                dpg.add_combo(
                    ["Constant", "Image"],
                    default_value="Constant",
                    width=95,
                    tag="combo_ext_fg_mode",
                    callback=self.on_gen_mode_changed,
                )
                dpg.add_input_float(
                    default_value=1.0,
                    width=95,
                    tag="input_ext_fg_val",
                    step=0,
                    callback=self.on_gen_mode_changed,
                )

            dpg.add_spacer(height=5)
            btn_create = dpg.add_button(
                label="Create Image",
                width=-1,
                height=30,
                tag="btn_ext_create",
                callback=self.on_create_image_clicked,
            )
            if dpg.does_item_exist("icon_button_theme"):
                dpg.bind_item_theme(btn_create, "icon_button_theme")

    def refresh_extraction_ui(self):
        viewer = self.gui.context_viewer
        has_image = bool(viewer and viewer.view_state and viewer.volume)

        if not has_image:
            tags_to_disable = [
                "check_ext_enable",
                "drag_ext_threshold_min",
                "drag_ext_threshold_max",
                "check_ext_preview",
                "color_ext_preview_min",
                "color_ext_preview_max",
                "check_ext_subpixel",
                "drag_ext_thickness",
                "combo_ext_bg_mode",
                "input_ext_bg_val",
                "combo_ext_fg_mode",
                "input_ext_fg_val",
                "btn_ext_create",
            ]
            for tag in tags_to_disable:
                if dpg.does_item_exist(tag):
                    dpg.configure_item(tag, enabled=False)

            self._current_image_id = None
            if dpg.does_item_exist("text_ext_bg_range"):
                dpg.set_value("text_ext_bg_range", "---")
                dpg.set_value("text_ext_fg_range", "---")
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

        # Dynamic Range Texts
        min_v = ext_state.threshold_min
        max_v = ext_state.threshold_max
        dpg.set_value("text_ext_bg_range", f"< {min_v:g}   OR   > {max_v:g}")
        dpg.set_value("text_ext_fg_range", f"[{min_v:g}  ...  {max_v:g}]")

        safe_min = min(0.0, vol._cached_min_val)
        for tag in ["drag_ext_threshold_min", "drag_ext_threshold_max"]:
            dpg.configure_item(tag, min_value=safe_min, max_value=vol._cached_max_val)
            dpg.configure_item(
                tag, speed=max(0.1, viewer.view_state.display.ww * 0.005)
            )

        # Context Switch Snap
        if self._current_image_id != img_id:
            self._current_image_id = img_id
            dpg.set_value("check_ext_enable", ext_state.is_enabled)
            dpg.set_value("drag_ext_threshold_min", ext_state.threshold_min)
            dpg.set_value("drag_ext_threshold_max", ext_state.threshold_max)
            dpg.set_value("check_ext_preview", ext_state.show_preview)
            dpg.set_value("check_ext_subpixel", ext_state.subpixel_accurate)
            if dpg.does_item_exist("color_ext_preview_min"):
                dpg.set_value(
                    "color_ext_preview_min", list(ext_state.preview_color_min)
                )
            if dpg.does_item_exist("color_ext_preview_max"):
                dpg.set_value(
                    "color_ext_preview_max", list(ext_state.preview_color_max)
                )
            dpg.set_value("drag_ext_thickness", ext_state.preview_thickness)
            dpg.set_value("combo_ext_bg_mode", ext_state.gen_bg_mode)
            dpg.set_value("input_ext_bg_val", ext_state.gen_bg_val)
            dpg.set_value("combo_ext_fg_mode", ext_state.gen_fg_mode)
            dpg.set_value("input_ext_fg_val", ext_state.gen_fg_val)

        # 4. CONTINUOUS SYNC
        else:
            if dpg.get_value("check_ext_enable") != ext_state.is_enabled:
                dpg.set_value("check_ext_enable", ext_state.is_enabled)

            if not dpg.is_item_active("drag_ext_threshold_min"):
                dpg.set_value("drag_ext_threshold_min", ext_state.threshold_min)

            if not dpg.is_item_active("drag_ext_threshold_max"):
                dpg.set_value("drag_ext_threshold_max", ext_state.threshold_max)

            if not dpg.is_item_active("drag_ext_thickness"):
                dpg.set_value("drag_ext_thickness", ext_state.preview_thickness)

            if not dpg.is_item_active("input_ext_bg_val"):
                dpg.set_value("input_ext_bg_val", ext_state.gen_bg_val)
            if not dpg.is_item_active("input_ext_fg_val"):
                dpg.set_value("input_ext_fg_val", ext_state.gen_fg_val)

            dpg.set_value("combo_ext_bg_mode", ext_state.gen_bg_mode)
            dpg.set_value("combo_ext_fg_mode", ext_state.gen_fg_mode)

            if dpg.get_value("check_ext_preview") != ext_state.show_preview:
                dpg.set_value("check_ext_preview", ext_state.show_preview)

            if dpg.get_value("check_ext_subpixel") != ext_state.subpixel_accurate:
                dpg.set_value("check_ext_subpixel", ext_state.subpixel_accurate)

            # --- FIX: Safe Float/Int Color Syncing ---
            if dpg.does_item_exist("color_ext_preview_min"):
                raw_ui_col_min = dpg.get_value("color_ext_preview_min")[:4]
                ui_scale_min = 255.0 if all(c <= 1.0 for c in raw_ui_col_min) else 1.0
                ui_col_min = [int(c * ui_scale_min) for c in raw_ui_col_min]
                if ui_col_min != list(ext_state.preview_color_min):
                    dpg.set_value(
                        "color_ext_preview_min", list(ext_state.preview_color_min)
                    )

            if dpg.does_item_exist("color_ext_preview_max"):
                raw_ui_col_max = dpg.get_value("color_ext_preview_max")[:4]
                ui_scale_max = 255.0 if all(c <= 1.0 for c in raw_ui_col_max) else 1.0
                ui_col_max = [int(c * ui_scale_max) for c in raw_ui_col_max]
                if ui_col_max != list(ext_state.preview_color_max):
                    dpg.set_value(
                        "color_ext_preview_max", list(ext_state.preview_color_max)
                    )

        # 5. UI LOCKING RULES
        dpg.configure_item("check_ext_enable", enabled=True)

        # Enable/Disable constant inputs based on dropdowns
        dpg.configure_item(
            "input_ext_bg_val", enabled=(ext_state.gen_bg_mode == "Constant")
        )
        dpg.configure_item(
            "input_ext_fg_val", enabled=(ext_state.gen_fg_mode == "Constant")
        )

        # Actionable controls that require the Master Switch to be ON
        locked_when_disabled = [
            "drag_ext_threshold_min",
            "btn_drag_ext_threshold_min_minus",
            "btn_drag_ext_threshold_min_plus",
            "drag_ext_threshold_max",
            "btn_drag_ext_threshold_max_minus",
            "btn_drag_ext_threshold_max_plus",
        ]

        # Preferences that can be configured at any time
        always_enabled = [
            "check_ext_preview",
            "check_ext_subpixel",
            "color_ext_preview_min",
            "color_ext_preview_max",
            "drag_ext_thickness",  # (If you added the thickness slider)
            "combo_ext_bg_mode",
            "input_ext_bg_val",
            "combo_ext_fg_mode",
            "input_ext_fg_val",
            "btn_ext_create",
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

        if sender == "color_ext_preview_min":
            scale = 255.0 if all(c <= 1.0 for c in app_data) else 1.0
            viewer.view_state.extraction.preview_color_min = [
                int(c * scale) for c in app_data[:4]
            ]

        elif sender == "color_ext_preview_max":
            scale = 255.0 if all(c <= 1.0 for c in app_data) else 1.0
            viewer.view_state.extraction.preview_color_max = [
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

        elif sender == "drag_ext_threshold_min":
            val = dpg.get_value("drag_ext_threshold_min")
            if val > viewer.view_state.extraction.threshold_max:
                viewer.view_state.extraction.threshold_max = val
            viewer.view_state.extraction.threshold_min = val

        elif sender == "drag_ext_threshold_max":
            val = dpg.get_value("drag_ext_threshold_max")
            if val < viewer.view_state.extraction.threshold_min:
                viewer.view_state.extraction.threshold_min = val
            viewer.view_state.extraction.threshold_max = val

        self.controller.ui_needs_refresh = True

    def on_step_button_clicked(self, sender, app_data, user_data):
        viewer = self.gui.context_viewer
        if not viewer or not viewer.view_state:
            return

        direction = user_data["dir"]
        tag = user_data["tag"]
        is_min = tag == "drag_ext_threshold_min"

        current_val = (
            viewer.view_state.extraction.threshold_min
            if is_min
            else viewer.view_state.extraction.threshold_max
        )
        step_size = (
            max(0.1, viewer.view_state.display.ww * 0.02) if viewer.view_state else 1.0
        )
        new_val = current_val + (step_size * direction)

        if hasattr(viewer.volume, "_cached_min_val"):
            new_val = np.clip(
                new_val, viewer.volume._cached_min_val, viewer.volume._cached_max_val
            )

        if is_min:
            if new_val > viewer.view_state.extraction.threshold_max:
                viewer.view_state.extraction.threshold_max = new_val
            viewer.view_state.extraction.threshold_min = new_val
        else:
            if new_val < viewer.view_state.extraction.threshold_min:
                viewer.view_state.extraction.threshold_min = new_val
            viewer.view_state.extraction.threshold_max = new_val

        self.controller.ui_needs_refresh = True

    def on_gen_mode_changed(self, sender, app_data, user_data):
        viewer = self.gui.context_viewer
        if not viewer or not viewer.view_state:
            return

        if sender == "combo_ext_bg_mode":
            viewer.view_state.extraction.gen_bg_mode = app_data
        elif sender == "combo_ext_fg_mode":
            viewer.view_state.extraction.gen_fg_mode = app_data
        elif sender == "input_ext_bg_val":
            viewer.view_state.extraction.gen_bg_val = app_data
        elif sender == "input_ext_fg_val":
            viewer.view_state.extraction.gen_fg_val = app_data

        self.controller.ui_needs_refresh = True

    def on_create_image_clicked(self, sender, app_data, user_data):
        viewer = self.gui.context_viewer
        if not viewer or not viewer.view_state:
            return
        self.controller.extraction.create_image(
            viewer.image_id, viewer.volume, viewer.view_state
        )
