import os
import csv
import logging
import threading
from typing import TYPE_CHECKING, List, Dict, Optional, Any
import numpy as np
import dearpygui.dearpygui as dpg
from vvv.plugins.plugin_api import PluginTagMixin, PluginAPI
from vvv.ui.ui_components import build_beginner_tooltip, build_name_filter_bar
from vvv.plugins.dose.dvh_calc import ROI_DVH_Curve, compute_roi_dvh

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from .control_dose import DosePluginController


class DVHWindow(PluginTagMixin):
    def __init__(self, plugin_id: str, controller: "DosePluginController"):
        self._plugin_id = plugin_id
        self._c = controller
        self._api: Optional[PluginAPI] = None

        self.curves: List[ROI_DVH_Curve] = []
        self.filter_text: str = ""
        self.filter_invert: bool = False
        self.is_cumulative: bool = True
        self.is_volume_relative: bool = True   # True: %, False: cc
        self.is_dose_relative: bool = False     # True: %, False: Gy
        self.norm_prescription_gy: float = 50.0 # From IntensityScalingComponent if available
        self.sort_column: Optional[str] = None
        self.sort_reverse: bool = False
        self.window_tag = self._t("dvh_window")
        self._calc_token: int = 0
        self._calc_stop: Optional[threading.Event] = None
        self._calc_thread: Optional[threading.Thread] = None

    def show_window(self, api: PluginAPI, async_calc: bool = True) -> None:
        self._api = api
        cfg_c = api.get_ui_config()["colors"]

        # If window exists, bring to front
        if dpg.does_item_exist(self.window_tag):
            dpg.focus_item(self.window_tag)
            self.recompute_and_update(fit_axes=True, async_calc=async_calc)
            return

        # Viewport dimensions for positioning
        vp_w = dpg.get_viewport_client_width() if dpg.is_dearpygui_running() else 1200
        vp_h = dpg.get_viewport_client_height() if dpg.is_dearpygui_running() else 800
        win_w = min(920, max(650, vp_w - 80))
        win_h = min(680, max(500, vp_h - 100))
        pos = [max(50, (vp_w - win_w) // 2), max(50, (vp_h - win_h) // 2)]

        with dpg.window(
            tag=self.window_tag,
            label="Dose-Volume Histogram (DVH / HDV)",
            width=win_w,
            height=win_h,
            pos=pos,
            no_collapse=False,
            on_close=self.on_window_close,
        ):
            # Top Controls Bar
            with dpg.group(horizontal=True):
                dpg.add_text("Dose:", color=cfg_c["text_dim"])
                dpg.add_text("---", tag=self._t("dvh_lbl_target_dose"), color=cfg_c["text_active"])
                dpg.add_spacer(width=20)
                dpg.add_button(
                    label="Refresh DVH",
                    callback=lambda: self.recompute_and_update(fit_axes=True),
                    tag=self._t("dvh_btn_refresh"),
                )
                btn_fit = dpg.add_button(
                    label="Fit View",
                    callback=lambda: self.fit_view(),
                    tag=self._t("dvh_btn_fit_view"),
                )
                build_beginner_tooltip(
                    btn_fit,
                    "Resets the plot view to comfortably fit all visible DVH curves.",
                    self._api,
                )
                dpg.add_button(
                    label="Export CSV...",
                    callback=self.on_export_csv_clicked,
                    tag=self._t("dvh_btn_export"),
                )

            dpg.add_spacer(height=4)

            # View Options Row
            with dpg.group(horizontal=True):
                # Cumulative vs Differential
                dpg.add_radio_button(
                    items=["Cumulative (cDVH)", "Differential (dDVH)"],
                    default_value="Cumulative (cDVH)",
                    horizontal=True,
                    tag=self._t("dvh_radio_curve_type"),
                    callback=self._on_display_option_changed,
                )
                dpg.add_spacer(width=12)
                # Volume Scale: % vs cc
                dpg.add_radio_button(
                    items=["Volume: %", "Volume: cm³"],
                    default_value="Volume: %",
                    horizontal=True,
                    tag=self._t("dvh_radio_volume_scale"),
                    callback=self._on_display_option_changed,
                )
                dpg.add_spacer(width=12)
                # Dose Scale: Gy vs %
                dpg.add_radio_button(
                    items=["Dose: Gy", "Dose: %"],
                    default_value="Dose: Gy",
                    horizontal=True,
                    tag=self._t("dvh_radio_dose_scale"),
                    callback=self._on_display_option_changed,
                )
                dpg.add_spacer(width=12)
                dpg.add_checkbox(
                    label="Legend:",
                    default_value=True,
                    tag=self._t("dvh_chk_show_legend"),
                    callback=self._on_toggle_legend,
                )
                combo_leg = dpg.add_combo(
                    items=["Top-Right", "Top-Left", "Bottom-Left", "Bottom-Right", "Outside"],
                    default_value="Top-Right",
                    width=105,
                    tag=self._t("dvh_combo_legend_loc"),
                    callback=self._on_legend_location_changed,
                )
                build_beginner_tooltip(
                    combo_leg,
                    "Switch plot legend corner (Top-Right, Top-Left, Bottom-Left, Bottom-Right, or Outside).\nYou can also right-click the legend inside the plot to configure it.",
                    self._api,
                )

            dpg.add_spacer(height=6)
            dpg.add_separator()
            dpg.add_spacer(height=6)

            # Main Section: 2 columns (Left: Plot, Right: Structure Checklist)
            with dpg.table(header_row=False, resizable=True, tag=self._t("dvh_split_table")):
                dpg.add_table_column(width_stretch=True, init_width_or_weight=600)
                dpg.add_table_column(width_fixed=True, init_width_or_weight=240)

                with dpg.table_row():
                    # Left column: Interactive Plot
                    with dpg.group():
                        with dpg.plot(
                            label="",
                            height=320,
                            width=-1,
                            tag=self._t("dvh_plot"),
                        ):
                            dpg.add_plot_legend(
                                location=dpg.mvPlot_Location_NorthEast,
                                tag=self._t("dvh_plot_legend"),
                            )
                            dpg.add_plot_axis(
                                dpg.mvXAxis,
                                label="Dose (Gy)",
                                tag=self._t("dvh_plot_x_axis"),
                            )
                            dpg.add_plot_axis(
                                dpg.mvYAxis,
                                label="Volume (%)",
                                tag=self._t("dvh_plot_y_axis"),
                            )

                    # Right column: Structure Selector
                    with dpg.group():
                        with dpg.group(horizontal=True):
                            dpg.add_text("Structures", color=cfg_c["text_header"])
                            dpg.add_spacer(width=10)
                            btn_all = dpg.add_button(
                                label="All",
                                width=40,
                                callback=self._on_select_all_structures,
                                tag=self._t("dvh_btn_select_all"),
                            )
                            build_beginner_tooltip(btn_all, "Check all visible structures", self._api)
                            btn_none = dpg.add_button(
                                label="None",
                                width=40,
                                callback=self._on_select_none_structures,
                                tag=self._t("dvh_btn_select_none"),
                            )
                            build_beginner_tooltip(btn_none, "Uncheck all visible structures", self._api)

                        dpg.add_spacer(height=3)

                        # Standardized name filter bar (matching ROI plugin)
                        build_name_filter_bar(
                            group_tag=self._t("group_dvh_filter"),
                            input_tag=self._t("input_dvh_filter"),
                            btn_clear_tag=self._t("btn_clear_dvh_filter"),
                            on_filter_changed=self._on_filter_changed,
                            on_clear_clicked=self._on_clear_filter,
                            hint="Filter...",
                            width=140,
                            api=self._api,
                            btn_invert_tag=self._t("btn_dvh_filter_invert"),
                            on_invert_clicked=self._on_toggle_filter_invert,
                        )

                        dpg.add_spacer(height=4)
                        with dpg.child_window(
                            height=250,
                            width=-1,
                            border=True,
                            tag=self._t("dvh_structures_list"),
                        ):
                            pass

            dpg.add_spacer(height=8)
            dpg.add_separator()
            dpg.add_spacer(height=4)

            # Bottom Section: Dosimetric Metrics Table
            dpg.add_text("Dosimetric Metrics", color=cfg_c["text_header"])
            with dpg.child_window(height=-1, border=True, tag=self._t("dvh_table_panel")):
                with dpg.table(
                    tag=self._t("dvh_metrics_table"),
                    header_row=True,
                    resizable=True,
                    sortable=True,
                    sort_tristate=True,
                    callback=self._on_table_sort,
                    borders_innerH=True,
                    borders_innerV=True,
                    borders_outerH=True,
                    borders_outerV=True,
                    row_background=True,
                ):
                    dpg.add_table_column(
                        label="Structure",
                        width_stretch=True,
                        tag=self._t("dvh_col_struct"),
                        user_data="roi_name",
                    )
                    dpg.add_table_column(
                        label="Vol (cm³)",
                        width_fixed=True,
                        init_width_or_weight=75,
                        tag=self._t("dvh_col_vol"),
                        user_data="volume_cc",
                    )
                    dpg.add_table_column(
                        label="Min (Gy)",
                        width_fixed=True,
                        init_width_or_weight=70,
                        tag=self._t("dvh_col_min"),
                        user_data="min_dose",
                    )
                    dpg.add_table_column(
                        label="Mean (Gy)",
                        width_fixed=True,
                        init_width_or_weight=75,
                        tag=self._t("dvh_col_mean"),
                        user_data="mean_dose",
                    )
                    dpg.add_table_column(
                        label="Max (Gy)",
                        width_fixed=True,
                        init_width_or_weight=70,
                        tag=self._t("dvh_col_max"),
                        user_data="max_dose",
                    )
                    dpg.add_table_column(
                        label="D98 (Gy)",
                        width_fixed=True,
                        init_width_or_weight=70,
                        tag=self._t("dvh_col_d98"),
                        user_data="d98",
                    )
                    dpg.add_table_column(
                        label="D50 (Gy)",
                        width_fixed=True,
                        init_width_or_weight=70,
                        tag=self._t("dvh_col_d50"),
                        user_data="median_dose",
                    )
                    dpg.add_table_column(
                        label="D2 (Gy)",
                        width_fixed=True,
                        init_width_or_weight=70,
                        tag=self._t("dvh_col_d2"),
                        user_data="d2",
                    )

        # Initial calculation
        self.recompute_and_update(fit_axes=True, async_calc=async_calc)

    def on_window_close(self):
        if self._calc_stop is not None:
            self._calc_stop.set()
        self._calc_token += 1
        if dpg.does_item_exist(self.window_tag):
            dpg.delete_item(self.window_tag)

    def _on_toggle_legend(self, sender=None, app_data=None, user_data=None):
        chk_tag = self._t("dvh_chk_show_legend")
        leg_tag = self._t("dvh_plot_legend")
        combo_tag = self._t("dvh_combo_legend_loc")
        if dpg.does_item_exist(leg_tag) and dpg.does_item_exist(chk_tag):
            val = dpg.get_value(chk_tag)
            dpg.configure_item(leg_tag, show=bool(val))
            if dpg.does_item_exist(combo_tag):
                dpg.configure_item(combo_tag, enabled=bool(val))

    def _on_legend_location_changed(self, sender=None, app_data=None, user_data=None):
        val = app_data if app_data else (dpg.get_value(self._t("dvh_combo_legend_loc")) if dpg.does_item_exist(self._t("dvh_combo_legend_loc")) else "Top-Right")
        leg_tag = self._t("dvh_plot_legend")
        if not dpg.does_item_exist(leg_tag):
            return

        loc_map = {
            "Top-Right": (dpg.mvPlot_Location_NorthEast, False),
            "Top-Left": (dpg.mvPlot_Location_NorthWest, False),
            "Bottom-Right": (dpg.mvPlot_Location_SouthEast, False),
            "Bottom-Left": (dpg.mvPlot_Location_SouthWest, False),
            "Outside": (dpg.mvPlot_Location_NorthEast, True),
        }
        loc, outside = loc_map.get(val, (dpg.mvPlot_Location_NorthEast, False))
        dpg.configure_item(leg_tag, location=loc, outside=outside)

    def _get_filtered_curves(self) -> List[ROI_DVH_Curve]:
        filter_lower = self.filter_text.strip().lower()
        if not filter_lower:
            return self.curves
        res = []
        for c in self.curves:
            match = filter_lower in c.roi_name.lower()
            if match if not self.filter_invert else not match:
                res.append(c)
        return res

    def _on_filter_changed(self, text: str):
        self.filter_text = text or ""
        self._rebuild_structure_checklist()
        self._render_metrics_table()

    def _on_clear_filter(self):
        self.filter_text = ""
        inp_tag = self._t("input_dvh_filter")
        if dpg.does_item_exist(inp_tag):
            dpg.set_value(inp_tag, "")
        self._rebuild_structure_checklist()
        self._render_metrics_table()

    def _on_toggle_filter_invert(self):
        self.filter_invert = not self.filter_invert
        btn_invert_tag = self._t("btn_dvh_filter_invert")
        if dpg.does_item_exist(btn_invert_tag):
            if self.filter_invert:
                if dpg.does_item_exist("active_nav_button_theme"):
                    dpg.bind_item_theme(btn_invert_tag, "active_nav_button_theme")
            else:
                dpg.bind_item_theme(btn_invert_tag, 0)
        self._rebuild_structure_checklist()
        self._render_metrics_table()

    def _on_display_option_changed(self, sender=None, app_data=None, user_data=None):
        if dpg.does_item_exist(self._t("dvh_radio_curve_type")):
            val = dpg.get_value(self._t("dvh_radio_curve_type"))
            self.is_cumulative = "Cumulative" in val

        if dpg.does_item_exist(self._t("dvh_radio_volume_scale")):
            val = dpg.get_value(self._t("dvh_radio_volume_scale"))
            self.is_volume_relative = "%" in val

        if dpg.does_item_exist(self._t("dvh_radio_dose_scale")):
            val = dpg.get_value(self._t("dvh_radio_dose_scale"))
            self.is_dose_relative = "%" in val

        self._render_plot_and_table(fit_axes=True)

    def _on_select_all_structures(self):
        for c in self._get_filtered_curves():
            c.enabled = True
            tag = self._t(f"chk_struct_{c.roi_id}")
            if dpg.does_item_exist(tag):
                dpg.set_value(tag, True)
        self._render_plot_and_table(fit_axes=False)

    def _on_select_none_structures(self):
        for c in self._get_filtered_curves():
            c.enabled = False
            tag = self._t(f"chk_struct_{c.roi_id}")
            if dpg.does_item_exist(tag):
                dpg.set_value(tag, False)
        self._render_plot_and_table(fit_axes=False)

    def _on_toggle_structure(self, sender, app_data, user_data):
        roi_id = user_data
        for c in self.curves:
            if c.roi_id == roi_id:
                c.enabled = bool(app_data)
                break
        self._render_plot_and_table(fit_axes=False)

    def fit_view(self):
        """Resets the plot view to comfortably encompass all visible curves."""
        self._apply_axis_limits()

    def _apply_axis_limits(self):
        """Applies proper axis limits based on current view modes and data ranges."""
        y_axis_tag = self._t("dvh_plot_y_axis")
        x_axis_tag = self._t("dvh_plot_x_axis")
        if not dpg.does_item_exist(y_axis_tag) or not dpg.does_item_exist(x_axis_tag):
            return

        enabled_curves = [c for c in self.curves if c.enabled]
        if not enabled_curves:
            enabled_curves = self.curves

        # X-Axis (Dose)
        if self.is_dose_relative:
            norm = self.norm_prescription_gy if self.norm_prescription_gy > 0 else 1.0
            max_x = max((float(np.max(c.doses)) / norm * 100.0 for c in enabled_curves), default=100.0)
            max_x = max_x * 1.05 if max_x > 0 else 100.0
        else:
            max_x = max((float(c.max_dose) for c in enabled_curves), default=60.0)
            max_x = max_x * 1.05 if max_x > 0 else 1.0

        # Y-Axis (Volume)
        if self.is_cumulative:
            if self.is_volume_relative:
                max_y = 105.0
            else:
                max_y = max((float(c.volume_cc) for c in enabled_curves), default=100.0) * 1.05
        else:
            if self.is_volume_relative:
                max_y = max((float(np.max(c.diff_volume_percent)) for c in enabled_curves), default=10.0) * 1.15
            else:
                max_y = max((float(np.max(c.diff_volume_absolute)) for c in enabled_curves), default=10.0) * 1.15
        max_y = max(max_y, 1.0)

        dpg.set_axis_limits(x_axis_tag, 0.0, float(max_x))
        dpg.set_axis_limits(y_axis_tag, 0.0, float(max_y))

    def wait_for_calculation(self, timeout: float = 5.0) -> bool:
        """Helper to wait for a background calculation to complete (primarily for tests)."""
        if self._calc_thread is not None and self._calc_thread.is_alive():
            self._calc_thread.join(timeout=timeout)
            return not self._calc_thread.is_alive()
        return True

    def recompute_and_update(self, fit_axes: bool = True, async_calc: bool = True) -> None:
        """Computes DVH for all currently loaded ROIs on the active dose target asynchronously."""
        if not self._api:
            return

        # Cancel any previous calculation
        if self._calc_stop is not None:
            self._calc_stop.set()
        stop_event = threading.Event()
        self._calc_stop = stop_event
        self._calc_token += 1
        current_token = self._calc_token

        is_active, dose_vol, is_ov, unit_str, target_id, target_vs = (
            self._c.get_dose_target_info()
        )
        if not is_active or not dose_vol:
            if dpg.does_item_exist(self._t("dvh_lbl_target_dose")):
                dpg.set_value(self._t("dvh_lbl_target_dose"), "No active dose image")
            return

        # Target dose label
        dose_name = getattr(dose_vol, "name", "Dose")
        role = "Overlay" if is_ov else "Base"

        # Get virtual scaling / prescription dose if available
        user_s = 1.0
        sc = None
        if hasattr(self._c, "_ui") and self._c._ui and hasattr(self._c._ui, "scaling_comp"):
            sc = self._c._ui.scaling_comp.get_state(target_id)
            if sc:
                user_s = float(sc.scaling_factor) if sc.scaling_factor != 0 else 1.0
        elif hasattr(dose_vol, "scale_factor") and dose_vol.scale_factor:
            user_s = float(dose_vol.scale_factor)
        if user_s == 0.0 or np.isnan(user_s):
            user_s = 1.0

        # Reference dose in physical units (Gy) corresponding to 100% relative dose
        if hasattr(self._c, "get_reference_dose"):
            raw_ref = self._c.get_reference_dose(dose_vol, is_ov, target_id)
            norm_prescription_gy = float(raw_ref * user_s)
        elif sc and sc.norm_target_value > 0:
            norm_prescription_gy = float(sc.norm_target_value)
        else:
            norm_prescription_gy = float(user_s * 50.0)

        # Global evaluation upper limit across dose volume to ensure uniform domain (in Gy)
        d_min, d_max = dose_vol.get_data_range()
        phys_d_max = float(d_max) * user_s
        global_max_dose = phys_d_max * 1.05 if phys_d_max > 0 else 1.0

        # Find reference image with ROIs (prioritize active viewer's view_state, or base)
        all_volumes = self._api.get_volumes()
        rois_dict = self._find_all_rois()

        roi_tasks = []
        for roi_id, roi_state in rois_dict.items():
            r_vol = all_volumes.get(roi_id)
            if not r_vol or r_vol.data is None:
                continue
            color = getattr(roi_state, "color", [255, 0, 0])
            roi_tasks.append((roi_id, roi_state.name, color, r_vol))

        if not roi_tasks:
            self.curves = []
            self.norm_prescription_gy = norm_prescription_gy
            if dpg.does_item_exist(self._t("dvh_lbl_target_dose")):
                dpg.set_value(self._t("dvh_lbl_target_dose"), f"[{role}] {dose_name} ({unit_str})")
            if dpg.does_item_exist(self._t("dvh_btn_refresh")):
                dpg.configure_item(self._t("dvh_btn_refresh"), enabled=True)
            self._rebuild_structure_checklist()
            self._render_plot_and_table(fit_axes=fit_axes)
            return

        if dpg.does_item_exist(self._t("dvh_lbl_target_dose")):
            dpg.set_value(
                self._t("dvh_lbl_target_dose"),
                f"[{role}] {dose_name} ({unit_str}) - Computing...",
            )
        if dpg.does_item_exist(self._t("dvh_btn_refresh")):
            dpg.configure_item(self._t("dvh_btn_refresh"), enabled=False)

        def _do_work():
            new_curves = []
            for roi_id, roi_name, color, r_vol in roi_tasks:
                if stop_event.is_set() or self._calc_token != current_token:
                    return

                try:
                    curve = compute_roi_dvh(
                        dose_vol=dose_vol,
                        roi_vol=r_vol,
                        roi_name=roi_name,
                        color=color,
                        max_eval_dose=global_max_dose,
                        dose_scaling_factor=user_s,
                    )
                    if curve:
                        curve.roi_id = roi_id
                        new_curves.append(curve)
                except Exception:
                    logger.exception("Error computing DVH for ROI %s", roi_name)

            if stop_event.is_set() or self._calc_token != current_token:
                return

            def _commit_on_main():
                if self._calc_token != current_token or stop_event.is_set():
                    return
                if not dpg.does_item_exist(self.window_tag):
                    return
                self.norm_prescription_gy = norm_prescription_gy
                self.curves = new_curves
                if dpg.does_item_exist(self._t("dvh_lbl_target_dose")):
                    dpg.set_value(
                        self._t("dvh_lbl_target_dose"),
                        f"[{role}] {dose_name} ({unit_str})",
                    )
                if dpg.does_item_exist(self._t("dvh_btn_refresh")):
                    dpg.configure_item(self._t("dvh_btn_refresh"), enabled=True)
                self._rebuild_structure_checklist()
                self._render_plot_and_table(fit_axes=fit_axes)

            if self._api:
                self._api.run_on_main_thread(_commit_on_main)

        if async_calc:
            self._calc_thread = threading.Thread(
                target=_do_work,
                name=f"dvh_calc_worker_{current_token}",
                daemon=True,
            )
            self._calc_thread.start()
        else:
            _do_work()

    def _find_all_rois(self) -> Dict[str, Any]:
        """Finds all segmented ROIs across all view states."""
        if not self._api:
            return {}
        rois = {}
        all_volumes = self._api.get_volumes()
        for vs in self._api.get_view_states().values():
            if vs and vs.rois:
                for rid, rstate in vs.rois.items():
                    if rid in all_volumes and rid not in rois:
                        rois[rid] = rstate
        if not rois:
            viewer = self._api.get_active_viewer()
            if viewer and viewer.view_state and viewer.view_state.rois:
                rois = dict(viewer.view_state.rois)
        return rois

    def _on_structure_color_edited(self, sender, app_data, user_data):
        roi_id = user_data
        from vvv.ui.ui_components import normalize_rgba_to_int
        new_rgb = normalize_rgba_to_int(app_data)[:3]

        for c in self.curves:
            if c.roi_id == roi_id:
                c.color = list(new_rgb) + [255]
                color_tag = self._t(f"dvh_series_col_{c.roi_id}")
                if dpg.does_item_exist(color_tag):
                    dpg.set_value(color_tag, list(new_rgb) + [255])
                text_tag = self._t(f"dvh_metric_name_{c.roi_id}")
                if dpg.does_item_exist(text_tag):
                    dpg.configure_item(text_tag, color=list(new_rgb) + [255])
                break

        if self._api:
            for vs_id, vs in self._api.get_view_states().items():
                if vs and vs.rois and roi_id in vs.rois:
                    vs.rois[roi_id].color = list(new_rgb)
                    vs.is_data_dirty = True
                    self._api.update_all_viewers_of_image(vs_id)
            self._api.request_refresh()

    def sync_colors(self) -> None:
        """Synchronizes DVH curve, checklist, and table colors with current ROI colors from ROI tool."""
        if not self._api or not dpg.does_item_exist(self.window_tag):
            return

        all_rois = self._find_all_rois()
        if not all_rois:
            return

        for c in self.curves:
            roi_state = all_rois.get(c.roi_id)
            if not roi_state or not hasattr(roi_state, "color"):
                continue

            raw_rgb = roi_state.color[:3]
            r = int(raw_rgb[0] * 255) if isinstance(raw_rgb[0], float) and raw_rgb[0] <= 1.0 else int(raw_rgb[0])
            g = int(raw_rgb[1] * 255) if isinstance(raw_rgb[1], float) and raw_rgb[1] <= 1.0 else int(raw_rgb[1])
            b = int(raw_rgb[2] * 255) if isinstance(raw_rgb[2], float) and raw_rgb[2] <= 1.0 else int(raw_rgb[2])
            r, g, b = max(0, min(255, r)), max(0, min(255, g)), max(0, min(255, b))
            new_color = [r, g, b, 255]

            if c.color[:3] != [r, g, b]:
                c.color = new_color

                # 1. Update plot line series theme color
                color_tag = self._t(f"dvh_series_col_{c.roi_id}")
                if dpg.does_item_exist(color_tag):
                    dpg.set_value(color_tag, new_color)

                # 2. Update color swatch in structure checklist
                swatch_tag = self._t(f"dvh_struct_color_{c.roi_id}")
                if dpg.does_item_exist(swatch_tag):
                    dpg.set_value(swatch_tag, new_color)

                # 3. Update structure name color in metrics table
                text_tag = self._t(f"dvh_metric_name_{c.roi_id}")
                if dpg.does_item_exist(text_tag):
                    dpg.configure_item(text_tag, color=new_color)

    def update_ui(self, api: PluginAPI) -> None:
        """Called every frame to ensure live sync with ROI tool."""
        if not dpg.does_item_exist(self.window_tag):
            return
        self._api = api
        self.sync_colors()

    def _rebuild_structure_checklist(self):
        list_tag = self._t("dvh_structures_list")
        if not dpg.does_item_exist(list_tag):
            return

        dpg.delete_item(list_tag, children_only=True)

        filtered = self._get_filtered_curves()
        for c in filtered:
            row_tag = self._t(f"dvh_struct_row_{c.roi_id}")
            with dpg.group(horizontal=True, parent=list_tag, tag=row_tag):
                dpg.add_checkbox(
                    default_value=c.enabled,
                    user_data=c.roi_id,
                    callback=self._on_toggle_structure,
                    tag=self._t(f"chk_struct_{c.roi_id}"),
                )
                r, g, b = c.color[:3]
                swatch_tag = self._t(f"dvh_struct_color_{c.roi_id}")
                dpg.add_color_edit(
                    default_value=[r, g, b, 255],
                    no_inputs=True,
                    no_label=True,
                    no_alpha=True,
                    width=18,
                    height=18,
                    tag=swatch_tag,
                    user_data=c.roi_id,
                    callback=self._on_structure_color_edited,
                )
                dpg.add_text(c.roi_name, tag=self._t(f"dvh_struct_name_{c.roi_id}"))

    @property
    def _column_attr_map(self) -> Dict[Any, str]:
        return {
            self._t("dvh_col_struct"): "roi_name",
            self._t("dvh_col_vol"): "volume_cc",
            self._t("dvh_col_min"): "min_dose",
            self._t("dvh_col_mean"): "mean_dose",
            self._t("dvh_col_max"): "max_dose",
            self._t("dvh_col_d98"): "d98",
            self._t("dvh_col_d50"): "median_dose",
            self._t("dvh_col_d2"): "d2",
            "Structure": "roi_name",
            "Vol (cm³)": "volume_cc",
            "Min (Gy)": "min_dose",
            "Mean (Gy)": "mean_dose",
            "Max (Gy)": "max_dose",
            "D98 (Gy)": "d98",
            "D50 (Gy)": "median_dose",
            "D2 (Gy)": "d2",
        }

    def _on_table_sort(self, sender=None, sort_specs=None, user_data=None):
        """Callback when any column header is clicked in the metrics table."""
        if not sort_specs or len(sort_specs) == 0:
            self.sort_column = None
            self.sort_reverse = False
        else:
            col_id, direction = sort_specs[0]
            self.sort_reverse = (direction < 0)

            attr = None
            if dpg.does_item_exist(col_id):
                attr = dpg.get_item_user_data(col_id)
            if not attr:
                attr = self._column_attr_map.get(col_id)
            if not attr and dpg.does_item_exist(col_id):
                alias = dpg.get_item_alias(col_id)
                if alias:
                    attr = self._column_attr_map.get(alias)
            if not attr and dpg.does_item_exist(col_id):
                label = dpg.get_item_label(col_id)
                if label:
                    attr = self._column_attr_map.get(label)

            self.sort_column = attr

        self._render_metrics_table()

    def _render_metrics_table(self):
        """Populates the dosimetric metrics table with currently filtered/visible structures."""
        table_tag = self._t("dvh_metrics_table")
        if not dpg.does_item_exist(table_tag):
            return

        rows = dpg.get_item_children(table_tag, slot=1) or []
        for r in rows:
            dpg.delete_item(r)

        targets = list(self._get_filtered_curves())
        if self.sort_column:
            attr = self.sort_column
            if attr == "roi_name":
                targets.sort(
                    key=lambda c: getattr(c, "roi_name", "").lower(),
                    reverse=self.sort_reverse,
                )
            else:
                targets.sort(
                    key=lambda c: float(getattr(c, attr, 0.0)),
                    reverse=self.sort_reverse,
                )

        for c in targets:
            row = dpg.add_table_row(parent=table_tag)
            # Structure name with color indicator
            r, g, b = c.color[:3]
            dpg.add_text(
                c.roi_name,
                color=[r, g, b, 255],
                parent=row,
                tag=self._t(f"dvh_metric_name_{c.roi_id}"),
            )
            dpg.add_text(f"{c.volume_cc:.2f}", parent=row)
            dpg.add_text(f"{c.min_dose:.2f}", parent=row)
            dpg.add_text(f"{c.mean_dose:.2f}", parent=row)
            dpg.add_text(f"{c.max_dose:.2f}", parent=row)
            dpg.add_text(f"{c.d98:.2f}", parent=row)
            dpg.add_text(f"{c.median_dose:.2f}", parent=row)
            dpg.add_text(f"{c.d2:.2f}", parent=row)

    def _render_plot_and_table(self, fit_axes: bool = False):
        """Redraws the DVH plot lines and updates the metrics table."""
        y_axis_tag = self._t("dvh_plot_y_axis")
        x_axis_tag = self._t("dvh_plot_x_axis")
        if not dpg.does_item_exist(y_axis_tag) or not dpg.does_item_exist(x_axis_tag):
            return

        # 1. Update Axis Labels
        x_label = "Dose (%)" if self.is_dose_relative else "Dose (Gy)"
        if self.is_volume_relative:
            y_label = "Volume (%)"
        else:
            y_label = "Volume (cm³)"

        dpg.configure_item(x_axis_tag, label=x_label)
        dpg.configure_item(y_axis_tag, label=y_label)

        # Clear existing plot series
        existing_children = dpg.get_item_children(y_axis_tag, slot=1) or []
        for child in existing_children:
            dpg.delete_item(child)

        # Add curves
        for c in self.curves:
            if not c.enabled:
                continue

            # Scale dose if relative
            if self.is_dose_relative and self.norm_prescription_gy > 0:
                x_vals = (c.doses / self.norm_prescription_gy) * 100.0
            else:
                x_vals = c.doses

            # Choose volume data
            if self.is_cumulative:
                y_vals = c.volume_percent if self.is_volume_relative else c.volume_absolute
            else:
                y_vals = c.diff_volume_percent if self.is_volume_relative else c.diff_volume_absolute

            series_tag = self._t(f"dvh_series_{c.roi_id}")
            line = dpg.add_line_series(
                list(x_vals),
                list(y_vals),
                label=c.roi_name,
                parent=y_axis_tag,
                tag=series_tag,
            )

            # Apply curve color and 2px thickness
            raw_rgb = c.color[:3]
            r = int(raw_rgb[0] * 255) if isinstance(raw_rgb[0], float) and raw_rgb[0] <= 1.0 else int(raw_rgb[0])
            g = int(raw_rgb[1] * 255) if isinstance(raw_rgb[1], float) and raw_rgb[1] <= 1.0 else int(raw_rgb[1])
            b = int(raw_rgb[2] * 255) if isinstance(raw_rgb[2], float) and raw_rgb[2] <= 1.0 else int(raw_rgb[2])
            r, g, b = max(0, min(255, r)), max(0, min(255, g)), max(0, min(255, b))

            theme_tag = self._t(f"dvh_series_theme_{c.roi_id}")
            if dpg.does_item_exist(theme_tag):
                dpg.delete_item(theme_tag)
            with dpg.theme(tag=theme_tag):
                with dpg.theme_component(dpg.mvLineSeries):
                    dpg.add_theme_color(
                        dpg.mvPlotCol_Line,
                        [r, g, b, 255],
                        category=dpg.mvThemeCat_Plots,
                        tag=self._t(f"dvh_series_col_{c.roi_id}"),
                    )
                    dpg.add_theme_color(
                        dpg.mvPlotCol_MarkerFill,
                        [r, g, b, 255],
                        category=dpg.mvThemeCat_Plots,
                    )
                    dpg.add_theme_color(
                        dpg.mvPlotCol_MarkerOutline,
                        [r, g, b, 255],
                        category=dpg.mvThemeCat_Plots,
                    )
                    dpg.add_theme_style(
                        dpg.mvPlotStyleVar_LineWeight,
                        2.0,
                        category=dpg.mvThemeCat_Plots,
                    )
            dpg.bind_item_theme(line, theme_tag)

        # Apply axis limits if requested (initial load, display options change, fit view)
        if fit_axes:
            self._apply_axis_limits()

        # 2. Rebuild Metrics Table
        self._render_metrics_table()

    def on_export_csv_clicked(self):
        """Exports DVH curves and metrics summary to a CSV file."""
        from vvv.ui.file_dialog import save_file_dialog

        file_path = save_file_dialog(
            "Export DVH Data as CSV",
            default_name="dvh_export.csv",
        )
        if not file_path:
            return

        if not file_path.lower().endswith(".csv"):
            file_path += ".csv"

        try:
            with open(file_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)

                # Export filtered curves if search filter active, otherwise all
                export_curves = list(self._get_filtered_curves() if self.filter_text else self.curves)
                if self.sort_column:
                    attr = self.sort_column
                    if attr == "roi_name":
                        export_curves.sort(
                            key=lambda c: getattr(c, "roi_name", "").lower(),
                            reverse=self.sort_reverse,
                        )
                    else:
                        export_curves.sort(
                            key=lambda c: float(getattr(c, attr, 0.0)),
                            reverse=self.sort_reverse,
                        )

                # 1. Summary Metrics Table
                writer.writerow(["# DVH Summary Metrics"])
                writer.writerow(["Structure", "Volume (cm3)", "Min (Gy)", "Mean (Gy)", "Max (Gy)", "D98 (Gy)", "D50 (Gy)", "D2 (Gy)"])
                for c in export_curves:
                    writer.writerow([
                        c.roi_name,
                        f"{c.volume_cc:.4f}",
                        f"{c.min_dose:.4f}",
                        f"{c.mean_dose:.4f}",
                        f"{c.max_dose:.4f}",
                        f"{c.d98:.4f}",
                        f"{c.median_dose:.4f}",
                        f"{c.d2:.4f}",
                    ])

                writer.writerow([])
                writer.writerow(["# Cumulative Dose-Volume Curves (Dose in Gy, Volume in %)"])

                # Headers
                headers = []
                for c in export_curves:
                    headers.extend([f"{c.roi_name}_Dose_Gy", f"{c.roi_name}_Vol_Pct"])
                writer.writerow(headers)

                # Curves data rows
                max_pts = max((len(c.doses) for c in export_curves), default=0)
                for i in range(max_pts):
                    row = []
                    for c in export_curves:
                        if i < len(c.doses):
                            row.extend([f"{c.doses[i]:.4f}", f"{c.volume_percent[i]:.4f}"])
                        else:
                            row.extend(["", ""])
                    writer.writerow(row)

            if self._api:
                self._api.notify(f"Exported DVH to {os.path.basename(file_path)}")
        except Exception as e:
            if self._api:
                self._api.notify(f"Export failed: {e}", color=[255, 100, 100])
