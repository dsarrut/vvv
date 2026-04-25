import numpy as np
import dearpygui.dearpygui as dpg
from vvv.config import WL_PRESETS, COLORMAPS
from vvv.ui.ui_components import build_stepped_slider, build_section_title


class IntensitiesUI:
    """Delegated UI handler for the Intensities tab."""

    def __init__(self, gui, controller):
        self.gui = gui
        self.controller = controller

    @staticmethod
    def build_tab_intensities(gui):
        cfg_c = gui.ui_cfg["colors"]

        with dpg.group(tag="tab_intensities", show=False):
            dpg.add_spacer(height=5)
            build_section_title("Window / Level", cfg_c["text_header"])

            with dpg.group(horizontal=True):
                dpg.add_text("Preset: ")
                dpg.add_combo(
                    list(WL_PRESETS.keys()) + ["Custom"],
                    default_value="Custom",
                    tag="combo_wl_presets",
                    width=-1,
                    callback=gui.intensities_ui.on_preset_changed,
                )

            build_stepped_slider(
                "Window: ",
                "drag_ww",
                callback=gui.intensities_ui.on_ww_changed,
                step_callback=gui.intensities_ui.on_step_button_clicked,
                min_val=1e-5,
            )
            build_stepped_slider(
                "Level:  ",
                "drag_wl",
                callback=gui.intensities_ui.on_wl_changed,
                step_callback=gui.intensities_ui.on_step_button_clicked,
            )

            dpg.add_spacer(height=10)
            build_section_title("Colormap & Threshold", cfg_c["text_header"])

            with dpg.group(horizontal=True):
                dpg.add_text("Map:    ")
                dpg.add_combo(
                    list(COLORMAPS.keys()),
                    default_value="Grayscale",
                    tag="combo_colormap",
                    width=-1,
                    callback=gui.intensities_ui.on_colormap_changed,
                )

            build_stepped_slider(
                "Min Thr:",
                "drag_min_threshold",
                callback=gui.intensities_ui.on_threshold_changed,
                step_callback=gui.intensities_ui.on_step_button_clicked,
                has_checkbox=True,
                check_tag="check_min_threshold",
                check_cb=gui.intensities_ui.on_threshold_toggle,
            )

            dpg.add_spacer(height=5)
            with dpg.group(horizontal=True):
                dpg.add_text("Image Range:", color=cfg_c["text_dim"])
                dpg.add_text("---", tag="text_intensities_minmax")

    def refresh_intensities_ui(self):
        viewer = self.gui.context_viewer
        has_image = (
            viewer is not None
            and getattr(viewer, "view_state", None) is not None
            and viewer.volume is not None
        )

        is_rgb = getattr(viewer.volume, "is_rgb", False) if has_image else False
        thr = viewer.view_state.display.base_threshold if has_image else None
        has_thr = thr is not None

        tags = [
            "combo_wl_presets",
            "drag_ww",
            "drag_wl",
            "combo_colormap",
        ]

        for t in tags:
            if dpg.does_item_exist(t):
                dpg.configure_item(
                    t,
                    enabled=(has_image and not is_rgb),
                )

        if dpg.does_item_exist("check_min_threshold"):
            dpg.set_value("check_min_threshold", has_thr)
            dpg.configure_item(
                "check_min_threshold", enabled=(has_image and not is_rgb)
            )

        if dpg.does_item_exist("drag_min_threshold"):
            if has_thr and not dpg.is_item_active("drag_min_threshold"):
                dpg.set_value("drag_min_threshold", thr)

            thr_enabled = has_image and not is_rgb and has_thr
            dpg.configure_item("drag_min_threshold", enabled=thr_enabled)
            if dpg.does_item_exist("btn_drag_min_threshold_minus"):
                dpg.configure_item("btn_drag_min_threshold_minus", enabled=thr_enabled)
            if dpg.does_item_exist("btn_drag_min_threshold_plus"):
                dpg.configure_item("btn_drag_min_threshold_plus", enabled=thr_enabled)

        if dpg.does_item_exist("text_intensities_minmax"):
            if not has_image or is_rgb:
                dpg.set_value("text_intensities_minmax", "---")
            else:
                vol = viewer.volume
                current_data_id = id(vol.data)
                if (
                    not hasattr(vol, "_cached_min_val")
                    or getattr(vol, "_cached_data_id", None) != current_data_id
                ):
                    # Lazy evaluation of image min and max
                    vol._cached_min_val = float(np.min(vol.data))
                    vol._cached_max_val = float(np.max(vol.data))
                    vol._cached_data_id = current_data_id

                min_v = vol._cached_min_val
                max_v = vol._cached_max_val
                dpg.set_value("text_intensities_minmax", f"{min_v:g} to {max_v:g}")

        # Dynamically scale the slider drag speed based on the current window width
        dynamic_speed = (
            max(0.1, viewer.view_state.display.ww * 0.005) if has_image else 1.0
        )
        for t in ["drag_ww", "drag_wl", "drag_min_threshold"]:
            if dpg.does_item_exist(t):
                dpg.configure_item(t, speed=dynamic_speed)

    def on_step_button_clicked(self, sender, app_data, user_data):
        target_tag = user_data["tag"]
        direction = user_data["dir"]

        current_val = dpg.get_value(target_tag)

        viewer = self.gui.context_viewer
        step_size = (
            max(0.1, viewer.view_state.display.ww * 0.02)
            if (viewer and viewer.view_state)
            else 1.0
        )

        new_val = current_val + (step_size * direction)

        if target_tag == "drag_ww":
            new_val = max(1e-5, new_val)

        dpg.set_value(target_tag, new_val)

        if target_tag == "drag_ww":
            self.on_ww_changed(sender, new_val, user_data)
        elif target_tag == "drag_wl":
            self.on_wl_changed(sender, new_val, user_data)
        elif target_tag == "drag_min_threshold":
            self.on_threshold_changed(sender, new_val, user_data)

    def on_preset_changed(self, sender, app_data, user_data):
        viewer = self.gui.context_viewer
        if not viewer or not viewer.view_state:
            return
        viewer.view_state.apply_wl_preset(app_data)
        self.controller.sync.propagate_window_level(viewer.image_id)
        self.controller.ui_needs_refresh = True

    def on_threshold_toggle(self, sender, app_data, user_data):
        viewer = self.gui.context_viewer
        if not viewer or not viewer.view_state:
            return
        is_enabled = app_data
        if is_enabled:
            val = dpg.get_value("drag_min_threshold")
            viewer.view_state.display.base_threshold = val
        else:
            viewer.view_state.display.base_threshold = None
        self.controller.sync.propagate_window_level(viewer.image_id)
        self.controller.ui_needs_refresh = True

    def on_ww_changed(self, sender, app_data, user_data):
        viewer = self.gui.context_viewer
        if not viewer or not viewer.view_state:
            return
        viewer.view_state.display.ww = max(1e-20, app_data)
        if dpg.does_item_exist("combo_wl_presets"):
            dpg.set_value("combo_wl_presets", "Custom")
        self.controller.sync.propagate_window_level(viewer.image_id)

    def on_wl_changed(self, sender, app_data, user_data):
        viewer = self.gui.context_viewer
        if not viewer or not viewer.view_state:
            return
        viewer.view_state.display.wl = app_data
        if dpg.does_item_exist("combo_wl_presets"):
            dpg.set_value("combo_wl_presets", "Custom")
        self.controller.sync.propagate_window_level(viewer.image_id)

    def on_colormap_changed(self, sender, app_data, user_data):
        viewer = self.gui.context_viewer
        if not viewer or not viewer.view_state:
            return
        viewer.view_state.display.colormap = app_data
        self.controller.sync.propagate_colormap(viewer.image_id)

    def on_threshold_changed(self, sender, app_data, user_data):
        viewer = self.gui.context_viewer
        if not viewer or not viewer.view_state:
            return
        viewer.view_state.display.base_threshold = app_data
        if dpg.does_item_exist("check_min_threshold"):
            dpg.set_value("check_min_threshold", True)
        self.controller.sync.propagate_window_level(viewer.image_id)
