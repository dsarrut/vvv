import threading
import numpy as np
import dearpygui.dearpygui as dpg
from vvv.plugins.plugin_api import PluginAPI
from vvv.config import WL_PRESETS, COLORMAPS


class HistogramState:
    """Per-image histogram state — view preferences and computed data — owned by the intensity plugin."""

    def __init__(self):
        # View preferences
        self.use_bars: bool = True
        self.use_log: bool = True
        self.bins: int = 256
        self.x_center: float | None = None
        self.x_range: float | None = None
        self.y_max: float | None = None
        # Computed data
        self.data_x: np.ndarray | None = None
        self.data_y: np.ndarray | None = None
        self.is_dirty: bool = True
        self.full_hist_ready: bool = False
        self.computing_full_hist: bool = False
        # Change-detection cache
        self._vol_data_id: int | None = None
        self._time_idx: int | None = None
        # Threading
        self.stop_event = threading.Event()


class IntensityController:
    def __init__(self, plugin_id: str):
        self._plugin_id = plugin_id
        self._api = None
        self._ui = None

        self._minmax_cache = {}
        self._last_sidebar_image_id = None
        self._last_popup_visible = {}
        self._last_colorscale_states = {}

        self._hist: dict[str, HistogramState] = {}

    def _t(self, name: str) -> str:
        return f"{self._plugin_id}_{name}"

    def _hs(self, viewer) -> HistogramState | None:
        if viewer and viewer.image_id:
            return self._hist.get(viewer.image_id)
        return None

    def _mark_interaction_for_image(self, image_id: str):
        if not self._api:
            return
        for viewer in self._api.get_viewers().values():
            if viewer.image_id == image_id:
                viewer._mark_lazy_interaction()

    @staticmethod
    def _update_histogram(vol, hs: "HistogramState", bins: int, subsample_step: int = 1, time_idx: int = 0):
        data = vol.data
        if getattr(vol, "is_dvf", False) and data.ndim >= 4:
            if data.ndim == 5:
                t_idx = min(time_idx, data.shape[0] - 1)
                vec = data[t_idx]
            else:
                vec = data
            total_count = vec.shape[1] * vec.shape[2] * vec.shape[3]
            if subsample_step > 1:
                flat_vec = vec.reshape(3, -1)[:, ::subsample_step]
                flat_data = np.sqrt(np.sum(flat_vec.astype(np.float64) ** 2, axis=0))
            else:
                flat_data = np.sqrt(np.sum(vec.astype(np.float64) ** 2, axis=0)).ravel()
        else:
            if data.ndim == 4:
                t_idx = min(time_idx, data.shape[0] - 1)
                active_data = data[t_idx]
            else:
                active_data = data
            total_count = active_data.size
            flat_data = active_data.ravel()[::subsample_step] if subsample_step > 1 else active_data.ravel()

        hist, bin_edges = np.histogram(flat_data, bins=bins)
        y = hist.astype(np.float32)
        if subsample_step > 1 and flat_data.size > 0:
            y *= total_count / flat_data.size

        hs.data_y = y
        hs.data_x = bin_edges[:-1].astype(np.float32)
        hs.is_dirty = False

    @staticmethod
    def _get_hist_bin_width(hs: "HistogramState") -> float:
        if hs.data_x is None or len(hs.data_x) < 2:
            return 1.0
        return float(hs.data_x[1] - hs.data_x[0])

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

        active_title = self._t("active_title")
        if dpg.does_item_exist(active_title):
            if has_image:
                name_str, is_outdated = api.get_image_display_name(viewer.image_id)
                color_key = "outdated" if is_outdated else "text_active"
            else:
                name_str, color_key = "No Image Selected", "text_active"
            dpg.set_value(active_title, name_str)
            dpg.configure_item(active_title, color=api.get_ui_config()["colors"][color_key])

        is_rgb = viewer.volume.is_rgb if has_image else False
        thr = viewer.view_state.display.base_threshold if has_image else None
        has_thr = thr is not None

        tags = [self._t("combo_wl_presets"), self._t("drag_ww"), self._t("drag_wl"), self._t("combo_colormap")]
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
            for btn in (f"btn_{drag_thr_tag}_minus", f"btn_{drag_thr_tag}_plus"):
                if dpg.does_item_exist(btn):
                    dpg.configure_item(btn, enabled=thr_enabled)

        minmax_tag = self._t("minmax")
        if dpg.does_item_exist(minmax_tag):
            if not has_image or is_rgb:
                dpg.set_value(minmax_tag, "---")
            else:
                vol = viewer.volume
                current_data_id = id(vol.data)
                if current_data_id not in self._minmax_cache:
                    self._minmax_cache = {current_data_id: (float(np.min(vol.data)), float(np.max(vol.data)))}
                min_v, max_v = self._minmax_cache[current_data_id]
                dpg.set_value(minmax_tag, f"{min_v:g} to {max_v:g}")

        ww_val = getattr(viewer.view_state.display, "ww", 1.0) if has_image and viewer.view_state else 1.0
        if ww_val is None:
            ww_val = 1.0
        dynamic_speed = max(0.1, ww_val * 0.005)
        for t in [self._t("drag_ww"), self._t("drag_wl"), self._t("drag_min_threshold")]:
            if dpg.does_item_exist(t):
                dpg.configure_item(t, speed=dynamic_speed)

        if has_image and not is_rgb:
            vs = viewer.view_state
            ww_tag = self._t("drag_ww")
            if dpg.does_item_exist(ww_tag) and not dpg.is_item_active(ww_tag):
                dpg.set_value(ww_tag, vs.display.ww)
            wl_tag = self._t("drag_wl")
            if dpg.does_item_exist(wl_tag) and not dpg.is_item_active(wl_tag):
                dpg.set_value(wl_tag, vs.display.wl)
            cmap_tag = self._t("combo_colormap")
            if dpg.does_item_exist(cmap_tag) and not dpg.is_item_active(cmap_tag):
                dpg.set_value(cmap_tag, vs.display.colormap)
            preset_tag = self._t("combo_wl_presets")
            if dpg.does_item_exist(preset_tag) and not dpg.is_item_active(preset_tag):
                matched = False
                for p_name, p_val in WL_PRESETS.items():
                    if p_val is not None:
                        if abs(vs.display.ww - p_val["ww"]) < 1e-3 and abs(vs.display.wl - p_val["wl"]) < 1e-3:
                            dpg.set_value(preset_tag, p_name)
                            matched = True
                            break
                if not matched:
                    cur_preset = dpg.get_value(preset_tag)
                    if cur_preset not in ["Custom", "Optimal", "Min/Max"]:
                        dpg.set_value(preset_tag, "Custom")
            self.sync_wl_lines_for_image(viewer.image_id)

        # Sync other open popup windows
        for img_id in self._hist:
            if img_id != (viewer.image_id if has_image else None):
                popup_win = self._t(f"wl_hist_popup_win_{img_id}")
                if dpg.does_item_exist(popup_win) and dpg.is_item_shown(popup_win):
                    self.sync_wl_lines_for_image(img_id)

        self._refresh_wl_histogram(viewer, has_image, is_rgb)

    def _refresh_wl_histogram(self, viewer, has_image, is_rgb):
        sidebar_plot_tag = self._t("wl_hist_plot")
        if dpg.does_item_exist(sidebar_plot_tag):
            dpg.configure_item(sidebar_plot_tag, show=(has_image and not is_rgb))

        active_img_id = viewer.image_id if (has_image and not is_rgb) else None

        for img_id, hs in list(self._hist.items()):
            popup_win = self._t(f"wl_hist_popup_win_{img_id}")
            popup_visible = dpg.does_item_exist(popup_win) and dpg.is_item_shown(popup_win)
            is_active = (img_id == active_img_id)
            sidebar_visible = is_active and dpg.is_item_shown(self._plugin_id)

            if not sidebar_visible and not popup_visible:
                continue

            vol = self._api.get_volumes().get(img_id)
            vs = self._api.get_view_states().get(img_id)
            if not vol or not vs or getattr(vol, "is_rgb", False):
                continue

            # Detect volume data changes
            current_data_id = id(vol.data)
            if hs._vol_data_id != current_data_id:
                hs.is_dirty = True
                hs._vol_data_id = current_data_id

            # Detect timepoint changes
            time_idx = vs.camera.time_idx if vs else 0
            if getattr(hs, "_time_idx", None) != time_idx:
                hs.is_dirty = True
                hs._time_idx = time_idx

            force_update_series = False
            if hs.is_dirty:
                n_vox = vol.data.size // vol.num_components
                step = max(1, n_vox // 100_000)
                self._update_histogram(vol, hs, hs.bins, step, time_idx)
                force_update_series = True

                hs.stop_event.clear()
                stop = hs.stop_event

                def _bg_compute(hs_obj, vol_obj, bins, t_idx):
                    IntensityController._update_histogram(vol_obj, hs_obj, bins, 1, t_idx)
                    if stop.is_set():
                        return
                    hs_obj.computing_full_hist = False
                    hs_obj.full_hist_ready = True
                    self._api.request_refresh()

                self._api.set_async_status(f"Computing accurate histogram for {vol.name}...")
                hs.computing_full_hist = True
                threading.Thread(target=_bg_compute, args=(hs, vol, hs.bins, time_idx), daemon=True).start()

            if hs.full_hist_ready:
                hs.full_hist_ready = False
                force_update_series = True
                self._api.set_async_status("Accurate histogram ready")

            sidebar_image_changed = (is_active and img_id != self._last_sidebar_image_id)
            was_popup_visible = self._last_popup_visible.get(img_id, False)
            popup_newly_visible = popup_visible and not was_popup_visible
            self._last_popup_visible[img_id] = popup_visible

            if force_update_series or sidebar_image_changed or popup_newly_visible:
                y_data = np.log10(hs.data_y + 1) if hs.use_log else hs.data_y
                max_y = self._compute_max_y(hs.data_y, hs.use_log)
                bin_w = self._get_hist_bin_width(hs)
                x_centers = (hs.data_x + bin_w / 2).tolist()
                x_edges_list = hs.data_x.tolist()
                y_list = y_data.tolist()

                if hs.x_center is None:
                    hs.x_center = float(vs.display.wl)
                if hs.x_range is None:
                    hs.x_range = max(1e-5, vs.display.ww / 0.3)
                if hs.y_max is None:
                    hs.y_max = max_y

                x_speed = max(0.01, hs.x_range * 0.005)
                y_speed = max(1e-4, float(hs.y_max) * 0.005)

                if is_active and (force_update_series or sidebar_image_changed):
                    self._update_hist_series(
                        self._t("wl_hist_series"),
                        self._t("wl_hist_y_axis"),
                        x_edges_list,
                        x_centers,
                        y_list,
                        bin_w,
                        use_bars=hs.use_bars
                    )
                    self._apply_hist_x_limits(hs, img_id)
                    y_axis = self._t("wl_hist_y_axis")
                    if dpg.does_item_exist(y_axis):
                        dpg.set_axis_limits(y_axis, 0.0, hs.y_max)
                    for tag_suffix, val, spd in (
                        ("drag_hist_xcenter", hs.x_center, x_speed),
                        ("drag_hist_xwidth", hs.x_range, x_speed),
                        ("drag_hist_ymax", hs.y_max, y_speed)
                    ):
                        tag = self._t(tag_suffix)
                        if dpg.does_item_exist(tag) and not dpg.is_item_active(tag):
                            dpg.set_value(tag, val)
                            dpg.configure_item(tag, speed=spd)
                    self._last_sidebar_image_id = img_id

                if popup_visible and (force_update_series or popup_newly_visible):
                    self._update_hist_series(
                        self._t(f"wl_hist_popup_series_{img_id}"),
                        self._t(f"wl_hist_popup_y_axis_{img_id}"),
                        x_edges_list,
                        x_centers,
                        y_list,
                        bin_w,
                        use_bars=hs.use_bars
                    )
                    self._apply_hist_x_limits(hs, img_id)
                    popup_y_axis = self._t(f"wl_hist_popup_y_axis_{img_id}")
                    if dpg.does_item_exist(popup_y_axis):
                        dpg.set_axis_limits(popup_y_axis, 0.0, hs.y_max)
                    for tag_suffix, val, spd in (
                        (f"drag_hist_popup_xcenter_{img_id}", hs.x_center, x_speed),
                        (f"drag_hist_popup_xwidth_{img_id}", hs.x_range, x_speed),
                        (f"drag_hist_popup_ymax_{img_id}", hs.y_max, y_speed)
                    ):
                        tag = self._t(tag_suffix)
                        if dpg.does_item_exist(tag) and not dpg.is_item_active(tag):
                            dpg.set_value(tag, val)
                            dpg.configure_item(tag, speed=spd)
                    popup_bins = self._t(f"drag_hist_popup_bins_{img_id}")
                    if dpg.does_item_exist(popup_bins) and not dpg.is_item_active(popup_bins):
                        dpg.set_value(popup_bins, hs.bins)

            # Update buttons/toggles
            if is_active:
                for tag_suffix, t_label, f_label, val in (
                    ("btn_hist_bar", "Line", "Bar", hs.use_bars),
                    ("btn_hist_log", "Lin", "Log", hs.use_log),
                ):
                    tag = self._t(tag_suffix)
                    if dpg.does_item_exist(tag):
                        dpg.configure_item(tag, label=t_label if val else f_label)
                txt_panel = self._t("txt_computing_full_hist")
                if dpg.does_item_exist(txt_panel):
                    dpg.configure_item(txt_panel, show=hs.computing_full_hist)

            if popup_visible:
                for tag_suffix, t_label, f_label, val in (
                    (f"btn_hist_popup_bar_{img_id}", "Line", "Bar", hs.use_bars),
                    (f"btn_hist_popup_log_{img_id}", "Lin", "Log", hs.use_log),
                ):
                    tag = self._t(tag_suffix)
                    if dpg.does_item_exist(tag):
                        dpg.configure_item(tag, label=t_label if val else f_label)
                txt_popup = self._t(f"txt_popup_computing_full_hist_{img_id}")
                if dpg.does_item_exist(txt_popup):
                    dpg.configure_item(txt_popup, show=hs.computing_full_hist)

    def _update_hist_series(self, series_tag, axis_tag, x_edges, x_centers, y_list, bin_w, use_bars=False):
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
            dpg.add_bar_series(x_centers, y_list, weight=bin_w, parent=axis_tag, tag=series_tag)
        else:
            dpg.add_line_series(x_edges, y_list, parent=axis_tag, tag=series_tag)
        theme = self._t("wl_hist_series_theme")
        if dpg.does_item_exist(theme):
            dpg.bind_item_theme(series_tag, theme)

    def sync_wl_lines(self, viewer, vs):
        if viewer and viewer.image_id:
            self.sync_wl_lines_for_image(viewer.image_id)

    def sync_wl_lines_for_image(self, img_id: str):
        vs = self._api.get_view_states().get(img_id)
        if not vs:
            return
        hs = self._hist.get(img_id)
        if not hs:
            return
        vol = self._api.get_volumes().get(img_id)
        if not vol or getattr(vol, "is_rgb", False) or vs.display.wl is None:
            return

        wl, ww = vs.display.wl, vs.display.ww
        lower = wl - ww / 2
        upper = wl + ww / 2

        max_y = self._compute_max_y(hs.data_y, hs.use_log)

        # Update sidebar if the modified image is currently active
        active_viewer = self._api.get_active_viewer()
        if active_viewer and active_viewer.image_id == img_id:
            if dpg.does_item_exist(self._t("wl_hist_lower")):
                self._safe_update_plot_elements(False, img_id, lower, upper, wl, max_y)

        # Update popup
        popup_win = self._t(f"wl_hist_popup_win_{img_id}")
        if dpg.does_item_exist(popup_win) and dpg.is_item_shown(popup_win):
            if dpg.does_item_exist(self._t(f"wl_hist_popup_lower_{img_id}")):
                self._safe_update_plot_elements(True, img_id, lower, upper, wl, max_y)
            self._update_colorscale_texture_for_image(img_id, vs, hs)
            self._safe_set(self._t(f"wl_popup_colorscale_min_{img_id}"), f"{lower:g}")
            self._safe_set(self._t(f"wl_popup_colorscale_max_{img_id}"), f"{upper:g}")

        self._sync_drag_floats_for_image(img_id, hs)
        self._apply_hist_x_limits(hs, img_id)

    def _safe_update_plot_elements(self, is_popup, img_id, lower, upper, wl, max_y):
        if is_popup:
            lower_tag = self._t(f"wl_hist_popup_lower_{img_id}")
            upper_tag = self._t(f"wl_hist_popup_upper_{img_id}")
            level_tag = self._t(f"wl_hist_popup_level_{img_id}")
            shade_tag = self._t(f"wl_hist_popup_shade_{img_id}")
        else:
            lower_tag = self._t("wl_hist_lower")
            upper_tag = self._t("wl_hist_upper")
            level_tag = self._t("wl_hist_level")
            shade_tag = self._t("wl_hist_shade")

        dpg.set_value(lower_tag, lower)
        dpg.set_value(upper_tag, upper)
        if dpg.does_item_exist(level_tag):
            dpg.set_value(level_tag, wl)
        shade_val = [[lower, upper], [max_y, max_y], [0.0, 0.0]]
        if max_y > 0 and dpg.does_item_exist(shade_tag):
            dpg.set_value(shade_tag, shade_val)

    def _sync_drag_floats_for_image(self, img_id: str, hs: HistogramState):
        active_viewer = self._api.get_active_viewer()
        if active_viewer and active_viewer.image_id == img_id:
            for tag_suffix, val in (
                ("drag_hist_xcenter", hs.x_center),
                ("drag_hist_xwidth", hs.x_range),
                ("drag_hist_ymax", hs.y_max),
            ):
                tag = self._t(tag_suffix)
                if val is not None and dpg.does_item_exist(tag) and not dpg.is_item_active(tag):
                    dpg.set_value(tag, val)

            x_range = hs.x_range
            if x_range and x_range > 0:
                center_speed = max(0.01, x_range * 0.005)
                for tag_suffix in ("drag_hist_xcenter",):
                    tag = self._t(tag_suffix)
                    if dpg.does_item_exist(tag) and not dpg.is_item_active(tag):
                        dpg.configure_item(tag, speed=center_speed)
                for tag_suffix in ("drag_hist_xwidth",):
                    tag = self._t(tag_suffix)
                    if dpg.does_item_exist(tag) and not dpg.is_item_active(tag):
                        cur = dpg.get_value(tag)
                        if cur and cur > 0:
                            dpg.configure_item(tag, speed=max(0.01, cur * 0.005))

        # Popup floats
        for tag_suffix, val in (
            (f"drag_hist_popup_xcenter_{img_id}", hs.x_center),
            (f"drag_hist_popup_xwidth_{img_id}", hs.x_range),
            (f"drag_hist_popup_ymax_{img_id}", hs.y_max),
        ):
            tag = self._t(tag_suffix)
            if val is not None and dpg.does_item_exist(tag) and not dpg.is_item_active(tag):
                dpg.set_value(tag, val)

        x_range = hs.x_range
        if x_range and x_range > 0:
            center_speed = max(0.01, x_range * 0.005)
            tag = self._t(f"drag_hist_popup_xcenter_{img_id}")
            if dpg.does_item_exist(tag) and not dpg.is_item_active(tag):
                dpg.configure_item(tag, speed=center_speed)
            tag = self._t(f"drag_hist_popup_xwidth_{img_id}")
            if dpg.does_item_exist(tag) and not dpg.is_item_active(tag):
                cur = dpg.get_value(tag)
                if cur and cur > 0:
                    dpg.configure_item(tag, speed=max(0.01, cur * 0.005))

    def _safe_set(self, tag, val):
        if dpg.does_item_exist(tag):
            dpg.set_value(tag, val)

    def _update_colorscale_texture_for_image(self, img_id: str, vs, hs: HistogramState):
        tex_tag = self._t(f"wl_colorscale_tex_{img_id}")
        if not dpg.does_item_exist(tex_tag):
            return

        view_center = hs.x_center
        if view_center is None:
            return

        if hs.x_range is not None:
            view_range = hs.x_range
        elif hs.data_x is not None:
            view_range = float(hs.data_x[-1] - hs.data_x[0])
        else:
            view_range = 1.0

        img_min = view_center - view_range / 2
        img_max = view_center + view_range / 2
        if img_max <= img_min:
            return

        dsp = vs.display
        wl, ww, cmap_name = dsp.wl, dsp.ww, dsp.colormap
        state = (wl, ww, cmap_name, img_min, img_max)
        if self._last_colorscale_states.get(img_id) == state:
            return
        self._last_colorscale_states[img_id] = state

        from vvv.maths.image_utils import compute_colorscale_gradient
        colors_list = compute_colorscale_gradient(wl, ww, cmap_name, img_min, img_max)
        dpg.set_value(tex_tag, colors_list)

    def _apply_hist_x_limits(self, hs: HistogramState, img_id: str):
        if hs.x_center is None or hs.x_range is None:
            return
        center = hs.x_center
        half = (hs.x_range or 1.0) / 2

        # Sidebar axis (only if active)
        active_viewer = self._api.get_active_viewer()
        if active_viewer and active_viewer.image_id == img_id:
            axis = self._t("wl_hist_x_axis")
            if dpg.does_item_exist(axis):
                dpg.set_axis_limits(axis, center - half, center + half)

        # Popup axis
        axis = self._t(f"wl_hist_popup_x_axis_{img_id}")
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
        if app_data:
            viewer.view_state.display.base_threshold = dpg.get_value(self._t("drag_min_threshold"))
        else:
            viewer.view_state.display.base_threshold = None
        self._api.propagate_window_level(viewer.image_id)
        self._api.request_refresh()

    def _on_hist_drag_bound(self, app_data, fallback_tag, image_id: str = None):
        if image_id is None:
            viewer = self._api.get_active_viewer()
            if not viewer:
                return
            image_id = viewer.image_id

        pos = float(app_data) if app_data is not None else dpg.get_value(fallback_tag)
        if pos is None:
            return

        vs = self._api.get_view_states().get(image_id)
        if not vs:
            return

        ww = max(1e-5, 2.0 * abs(vs.display.wl - pos))
        self._mark_interaction_for_image(image_id)
        vs.display.ww = ww

        # Update sidebar if the modified image is currently active
        active_viewer = self._api.get_active_viewer()
        if active_viewer and active_viewer.image_id == image_id:
            dpg.set_value(self._t("drag_ww"), ww)
            preset_tag = self._t("combo_wl_presets")
            if dpg.does_item_exist(preset_tag):
                dpg.set_value(preset_tag, "Custom")

        self.sync_wl_lines_for_image(image_id)
        self._api.propagate_window_level(image_id)

    def _on_hist_drag_level(self, app_data, fallback_tag, image_id: str = None):
        if image_id is None:
            viewer = self._api.get_active_viewer()
            if not viewer:
                return
            image_id = viewer.image_id

        pos = float(app_data) if app_data is not None else dpg.get_value(fallback_tag)
        if pos is None:
            return

        vs = self._api.get_view_states().get(image_id)
        if not vs:
            return

        self._mark_interaction_for_image(image_id)
        vs.display.wl = pos

        active_viewer = self._api.get_active_viewer()
        if active_viewer and active_viewer.image_id == image_id:
            dpg.set_value(self._t("drag_wl"), pos)
            preset_tag = self._t("combo_wl_presets")
            if dpg.does_item_exist(preset_tag):
                dpg.set_value(preset_tag, "Custom")

        self.sync_wl_lines_for_image(image_id)
        self._api.propagate_window_level(image_id)

    def on_hist_drag_lower(self, _, app_data, __): self._on_hist_drag_bound(app_data, self._t("wl_hist_lower"))
    def on_hist_drag_upper(self, _, app_data, __): self._on_hist_drag_bound(app_data, self._t("wl_hist_upper"))
    def on_hist_drag_level(self, _, app_data, __): self._on_hist_drag_level(app_data, self._t("wl_hist_level"))
    def on_hist_popup_drag_lower(self, _, app_data, user_data): self._on_hist_drag_bound(app_data, self._t(f"wl_hist_popup_lower_{user_data}"), user_data)
    def on_hist_popup_drag_upper(self, _, app_data, user_data): self._on_hist_drag_bound(app_data, self._t(f"wl_hist_popup_upper_{user_data}"), user_data)
    def on_hist_popup_drag_level(self, _, app_data, user_data): self._on_hist_drag_level(app_data, self._t(f"wl_hist_popup_level_{user_data}"), user_data)

    def on_hist_center(self, _sender, _app_data, user_data):
        image_id = user_data
        if image_id is None:
            viewer = self._api.get_active_viewer()
            if not viewer:
                return
            image_id = viewer.image_id

        vs = self._api.get_view_states().get(image_id)
        hs = self._hist.get(image_id)
        if not vs or not hs:
            return

        dsp = vs.display
        hs.x_center = float(dsp.wl)
        hs.x_range = dsp.ww / 0.3
        self._apply_hist_x_limits(hs, image_id)

        # Update sidebar floats if this image is active
        active_viewer = self._api.get_active_viewer()
        if active_viewer and active_viewer.image_id == image_id:
            for tag_suffix in ("drag_hist_xcenter", "drag_hist_xwidth"):
                tag = self._t(tag_suffix)
                if dpg.does_item_exist(tag):
                    dpg.set_value(tag, hs.x_center if "xcenter" in tag_suffix else hs.x_range)

        # Update popup floats
        for tag_suffix in (f"drag_hist_popup_xcenter_{image_id}", f"drag_hist_popup_xwidth_{image_id}"):
            tag = self._t(tag_suffix)
            if dpg.does_item_exist(tag):
                dpg.set_value(tag, hs.x_center if "xcenter" in tag_suffix else hs.x_range)

    def on_hist_popup(self, sender, app_data, user_data):
        if not self._ui or not self._api:
            return
        viewer = self._api.get_active_viewer()
        if not viewer or not viewer.image_id:
            return
        image_id = viewer.image_id
        self._ui.create_popup_ui(self._api, image_id)

        popup_win = self._t(f"wl_hist_popup_win_{image_id}")
        if dpg.does_item_exist(popup_win) and dpg.is_item_shown(popup_win):
            hs = self._hist.get(image_id)
            vs = self._api.get_view_states().get(image_id)
            if hs and vs:
                if hs.data_x is not None:
                    y_raw = hs.data_y
                    y_data = np.log10(y_raw + 1) if hs.use_log else y_raw
                    bin_w = self._get_hist_bin_width(hs)
                    x_centers = (hs.data_x + bin_w / 2).tolist()
                    self._update_hist_series(
                        self._t(f"wl_hist_popup_series_{image_id}"),
                        self._t(f"wl_hist_popup_y_axis_{image_id}"),
                        hs.data_x.tolist(),
                        x_centers,
                        y_data.tolist(),
                        bin_w,
                        use_bars=hs.use_bars
                    )
                    popup_y_axis = self._t(f"wl_hist_popup_y_axis_{image_id}")
                    if dpg.does_item_exist(popup_y_axis):
                        dpg.fit_axis_data(popup_y_axis)
                    if hs.x_center is not None and hs.x_range is not None:
                        self._apply_hist_x_limits(hs, image_id)
                    else:
                        wl, ww = vs.display.wl, vs.display.ww
                        popup_x_axis = self._t(f"wl_hist_popup_x_axis_{image_id}")
                        if dpg.does_item_exist(popup_x_axis):
                            dpg.set_axis_limits(popup_x_axis, wl - ww / 0.6, wl + ww / 0.6)
                self.sync_wl_lines_for_image(image_id)

    def on_hist_xcenter_drag(self, _sender, app_data, user_data):
        image_id = user_data
        if image_id is None:
            viewer = self._api.get_active_viewer()
            if not viewer:
                return
            image_id = viewer.image_id
        if app_data is None:
            return
        hs = self._hist.get(image_id)
        if hs:
            hs.x_center = float(app_data)
            self._apply_hist_x_limits(hs, image_id)

    def on_hist_xwidth_drag(self, _sender, app_data, user_data):
        image_id = user_data
        if image_id is None:
            viewer = self._api.get_active_viewer()
            if not viewer:
                return
            image_id = viewer.image_id
        if app_data is None:
            return
        hs = self._hist.get(image_id)
        if hs:
            hs.x_range = max(1e-5, float(app_data))
            self._apply_hist_x_limits(hs, image_id)

    def on_hist_ymax_drag(self, _sender, app_data, user_data):
        image_id = user_data
        if image_id is None:
            viewer = self._api.get_active_viewer()
            if not viewer:
                return
            image_id = viewer.image_id
        if app_data is None:
            return
        hs = self._hist.get(image_id)
        if hs:
            hs.y_max = max(1e-5, float(app_data))
            for axis in (self._t("wl_hist_y_axis"), self._t(f"wl_hist_popup_y_axis_{image_id}")):
                if dpg.does_item_exist(axis):
                    dpg.set_axis_limits(axis, 0.0, hs.y_max)

    def on_hist_bar_toggle(self, _sender, _app_data, user_data):
        image_id = user_data
        if image_id is None:
            viewer = self._api.get_active_viewer()
            if not viewer:
                return
            image_id = viewer.image_id
        hs = self._hist.get(image_id)
        if hs is None:
            return
        hs.use_bars = not hs.use_bars
        tag = self._t(f"drag_hist_popup_bins_{image_id}")
        if dpg.does_item_exist(tag):
            dpg.configure_item(tag, show=hs.use_bars)
        hs.is_dirty = True
        self._api.request_refresh()

    def on_hist_bins_drag(self, _sender, _app_data, user_data):
        image_id = user_data
        if image_id is None:
            viewer = self._api.get_active_viewer()
            if not viewer:
                return
            image_id = viewer.image_id
        hs = self._hist.get(image_id)
        if hs is None:
            return
        hs.bins = int(float(_app_data))
        hs.is_dirty = True
        self._api.request_refresh()

    def on_hist_log_toggle(self, _sender, _app_data, user_data):
        image_id = user_data
        if image_id is None:
            viewer = self._api.get_active_viewer()
            if not viewer:
                return
            image_id = viewer.image_id
        hs = self._hist.get(image_id)
        if hs is None:
            return
        hs.use_log = not hs.use_log
        hs.y_max = None
        hs.is_dirty = True
        self._api.request_refresh()

    def on_step_button_clicked(self, sender, app_data, user_data):
        target_tag = user_data["tag"]
        direction = user_data["dir"]
        current_val = dpg.get_value(target_tag) or 0.0
        viewer = self._api.get_active_viewer()
        step_size = max(0.1, viewer.view_state.display.ww * 0.02) if (viewer and viewer.view_state) else 1.0
        new_val = current_val + step_size * direction
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
        hs = self._hist.pop(image_id, None)
        if hs is not None:
            hs.stop_event.set()
        popup_win = self._t(f"wl_hist_popup_win_{image_id}")
        if dpg.does_item_exist(popup_win):
            dpg.delete_item(popup_win)
        self._last_colorscale_states.pop(image_id, None)
        self._last_popup_visible.pop(image_id, None)
        if self._last_sidebar_image_id == image_id:
            self._last_sidebar_image_id = None

    def serialize_image_state(self, image_id: str) -> dict:
        hs = self._hist.get(image_id)
        if hs is None:
            return {}
        return {
            "use_bars": hs.use_bars,
            "use_log": hs.use_log,
            "bins": hs.bins,
            "x_center": hs.x_center,
            "x_range": hs.x_range,
            "y_max": hs.y_max,
        }

    def restore_image_state(self, image_id: str, data: dict) -> None:
        hs = self._hist.get(image_id)
        if hs is None:
            return
        hs.use_bars = data.get("use_bars", hs.use_bars)
        hs.use_log = data.get("use_log", hs.use_log)
        hs.bins = data.get("bins", hs.bins)
        hs.x_center = data.get("x_center", hs.x_center)
        hs.x_range = data.get("x_range", hs.x_range)
        hs.y_max = data.get("y_max", hs.y_max)

    def save_settings(self, api) -> None:
        pass

    def load_settings(self, api) -> None:
        pass

    def destroy(self) -> None:
        for hs in self._hist.values():
            hs.stop_event.set()
        for img_id in list(self._hist.keys()):
            popup_win = self._t(f"wl_hist_popup_win_{img_id}")
            if dpg.does_item_exist(popup_win):
                dpg.delete_item(popup_win)
