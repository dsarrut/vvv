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
        self._hist_bin_width = 1.0
        self._hist_min_x = 0.0
        self._hist_max_x = 1.0
        self._last_colormap = ""
        self._last_popup_image_id = None
        self._last_sidebar_image_id = None
        self._intensities_tab_was_shown = False

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

            #dpg.add_spacer(height=10)
            #build_section_title("Colormap & Threshold", cfg_c["text_header"])

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
                zoom_mod=dpg.mvKey_ModCtrl,
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
                    color=[80, 160, 255, 255],
                    thickness=3.0,
                    default_value=0.0,
                    callback=gui.intensities_ui.on_hist_drag_lower,
                )
                dpg.add_drag_line(
                    tag="wl_hist_upper",
                    color=[80, 160, 255, 255],
                    thickness=3.0,
                    default_value=1.0,
                    callback=gui.intensities_ui.on_hist_drag_upper,
                )
                dpg.add_drag_line(
                    tag="wl_hist_level",
                    color=[255, 160, 40, 255],
                    thickness=3.0,
                    default_value=0.5,
                    callback=gui.intensities_ui.on_hist_drag_level,
                )

            dpg.add_spacer(height=2)
            with dpg.group(horizontal=True):
                dpg.add_button(
                    label="Ctr", width=36, tag="btn_hist_center",
                    callback=gui.intensities_ui.on_hist_center,
                )
                dpg.add_button(
                    label="Auto", width=40, tag="btn_hist_auto_center",
                    callback=gui.intensities_ui.on_hist_auto_center,
                )
                dpg.add_button(
                    label="Bar", width=34, tag="btn_hist_bar",
                    callback=gui.intensities_ui.on_hist_bar_toggle,
                )
                dpg.add_button(
                    label="Lin", width=30, tag="btn_hist_log",
                    callback=gui.intensities_ui.on_hist_log_toggle,
                )
                btn_popup = dpg.add_button(
                    label="", tag="btn_hist_popup",
                    callback=gui.intensities_ui.on_hist_popup,
                )
                if dpg.does_item_exist("icon_font_tag"):
                    dpg.bind_item_font(btn_popup, "icon_font_tag")
            with dpg.group(horizontal=True):
                dpg.add_text("C:", color=cfg_c["text_dim"])
                dpg.add_drag_float(
                    tag="drag_hist_xcenter", default_value=0.0, speed=1.0,
                    min_value=-1e10, max_value=1e10, format="%.4g", width=65,
                    callback=gui.intensities_ui.on_hist_xcenter_drag,
                )
                dpg.add_text("W:", color=cfg_c["text_dim"])
                dpg.add_drag_float(
                    tag="drag_hist_xwidth", default_value=1.0, speed=1.0,
                    min_value=1e-5, max_value=1e10, format="%.3g", width=60,
                    callback=gui.intensities_ui.on_hist_xwidth_drag,
                )
                dpg.add_text("Y:", color=cfg_c["text_dim"])
                dpg.add_drag_float(
                    tag="drag_hist_ymax", default_value=1.0, speed=0.01,
                    min_value=1e-5, max_value=1e10, format="%.2g", width=-1,
                    callback=gui.intensities_ui.on_hist_ymax_drag,
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

            with dpg.theme(tag="wl_hist_series_theme"):
                with dpg.theme_component(dpg.mvLineSeries):
                    dpg.add_theme_color(
                        dpg.mvPlotCol_Line, [120, 220, 140, 230],
                        category=dpg.mvThemeCat_Plots,
                    )
                with dpg.theme_component(dpg.mvBarSeries):
                    dpg.add_theme_color(
                        dpg.mvPlotCol_Fill, [120, 220, 140, 180],
                        category=dpg.mvThemeCat_Plots,
                    )
                    dpg.add_theme_color(
                        dpg.mvPlotCol_Line, [120, 220, 140, 230],
                        category=dpg.mvThemeCat_Plots,
                    )
            dpg.bind_item_theme("wl_hist_series", "wl_hist_series_theme")

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

        # Detect volume data changes (image reload from disk replaces the array object)
        current_data_id = id(viewer.volume.data)
        if getattr(vs, "_hist_vol_data_id", None) != current_data_id:
            vs.histogram_is_dirty = True
            vs._hist_vol_data_id = current_data_id

        # Lazy: don't pay the compute cost until the intensity panel is visible
        if vs.histogram_is_dirty and not dpg.is_item_shown("tab_intensities"):
            return

        image_id = getattr(viewer, "image_id", None)
        popup_exists = dpg.does_item_exist("wl_hist_popup_series")
        popup_needs_update = popup_exists and image_id != self._last_popup_image_id
        sidebar_image_changed = image_id != self._last_sidebar_image_id

        num_bins = int(dpg.get_value("drag_hist_popup_bins")) if dpg.does_item_exist("drag_hist_popup_bins") else 256

        histogram_was_dirty = vs.histogram_is_dirty
        if histogram_was_dirty or popup_needs_update or sidebar_image_changed:
            if histogram_was_dirty:
                vs.update_histogram(bins=num_bins)
            use_log = vs.use_log_y
            y_data = np.log10(vs.hist_data_y + 1) if use_log else vs.hist_data_y
            self._hist_max_y = float(np.max(y_data)) if len(y_data) > 0 else 1.0
            x_edges = vs.hist_data_x
            if len(x_edges) > 1:
                self._hist_bin_width = float(x_edges[1] - x_edges[0])
                self._hist_min_x = float(x_edges[0])
                self._hist_max_x = float(x_edges[-1]) + self._hist_bin_width
            x_centers = (x_edges + self._hist_bin_width / 2).tolist()
            x_edges_list = x_edges.tolist()
            y_list = y_data.tolist()
            dsp = vs.display
            use_bars = dsp.hist_use_bars
            # Initialise per-image histogram view state on first load if not already set
            if dsp.hist_x_center is None:
                dsp.hist_x_center = float(vs.display.wl)
            if dsp.hist_x_range is None:
                # Default to 2x the WL window to show surrounding context
                dsp.hist_x_range = dsp.ww * 2.0
            if dsp.hist_y_max is None:
                dsp.hist_y_max = self._hist_max_y

            x_speed = max(0.01, dsp.hist_x_range * 0.005)
            y_speed = max(1e-4, dsp.hist_y_max * 0.005)

            if histogram_was_dirty or sidebar_image_changed:
                self._update_hist_series(
                    "wl_hist_series", "wl_hist_y_axis",
                    x_edges_list, x_centers, y_list, use_bars=use_bars,
                )
                self._apply_hist_x_limits(dsp)
                dpg.set_axis_limits("wl_hist_y_axis", 0.0, dsp.hist_y_max)
                for tag, val, spd in (
                    ("drag_hist_xcenter", dsp.hist_x_center, x_speed),
                    ("drag_hist_xwidth", dsp.hist_x_range, x_speed),
                    ("drag_hist_ymax", dsp.hist_y_max, y_speed),
                ):
                    if dpg.does_item_exist(tag) and not dpg.is_item_active(tag):
                        dpg.set_value(tag, val)
                        dpg.configure_item(tag, speed=spd)
                self._last_sidebar_image_id = image_id
            if popup_exists:
                self._update_hist_series(
                    "wl_hist_popup_series", "wl_hist_popup_y_axis",
                    x_edges_list, x_centers, y_list, use_bars=use_bars,
                )
                self._apply_hist_x_limits(dsp)
                dpg.set_axis_limits("wl_hist_popup_y_axis", 0.0, dsp.hist_y_max)
                for tag, val, spd in (
                    ("drag_hist_popup_xcenter", dsp.hist_x_center, x_speed),
                    ("drag_hist_popup_xwidth", dsp.hist_x_range, x_speed),
                    ("drag_hist_popup_ymax", dsp.hist_y_max, y_speed),
                ):
                    if dpg.does_item_exist(tag) and not dpg.is_item_active(tag):
                        dpg.set_value(tag, val)
                        dpg.configure_item(tag, speed=spd)
                self._last_popup_image_id = image_id

        # Sync per-image button labels whenever UI refreshes (sidebar + popup)
        dsp = vs.display
        for tag, t_label, f_label, val in (
            ("btn_hist_bar",             "Line",  "Bar",  dsp.hist_use_bars),
            ("btn_hist_popup_bar",       "Line",  "Bar",  dsp.hist_use_bars),
            ("btn_hist_log",             "Lin",   "Log",  dsp.hist_use_log),
            ("btn_hist_popup_log",       "Lin",   "Log",  dsp.hist_use_log),
            ("btn_hist_auto_center",     "Auto*", "Auto", dsp.hist_auto_center),
            ("btn_hist_popup_auto_center","Auto*","Auto", dsp.hist_auto_center),
        ):
            if dpg.does_item_exist(tag):
                dpg.configure_item(tag, label=t_label if val else f_label)

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
        shade_val = [[lower, upper], [self._hist_max_y, self._hist_max_y], [0.0, 0.0]]
        if self._hist_max_y > 0 and dpg.does_item_exist("wl_hist_shade"):
            dpg.set_value("wl_hist_shade", shade_val)

        # Sync popup bars
        if dpg.does_item_exist("wl_hist_popup_lower"):
            dpg.set_value("wl_hist_popup_lower", lower)
            dpg.set_value("wl_hist_popup_upper", upper)
            if dpg.does_item_exist("wl_hist_popup_level"):
                dpg.set_value("wl_hist_popup_level", wl)
            if self._hist_max_y > 0 and dpg.does_item_exist("wl_hist_popup_shade"):
                dpg.set_value("wl_hist_popup_shade", shade_val)

        # Colormap scale bar in popup — redraw texture with WL-aware gradient
        if dpg.does_item_exist("wl_popup_colorscale_min") and dpg.does_item_exist("wl_popup_colorscale_max"):
            self._update_colorscale_texture(vs)
            dpg.set_value("wl_popup_colorscale_min", f"{lower:g}")
            dpg.set_value("wl_popup_colorscale_max", f"{upper:g}")

        # Trigger histogram compute when intensity tab becomes visible
        tab_shown = dpg.is_item_shown("tab_intensities")
        if tab_shown and not self._intensities_tab_was_shown:
            self.controller.ui_needs_refresh = True
        self._intensities_tab_was_shown = tab_shown

        # Auto-center per image preference
        dsp = vs.display
        if dsp.hist_auto_center:
            dsp.hist_x_center = wl

        # Keep drag float displays in sync (only when not being actively dragged)
        for tag, val in (
            ("drag_hist_xcenter", dsp.hist_x_center),
            ("drag_hist_popup_xcenter", dsp.hist_x_center),
            ("drag_hist_xwidth", dsp.hist_x_range),
            ("drag_hist_popup_xwidth", dsp.hist_x_range),
            ("drag_hist_ymax", dsp.hist_y_max),
            ("drag_hist_popup_ymax", dsp.hist_y_max),
        ):
            if val is not None and dpg.does_item_exist(tag) and not dpg.is_item_active(tag):
                dpg.set_value(tag, val)

        # Log-adaptive speed: update when not dragging so next drag starts correct
        x_range = dsp.hist_x_range
        if x_range and x_range > 0:
            center_speed = max(0.01, x_range * 0.005)
            for tag in ("drag_hist_xcenter", "drag_hist_popup_xcenter"):
                if dpg.does_item_exist(tag) and not dpg.is_item_active(tag):
                    dpg.configure_item(tag, speed=center_speed)
            for tag in ("drag_hist_xwidth", "drag_hist_popup_xwidth"):
                if dpg.does_item_exist(tag) and not dpg.is_item_active(tag):
                    cur = dpg.get_value(tag)
                    if cur and cur > 0:
                        dpg.configure_item(tag, speed=max(0.01, cur * 0.005))

        # Apply x limits last — must win over any scroll or series update that ran earlier this tick
        if dsp.hist_x_center is not None and dsp.hist_x_range is not None:
            self._apply_hist_x_limits(dsp)

    def _update_colorscale_texture(self, vs):
        # Ensure the texture exists before trying to update it
        if not dpg.does_item_exist("wl_colorscale_tex") or vs.display.hist_x_center is None:
            return
        dsp = vs.display
        view_center = dsp.hist_x_center if dsp.hist_x_center is not None else dsp.wl
        view_range = dsp.hist_x_range if dsp.hist_x_range is not None else (self._hist_max_x - self._hist_min_x)
        img_min = view_center - view_range / 2
        img_max = view_center + view_range / 2
        if img_max <= img_min:
            return
        cmap = COLORMAPS.get(vs.display.colormap, COLORMAPS["Grayscale"])
        wl, ww = vs.display.wl, vs.display.ww
        lower, upper = wl - ww / 2, wl + ww / 2
        x = np.linspace(img_min, img_max, 256, dtype=np.float32)
        t = np.clip((x - lower) / max(ww, 1e-10), 0.0, 1.0)
        idx = (t * 255).astype(np.int32)
        colors = cmap[idx].copy()
        colors[x < lower] = [0.0, 0.0, 0.0, 1.0]
        colors[x > upper] = [1.0, 1.0, 1.0, 1.0]
        dpg.set_value("wl_colorscale_tex", colors.flatten().tolist())

    def _apply_hist_x_limits(self, dsp):
        center = dsp.hist_x_center
        half = (dsp.hist_x_range or 1.0) / 2
        # Explicitly target both the sidebar and popup X-axes
        for axis in ["wl_hist_x_axis", "wl_hist_popup_x_axis"]:
            if dpg.does_item_exist(axis):
                dpg.set_axis_limits(axis, center - half, center + half)

    def _update_hist_series(self, series_tag, axis_tag, x_edges, x_centers, y_list, use_bars=False):
        # Update in-place when the series type matches — avoids DPG resetting
        # the x-axis to auto-fit mode, which would override set_axis_limits.
        if dpg.does_item_exist(series_tag):
            existing = dpg.get_item_type(series_tag)
            type_matches = ("BarSeries" in existing) == use_bars
            if type_matches:
                if use_bars:
                    dpg.set_value(series_tag, [x_centers, y_list])
                    dpg.configure_item(series_tag, weight=self._hist_bin_width)
                else:
                    dpg.set_value(series_tag, [x_edges, y_list])
                return
            dpg.delete_item(series_tag)

        if use_bars:
            dpg.add_bar_series(
                x_centers, y_list,
                weight=self._hist_bin_width,
                parent=axis_tag,
                tag=series_tag,
            )
        else:
            dpg.add_line_series(x_edges, y_list, parent=axis_tag, tag=series_tag)
        if dpg.does_item_exist("wl_hist_series_theme"):
            dpg.bind_item_theme(series_tag, "wl_hist_series_theme")

    def on_hist_xcenter_drag(self, _sender, app_data, _user_data):
        viewer = self.gui.context_viewer
        if not viewer or not viewer.view_state or app_data is None:
            return
        dsp = viewer.view_state.display
        dsp.hist_x_center = float(app_data)
        self._apply_hist_x_limits(dsp)

    def on_hist_xwidth_drag(self, _sender, app_data, _user_data):
        viewer = self.gui.context_viewer
        if not viewer or not viewer.view_state or app_data is None:
            return
        dsp = viewer.view_state.display
        dsp.hist_x_range = max(1e-5, float(app_data))
        self._apply_hist_x_limits(dsp)

    def on_hist_ymax_drag(self, _sender, app_data, _user_data):
        viewer = self.gui.context_viewer
        if not viewer or not viewer.view_state or app_data is None:
            return
        dsp = viewer.view_state.display
        dsp.hist_y_max = max(1e-5, float(app_data))
        for axis in ("wl_hist_y_axis", "wl_hist_popup_y_axis"):
            if dpg.does_item_exist(axis):
                dpg.set_axis_limits(axis, 0.0, dsp.hist_y_max)

    def on_hist_bar_toggle(self, _sender, _app_data, _user_data):
        viewer = self.gui.context_viewer
        if not viewer or not viewer.view_state:
            return
        dsp = viewer.view_state.display
        dsp.hist_use_bars = not dsp.hist_use_bars
        if dpg.does_item_exist("btn_hist_bar"):
            dpg.configure_item("btn_hist_bar", label="Line" if dsp.hist_use_bars else "Bar")
        for tag in ("drag_hist_popup_bins",):
            if dpg.does_item_exist(tag):
                dpg.configure_item(tag, show=dsp.hist_use_bars)
        viewer.view_state.histogram_is_dirty = True
        self.controller.ui_needs_refresh = True

    def on_hist_bins_drag(self, _sender, _app_data, _user_data):
        viewer = self.gui.context_viewer
        if not viewer or not viewer.view_state:
            return
        viewer.view_state.histogram_is_dirty = True
        self.controller.ui_needs_refresh = True

    def on_hist_log_toggle(self, _sender, _app_data, _user_data):
        viewer = self.gui.context_viewer
        if not viewer or not viewer.view_state:
            return
        dsp = viewer.view_state.display
        dsp.hist_use_log = not dsp.hist_use_log
        if dpg.does_item_exist("btn_hist_log"):
            dpg.configure_item("btn_hist_log", label="Lin" if dsp.hist_use_log else "Log")
        viewer.view_state.histogram_is_dirty = True
        self.controller.ui_needs_refresh = True

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

    def on_hist_center(self, _sender, _app_data, _user_data):
        viewer = self.gui.context_viewer
        if not viewer or not viewer.view_state:
            return
        dsp = viewer.view_state.display
        dsp.hist_x_center = float(dsp.wl)
        dsp.hist_x_range = dsp.ww * 4.0 / 3.0
        self._apply_hist_x_limits(dsp)
        for tag in ("drag_hist_xcenter", "drag_hist_popup_xcenter"):
            if dpg.does_item_exist(tag):
                dpg.set_value(tag, dsp.hist_x_center)
        for tag in ("drag_hist_xwidth", "drag_hist_popup_xwidth"):
            if dpg.does_item_exist(tag):
                dpg.set_value(tag, dsp.hist_x_range)

    def on_hist_auto_center(self, _sender, _app_data, _user_data):
        viewer = self.gui.context_viewer
        if not viewer or not viewer.view_state:
            return
        dsp = viewer.view_state.display
        dsp.hist_auto_center = not dsp.hist_auto_center
        if dpg.does_item_exist("btn_hist_auto_center"):
            dpg.configure_item(
                "btn_hist_auto_center",
                label="Auto*" if dsp.hist_auto_center else "Auto",
            )

    def on_hist_popup(self, _sender, _app_data, _user_data):
        popup_tag = "wl_hist_popup_win"
        if dpg.does_item_exist(popup_tag):
            cfg = dpg.get_item_configuration(popup_tag)
            dpg.configure_item(popup_tag, show=not cfg.get("show", True))
            return

        # Texture must live in the texture registry, not inside the window
        if not dpg.does_item_exist("wl_colorscale_tex"):
            dpg.add_dynamic_texture(
                width=256, height=1,
                default_value=[0.5] * (256 * 4),
                tag="wl_colorscale_tex",
                parent="global_texture_registry",
            )

        with dpg.window(label="Histogram", tag=popup_tag, width=700, height=560):
            with dpg.plot(
                tag="wl_hist_popup_plot",
                height=360,
                width=-1,
                no_title=True,
                no_mouse_pos=True,
            ):
                dpg.add_plot_axis(dpg.mvXAxis, tag="wl_hist_popup_x_axis")
                with dpg.plot_axis(
                    dpg.mvYAxis, tag="wl_hist_popup_y_axis", no_tick_labels=True
                ):
                    dpg.add_shade_series(
                        [0.0, 1.0], [1.0, 1.0], y2=[0.0, 0.0],
                        tag="wl_hist_popup_shade",
                    )
                    dpg.add_line_series([], [], tag="wl_hist_popup_series")
                dpg.add_drag_line(
                    tag="wl_hist_popup_lower",
                    color=[80, 160, 255, 255],
                    thickness=3.0,
                    callback=self.on_hist_popup_drag_lower,
                )
                dpg.add_drag_line(
                    tag="wl_hist_popup_upper",
                    color=[80, 160, 255, 255],
                    thickness=3.0,
                    callback=self.on_hist_popup_drag_upper,
                )
                dpg.add_drag_line(
                    tag="wl_hist_popup_level",
                    color=[255, 160, 40, 255],
                    thickness=3.0,
                    callback=self.on_hist_popup_drag_level,
                )

            # Colormap scale bar
            dpg.add_spacer(height=4)
            dpg.add_image(
                "wl_colorscale_tex",
                width=660, height=20,
                tag="wl_popup_colorscale_img",
            )
            with dpg.group(horizontal=True):
                dpg.add_text("---", tag="wl_popup_colorscale_min", color=[160, 160, 160, 255])
                arrow = dpg.add_text("", color=[160, 160, 160, 255])
                if dpg.does_item_exist("icon_font_tag"):
                    dpg.bind_item_font(arrow, "icon_font_tag")
                dpg.add_text("---", tag="wl_popup_colorscale_max", color=[160, 160, 160, 255])

            # Control buttons
            dpg.add_spacer(height=6)
            with dpg.group(horizontal=True):
                dpg.add_button(label="Ctr", width=42, callback=self.on_hist_center)
                dpg.add_button(label="Auto", width=46, tag="btn_hist_popup_auto_center", callback=self.on_hist_auto_center)
                dpg.add_button(label="Bar", width=38, tag="btn_hist_popup_bar", callback=self.on_hist_bar_toggle)
                dpg.add_button(label="Lin", width=34, tag="btn_hist_popup_log", callback=self.on_hist_log_toggle)
                dpg.add_drag_int(
                    tag="drag_hist_popup_bins", default_value=256, speed=2.0,
                    min_value=32, max_value=1024, format="%d bins",
                    width=80, show=False,
                    callback=self.on_hist_bins_drag,
                )
            dpg.add_spacer(height=4)
            with dpg.group(horizontal=True):
                dpg.add_text("C:")
                dpg.add_drag_float(
                    tag="drag_hist_popup_xcenter", default_value=0.0, speed=1.0,
                    min_value=-1e10, max_value=1e10, format="%.4g", width=110,
                    callback=self.on_hist_xcenter_drag,
                )
                dpg.add_text("W:")
                dpg.add_drag_float(
                    tag="drag_hist_popup_xwidth", default_value=1.0, speed=1.0,
                    min_value=1e-5, max_value=1e10, format="%.4g", width=110,
                    callback=self.on_hist_xwidth_drag,
                )
                dpg.add_text("Y:")
                dpg.add_drag_float(
                    tag="drag_hist_popup_ymax", default_value=1.0, speed=0.01,
                    min_value=1e-5, max_value=1e10, format="%.3g", width=-1,
                    callback=self.on_hist_ymax_drag,
                )

        dpg.bind_item_theme("wl_hist_popup_shade", "wl_shade_theme")

        viewer = self.gui.context_viewer
        if viewer and viewer.view_state and viewer.view_state.hist_data_x is not None:
            vs = viewer.view_state
            y_raw = vs.hist_data_y
            y_data = np.log10(y_raw + 1) if vs.use_log_y else y_raw
            x_edges = vs.hist_data_x
            x_centers = (x_edges + self._hist_bin_width / 2).tolist()
            self._update_hist_series(
                "wl_hist_popup_series", "wl_hist_popup_y_axis",
                x_edges.tolist(), x_centers, y_data.tolist(),
                use_bars=vs.display.hist_use_bars,
            )
            dpg.fit_axis_data("wl_hist_popup_y_axis")
            
            # Ensure popup initializes with the same view as the sidebar
            if vs.display.hist_x_center is not None and vs.display.hist_x_range is not None:
                self._apply_hist_x_limits(vs.display)
            else:
                # Fallback to current W/L window
                wl, ww = vs.display.wl, vs.display.ww
                margin = ww
                dpg.set_axis_limits("wl_hist_popup_x_axis", wl - margin, wl + margin)

            # Populate colorscale immediately
            self._update_colorscale_texture(vs)
            lower, upper = vs.display.wl - vs.display.ww / 2, vs.display.wl + vs.display.ww / 2
            dpg.set_value("wl_popup_colorscale_min", f"{lower:g}")
            dpg.set_value("wl_popup_colorscale_max", f"{upper:g}")

    def on_hist_popup_drag_lower(self, _sender, app_data, _user_data):
        pos = float(app_data) if app_data is not None else dpg.get_value("wl_hist_popup_lower")
        if pos is None:
            return
        viewer = self.gui.context_viewer
        if not viewer or not viewer.view_state:
            return
        wl = viewer.view_state.display.wl
        ww = max(1e-5, 2.0 * (wl - pos))
        viewer._mark_lazy_interaction()
        viewer.view_state.display.ww = ww
        dpg.set_value("drag_ww", ww)
        if dpg.does_item_exist("combo_wl_presets"):
            dpg.set_value("combo_wl_presets", "Custom")
        self.controller.sync.propagate_window_level(viewer.image_id)

    def on_hist_popup_drag_upper(self, _sender, app_data, _user_data):
        pos = float(app_data) if app_data is not None else dpg.get_value("wl_hist_popup_upper")
        if pos is None:
            return
        viewer = self.gui.context_viewer
        if not viewer or not viewer.view_state:
            return
        wl = viewer.view_state.display.wl
        ww = max(1e-5, 2.0 * (pos - wl))
        viewer._mark_lazy_interaction()
        viewer.view_state.display.ww = ww
        dpg.set_value("drag_ww", ww)
        if dpg.does_item_exist("combo_wl_presets"):
            dpg.set_value("combo_wl_presets", "Custom")
        self.controller.sync.propagate_window_level(viewer.image_id)

    def on_hist_popup_drag_level(self, _sender, app_data, _user_data):
        pos = float(app_data) if app_data is not None else dpg.get_value("wl_hist_popup_level")
        if pos is None:
            return
        viewer = self.gui.context_viewer
        if not viewer or not viewer.view_state:
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
