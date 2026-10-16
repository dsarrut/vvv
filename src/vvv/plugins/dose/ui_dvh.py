import os
import csv
from typing import TYPE_CHECKING, List, Dict, Optional, Any
import numpy as np
import dearpygui.dearpygui as dpg
from vvv.plugins.plugin_api import PluginTagMixin, PluginAPI
from vvv.ui.ui_components import build_beginner_tooltip
from vvv.plugins.dose.dvh_calc import ROI_DVH_Curve, compute_roi_dvh

if TYPE_CHECKING:
    from .control_dose import DosePluginController


class DVHWindow(PluginTagMixin):
    def __init__(self, plugin_id: str, controller: "DosePluginController"):
        self._plugin_id = plugin_id
        self._c = controller
        self._api: Optional[PluginAPI] = None

        self.curves: List[ROI_DVH_Curve] = []
        self.is_cumulative: bool = True
        self.is_volume_relative: bool = True   # True: %, False: cc
        self.is_dose_relative: bool = False     # True: %, False: Gy
        self.norm_prescription_gy: float = 50.0 # From IntensityScalingComponent if available
        self.window_tag = self._t("dvh_window")

    def show_window(self, api: PluginAPI) -> None:
        self._api = api
        cfg_c = api.get_ui_config()["colors"]

        # If window exists, bring to front
        if dpg.does_item_exist(self.window_tag):
            dpg.focus_item(self.window_tag)
            self.recompute_and_update(fit_axes=True)
            return

        # Viewport dimensions for positioning
        vp_w = dpg.get_viewport_client_width() if dpg.is_dearpygui_running() else 1200
        vp_h = dpg.get_viewport_client_height() if dpg.is_dearpygui_running() else 800
        win_w = min(880, max(600, vp_w - 100))
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
                dpg.add_spacer(width=15)
                # Volume Scale: % vs cc
                dpg.add_radio_button(
                    items=["Volume: %", "Volume: cm³"],
                    default_value="Volume: %",
                    horizontal=True,
                    tag=self._t("dvh_radio_volume_scale"),
                    callback=self._on_display_option_changed,
                )
                dpg.add_spacer(width=15)
                # Dose Scale: Gy vs %
                dpg.add_radio_button(
                    items=["Dose: Gy", "Dose: %"],
                    default_value="Dose: Gy",
                    horizontal=True,
                    tag=self._t("dvh_radio_dose_scale"),
                    callback=self._on_display_option_changed,
                )
                dpg.add_spacer(width=15)
                dpg.add_checkbox(
                    label="Legend",
                    default_value=True,
                    tag=self._t("dvh_chk_show_legend"),
                    callback=self._on_toggle_legend,
                )

            dpg.add_spacer(height=6)
            dpg.add_separator()
            dpg.add_spacer(height=6)

            # Main Section: 2 columns (Left: Plot, Right: Structure Checklist)
            with dpg.table(header_row=False, resizable=True, tag=self._t("dvh_split_table")):
                dpg.add_table_column(width_stretch=True, init_width_or_weight=620)
                dpg.add_table_column(width_fixed=True, init_width_or_weight=220)

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
                        dpg.add_text("Structures", color=cfg_c["text_header"])
                        with dpg.group(horizontal=True):
                            dpg.add_button(
                                label="All",
                                width=45,
                                callback=self._on_select_all_structures,
                            )
                            dpg.add_button(
                                label="None",
                                width=45,
                                callback=self._on_select_none_structures,
                            )

                        dpg.add_spacer(height=4)
                        with dpg.child_window(
                            height=280,
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
                    borders_innerH=True,
                    borders_innerV=True,
                    borders_outerH=True,
                    borders_outerV=True,
                    row_background=True,
                ):
                    dpg.add_table_column(label="Structure", width_stretch=True)
                    dpg.add_table_column(label="Vol (cm³)", width_fixed=True, init_width_or_weight=75)
                    dpg.add_table_column(label="Min (Gy)", width_fixed=True, init_width_or_weight=70)
                    dpg.add_table_column(label="Mean (Gy)", width_fixed=True, init_width_or_weight=75)
                    dpg.add_table_column(label="Max (Gy)", width_fixed=True, init_width_or_weight=70)
                    dpg.add_table_column(label="D98 (Gy)", width_fixed=True, init_width_or_weight=70)
                    dpg.add_table_column(label="D50 (Gy)", width_fixed=True, init_width_or_weight=70)
                    dpg.add_table_column(label="D2 (Gy)", width_fixed=True, init_width_or_weight=70)

        # Initial calculation
        self.recompute_and_update(fit_axes=True)

    def on_window_close(self):
        if dpg.does_item_exist(self.window_tag):
            dpg.delete_item(self.window_tag)

    def _on_toggle_legend(self, sender=None, app_data=None, user_data=None):
        chk_tag = self._t("dvh_chk_show_legend")
        leg_tag = self._t("dvh_plot_legend")
        if dpg.does_item_exist(leg_tag) and dpg.does_item_exist(chk_tag):
            val = dpg.get_value(chk_tag)
            dpg.configure_item(leg_tag, show=bool(val))

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
        for c in self.curves:
            c.enabled = True
            tag = self._t(f"chk_struct_{c.roi_id}")
            if dpg.does_item_exist(tag):
                dpg.set_value(tag, True)
        self._render_plot_and_table(fit_axes=False)

    def _on_select_none_structures(self):
        for c in self.curves:
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
        else:
            max_x = max((float(c.max_dose) for c in enabled_curves), default=60.0)
        max_x = max(max_x * 1.05, 1.0)

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

    def recompute_and_update(self, fit_axes: bool = True) -> None:
        """Computes DVH for all currently loaded ROIs on the active dose target."""
        if not self._api:
            return

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
        if dpg.does_item_exist(self._t("dvh_lbl_target_dose")):
            dpg.set_value(self._t("dvh_lbl_target_dose"), f"[{role}] {dose_name} ({unit_str})")

        # Get scaling / prescription dose if available
        if hasattr(self._c, "_ui") and self._c._ui and hasattr(self._c._ui, "scaling_comp"):
            sc = self._c._ui.scaling_comp.get_state(target_id)
            if sc and sc.norm_target_value > 0:
                self.norm_prescription_gy = float(sc.norm_target_value)

        # Global evaluation upper limit across dose volume to ensure uniform domain
        d_min, d_max = dose_vol.get_data_range()
        global_max_dose = max(float(d_max) * 1.05, 10.0)

        # Find reference image with ROIs (prioritize active viewer's view_state, or base)
        viewer = self._api.get_active_viewer()
        all_view_states = self._api.get_view_states()
        all_volumes = self._api.get_volumes()

        rois_dict = {}
        if viewer and viewer.view_state and viewer.view_state.rois:
            rois_dict = viewer.view_state.rois
        else:
            # Look for any open image with ROIs
            for vs in all_view_states.values():
                if vs.rois:
                    rois_dict = vs.rois
                    break

        self.curves = []
        for roi_id, roi_state in rois_dict.items():
            r_vol = all_volumes.get(roi_id)
            if not r_vol or r_vol.data is None:
                continue

            # Compute DVH curve
            color = getattr(roi_state, "color", [255, 0, 0])
            curve = compute_roi_dvh(
                dose_vol=dose_vol,
                roi_vol=r_vol,
                roi_name=roi_state.name,
                color=color,
                max_eval_dose=global_max_dose,
            )
            if curve:
                curve.roi_id = roi_id
                self.curves.append(curve)

        self._rebuild_structure_checklist()
        self._render_plot_and_table(fit_axes=fit_axes)

    def _rebuild_structure_checklist(self):
        list_tag = self._t("dvh_structures_list")
        if not dpg.does_item_exist(list_tag):
            return

        dpg.delete_item(list_tag, children_only=True)

        for c in self.curves:
            row_tag = self._t(f"dvh_struct_row_{c.roi_id}")
            with dpg.group(horizontal=True, parent=list_tag, tag=row_tag):
                dpg.add_checkbox(
                    default_value=c.enabled,
                    user_data=c.roi_id,
                    callback=self._on_toggle_structure,
                    tag=self._t(f"chk_struct_{c.roi_id}"),
                )
                r, g, b = c.color[:3]
                dpg.add_color_edit(
                    default_value=[r, g, b, 255],
                    no_inputs=True,
                    no_label=True,
                    no_alpha=True,
                    width=18,
                    height=18,
                )
                dpg.add_text(c.roi_name)

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
            r, g, b = c.color[:3]
            theme_tag = self._t(f"dvh_series_theme_{c.roi_id}")
            if dpg.does_item_exist(theme_tag):
                dpg.delete_item(theme_tag)
            with dpg.theme(tag=theme_tag):
                with dpg.theme_component(dpg.mvLineSeries):
                    dpg.add_theme_color(dpg.mvPlotCol_Line, [r, g, b, 255])
                    dpg.add_theme_style(dpg.mvPlotStyleVar_LineWeight, 2.0, category=dpg.mvThemeCat_Plots)
            dpg.bind_item_theme(line, theme_tag)

        # Apply axis limits if requested (initial load, display options change, fit view)
        if fit_axes:
            self._apply_axis_limits()

        # 2. Rebuild Metrics Table
        table_tag = self._t("dvh_metrics_table")
        if dpg.does_item_exist(table_tag):
            rows = dpg.get_item_children(table_tag, slot=1) or []
            for r in rows:
                dpg.delete_item(r)

            for c in self.curves:
                row = dpg.add_table_row(parent=table_tag)
                # Structure name with color indicator
                r, g, b = c.color[:3]
                dpg.add_text(c.roi_name, color=[r, g, b, 255], parent=row)
                dpg.add_text(f"{c.volume_cc:.2f}", parent=row)
                dpg.add_text(f"{c.min_dose:.2f}", parent=row)
                dpg.add_text(f"{c.mean_dose:.2f}", parent=row)
                dpg.add_text(f"{c.max_dose:.2f}", parent=row)
                dpg.add_text(f"{c.d98:.2f}", parent=row)
                dpg.add_text(f"{c.median_dose:.2f}", parent=row)
                dpg.add_text(f"{c.d2:.2f}", parent=row)

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

                # 1. Summary Metrics Table
                writer.writerow(["# DVH Summary Metrics"])
                writer.writerow(["Structure", "Volume (cm3)", "Min (Gy)", "Mean (Gy)", "Max (Gy)", "D98 (Gy)", "D50 (Gy)", "D2 (Gy)"])
                for c in self.curves:
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
                for c in self.curves:
                    headers.extend([f"{c.roi_name}_Dose_Gy", f"{c.roi_name}_Vol_Pct"])
                writer.writerow(headers)

                # Curves data rows
                max_pts = max((len(c.doses) for c in self.curves), default=0)
                for i in range(max_pts):
                    row = []
                    for c in self.curves:
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
