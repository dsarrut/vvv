import dearpygui.dearpygui as dpg
from vvv.config import WL_PRESETS, COLORMAPS
from vvv.ui.ui_components import (
    build_stepped_slider,
    build_section_title,
    build_help_button,
    build_beginner_tooltip,
    build_tooltip,
    build_icon_button,
    label_row,
    FIELD_RIGHT_MARGIN,
    LABEL_COL_W,
    SMALL_BTN_W,
)
from .control_intensity import IntensityController
from vvv.plugins.plugin_api import PluginTagMixin

HIST_BTN_W = SMALL_BTN_W  # Ctr / Bar-Line / Lin-Log: fits the longer labels ("Line")


class IntensityUI(PluginTagMixin):
    def __init__(self, plugin_id: str, controller: IntensityController):
        self._plugin_id = plugin_id
        self._c = controller
        self._api = None

    def create_ui(self, parent, api) -> None:
        self._api = api
        cfg_c = api.get_ui_config()["colors"]

        with dpg.group(parent=parent or 0, tag=self._plugin_id):
            build_section_title("Window / Level", cfg_c["text_header"])

            dpg.add_text(
                "No Image Selected",
                tag=self._t("active_title"),
                color=cfg_c["text_active"],
            )

            with label_row("Preset", LABEL_COL_W):
                dpg.add_combo(
                    list(WL_PRESETS.keys()) + ["Custom"],
                    default_value="Custom",
                    tag=self._t("combo_wl_presets"),
                    width=-FIELD_RIGHT_MARGIN,
                    callback=self._c.on_preset_changed,
                )

            build_stepped_slider(
                "Window",
                self._t("drag_ww"),
                callback=self._c.on_ww_changed,
                step_callback=self._c.on_step_button_clicked,
                min_val=1e-5,
                help_text="Window / Level controls image contrast and brightness.\nWindow: The range of visible values.\nLevel: The center point of the visible range.",
                gui=api,
                label_col=LABEL_COL_W,
            )
            build_stepped_slider(
                "Level",
                self._t("drag_wl"),
                callback=self._c.on_wl_changed,
                step_callback=self._c.on_step_button_clicked,
                gui=api,
                label_col=LABEL_COL_W,
            )

            with label_row("Map", LABEL_COL_W):
                dpg.add_combo(
                    list(COLORMAPS.keys()),
                    default_value="Grayscale",
                    tag=self._t("combo_colormap"),
                    width=-FIELD_RIGHT_MARGIN,
                    callback=self._c.on_colormap_changed,
                )

            build_stepped_slider(
                "Min Thr",
                self._t("drag_min_threshold"),
                callback=self._c.on_threshold_changed,
                step_callback=self._c.on_step_button_clicked,
                has_checkbox=True,
                check_tag=self._t("check_min_threshold"),
                check_cb=self._c.on_threshold_toggle,
                help_text="Pixels below this threshold value are rendered completely transparent.",
                gui=api,
                label_col=LABEL_COL_W,
            )

            dpg.add_spacer(height=5)
            with dpg.group(horizontal=True):
                dpg.add_text("Image Range:", color=cfg_c["text_dim"])
                dpg.add_text("---", tag=self._t("minmax"))

            dpg.add_spacer(height=4)
            with dpg.plot(
                tag=self._t("wl_hist_plot"),
                height=120,
                width=-FIELD_RIGHT_MARGIN,
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
                btn_ctr = dpg.add_button(
                    label="Ctr", width=HIST_BTN_W, tag=self._t("btn_hist_center"),
                    callback=self._c.on_hist_center,
                )
                build_beginner_tooltip(btn_ctr, "Center histogram view around current W/L window", api)
                btn_bar = dpg.add_button(
                    label="Bar", width=HIST_BTN_W, tag=self._t("btn_hist_bar"),
                    callback=self._c.on_hist_bar_toggle,
                )
                build_beginner_tooltip(btn_bar, "Histogram style (Bar / Line): click to switch", api)
                btn_lin = dpg.add_button(
                    label="Log", width=HIST_BTN_W, tag=self._t("btn_hist_log"),
                    callback=self._c.on_hist_log_toggle,
                )
                build_beginner_tooltip(btn_lin, "Frequency scale (Lin / Log): click to switch", api)
                build_icon_button(
                    icon="\uf35d",
                    tag=self._t("btn_hist_popup"),
                    callback=self._c.on_hist_popup,
                    tooltip="Open standalone floating histogram window",
                    gui=api,
                )
                dpg.add_text(
                    "computing full histogram",
                    tag=self._t("txt_computing_full_hist"),
                    color=[255, 160, 40, 255],
                    show=False,
                )
                build_help_button(
                    "Histogram — intensity distribution of the image.\n\n"
                    "Drag the blue lines to set the Window (lower / upper bounds).\n"
                    "Drag the orange line to move the Level (center brightness).\n\n"
                    "Ctr: Center the histogram view on the current Window/Level.\n"
                    "Bar / Line: Current histogram style; click to switch.\n"
                    "Lin / Log: Current Y scale (linear or log); click to switch.\n"
                    ": Open in a larger floating window.",
                    api,
                )
            # Histogram view: one row per value, aligned with the rows above
            for label, suffix, default, speed, vmin, cb, tip in (
                ("X center", "xcenter", 0.0, 1.0, -1e10, self._c.on_hist_xcenter_drag,
                 "X-axis center of the histogram view."),
                ("X width", "xwidth", 1.0, 1.0, 1e-5, self._c.on_hist_xwidth_drag,
                 "Width (zoom) of the histogram X axis."),
                ("Y max", "ymax", 1.0, 0.01, 1e-5, self._c.on_hist_ymax_drag,
                 "Maximum visible height of the histogram Y axis."),
            ):
                with label_row(label, LABEL_COL_W, color=cfg_c["text_dim"]):
                    dpg.add_drag_float(
                        tag=self._t(f"drag_hist_{suffix}"), default_value=default, speed=speed,
                        min_value=vmin, max_value=1e10, format="%.5g",
                        width=-FIELD_RIGHT_MARGIN, callback=cb,
                    )
                build_beginner_tooltip(self._t(f"drag_hist_{suffix}"), tip, api)

            shade_theme = self._t("wl_shade_theme")
            if not dpg.does_item_exist(shade_theme):
                with dpg.theme(tag=shade_theme):
                    with dpg.theme_component(dpg.mvShadeSeries):
                        dpg.add_theme_color(
                            dpg.mvPlotCol_Fill, [100, 180, 255, 30],
                            category=dpg.mvThemeCat_Plots,
                        )
                        dpg.add_theme_color(
                            dpg.mvPlotCol_Line, [0, 0, 0, 0],
                            category=dpg.mvThemeCat_Plots,
                        )
            dpg.bind_item_theme(self._t("wl_hist_shade"), shade_theme)

            series_theme = self._t("wl_hist_series_theme")
            if not dpg.does_item_exist(series_theme):
                with dpg.theme(tag=series_theme):
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
            dpg.bind_item_theme(self._t("wl_hist_series"), series_theme)

    def create_popup_ui(self, api, image_id: str) -> None:
        popup_tag = self._t(f"wl_hist_popup_win_{image_id}")
        if dpg.does_item_exist(popup_tag):
            cfg = dpg.get_item_configuration(popup_tag)
            dpg.configure_item(popup_tag, show=not cfg.get("show", True))
            return

        hs = self._c._hist.get(image_id)
        use_bars = hs.use_bars if hs else False

        tex_tag = self._t(f"wl_colorscale_tex_{image_id}")
        if not dpg.does_item_exist(tex_tag):
            dpg.add_dynamic_texture(
                width=256, height=1,
                default_value=[0.5] * (256 * 4),
                tag=tex_tag,
                parent="global_texture_registry",
            )

        image_name, _ = api.get_image_display_name(image_id)
        with dpg.window(label=f"Histogram {image_name}", tag=popup_tag, width=700, height=560):
            with dpg.plot(
                tag=self._t(f"wl_hist_popup_plot_{image_id}"),
                height=360,
                width=-1,
                no_title=True,
                no_mouse_pos=True,
            ):
                dpg.add_plot_axis(dpg.mvXAxis, tag=self._t(f"wl_hist_popup_x_axis_{image_id}"))
                with dpg.plot_axis(
                    dpg.mvYAxis, tag=self._t(f"wl_hist_popup_y_axis_{image_id}"), no_tick_labels=True
                ):
                    dpg.add_shade_series(
                        [0.0, 1.0], [1.0, 1.0], y2=[0.0, 0.0],
                        tag=self._t(f"wl_hist_popup_shade_{image_id}"),
                    )
                    dpg.add_line_series([], [], tag=self._t(f"wl_hist_popup_series_{image_id}"))
                dpg.add_drag_line(
                    tag=self._t(f"wl_hist_popup_lower_{image_id}"),
                    color=[80, 160, 255, 255],
                    thickness=3.0,
                    callback=self._c.on_hist_popup_drag_lower,
                    user_data=image_id,
                )
                dpg.add_drag_line(
                    tag=self._t(f"wl_hist_popup_upper_{image_id}"),
                    color=[80, 160, 255, 255],
                    thickness=3.0,
                    callback=self._c.on_hist_popup_drag_upper,
                    user_data=image_id,
                )
                dpg.add_drag_line(
                    tag=self._t(f"wl_hist_popup_level_{image_id}"),
                    color=[255, 160, 40, 255],
                    thickness=3.0,
                    callback=self._c.on_hist_popup_drag_level,
                    user_data=image_id,
                )

            # Colormap scale bar
            dpg.add_spacer(height=4)
            dpg.add_image(
                tex_tag,
                width=660, height=20,
                tag=self._t(f"wl_popup_colorscale_img_{image_id}"),
            )
            with dpg.group(horizontal=True):
                dpg.add_text("---", tag=self._t(f"wl_popup_colorscale_min_{image_id}"), color=[160, 160, 160, 255])
                arrow = dpg.add_text("", color=[160, 160, 160, 255])
                if dpg.does_item_exist("icon_font_tag"):
                    dpg.bind_item_font(arrow, "icon_font_tag")
                dpg.add_text("---", tag=self._t(f"wl_popup_colorscale_max_{image_id}"), color=[160, 160, 160, 255])

            # Control buttons
            dpg.add_spacer(height=6)
            with dpg.group(horizontal=True):
                dpg.add_button(label="Ctr", width=HIST_BTN_W, callback=self._c.on_hist_center, user_data=image_id)
                dpg.add_button(label="Bar", width=HIST_BTN_W, tag=self._t(f"btn_hist_popup_bar_{image_id}"), callback=self._c.on_hist_bar_toggle, user_data=image_id)
                dpg.add_button(label="Log", width=HIST_BTN_W, tag=self._t(f"btn_hist_popup_log_{image_id}"), callback=self._c.on_hist_log_toggle, user_data=image_id)
                dpg.add_drag_int(
                    tag=self._t(f"drag_hist_popup_bins_{image_id}"), default_value=256, speed=2.0,
                    min_value=32, max_value=1024, format="%d bins",
                    width=110, show=use_bars,
                    callback=self._c.on_hist_bins_drag,
                    user_data=image_id,
                )
                dpg.add_text(
                    "computing full histogram",
                    tag=self._t(f"txt_popup_computing_full_hist_{image_id}"),
                    color=[255, 160, 40, 255],
                    show=False,
                )
                build_help_button(
                    "Histogram — intensity distribution of the image.\n\n"
                    "Drag the blue lines to set the Window (lower / upper bounds).\n"
                    "Drag the orange line to move the Level (center brightness).\n\n"
                    "Ctr: Center the view on the current Window/Level.\n"
                    "Bar / Line: Current histogram style; click to switch.\n"
                    "Lin / Log: Current Y scale (linear or log); click to switch.\n"
                    "Bins: Number of histogram bins (bar mode only).",
                    api,
                )
            dpg.add_spacer(height=4)
            with dpg.group(horizontal=True):
                c_lbl = dpg.add_text("X center:")
                build_beginner_tooltip(c_lbl, "C — X-axis center of the histogram view.", api)
                dpg.add_drag_float(
                    tag=self._t(f"drag_hist_popup_xcenter_{image_id}"), default_value=0.0, speed=1.0,
                    min_value=-1e10, max_value=1e10, format="%.5g", width=110,
                    callback=self._c.on_hist_xcenter_drag,
                    user_data=image_id,
                )
                w_lbl = dpg.add_text("X width:")
                build_beginner_tooltip(w_lbl, "W — Width (zoom) of the histogram X axis.", api)
                dpg.add_drag_float(
                    tag=self._t(f"drag_hist_popup_xwidth_{image_id}"), default_value=1.0, speed=1.0,
                    min_value=1e-5, max_value=1e10, format="%.5g", width=110,
                    callback=self._c.on_hist_xwidth_drag,
                    user_data=image_id,
                )
                y_lbl = dpg.add_text("Y max:")
                build_beginner_tooltip(y_lbl, "Y — Maximum visible height of the histogram Y axis.", api)
                dpg.add_drag_float(
                    tag=self._t(f"drag_hist_popup_ymax_{image_id}"), default_value=1.0, speed=0.01,
                    min_value=1e-5, max_value=1e10, format="%.5g", width=110,
                    callback=self._c.on_hist_ymax_drag,
                    user_data=image_id,
                )

        dpg.bind_item_theme(self._t(f"wl_hist_popup_shade_{image_id}"), self._t("wl_shade_theme"))
        dpg.bind_item_theme(self._t(f"wl_hist_popup_series_{image_id}"), self._t("wl_hist_series_theme"))

        # Position the window at the bottom right of the viewport
        vp_w = dpg.get_viewport_client_width()
        vp_h = dpg.get_viewport_client_height()
        win_w, win_h = 700, 560
        dpg.set_item_pos(
            popup_tag, [max(10, vp_w - win_w - 20), max(10, vp_h - win_h - 40)]
        )

