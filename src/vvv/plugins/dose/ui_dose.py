import dearpygui.dearpygui as dpg
from typing import TYPE_CHECKING
from vvv.plugins.plugin_api import PluginTagMixin, PluginAPI
from vvv.ui.ui_components import build_section_title, build_beginner_tooltip, build_help_button
from .control_dose import NORM_MODES

if TYPE_CHECKING:
    from .control_dose import DosePluginController


class DosePluginUI(PluginTagMixin):
    def __init__(self, plugin_id: str, controller: "DosePluginController"):
        self._plugin_id = plugin_id
        self._c = controller
        self._api: PluginAPI = None  # type: ignore

    def create_ui(self, parent, api: PluginAPI) -> None:
        self._api = api
        cfg_c = api.get_ui_config()["colors"]

        with dpg.group(parent=parent or 0, tag=self._plugin_id):
            build_section_title("Dose", cfg_c["text_header"])

            # -------------------------------------------------------------
            # 1. REQUIREMENT / INACTIVE STATE BANNER
            # -------------------------------------------------------------
            with dpg.group(tag=self._t("group_dose_requirement"), show=True):
                dpg.add_text(
                    "Dose Unit Required",
                    color=cfg_c.get("warning", [255, 180, 50, 255]),
                )
                dpg.add_spacer(height=4)
                dpg.add_text(
                    "This tool is active when the base image or\n"
                    "fused overlay has a Gy-compatible unit:\n"
                    "  - Gy\n"
                    "  - mGy\n"
                    "  - Gy/decay",
                    color=cfg_c["text_dim"],
                )
                dpg.add_spacer(height=6)
                dpg.add_text(
                    "Current: No Gy image selected",
                    tag=self._t("text_current_units"),
                    color=cfg_c["text_dim"],
                )
                dpg.add_spacer(height=8)

                btn_enable = dpg.add_button(
                    label="Enable (Set unit to Gy)",
                    width=-1,
                    callback=self._c.on_enable_clicked,
                    tag=self._t("btn_enable_gy"),
                )
                build_beginner_tooltip(
                    btn_enable,
                    "Assigns physical unit 'Gy' to the active dose image\n"
                    "(prioritizes fused overlay if present, otherwise base image).",
                    api,
                )
                build_help_button(
                    "Radiation Dose Requirements:\n"
                    "- The dose plugin analyzes absorbed dose in Gray (Gy).\n"
                    "- DICOM RTDOSE files are automatically detected as Gy.\n"
                    "- For other formats (NIfTI, MetaImage), clicking 'Enable' sets the unit to Gy.",
                    api,
                )

            # -------------------------------------------------------------
            # 2. ACTIVE DOSE STATE CONTENT (Tools Container)
            # -------------------------------------------------------------
            with dpg.group(tag=self._t("group_dose_content"), show=False):
                with dpg.group(horizontal=True):
                    dpg.add_text("Target: ", color=cfg_c["text_dim"])
                    dpg.add_text(
                        "None",
                        tag=self._t("text_target_dose_image"),
                        color=cfg_c["text_active"],
                    )

                dpg.add_spacer(height=4)
                dpg.add_separator()
                dpg.add_spacer(height=4)

                # --- Section A: Dose Scaling ---
                with dpg.collapsing_header(label="Dose Scaling", default_open=True):
                    dpg.add_text("Scaling Factor (S):", color=cfg_c["text_dim"])
                    inp_s = dpg.add_input_float(
                        tag=self._t("input_scale_factor"),
                        default_value=1.0,
                        step=0.1,
                        step_fast=1.0,
                        format="%.4g",
                        width=-1,
                        callback=self._on_scale_factor_changed,
                    )
                    build_beginner_tooltip(
                        inp_s,
                        "Physical dose multiplier: D_scaled = S * D_raw.\n"
                        "Use for Monte Carlo calibration or unit conversions.",
                        api,
                    )

                    with dpg.group(horizontal=True):
                        dpg.add_button(
                            label="x1",
                            width=45,
                            callback=lambda: self._set_scale_factor(1.0),
                        )
                        dpg.add_button(
                            label="x0.001",
                            width=55,
                            callback=lambda: self._set_scale_factor(0.001),
                        )
                        dpg.add_button(
                            label="x1000",
                            width=55,
                            callback=lambda: self._set_scale_factor(1000.0),
                        )
                        btn_bake = dpg.add_button(
                            label="Apply to Voxels",
                            callback=lambda: self._c.bake_scaling_factor(),
                        )
                        build_beginner_tooltip(
                            btn_bake,
                            "Permanently multiplies the voxel values in memory by S\n"
                            "and resets S back to 1.0.",
                            api,
                        )

                dpg.add_spacer(height=4)
                dpg.add_separator()
                dpg.add_spacer(height=4)

                # --- Section B: Normalization Modes ---
                with dpg.collapsing_header(label="Normalization", default_open=True):
                    dpg.add_text("Mode:", color=cfg_c["text_dim"])
                    dpg.add_radio_button(
                        tag=self._t("radio_norm_mode"),
                        items=NORM_MODES,
                        default_value="Absolute Dose",
                        callback=self._on_norm_mode_changed,
                    )

                    # Prescription dose sub-group
                    with dpg.group(tag=self._t("group_norm_rx"), show=False):
                        dpg.add_spacer(height=2)
                        dpg.add_text("Prescription Dose (Gy):", color=cfg_c["text_dim"])
                        inp_rx = dpg.add_input_float(
                            tag=self._t("input_rx_dose"),
                            default_value=50.0,
                            step=1.0,
                            step_fast=10.0,
                            format="%.3g",
                            width=-1,
                            callback=self._on_rx_dose_changed,
                        )
                        build_beginner_tooltip(
                            inp_rx,
                            "Reference target prescription dose D_rx (100% level).",
                            api,
                        )
                        with dpg.group(horizontal=True):
                            dpg.add_button(
                                label="2 Gy",
                                width=45,
                                callback=lambda: self._set_rx_dose(2.0),
                            )
                            dpg.add_button(
                                label="50 Gy",
                                width=50,
                                callback=lambda: self._set_rx_dose(50.0),
                            )
                            dpg.add_button(
                                label="60 Gy",
                                width=50,
                                callback=lambda: self._set_rx_dose(60.0),
                            )
                            dpg.add_button(
                                label="Set to Max",
                                callback=self._set_rx_to_max,
                            )

                    # ROI Mean sub-group
                    with dpg.group(tag=self._t("group_norm_roi"), show=False):
                        dpg.add_spacer(height=2)
                        dpg.add_text("Target ROI:", color=cfg_c["text_dim"])
                        dpg.add_combo(
                            tag=self._t("combo_norm_roi"),
                            items=["(None)"],
                            default_value="(None)",
                            width=-1,
                            callback=self._on_roi_selected,
                        )
                        dpg.add_text(
                            "ROI Mean: ---",
                            tag=self._t("text_norm_roi_mean"),
                            color=cfg_c["text_active"],
                        )

                dpg.add_spacer(height=4)
                dpg.add_separator()
                dpg.add_spacer(height=4)

                # --- Section C: Dose Range & Sampling ---
                with dpg.collapsing_header(label="Dose Range & Sampling", default_open=True):
                    with dpg.group(horizontal=True):
                        dpg.add_text("Min Dose: ", color=cfg_c["text_dim"])
                        dpg.add_text("0.00 Gy", tag=self._t("text_dose_min"), color=cfg_c["text_active"])
                    with dpg.group(horizontal=True):
                        dpg.add_text("Max Dose: ", color=cfg_c["text_dim"])
                        dpg.add_text("0.00 Gy", tag=self._t("text_dose_max"), color=cfg_c["text_active"])

                    with dpg.group(tag=self._t("group_dose_ref_row"), horizontal=True, show=False):
                        dpg.add_text("Ref (100%): ", color=cfg_c["text_dim"])
                        dpg.add_text("0.00 Gy", tag=self._t("text_dose_ref"), color=cfg_c.get("warning", [255, 180, 50, 255]))

                    dpg.add_spacer(height=2)
                    with dpg.group(horizontal=True):
                        dpg.add_text("Point Dose: ", color=cfg_c["text_dim"])
                        dpg.add_text("---", tag=self._t("text_dose_point"), color=cfg_c.get("text_status_ok", [80, 220, 100, 255]))

                dpg.add_spacer(height=4)
                dpg.add_separator()
                dpg.add_spacer(height=4)

                # --- Section D: Display & Presets ---
                with dpg.collapsing_header(label="Display & Presets", default_open=True):
                    dpg.add_text("Window / Level Presets:", color=cfg_c["text_dim"])
                    with dpg.group(horizontal=True):
                        btn_w100 = dpg.add_button(
                            label="[0 - 100%]",
                            callback=lambda: self._c.apply_display_window("rx_100"),
                        )
                        build_beginner_tooltip(
                            btn_w100,
                            "Sets window range from 0 to 100% of reference dose.",
                            api,
                        )
                        btn_w107 = dpg.add_button(
                            label="[0 - 107%]",
                            callback=lambda: self._c.apply_display_window("rx_107"),
                        )
                        build_beginner_tooltip(
                            btn_w107,
                            "Sets window range from 0 to 107% (standard ICRU clinical target coverage).",
                            api,
                        )
                        btn_wfull = dpg.add_button(
                            label="Full Range",
                            callback=lambda: self._c.apply_display_window("full_range"),
                        )
                        build_beginner_tooltip(
                            btn_wfull,
                            "Sets window range covering the entire image min to max dose.",
                            api,
                        )

                    dpg.add_spacer(height=2)
                    chk_thr = dpg.add_checkbox(
                        tag=self._t("chk_bg_threshold"),
                        label="Threshold < 5% Ref",
                        default_value=False,
                        callback=self._on_threshold_toggled,
                    )
                    build_beginner_tooltip(
                        chk_thr,
                        "Hides low background dose below 5% of the reference level\n"
                        "so underlying anatomy remains visible.",
                        api,
                    )

                    dpg.add_spacer(height=4)
                    dpg.add_text("Colormap:", color=cfg_c["text_dim"])
                    with dpg.group(horizontal=True):
                        dpg.add_button(
                            label="Dosimetry",
                            callback=lambda: self._c.set_colormap("Dosimetry"),
                        )
                        dpg.add_button(
                            label="Jet",
                            callback=lambda: self._c.set_colormap("Jet"),
                        )
                        dpg.add_button(
                            label="Turbo",
                            callback=lambda: self._c.set_colormap("Turbo"),
                        )
                        dpg.add_button(
                            label="Hot",
                            callback=lambda: self._c.set_colormap("Hot"),
                        )

    # -------------------------------------------------------------
    # Callbacks
    # -------------------------------------------------------------
    def _on_scale_factor_changed(self, sender, app_data, user_data) -> None:
        _, _, _, _, target_id, _ = self._c.get_dose_target_info()
        if target_id and app_data is not None:
            settings = self._c.get_settings(target_id)
            settings.scaling_factor = float(app_data)
            self.update_ui(self._api)
            if self._api:
                self._api.request_refresh()

    def _set_scale_factor(self, val: float) -> None:
        _, _, _, _, target_id, _ = self._c.get_dose_target_info()
        if target_id:
            settings = self._c.get_settings(target_id)
            settings.scaling_factor = val
            if dpg.does_item_exist(self._t("input_scale_factor")):
                dpg.set_value(self._t("input_scale_factor"), val)
            self.update_ui(self._api)
            if self._api:
                self._api.request_refresh()

    def _on_norm_mode_changed(self, sender, app_data, user_data) -> None:
        _, _, _, _, target_id, _ = self._c.get_dose_target_info()
        if target_id and app_data is not None:
            settings = self._c.get_settings(target_id)
            settings.norm_mode = str(app_data)
            self.update_ui(self._api)
            if self._api:
                self._api.request_refresh()

    def _on_rx_dose_changed(self, sender, app_data, user_data) -> None:
        _, _, _, _, target_id, _ = self._c.get_dose_target_info()
        if target_id and app_data is not None:
            settings = self._c.get_settings(target_id)
            settings.rx_dose = float(app_data)
            self.update_ui(self._api)
            if self._api:
                self._api.request_refresh()

    def _set_rx_dose(self, val: float) -> None:
        _, _, _, _, target_id, _ = self._c.get_dose_target_info()
        if target_id:
            settings = self._c.get_settings(target_id)
            settings.rx_dose = val
            if dpg.does_item_exist(self._t("input_rx_dose")):
                dpg.set_value(self._t("input_rx_dose"), val)
            self.update_ui(self._api)
            if self._api:
                self._api.request_refresh()

    def _set_rx_to_max(self) -> None:
        is_active, target_vol, _, _, target_id, _ = self._c.get_dose_target_info()
        if is_active and target_vol and target_id:
            settings = self._c.get_settings(target_id)
            _, d_max = self._c.get_scaled_dose_range(target_vol, settings.scaling_factor)
            settings.rx_dose = d_max
            if dpg.does_item_exist(self._t("input_rx_dose")):
                dpg.set_value(self._t("input_rx_dose"), d_max)
            self.update_ui(self._api)
            if self._api:
                self._api.request_refresh()

    def _on_roi_selected(self, sender, app_data, user_data) -> None:
        _, _, _, _, target_id, _ = self._c.get_dose_target_info()
        if target_id and app_data:
            settings = self._c.get_settings(target_id)
            # app_data is formatted as "{roi_name} ({roi_id})" or "(None)"
            if app_data == "(None)":
                settings.norm_roi_id = None
            else:
                parts = app_data.rsplit(" (", 1)
                if len(parts) == 2 and parts[1].endswith(")"):
                    settings.norm_roi_id = parts[1][:-1]
                else:
                    settings.norm_roi_id = app_data
            self.update_ui(self._api)
            if self._api:
                self._api.request_refresh()

    def _on_threshold_toggled(self, sender, app_data, user_data) -> None:
        if app_data is not None:
            self._c.set_background_threshold(bool(app_data))

    # -------------------------------------------------------------
    # UI Update Logic
    # -------------------------------------------------------------
    def update_ui(self, api: PluginAPI) -> None:
        if not dpg.does_item_exist(self._t("group_dose_requirement")):
            return

        is_active, target_vol, is_overlay, current_unit, target_id, target_vs = (
            self._c.get_dose_target_info()
        )

        if is_active and target_vol is not None and target_id is not None:
            # 1. Show active content, hide requirement banner
            dpg.configure_item(self._t("group_dose_requirement"), show=False)
            dpg.configure_item(self._t("group_dose_content"), show=True)

            role = "Overlay" if is_overlay else "Base"
            display_name = getattr(target_vol, "name", "Image")
            target_str = f"[{role}] {display_name} ({current_unit})"
            if dpg.does_item_exist(self._t("text_target_dose_image")):
                dpg.set_value(self._t("text_target_dose_image"), target_str)

            settings = self._c.get_settings(target_id)
            s = settings.scaling_factor
            d_min, d_max = self._c.get_scaled_dose_range(target_vol, s)
            d_ref = self._c.get_reference_dose(target_vol, is_overlay, settings)
            unit_lbl = current_unit or "Gy"

            # 2. Update Scaling Input (only if not active to avoid cursor fighting)
            if dpg.does_item_exist(self._t("input_scale_factor")):
                if not dpg.is_item_active(self._t("input_scale_factor")):
                    dpg.set_value(self._t("input_scale_factor"), s)

            # 3. Update Normalization Mode & Sub-groups
            if dpg.does_item_exist(self._t("radio_norm_mode")):
                if dpg.get_value(self._t("radio_norm_mode")) != settings.norm_mode:
                    dpg.set_value(self._t("radio_norm_mode"), settings.norm_mode)

            is_rx = settings.norm_mode == "% to Prescription"
            is_roi = settings.norm_mode == "% to ROI Mean"
            if dpg.does_item_exist(self._t("group_norm_rx")):
                dpg.configure_item(self._t("group_norm_rx"), show=is_rx)
            if dpg.does_item_exist(self._t("group_norm_roi")):
                dpg.configure_item(self._t("group_norm_roi"), show=is_roi)

            if is_rx and dpg.does_item_exist(self._t("input_rx_dose")):
                if not dpg.is_item_active(self._t("input_rx_dose")):
                    dpg.set_value(self._t("input_rx_dose"), settings.rx_dose)

            if is_roi:
                # Update combo list of ROIs
                viewer = api.get_active_viewer()
                roi_items = ["(None)"]
                roi_dict = getattr(viewer.view_state, "rois", {}) if (viewer and viewer.view_state) else {}
                current_selected_str = "(None)"
                for r_id, r_state in roi_dict.items():
                    r_name = getattr(r_state, "name", r_id)
                    item_str = f"{r_name} ({r_id})"
                    roi_items.append(item_str)
                    if r_id == settings.norm_roi_id:
                        current_selected_str = item_str

                if dpg.does_item_exist(self._t("combo_norm_roi")):
                    dpg.configure_item(self._t("combo_norm_roi"), items=roi_items)
                    dpg.set_value(self._t("combo_norm_roi"), current_selected_str)

                # Show computed ROI Mean
                raw_mean = self._c.compute_roi_mean_dose(target_vol, is_overlay, settings.norm_roi_id) if settings.norm_roi_id else 0.0
                scaled_mean = raw_mean * s
                if dpg.does_item_exist(self._t("text_norm_roi_mean")):
                    dpg.set_value(self._t("text_norm_roi_mean"), f"ROI Mean: {scaled_mean:.3g} {unit_lbl}")

            # 4. Update Dose Range Readouts
            if settings.norm_mode == "Absolute Dose":
                txt_min = f"{d_min:.3g} {unit_lbl}"
                txt_max = f"{d_max:.3g} {unit_lbl}"
                if dpg.does_item_exist(self._t("group_dose_ref_row")):
                    dpg.configure_item(self._t("group_dose_ref_row"), show=False)
            else:
                pct_min = (d_min / d_ref) * 100.0 if d_ref > 0 else 0.0
                pct_max = (d_max / d_ref) * 100.0 if d_ref > 0 else 0.0
                txt_min = f"{d_min:.3g} {unit_lbl}  ({pct_min:.1f} %)"
                txt_max = f"{d_max:.3g} {unit_lbl}  ({pct_max:.1f} %)"
                if dpg.does_item_exist(self._t("group_dose_ref_row")):
                    dpg.configure_item(self._t("group_dose_ref_row"), show=True)
                if dpg.does_item_exist(self._t("text_dose_ref")):
                    dpg.set_value(self._t("text_dose_ref"), f"{d_ref:.3g} {unit_lbl}")

            if dpg.does_item_exist(self._t("text_dose_min")):
                dpg.set_value(self._t("text_dose_min"), txt_min)
            if dpg.does_item_exist(self._t("text_dose_max")):
                dpg.set_value(self._t("text_dose_max"), txt_max)

            # 5. Update Point Dose Sampling (Crosshair Tracker)
            pt_dose, pt_pct = self._c.get_crosshair_dose_sample()
            if pt_dose is not None:
                if settings.norm_mode == "Absolute Dose":
                    txt_pt = f"{pt_dose:.3g} {unit_lbl}"
                else:
                    txt_pt = f"{pt_dose:.3g} {unit_lbl}  ({pt_pct:.1f} %)"
            else:
                txt_pt = "---"

            if dpg.does_item_exist(self._t("text_dose_point")):
                dpg.set_value(self._t("text_dose_point"), txt_pt)

            # 6. Background threshold checkbox state
            if dpg.does_item_exist(self._t("chk_bg_threshold")):
                dpg.set_value(self._t("chk_bg_threshold"), settings.threshold_5pct)

        else:
            # Show requirement banner, hide tools content
            dpg.configure_item(self._t("group_dose_requirement"), show=True)
            dpg.configure_item(self._t("group_dose_content"), show=False)

            viewer = api.get_active_viewer()
            if viewer and viewer.volume:
                base_name = getattr(viewer.volume, "name", "Base")
                base_unit = getattr(viewer.volume, "unit", "?") or "?"
                status_txt = f"Base: {base_name} ({base_unit})"

                if viewer.view_state and viewer.view_state.display.overlay:
                    ov_id = viewer.view_state.display.overlay.image_id
                    ov_vol = api.get_volumes().get(ov_id) if ov_id else None
                    if ov_vol:
                        ov_unit = getattr(ov_vol, "unit", "?") or "?"
                        status_txt += f"\nOverlay: {ov_vol.name} ({ov_unit})"
            else:
                status_txt = "No image selected"

            if dpg.does_item_exist(self._t("text_current_units")):
                dpg.set_value(self._t("text_current_units"), f"Current: {status_txt}")
