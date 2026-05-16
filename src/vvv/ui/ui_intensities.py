import numpy as np
import dearpygui.dearpygui as dpg
from vvv.config import WL_PRESETS, COLORMAPS
from vvv.ui.ui_components import build_stepped_slider, build_section_title


class IntensitiesUI:
    """Delegated UI handler for the Intensities tab."""

    def __init__(self, gui, controller):
        self.gui = gui
        self.controller = controller
        self._hist_max_y = 1.0

    @staticmethod
    def build_tab_intensities(gui):
        cfg_c = gui.ui_cfg["colors"]

        with dpg.group(tag="tab_intensities", show=False):
            build_section_title("Window / Level", cfg_c["text_header"])

            dpg.add_text(
                "No Image Selected",
                tag="text_intensities_active_title",
                color=cfg_c["text_active"],
            )

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
                help_text="Window / Level controls image contrast and brightness.\nWindow: The range of visible values.\nLevel: The center point of the visible range.",
                gui=gui,
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
                help_text="Pixels below this threshold value are rendered completely transparent.",
                gui=gui,
            )

            dpg.add_spacer(height=5)
            with dpg.group(horizontal=True):
                dpg.add_text("Image Range:", color=cfg_c["text_dim"])
                dpg.add_text("---", tag="text_intensities_minmax")

            dpg.add_spacer(height=4)
            with dpg.plot(
                tag="wl_hist_plot",
                height=120,
                width=-1,
                no_title=True,
                no_mouse_pos=True,
                no_box_select=True,
                show=False,
            ):
                dpg.add_plot_axis(dpg.mvXAxis, tag="wl_hist_x_axis")
                with dpg.plot_axis(dpg.mvYAxis, tag="wl_hist_y_axis", no_tick_labels=True):
                    dpg.add_shade_series(
                        [0.0, 1.0], [1.0, 1.0], y2=[0.0, 0.0],
                        tag="wl_hist_shade",
                    )
                    dpg.add_line_series([], [], tag="wl_hist_series")
                dpg.add_drag_line(
                    tag="wl_hist_lower",
                    color=[100, 180, 255, 200],
                    thickness=2.0,
                    default_value=0.0,
                    callback=gui.intensities_ui.on_hist_drag_lower,
                )
                dpg.add_drag_line(
                    tag="wl_hist_upper",
                    color=[100, 180, 255, 200],
                    thickness=2.0,
                    default_value=1.0,
                    callback=gui.intensities_ui.on_hist_drag_upper,
                )
                dpg.add_drag_line(
                    tag="wl_hist_level",
                    color=[255, 160, 60, 240],
                    thickness=2.0,
                    default_value=0.5,
                    callback=gui.intensities_ui.on_hist_drag_level,
                )

            with dpg.theme(tag="wl_shade_theme"):
                with dpg.theme_component(dpg.mvShadeSeries):
                    dpg.add_theme_color(
                        dpg.mvPlotCol_Fill, [100, 180, 255, 30],
                        category=dpg.mvThemeCat_Plots,
                    )
                    dpg.add_theme_color(
                        dpg.mvPlotCol_Line, [0, 0, 0, 0],
                        category=dpg.mvThemeCat_Plots,
                    )
            dpg.bind_item_theme("wl_hist_shade", "wl_shade_theme")

    def refresh_intensities_ui(self):
        viewer = self.gui.context_viewer
        has_image = bool(viewer and viewer.view_state and viewer.volume)

        if dpg.does_item_exist("text_intensities_active_title"):
            if has_image:
                name_str, is_outdated = self.controller.get_image_display_name(
                    viewer.image_id
                )
                dpg.set_value("text_intensities_active_title", name_str)
                col = (
                    self.gui.ui_cfg["colors"]["outdated"]
                    if is_outdated
                    else self.gui.ui_cfg["colors"]["text_active"]
                )
                dpg.configure_item("text_intensities_active_title", color=col)
            else:
                dpg.set_value("text_intensities_active_title", "No Image Selected")
                dpg.configure_item(
                    "text_intensities_active_title",
                    color=self.gui.ui_cfg["colors"]["text_active"],
                )

        is_rgb = viewer.volume.is_rgb if has_image else False
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

        self._refresh_wl_histogram(viewer, has_image, is_rgb)

    def _refresh_wl_histogram(self, viewer, has_image, is_rgb):
        if not dpg.does_item_exist("wl_hist_plot"):
            return

        if not has_image or is_rgb:
            dpg.configure_item("wl_hist_plot", show=False)
            return

        vs = viewer.view_state
        if vs.histogram_is_dirty:
            vs.update_histogram()
            use_log = vs.use_log_y
            y_data = np.log10(vs.hist_data_y + 1) if use_log else vs.hist_data_y
            self._hist_max_y = float(np.max(y_data)) if len(y_data) > 0 else 1.0
            dpg.set_value("wl_hist_series", [vs.hist_data_x.tolist(), y_data.tolist()])
            dpg.fit_axis_data("wl_hist_x_axis")
            dpg.fit_axis_data("wl_hist_y_axis")

        dpg.configure_item("wl_hist_plot", show=True)

    def sync_wl_lines(self, viewer, vs):
        """Update histogram drag line positions every frame — called from sync_bound_ui."""
        if not dpg.does_item_exist("wl_hist_lower"):
            return
        if getattr(viewer.volume, "is_rgb", False):
            return
        wl = vs.display.wl
        ww = vs.display.ww
        lower = wl - ww / 2
        upper = wl + ww / 2
        dpg.set_value("wl_hist_lower", lower)
        dpg.set_value("wl_hist_upper", upper)
        if dpg.does_item_exist("wl_hist_level"):
            dpg.set_value("wl_hist_level", wl)
        if self._hist_max_y > 0 and dpg.does_item_exist("wl_hist_shade"):
            dpg.set_value("wl_hist_shade", [[lower, upper], [self._hist_max_y, self._hist_max_y], [0.0, 0.0]])

    def on_hist_drag_lower(self, _sender, app_data, _user_data):
        viewer = self.gui.context_viewer
        if not viewer or not viewer.view_state:
            return
        pos = float(app_data) if app_data is not None else dpg.get_value("wl_hist_lower")
        if pos is None:
            return
        wl = viewer.view_state.display.wl
        ww = max(1e-5, 2.0 * (wl - pos))
        viewer._mark_lazy_interaction()
        viewer.view_state.display.ww = ww
        dpg.set_value("drag_ww", ww)
        if dpg.does_item_exist("combo_wl_presets"):
            dpg.set_value("combo_wl_presets", "Custom")
        self.controller.sync.propagate_window_level(viewer.image_id)

    def on_hist_drag_upper(self, _sender, app_data, _user_data):
        viewer = self.gui.context_viewer
        if not viewer or not viewer.view_state:
            return
        pos = float(app_data) if app_data is not None else dpg.get_value("wl_hist_upper")
        if pos is None:
            return
        wl = viewer.view_state.display.wl
        ww = max(1e-5, 2.0 * (pos - wl))
        viewer._mark_lazy_interaction()
        viewer.view_state.display.ww = ww
        dpg.set_value("drag_ww", ww)
        if dpg.does_item_exist("combo_wl_presets"):
            dpg.set_value("combo_wl_presets", "Custom")
        self.controller.sync.propagate_window_level(viewer.image_id)

    def on_hist_drag_level(self, _sender, app_data, _user_data):
        viewer = self.gui.context_viewer
        if not viewer or not viewer.view_state:
            return
        pos = float(app_data) if app_data is not None else dpg.get_value("wl_hist_level")
        if pos is None:
            return
        viewer._mark_lazy_interaction()
        viewer.view_state.display.wl = pos
        dpg.set_value("drag_wl", pos)
        if dpg.does_item_exist("combo_wl_presets"):
            dpg.set_value("combo_wl_presets", "Custom")
        self.controller.sync.propagate_window_level(viewer.image_id)

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
        viewer._mark_lazy_interaction()
        viewer.view_state.display.ww = max(1e-20, app_data)
        if dpg.does_item_exist("combo_wl_presets"):
            dpg.set_value("combo_wl_presets", "Custom")
        self.controller.sync.propagate_window_level(viewer.image_id)

    def on_wl_changed(self, sender, app_data, user_data):
        viewer = self.gui.context_viewer
        if not viewer or not viewer.view_state:
            return
        viewer._mark_lazy_interaction()
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
