import threading
import numpy as np
import dearpygui.dearpygui as dpg
from vvv.plugins.plugin_api import PluginAPI
from vvv.config import WL_PRESETS, COLORMAPS


class HistogramState:
    """Per-image histogram view preferences, owned by the intensity plugin."""

    def __init__(self):
        self.use_bars: bool = True
        self.use_log: bool = True
        self.bins: int = 256
        self.x_center: float | None = None
        self.x_range: float | None = None
        self.y_max: float | None = None
        self._vol_data_id: int | None = None  # change-detection cache


class IntensityController:
    def __init__(self, plugin_id: str):
        self._plugin_id = plugin_id
        self._api = None
        self._ui = None

        # State caches for rendering optimization
        self._minmax_cache = {}
        self._last_sidebar_image_id = None
        self._last_popup_image_id = None
        self._last_colorscale_state = None

        # Per-image histogram view state (created in on_image_loaded)
        self._hist: dict[str, HistogramState] = {}

        # Stop event for the background histogram thread
        self._hist_stop = threading.Event()

    def _t(self, name: str) -> str:
        return f"{self._plugin_id}_{name}"

    def _hs(self, viewer) -> HistogramState | None:
        """Return the HistogramState for the viewer's current image, or None."""
        if viewer and viewer.image_id:
            return self._hist.get(viewer.image_id)
        return None

    @staticmethod
    def _compute_max_y(hist_data_y, use_log: bool) -> float:
        if hist_data_y is None or len(hist_data_y) == 0:
            return 1.0
        if use_log:
            return float(np.max(np.log10(hist_data_y + 1)))
        return float(np.max(hist_data_y))

    def bind(self, api: PluginAPI) -> None:
        self._api = api

    def bind_ui(self, ui) -> None:
        self._ui = ui

    def update(self, api: PluginAPI) -> None:
        viewer = api.get_active_viewer()
        has_image = bool(viewer and viewer.view_state and viewer.volume)

        # Update the active image title
        active_title = self._t("active_title")
        if dpg.does_item_exist(active_title):
            if has_image:
                name_str, is_outdated = api.get_image_display_name(viewer.image_id)
                color_key = "outdated" if is_outdated else "text_active"
            else:
                name_str, color_key = "No Image Selected", "text_active"
            dpg.set_value(active_title, name_str)
            dpg.configure_item(
                active_title, color=api.get_ui_config()["colors"][color_key]
            )

        is_rgb = viewer.volume.is_rgb if has_image else False
        thr = viewer.view_state.display.base_threshold if has_image else None
        has_thr = thr is not None

        # Enable/disable controls
        tags = [
            self._t("combo_wl_presets"),
            self._t("drag_ww"),
            self._t("drag_wl"),
            self._t("combo_colormap"),
        ]
        for t in tags:
            if dpg.does_item_exist(t):
                dpg.configure_item(t, enabled=(has_image and not is_rgb))

        check_tag = self._t("check_min_threshold")
        if dpg.does_item_exist(check_tag):
            dpg.set_value(check_tag, has_thr)
            dpg.configure_item(check_tag, enabled=(has_image and not is_rgb))

        drag_thr_tag = self._t("drag_min_threshold")
        if dpg.does_item_exist(drag_thr_tag):
            if has_thr and not dpg.is_item_active(drag_thr_tag):
                dpg.set_value(drag_thr_tag, thr)

            thr_enabled = has_image and not is_rgb and has_thr
            dpg.configure_item(drag_thr_tag, enabled=thr_enabled)

            btn_minus = f"btn_{drag_thr_tag}_minus"
            if dpg.does_item_exist(btn_minus):
                dpg.configure_item(btn_minus, enabled=thr_enabled)

            btn_plus = f"btn_{drag_thr_tag}_plus"
            if dpg.does_item_exist(btn_plus):
                dpg.configure_item(btn_plus, enabled=thr_enabled)

        # Update Image Range
        minmax_tag = self._t("minmax")
        if dpg.does_item_exist(minmax_tag):
            if not has_image or is_rgb:
                dpg.set_value(minmax_tag, "---")
            else:
                vol = viewer.volume
                current_data_id = id(vol.data)
                if current_data_id not in self._minmax_cache:
                    self._minmax_cache = {
                        current_data_id: (
                            float(np.min(vol.data)),
                            float(np.max(vol.data)),
                        )
                    }
                min_v, max_v = self._minmax_cache[current_data_id]
                dpg.set_value(minmax_tag, f"{min_v:g} to {max_v:g}")

        # Dynamically scale the slider drag speed based on the current window width
        ww_val = (
            getattr(viewer.view_state.display, "ww", 1.0)
            if has_image and viewer.view_state
            else 1.0
        )
        if ww_val is None:
            ww_val = 1.0
        dynamic_speed = max(0.1, ww_val * 0.005)
        for t in [
            self._t("drag_ww"),
            self._t("drag_wl"),
            self._t("drag_min_threshold"),
        ]:
            if dpg.does_item_exist(t):
                dpg.configure_item(t, speed=dynamic_speed)

        # Sync numerical inputs and lines
        if has_image and not is_rgb:
            vs = viewer.view_state

            # Sync drag sliders
            ww_tag = self._t("drag_ww")
            if dpg.does_item_exist(ww_tag) and not dpg.is_item_active(ww_tag):
                dpg.set_value(ww_tag, vs.display.ww)
            wl_tag = self._t("drag_wl")
            if dpg.does_item_exist(wl_tag) and not dpg.is_item_active(wl_tag):
                dpg.set_value(wl_tag, vs.display.wl)

            # Sync Colormap combo
            cmap_tag = self._t("combo_colormap")
            if dpg.does_item_exist(cmap_tag) and not dpg.is_item_active(cmap_tag):
                dpg.set_value(cmap_tag, vs.display.colormap)

            # Sync Preset combo
            preset_tag = self._t("combo_wl_presets")
            if dpg.does_item_exist(preset_tag) and not dpg.is_item_active(
                preset_tag
            ):
                matched = False
                for p_name, p_val in WL_PRESETS.items():
                    if p_val is not None:
                        if (
                            abs(vs.display.ww - p_val["ww"]) < 1e-3
                            and abs(vs.display.wl - p_val["wl"]) < 1e-3
                        ):
                            dpg.set_value(preset_tag, p_name)
                            matched = True
                            break
                if not matched:
                    cur_preset = dpg.get_value(preset_tag)
                    if cur_preset not in ["Custom", "Optimal", "Min/Max"]:
                        dpg.set_value(preset_tag, "Custom")

            # Sync lines and plots
            self.sync_wl_lines(viewer, vs)

        # Refresh histogram
        self._refresh_wl_histogram(viewer, has_image, is_rgb)

    def _refresh_wl_histogram(self, viewer, has_image, is_rgb):
        plot_tag = self._t("wl_hist_plot")
        if not dpg.does_item_exist(plot_tag):
            return

        if not has_image or is_rgb:
            dpg.configure_item(plot_tag, show=False)
            return

        hs = self._hs(viewer)
        if hs is None:
            return

        vs = viewer.view_state

        # Detect volume data changes (image reload from disk replaces the array object)
        current_data_id = id(viewer.volume.data)
        if hs._vol_data_id != current_data_id:
            vs.histogram_is_dirty = True
            hs._vol_data_id = current_data_id

        # Lazy: only compute if the sidebar tab OR the floating popup is visible
        sidebar_visible = dpg.is_item_shown(self._plugin_id)
        popup_win = self._t("wl_hist_popup_win")
        popup_visible = dpg.does_item_exist(popup_win) and dpg.is_item_shown(popup_win)

        if vs.histogram_is_dirty and not sidebar_visible and not popup_visible:
            return

        image_id = getattr(viewer, "image_id", None)
        popup_series = self._t("wl_hist_popup_series")
        popup_exists = dpg.does_item_exist(popup_series)
        popup_needs_update = popup_exists and image_id != self._last_popup_image_id
        sidebar_image_changed = image_id != self._last_sidebar_image_id

        # Logic: Fast compute immediately (approx), Full compute in background (accurate).
        force_update_series = False
        if vs.histogram_is_dirty:
            # 1. Fast Approximation (Sync)
            n_vox = viewer.volume.data.size // viewer.volume.num_components
            step = max(1, n_vox // 100_000)
            vs.update_histogram(bins=hs.bins, subsample_step=step)
            force_update_series = True

            # 2. Accurate Compute (Async)
            self._hist_stop.clear()
            stop = self._hist_stop

            def _bg_compute(vs_obj, bins):
                vs_obj.update_histogram(bins=bins, subsample_step=1)
                if stop.is_set():
                    return
                vs_obj.computing_full_hist = False
                vs_obj.full_hist_ready = True
                self._api.request_refresh()

            self._api.set_async_status("Computing accurate histogram...")
            vs.computing_full_hist = True
            threading.Thread(
                target=_bg_compute,
                args=(vs, hs.bins),
                daemon=True,
            ).start()

        if getattr(vs, "full_hist_ready", False):
            vs.full_hist_ready = False
            force_update_series = True
            self._api.set_async_status("Accurate histogram ready")

        if force_update_series or sidebar_image_changed or popup_needs_update:
            y_data = np.log10(vs.hist_data_y + 1) if hs.use_log else vs.hist_data_y
            max_y = self._compute_max_y(vs.hist_data_y, hs.use_log)
            x_edges = vs.hist_data_x
            bin_w = vs.get_hist_bin_width()
            x_centers = (x_edges + bin_w / 2).tolist()
            x_edges_list = x_edges.tolist()
            y_list = y_data.tolist()

            # --- Robust Histogram View Initialization ---
            dsp = vs.display
            if hs.x_center is None:
                hs.x_center = float(dsp.wl)
            if hs.x_range is None:
                hs.x_range = max(1e-5, dsp.ww / 0.3)
            if hs.y_max is None:
                hs.y_max = max_y

            x_speed = max(0.01, hs.x_range * 0.005)
            y_speed = max(1e-4, float(hs.y_max) * 0.005)

            if force_update_series or sidebar_image_changed:
                self._update_hist_series(
                    self._t("wl_hist_series"),
                    self._t("wl_hist_y_axis"),
                    x_edges_list,
                    x_centers,
                    y_list,
                    bin_w,
                    use_bars=hs.use_bars,
                )
                self._apply_hist_x_limits(hs)
                y_axis = self._t("wl_hist_y_axis")
                if dpg.does_item_exist(y_axis):
                    dpg.set_axis_limits(y_axis, 0.0, hs.y_max)
                for tag_suffix, val, spd in (
                    ("drag_hist_xcenter", hs.x_center, x_speed),
                    ("drag_hist_xwidth", hs.x_range, x_speed),
                    ("drag_hist_ymax", hs.y_max, y_speed),
                ):
                    tag = self._t(tag_suffix)
                    if dpg.does_item_exist(tag) and not dpg.is_item_active(tag):
                        dpg.set_value(tag, val)
                        dpg.configure_item(tag, speed=spd)
                self._last_sidebar_image_id = image_id
            if popup_exists and (force_update_series or popup_needs_update):
                self._update_hist_series(
                    self._t("wl_hist_popup_series"),
                    self._t("wl_hist_popup_y_axis"),
                    x_edges_list,
                    x_centers,
                    y_list,
                    bin_w,
                    use_bars=hs.use_bars,
                )
                self._apply_hist_x_limits(hs)
                popup_y_axis = self._t("wl_hist_popup_y_axis")
                if dpg.does_item_exist(popup_y_axis):
                    dpg.set_axis_limits(popup_y_axis, 0.0, hs.y_max)
                for tag_suffix, val, spd in (
                    ("drag_hist_popup_xcenter", hs.x_center, x_speed),
                    ("drag_hist_popup_xwidth", hs.x_range, x_speed),
                    ("drag_hist_popup_ymax", hs.y_max, y_speed),
                ):
                    tag = self._t(tag_suffix)
                    if dpg.does_item_exist(tag) and not dpg.is_item_active(tag):
                        dpg.set_value(tag, val)
                        dpg.configure_item(tag, speed=spd)
                popup_bins = self._t("drag_hist_popup_bins")
                if dpg.does_item_exist(popup_bins) and not dpg.is_item_active(popup_bins):
                    dpg.set_value(popup_bins, hs.bins)
                self._last_popup_image_id = image_id

        # Sync per-image button labels whenever UI refreshes (sidebar + popup)
        for tag_suffix, t_label, f_label, val in (
            ("btn_hist_bar", "Line", "Bar", hs.use_bars),
            ("btn_hist_popup_bar", "Line", "Bar", hs.use_bars),
            ("btn_hist_log", "Lin", "Log", hs.use_log),
            ("btn_hist_popup_log", "Lin", "Log", hs.use_log),
        ):
            tag = self._t(tag_suffix)
            if dpg.does_item_exist(tag):
                dpg.configure_item(tag, label=t_label if val else f_label)

        dpg.configure_item(plot_tag, show=True)

        is_computing = (
            has_image
            and not is_rgb
            and getattr(viewer.view_state, "computing_full_hist", False)
        )
        for tag_suffix in ("txt_computing_full_hist", "txt_popup_computing_full_hist"):
            tag = self._t(tag_suffix)
            if dpg.does_item_exist(tag):
                dpg.configure_item(tag, show=is_computing)

    def _update_hist_series(
        self, series_tag, axis_tag, x_edges, x_centers, y_list, bin_w, use_bars=False
    ):
        if dpg.does_item_exist(series_tag):
            existing = dpg.get_item_type(series_tag)
            type_matches = ("BarSeries" in existing) == use_bars
            if type_matches:
                if use_bars:
                    dpg.set_value(series_tag, [x_centers, y_list])
                    dpg.configure_item(series_tag, weight=bin_w)
                else:
                    dpg.set_value(series_tag, [x_edges, y_list])
                return
            dpg.delete_item(series_tag)

        if use_bars:
            dpg.add_bar_series(
                x_centers,
                y_list,
                weight=bin_w,
                parent=axis_tag,
                tag=series_tag,
            )
        else:
            dpg.add_line_series(x_edges, y_list, parent=axis_tag, tag=series_tag)
        theme = self._t("wl_hist_series_theme")
        if dpg.does_item_exist(theme):
            dpg.bind_item_theme(series_tag, theme)

    def sync_wl_lines(self, viewer, vs):
        """Update histogram drag line positions every frame."""
        if not vs or not dpg.does_item_exist(self._t("wl_hist_lower")):
            return

        hs = self._hs(viewer)
        if hs is None:
            return

        dsp = vs.display
        if getattr(viewer.volume, "is_rgb", False) or dsp.wl is None:
            return

        wl, ww = dsp.wl, dsp.ww
        lower = wl - ww / 2
        upper = wl + ww / 2

        # 1. Update Plot Elements (Sidebar and Popup)
        max_y = self._compute_max_y(vs.hist_data_y, hs.use_log)
        for suffix in ["", "_popup"]:
            if dpg.does_item_exist(self._t(f"wl_hist{suffix}_lower")):
                self._safe_update_plot_elements(suffix, lower, upper, wl, max_y)

        # 2. Update Popup-Specific visuals
        popup_win = self._t("wl_hist_popup_win")
        if dpg.does_item_exist(popup_win) and dpg.is_item_shown(popup_win):
            self._update_colorscale_texture(vs, hs)
            self._safe_set(self._t("wl_popup_colorscale_min"), f"{lower:g}")
            self._safe_set(self._t("wl_popup_colorscale_max"), f"{upper:g}")

        # 3. Sync numerical inputs
        self._sync_drag_floats(hs)
        self._apply_hist_x_limits(hs)

    def _safe_update_plot_elements(self, suffix, lower, upper, wl, max_y):
        """Helper to update drag lines and shade series for sidebar or popup."""
        dpg.set_value(self._t(f"wl_hist{suffix}_lower"), lower)
        dpg.set_value(self._t(f"wl_hist{suffix}_upper"), upper)
        if dpg.does_item_exist(self._t(f"wl_hist{suffix}_level")):
            dpg.set_value(self._t(f"wl_hist{suffix}_level"), wl)

        shade_val = [[lower, upper], [max_y, max_y], [0.0, 0.0]]
        shade_tag = self._t(f"wl_hist{suffix}_shade")
        if max_y > 0 and dpg.does_item_exist(shade_tag):
            dpg.set_value(shade_tag, shade_val)

    def _sync_drag_floats(self, hs: HistogramState):
        # Keep drag float displays in sync (only when not being actively dragged)
        for tag_suffix, val in (
            ("drag_hist_xcenter", hs.x_center),
            ("drag_hist_popup_xcenter", hs.x_center),
            ("drag_hist_xwidth", hs.x_range),
            ("drag_hist_popup_xwidth", hs.x_range),
            ("drag_hist_ymax", hs.y_max),
            ("drag_hist_popup_ymax", hs.y_max),
        ):
            tag = self._t(tag_suffix)
            if (
                val is not None
                and dpg.does_item_exist(tag)
                and not dpg.is_item_active(tag)
            ):
                dpg.set_value(tag, val)

        # Log-adaptive speed: update when not dragging so next drag starts correct
        x_range = hs.x_range
        if x_range and x_range > 0:
            center_speed = max(0.01, x_range * 0.005)
            for tag_suffix in ("drag_hist_xcenter", "drag_hist_popup_xcenter"):
                tag = self._t(tag_suffix)
                if dpg.does_item_exist(tag) and not dpg.is_item_active(tag):
                    dpg.configure_item(tag, speed=center_speed)
            for tag_suffix in ("drag_hist_xwidth", "drag_hist_popup_xwidth"):
                tag = self._t(tag_suffix)
                if dpg.does_item_exist(tag) and not dpg.is_item_active(tag):
                    cur = dpg.get_value(tag)
                    if cur and cur > 0:
                        dpg.configure_item(tag, speed=max(0.01, cur * 0.005))

    def _safe_set(self, tag, val):
        if dpg.does_item_exist(tag):
            dpg.set_value(tag, val)

    def _update_colorscale_texture(self, vs, hs: HistogramState):
        """Update the colormap preview texture with radiometric state caching."""
        tex_tag = self._t("wl_colorscale_tex")
        if not dpg.does_item_exist(tex_tag):
            return

        view_center = hs.x_center
        if view_center is None:
            return

        if hs.x_range is not None:
            view_range = hs.x_range
        elif vs.hist_data_x is not None:
            view_range = float(vs.hist_data_x[-1] - vs.hist_data_x[0])
        else:
            view_range = 1.0

        img_min = view_center - view_range / 2
        img_max = view_center + view_range / 2
        if img_max <= img_min:
            return

        # Performance: Skip the expensive numpy->list conversion if nothing changed
        dsp = vs.display
        wl, ww, cmap_name = dsp.wl, dsp.ww, dsp.colormap
        state = (wl, ww, cmap_name, img_min, img_max)
        if self._last_colorscale_state == state:
            return
        self._last_colorscale_state = state

        from vvv.maths.image_utils import compute_colorscale_gradient

        colors_list = compute_colorscale_gradient(wl, ww, cmap_name, img_min, img_max)
        dpg.set_value(tex_tag, colors_list)

    def _apply_hist_x_limits(self, hs: HistogramState):
        if hs.x_center is None or hs.x_range is None:
            return
        center = hs.x_center
        half = (hs.x_range or 1.0) / 2
        for axis_suffix in ["_x_axis", "_popup_x_axis"]:
            axis = self._t(f"wl_hist{axis_suffix}")
            if dpg.does_item_exist(axis):
                dpg.set_axis_limits(axis, center - half, center + half)

    # --- Callbacks ---
    def on_preset_changed(self, sender, app_data, user_data):
        viewer = self._api.get_active_viewer()
        if not viewer or not viewer.view_state:
            return
        viewer.view_state.apply_wl_preset(app_data)
        self._api.propagate_window_level(viewer.image_id)
        self._api.request_refresh()

    def on_ww_changed(self, sender, app_data, user_data):
        viewer = self._api.get_active_viewer()
        if not viewer or not viewer.view_state:
            return
        viewer._mark_lazy_interaction()
        viewer.view_state.display.ww = max(1e-20, app_data)
        preset_tag = self._t("combo_wl_presets")
        if dpg.does_item_exist(preset_tag):
            dpg.set_value(preset_tag, "Custom")
        self._api.propagate_window_level(viewer.image_id)

    def on_wl_changed(self, sender, app_data, user_data):
        viewer = self._api.get_active_viewer()
        if not viewer or not viewer.view_state:
            return
        viewer._mark_lazy_interaction()
        viewer.view_state.display.wl = app_data
        preset_tag = self._t("combo_wl_presets")
        if dpg.does_item_exist(preset_tag):
            dpg.set_value(preset_tag, "Custom")
        self._api.propagate_window_level(viewer.image_id)

    def on_colormap_changed(self, sender, app_data, user_data):
        viewer = self._api.get_active_viewer()
        if not viewer or not viewer.view_state:
            return
        viewer.view_state.display.colormap = app_data
        self._api.propagate_colormap(viewer.image_id)

    def on_threshold_changed(self, sender, app_data, user_data):
        viewer = self._api.get_active_viewer()
        if not viewer or not viewer.view_state:
            return
        viewer.view_state.display.base_threshold = app_data
        check_tag = self._t("check_min_threshold")
        if dpg.does_item_exist(check_tag):
            dpg.set_value(check_tag, True)
        self._api.propagate_window_level(viewer.image_id)

    def on_threshold_toggle(self, sender, app_data, user_data):
        viewer = self._api.get_active_viewer()
        if not viewer or not viewer.view_state:
            return
        is_enabled = app_data
        if is_enabled:
            val = dpg.get_value(self._t("drag_min_threshold"))
            viewer.view_state.display.base_threshold = val
        else:
            viewer.view_state.display.base_threshold = None
        self._api.propagate_window_level(viewer.image_id)
        self._api.request_refresh()

    def _on_hist_drag_bound(self, app_data, fallback_tag):
        pos = (
            float(app_data) if app_data is not None else dpg.get_value(fallback_tag)
        )
        if pos is None:
            return
        viewer = self._api.get_active_viewer()
        if not viewer or not viewer.view_state:
            return
        ww = max(1e-5, 2.0 * abs(viewer.view_state.display.wl - pos))
        viewer._mark_lazy_interaction()
        viewer.view_state.display.ww = ww
        dpg.set_value(self._t("drag_ww"), ww)
        preset_tag = self._t("combo_wl_presets")
        if dpg.does_item_exist(preset_tag):
            dpg.set_value(preset_tag, "Custom")
        self.sync_wl_lines(viewer, viewer.view_state)
        self._api.propagate_window_level(viewer.image_id)

    def _on_hist_drag_level(self, app_data, fallback_tag):
        pos = (
            float(app_data) if app_data is not None else dpg.get_value(fallback_tag)
        )
        if pos is None:
            return
        viewer = self._api.get_active_viewer()
        if not viewer or not viewer.view_state:
            return
        viewer._mark_lazy_interaction()
        viewer.view_state.display.wl = pos
        dpg.set_value(self._t("drag_wl"), pos)
        preset_tag = self._t("combo_wl_presets")
        if dpg.does_item_exist(preset_tag):
            dpg.set_value(preset_tag, "Custom")
        self.sync_wl_lines(viewer, viewer.view_state)
        self._api.propagate_window_level(viewer.image_id)

    def on_hist_drag_lower(self, _, app_data, __):
        self._on_hist_drag_bound(app_data, self._t("wl_hist_lower"))

    def on_hist_drag_upper(self, _, app_data, __):
        self._on_hist_drag_bound(app_data, self._t("wl_hist_upper"))

    def on_hist_drag_level(self, _, app_data, __):
        self._on_hist_drag_level(app_data, self._t("wl_hist_level"))

    def on_hist_popup_drag_lower(self, _, app_data, __):
        self._on_hist_drag_bound(app_data, self._t("wl_hist_popup_lower"))

    def on_hist_popup_drag_upper(self, _, app_data, __):
        self._on_hist_drag_bound(app_data, self._t("wl_hist_popup_upper"))

    def on_hist_popup_drag_level(self, _, app_data, __):
        self._on_hist_drag_level(app_data, self._t("wl_hist_popup_level"))

    def on_hist_center(self, _sender, _app_data, _user_data):
        viewer = self._api.get_active_viewer()
        if not viewer or not viewer.view_state:
            return
        hs = self._hs(viewer)
        if hs is None:
            return
        dsp = viewer.view_state.display
        hs.x_center = float(dsp.wl)
        hs.x_range = dsp.ww / 0.3
        self._apply_hist_x_limits(hs)
        for tag_suffix in ("drag_hist_xcenter", "drag_hist_popup_xcenter"):
            tag = self._t(tag_suffix)
            if dpg.does_item_exist(tag):
                dpg.set_value(tag, hs.x_center)
        for tag_suffix in ("drag_hist_xwidth", "drag_hist_popup_xwidth"):
            tag = self._t(tag_suffix)
            if dpg.does_item_exist(tag):
                dpg.set_value(tag, hs.x_range)

    def on_hist_popup(self, sender, app_data, user_data):
        if self._ui and self._api:
            self._ui.create_popup_ui(self._api)

            viewer = self._api.get_active_viewer()
            if viewer and viewer.view_state:
                vs = viewer.view_state
                hs = self._hs(viewer)
                self._last_popup_image_id = viewer.image_id
                if hs and vs.hist_data_x is not None:
                    y_raw = vs.hist_data_y
                    y_data = np.log10(y_raw + 1) if hs.use_log else y_raw
                    x_edges = vs.hist_data_x
                    bin_w = vs.get_hist_bin_width()
                    x_centers = (x_edges + bin_w / 2).tolist()
                    self._update_hist_series(
                        self._t("wl_hist_popup_series"),
                        self._t("wl_hist_popup_y_axis"),
                        x_edges.tolist(),
                        x_centers,
                        y_data.tolist(),
                        bin_w,
                        use_bars=hs.use_bars,
                    )
                    popup_y_axis = self._t("wl_hist_popup_y_axis")
                    if dpg.does_item_exist(popup_y_axis):
                        dpg.fit_axis_data(popup_y_axis)

                    if hs.x_center is not None and hs.x_range is not None:
                        self._apply_hist_x_limits(hs)
                    else:
                        wl, ww = vs.display.wl, vs.display.ww
                        margin = ww / 0.6
                        popup_x_axis = self._t("wl_hist_popup_x_axis")
                        if dpg.does_item_exist(popup_x_axis):
                            dpg.set_axis_limits(
                                popup_x_axis, wl - margin, wl + margin
                            )

                self.sync_wl_lines(viewer, vs)

    def on_hist_xcenter_drag(self, _sender, app_data, _user_data):
        viewer = self._api.get_active_viewer()
        if not viewer or not viewer.view_state or app_data is None:
            return
        hs = self._hs(viewer)
        if hs is None:
            return
        hs.x_center = float(app_data)
        self._apply_hist_x_limits(hs)

    def on_hist_xwidth_drag(self, _sender, app_data, _user_data):
        viewer = self._api.get_active_viewer()
        if not viewer or not viewer.view_state or app_data is None:
            return
        hs = self._hs(viewer)
        if hs is None:
            return
        hs.x_range = max(1e-5, float(app_data))
        self._apply_hist_x_limits(hs)

    def on_hist_ymax_drag(self, _sender, app_data, _user_data):
        viewer = self._api.get_active_viewer()
        if not viewer or not viewer.view_state or app_data is None:
            return
        hs = self._hs(viewer)
        if hs is None:
            return
        hs.y_max = max(1e-5, float(app_data))
        for axis_suffix in ("wl_hist_y_axis", "wl_hist_popup_y_axis"):
            axis = self._t(axis_suffix)
            if dpg.does_item_exist(axis):
                dpg.set_axis_limits(axis, 0.0, hs.y_max)

    def on_hist_bar_toggle(self, _sender, _app_data, _user_data):
        viewer = self._api.get_active_viewer()
        if not viewer or not viewer.view_state:
            return
        hs = self._hs(viewer)
        if hs is None:
            return
        hs.use_bars = not hs.use_bars
        tag = self._t("drag_hist_popup_bins")
        if dpg.does_item_exist(tag):
            dpg.configure_item(tag, show=hs.use_bars)
        viewer.view_state.histogram_is_dirty = True
        self._api.request_refresh()

    def on_hist_bins_drag(self, _sender, _app_data, _user_data):
        viewer = self._api.get_active_viewer()
        if not viewer or not viewer.view_state:
            return
        hs = self._hs(viewer)
        if hs is None:
            return
        hs.bins = int(float(_app_data))
        viewer.view_state.histogram_is_dirty = True
        self._api.request_refresh()

    def on_hist_log_toggle(self, _sender, _app_data, _user_data):
        viewer = self._api.get_active_viewer()
        if not viewer or not viewer.view_state:
            return
        hs = self._hs(viewer)
        if hs is None:
            return
        hs.use_log = not hs.use_log
        hs.y_max = None
        viewer.view_state.histogram_is_dirty = True
        self._api.request_refresh()

    def on_step_button_clicked(self, sender, app_data, user_data):
        target_tag = user_data["tag"]
        direction = user_data["dir"]

        current_val = dpg.get_value(target_tag)
        if current_val is None:
            current_val = 0.0

        viewer = self._api.get_active_viewer()
        step_size = (
            max(0.1, viewer.view_state.display.ww * 0.02)
            if (viewer and viewer.view_state)
            else 1.0
        )

        new_val = current_val + (step_size * direction)

        if target_tag == self._t("drag_ww"):
            new_val = max(1e-5, new_val)

        dpg.set_value(target_tag, new_val)

        if target_tag == self._t("drag_ww"):
            self.on_ww_changed(sender, new_val, user_data)
        elif target_tag == self._t("drag_wl"):
            self.on_wl_changed(sender, new_val, user_data)
        elif target_tag == self._t("drag_min_threshold"):
            self.on_threshold_changed(sender, new_val, user_data)

    # --- Lifecycle ---

    def on_image_loaded(self, image_id: str) -> None:
        self._hist[image_id] = HistogramState()

    def on_image_removed(self, image_id: str) -> None:
        self._hist_stop.set()
        self._hist.pop(image_id, None)
        popup_win = self._t("wl_hist_popup_win")
        if dpg.does_item_exist(popup_win):
            dpg.delete_item(popup_win)
        if self._last_sidebar_image_id == image_id:
            self._last_sidebar_image_id = None
        if self._last_popup_image_id == image_id:
            self._last_popup_image_id = None

    def save_settings(self, api) -> None:
        pass

    def load_settings(self, api) -> None:
        pass

    def destroy(self) -> None:
        self._hist_stop.set()
