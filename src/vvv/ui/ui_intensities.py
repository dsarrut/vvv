import dearpygui.dearpygui as dpg
from vvv.config import WL_PRESETS, COLORMAPS


class IntensitiesUI:
    """Delegated UI handler for the Intensities tab."""

    def __init__(self, gui, controller):
        self.gui = gui
        self.controller = controller

    @staticmethod
    def build_tab_intensities(gui):
        cfg_c = gui.ui_cfg["colors"]

        def build_slider_row(label, tag, callback, min_val=None):
            with dpg.group(horizontal=True):
                dpg.add_text(label)
                dpg.add_button(
                    label="-",
                    width=20,
                    user_data={"tag": tag, "dir": -1},
                    callback=gui.intensities_ui.on_step_button_clicked,
                )
                kwargs = {
                    "tag": tag,
                    "width": -35,
                    "speed": 1.0,
                    "callback": callback,
                }
                kwargs["min_value"] = min_val if min_val is not None else -1e9
                kwargs["max_value"] = 1e9
                dpg.add_drag_float(**kwargs)
                dpg.add_button(
                    label="+",
                    width=20,
                    user_data={"tag": tag, "dir": 1},
                    callback=gui.intensities_ui.on_step_button_clicked,
                )

        with dpg.tab(label="Intensities", tag="tab_intensities"):
            dpg.add_spacer(height=5)
            dpg.add_text("Window / Level", color=cfg_c["text_header"])
            dpg.add_separator()

            with dpg.group(horizontal=True):
                dpg.add_text("Preset: ")
                dpg.add_combo(
                    list(WL_PRESETS.keys()) + ["Custom"],
                    default_value="Custom",
                    tag="combo_wl_presets",
                    width=-1,
                    callback=gui.intensities_ui.on_preset_changed,
                )

            build_slider_row(
                "Window: ",
                "drag_ww",
                gui.intensities_ui.on_ww_changed,
                min_val=1e-5,
            )
            build_slider_row(
                "Level:  ",
                "drag_wl",
                gui.intensities_ui.on_wl_changed,
            )

            dpg.add_spacer(height=10)
            dpg.add_text("Colormap & Threshold", color=cfg_c["text_header"])
            dpg.add_separator()

            with dpg.group(horizontal=True):
                dpg.add_text("Map:    ")
                dpg.add_combo(
                    list(COLORMAPS.keys()),
                    default_value="Grayscale",
                    tag="combo_colormap",
                    width=-1,
                    callback=gui.intensities_ui.on_colormap_changed,
                )

            build_slider_row(
                "Min Thr:",
                "drag_min_threshold",
                gui.intensities_ui.on_threshold_changed,
            )

    def refresh_intensities_ui(self):
        viewer = self.gui.context_viewer
        has_image = (
            viewer is not None
            and getattr(viewer, "view_state", None) is not None
            and viewer.volume is not None
        )

        tags = [
            "combo_wl_presets",
            "drag_ww",
            "drag_wl",
            "combo_colormap",
            "drag_min_threshold",
        ]

        for t in tags:
            if dpg.does_item_exist(t):
                dpg.configure_item(
                    t,
                    enabled=(has_image and not getattr(viewer.volume, "is_rgb", False)),
                )

    def on_step_button_clicked(self, sender, app_data, user_data):
        target_tag = user_data["tag"]
        direction = user_data["dir"]

        current_val = dpg.get_value(target_tag)
        step_size = 1.0
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
        self.controller.sync.propagate_window_level(viewer.image_id)
