import dearpygui.dearpygui as dpg
from vvv.config import WL_PRESETS, COLORMAPS
from vvv.ui.ui_components import build_stepped_slider, build_section_title, build_help_button, build_beginner_tooltip
from .control_intensity import IntensityController


class IntensityUI:
    def __init__(self, plugin_id: str, controller: IntensityController):
        self._plugin_id = plugin_id
        self._c = controller

    def _t(self, name: str) -> str:
        return f"{self._plugin_id}_{name}"

    def create_ui(self, parent, api) -> None:
        cfg_c = api.get_ui_config()["colors"]

        with dpg.group(parent=parent or 0, tag=self._plugin_id):
            build_section_title("Window / Level", cfg_c["text_header"])

            dpg.add_text(
                "No Image Selected",
                tag=self._t("active_title"),
                color=cfg_c["text_active"],
            )

            with dpg.group(horizontal=True):
                dpg.add_text("Preset: ")
                dpg.add_combo(
                    list(WL_PRESETS.keys()) + ["Custom"],
                    default_value="Custom",
                    tag=self._t("combo_wl_presets"),
                    width=-1,
                    callback=self._c.on_preset_changed,
                )

            build_stepped_slider(
                "Window: ",
                self._t("drag_ww"),
                callback=self._c.on_ww_changed,
                step_callback=self._c.on_step_button_clicked,
                min_val=1e-5,
                help_text="Window / Level controls image contrast and brightness.\nWindow: The range of visible values.\nLevel: The center point of the visible range.",
                gui=api,
            )
            build_stepped_slider(
                "Level:  ",
                self._t("drag_wl"),
                callback=self._c.on_wl_changed,
                step_callback=self._c.on_step_button_clicked,
            )

            with dpg.group(horizontal=True):
                dpg.add_text("Map:    ")
                dpg.add_combo(
                    list(COLORMAPS.keys()),
                    default_value="Grayscale",
                    tag=self._t("combo_colormap"),
                    width=-1,
                    callback=self._c.on_colormap_changed,
                )

            build_stepped_slider(
                "Min Thr:",
                self._t("drag_min_threshold"),
                callback=self._c.on_threshold_changed,
                step_callback=self._c.on_step_button_clicked,
                has_checkbox=True,
                check_tag=self._t("check_min_threshold"),
                check_cb=self._c.on_threshold_toggle,
                help_text="Pixels below this threshold value are rendered completely transparent.",
                gui=api,
            )

            dpg.add_spacer(height=5)
            with dpg.group(horizontal=True):
                dpg.add_text("Image Range:", color=cfg_c["text_dim"])
                dpg.add_text("---", tag=self._t("minmax"))

            dpg.add_spacer(height=4)
            with dpg.plot(
                tag=self._t("wl_hist_plot"),
                height=120,
                width=-1,
                no_title=True,
                no_mouse_pos=True,
                no_box_select=True,
                zoom_mod=dpg.mvKey_ModCtrl,
                show=False,
            ):
                dpg.add_plot_axis(dpg.mvXAxis, tag=self._t("wl_hist_x_axis"))
                with dpg.plot_axis(dpg.mvYAxis, tag=self._t("wl_hist_y_axis"), no_tick_labels=True):
                    dpg.add_shade_series(
                        [0.0, 1.0], [1.0, 1.0], y2=[0.0, 0.0],
                        tag=self._t("wl_hist_shade"),
                    )
                    dpg.add_line_series([], [], tag=self._t("wl_hist_series"))
                dpg.add_drag_line(
                    tag=self._t("wl_hist_lower"),
                    color=[80, 160, 255, 255],
                    thickness=3.0,
                    default_value=0.0,
                    callback=self._c.on_hist_drag_lower,
                )
                dpg.add_drag_line(
                    tag=self._t("wl_hist_upper"),
                    color=[80, 160, 255, 255],
                    thickness=3.0,
                    default_value=1.0,
                    callback=self._c.on_hist_drag_upper,
                )
                dpg.add_drag_line(
                    tag=self._t("wl_hist_level"),
                    color=[255, 160, 40, 255],
                    thickness=3.0,
                    default_value=0.5,
                    callback=self._c.on_hist_drag_level,
                )

            dpg.add_spacer(height=2)
            with dpg.group(horizontal=True):
                dpg.add_button(
                    label="Ctr", width=36, tag=self._t("btn_hist_center"),
                    callback=self._c.on_hist_center,
                )
                dpg.add_button(
                    label="Bar", width=34, tag=self._t("btn_hist_bar"),
                    callback=self._c.on_hist_bar_toggle,
                )
                dpg.add_button(
                    label="Lin", width=30, tag=self._t("btn_hist_log"),
                    callback=self._c.on_hist_log_toggle,
                )
                btn_popup = dpg.add_button(
                    label="", tag=self._t("btn_hist_popup"),
                    callback=self._c.on_hist_popup,
                )
                if dpg.does_item_exist("icon_font_tag"):
                    dpg.bind_item_font(btn_popup, "icon_font_tag")
                build_help_button(
                    "Histogram — intensity distribution of the image.\n\n"
                    "Drag the blue lines to set the Window (lower / upper bounds).\n"
                    "Drag the orange line to move the Level (center brightness).\n\n"
                    "Ctr: Center the histogram view on the current Window/Level.\n"
                    "Auto: Keep the view centered automatically as you drag.\n"
                    "Bar / Line: Toggle bar vs. line histogram style.\n"
                    "Lin / Log: Toggle linear vs. logarithmic Y axis.\n"
                    ": Open in a larger floating window.",
                    api,
                )
            with dpg.group(horizontal=True):
                c_lbl = dpg.add_text("C:", color=cfg_c["text_dim"])
                build_beginner_tooltip(c_lbl, "C — X-axis center of the histogram view.", api)
                dpg.add_drag_float(
                    tag=self._t("drag_hist_xcenter"), default_value=0.0, speed=1.0,
                    min_value=-1e10, max_value=1e10, format="%.4g", width=65,
                    callback=self._c.on_hist_xcenter_drag,
                )
                w_lbl = dpg.add_text("W:", color=cfg_c["text_dim"])
                build_beginner_tooltip(w_lbl, "W — Width (zoom) of the histogram X axis.", api)
                dpg.add_drag_float(
                    tag=self._t("drag_hist_xwidth"), default_value=1.0, speed=1.0,
                    min_value=1e-5, max_value=1e10, format="%.3g", width=60,
                    callback=self._c.on_hist_xwidth_drag,
                )
                y_lbl = dpg.add_text("Y:", color=cfg_c["text_dim"])
                build_beginner_tooltip(y_lbl, "Y — Maximum visible height of the histogram Y axis.", api)
                dpg.add_drag_float(
                    tag=self._t("drag_hist_ymax"), default_value=1.0, speed=0.01,
                    min_value=1e-5, max_value=1e10, format="%.2g", width=-1,
                    callback=self._c.on_hist_ymax_drag,
                )

            with dpg.theme(tag=self._t("wl_shade_theme")):
                with dpg.theme_component(dpg.mvShadeSeries):
                    dpg.add_theme_color(
                        dpg.mvPlotCol_Fill, [100, 180, 255, 30],
                        category=dpg.mvThemeCat_Plots,
                    )
                    dpg.add_theme_color(
                        dpg.mvPlotCol_Line, [0, 0, 0, 0],
                        category=dpg.mvThemeCat_Plots,
                    )
            dpg.bind_item_theme(self._t("wl_hist_shade"), self._t("wl_shade_theme"))

            with dpg.theme(tag=self._t("wl_hist_series_theme")):
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
            dpg.bind_item_theme(self._t("wl_hist_series"), self._t("wl_hist_series_theme"))

    def create_popup_ui(self, api) -> None:
        popup_tag = self._t("wl_hist_popup_win")
        if dpg.does_item_exist(popup_tag):
            cfg = dpg.get_item_configuration(popup_tag)
            dpg.configure_item(popup_tag, show=not cfg.get("show", True))
            return

        viewer = api.get_active_viewer()
        use_bars = False
        if viewer and viewer.view_state:
            use_bars = getattr(viewer.view_state.display, "hist_use_bars", False)

        tex_tag = self._t("wl_colorscale_tex")
        if not dpg.does_item_exist(tex_tag):
            dpg.add_dynamic_texture(
                width=256, height=1,
                default_value=[0.5] * (256 * 4),
                tag=tex_tag,
                parent="global_texture_registry",
            )

        with dpg.window(label="Histogram", tag=popup_tag, width=700, height=560):
            with dpg.plot(
                tag=self._t("wl_hist_popup_plot"),
                height=360,
                width=-1,
                no_title=True,
                no_mouse_pos=True,
            ):
                dpg.add_plot_axis(dpg.mvXAxis, tag=self._t("wl_hist_popup_x_axis"))
                with dpg.plot_axis(
                    dpg.mvYAxis, tag=self._t("wl_hist_popup_y_axis"), no_tick_labels=True
                ):
                    dpg.add_shade_series(
                        [0.0, 1.0], [1.0, 1.0], y2=[0.0, 0.0],
                        tag=self._t("wl_hist_popup_shade"),
                    )
                    dpg.add_line_series([], [], tag=self._t("wl_hist_popup_series"))
                dpg.add_drag_line(
                    tag=self._t("wl_hist_popup_lower"),
                    color=[80, 160, 255, 255],
                    thickness=3.0,
                    callback=self._c.on_hist_popup_drag_lower,
                )
                dpg.add_drag_line(
                    tag=self._t("wl_hist_popup_upper"),
                    color=[80, 160, 255, 255],
                    thickness=3.0,
                    callback=self._c.on_hist_popup_drag_upper,
                )
                dpg.add_drag_line(
                    tag=self._t("wl_hist_popup_level"),
                    color=[255, 160, 40, 255],
                    thickness=3.0,
                    callback=self._c.on_hist_popup_drag_level,
                )

            # Colormap scale bar
            dpg.add_spacer(height=4)
            dpg.add_image(
                tex_tag,
                width=660, height=20,
                tag=self._t("wl_popup_colorscale_img"),
            )
            with dpg.group(horizontal=True):
                dpg.add_text("---", tag=self._t("wl_popup_colorscale_min"), color=[160, 160, 160, 255])
                arrow = dpg.add_text("", color=[160, 160, 160, 255])
                if dpg.does_item_exist("icon_font_tag"):
                    dpg.bind_item_font(arrow, "icon_font_tag")
                dpg.add_text("---", tag=self._t("wl_popup_colorscale_max"), color=[160, 160, 160, 255])

            # Control buttons
            dpg.add_spacer(height=6)
            with dpg.group(horizontal=True):
                dpg.add_button(label="Ctr", width=42, callback=self._c.on_hist_center)
                dpg.add_button(label="Bar", width=38, tag=self._t("btn_hist_popup_bar"), callback=self._c.on_hist_bar_toggle)
                dpg.add_button(label="Lin", width=34, tag=self._t("btn_hist_popup_log"), callback=self._c.on_hist_log_toggle)
                dpg.add_drag_int(
                    tag=self._t("drag_hist_popup_bins"), default_value=256, speed=2.0,
                    min_value=32, max_value=1024, format="%d bins",
                    width=80, show=use_bars,
                    callback=self._c.on_hist_bins_drag,
                )
                build_help_button(
                    "Histogram — intensity distribution of the image.\n\n"
                    "Drag the blue lines to set the Window (lower / upper bounds).\n"
                    "Drag the orange line to move the Level (center brightness).\n\n"
                    "Ctr: Center the view on the current Window/Level.\n"
                    "Auto: Keep the view centered automatically as you drag.\n"
                    "Bar / Line: Toggle bar vs. line histogram style.\n"
                    "Lin / Log: Toggle linear vs. logarithmic Y axis.\n"
                    "Bins: Number of histogram bins (bar mode only).",
                    api,
                )
            dpg.add_spacer(height=4)
            with dpg.group(horizontal=True):
                c_lbl = dpg.add_text("C:")
                build_beginner_tooltip(c_lbl, "C — X-axis center of the histogram view.", api)
                dpg.add_drag_float(
                    tag=self._t("drag_hist_popup_xcenter"), default_value=0.0, speed=1.0,
                    min_value=-1e10, max_value=1e10, format="%.4g", width=110,
                    callback=self._c.on_hist_xcenter_drag,
                )
                w_lbl = dpg.add_text("W:")
                build_beginner_tooltip(w_lbl, "W — Width (zoom) of the histogram X axis.", api)
                dpg.add_drag_float(
                    tag=self._t("drag_hist_popup_xwidth"), default_value=1.0, speed=1.0,
                    min_value=1e-5, max_value=1e10, format="%.4g", width=110,
                    callback=self._c.on_hist_xwidth_drag,
                )
                y_lbl = dpg.add_text("Y:")
                build_beginner_tooltip(y_lbl, "Y — Maximum visible height of the histogram Y axis.", api)
                dpg.add_drag_float(
                    tag=self._t("drag_hist_popup_ymax"), default_value=1.0, speed=0.01,
                    min_value=1e-5, max_value=1e10, format="%.3g", width=-1,
                    callback=self._c.on_hist_ymax_drag,
                )

        dpg.bind_item_theme(self._t("wl_hist_popup_shade"), self._t("wl_shade_theme"))
        dpg.bind_item_theme(self._t("wl_hist_popup_series"), self._t("wl_hist_series_theme"))

        # Position the window at the bottom right of the viewport
        vp_w = dpg.get_viewport_client_width()
        vp_h = dpg.get_viewport_client_height()
        win_w, win_h = 700, 560
        dpg.set_item_pos(
            popup_tag, [max(10, vp_w - win_w - 20), max(10, vp_h - win_h - 40)]
        )

