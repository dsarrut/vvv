import dearpygui.dearpygui as dpg
from typing import TYPE_CHECKING, Any
from vvv.plugins.plugin_api import PluginTagMixin, PluginAPI
from vvv.ui.ui_components import (
    build_section_title,
    build_horizontal_separator,
    build_beginner_tooltip,
    build_help_button,
    build_stepped_slider,
    build_delete_button,
    build_icon_button,
    FIELD_RIGHT_MARGIN,
    requirement_banner,
    set_controls_enabled,
)
from vvv.utils import compute_adaptive_step_and_speed
from vvv.ui.ui_scaling import IntensityScalingComponent
from vvv.plugins.dose.ui_dvh import DVHWindow

if TYPE_CHECKING:
    from .control_dose import DosePluginController


class DosePluginUI(PluginTagMixin):
    def __init__(self, plugin_id: str, controller: "DosePluginController"):
        self._plugin_id = plugin_id
        self._c = controller
        self._api: PluginAPI = None  # type: ignore
        self.scaling_comp = IntensityScalingComponent(
            prefix=self._t("scaling"),
            get_target_fn=self._get_scaling_target,
            default_target_value=50.0,
            ref_label="Prescription",
        )
        self.dvh_win = DVHWindow(plugin_id=self._plugin_id, controller=self._c)
        self.dvh_win.on_visibility_changed = self.set_dvh_button_state

    def _get_scaling_target(self):
        is_active, target_vol, is_ov, unit_str, target_id, target_vs = (
            self._c.get_dose_target_info()
        )
        if not is_active or not target_vol:
            return None, None, False, None, None
        return target_vol, target_vs, is_ov, unit_str, target_id

    def _bind_icon_font(self, item: Any) -> None:
        if dpg.does_item_exist("icon_font_tag"):
            dpg.bind_item_font(item, "icon_font_tag")

    def create_ui(self, parent, api: PluginAPI) -> None:
        self._api = api
        cfg_c = api.get_ui_config()["colors"]

        with dpg.group(parent=parent or 0, tag=self._plugin_id):
            build_section_title("Dose", cfg_c["text_header"])
            dpg.add_spacer(height=2)

            # -------------------------------------------------------------
            # 1. REQUIREMENT / INACTIVE STATE BANNER
            # -------------------------------------------------------------
            with requirement_banner(
                self._t("group_dose_requirement"),
                "Needs a dose image (Gy, mGy or Gy/decay) as base or fused image.",
                self._t("text_current_units"),
                cfg_c,
            ):
                btn_enable = dpg.add_button(
                    label="Enable (Set unit to Gy)",
                    width=-FIELD_RIGHT_MARGIN,
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
            # Always shown, greyed out while no dose image (shows what exists)
            with dpg.group(tag=self._t("group_dose_content")):
                with dpg.group(horizontal=True):
                    dpg.add_text("Target: ", color=cfg_c["text_dim"])
                    dpg.add_text(
                        "None",
                        tag=self._t("text_target_dose_image"),
                        color=cfg_c["text_active"],
                    )

                dpg.add_spacer(height=5)

                # --- Shared Intensity Scaling & Normalization Component ---
                self.scaling_comp.create_ui(parent=None, api=api)

                dpg.add_spacer(height=6)

                # --- Isodose Contours Section ---
                build_section_title("Isodose Contours", cfg_c["text_header"])
                dpg.add_spacer(height=3)

                # 1. Shading toggle and Opacity slider on the same row
                with dpg.group(horizontal=True, tag=self._t("group_shading_opacity")):
                    dpg.add_checkbox(
                        label="Shading",
                        tag=self._t("check_isodose_shading"),
                        default_value=False,
                        callback=self._c.on_toggle_shading,
                    )
                    build_beginner_tooltip(
                        self._t("check_isodose_shading"),
                        "Displays semi-transparent colorwash shading between isodose levels.",
                        api,
                    )
                    dpg.add_text("Opacity:", color=cfg_c["text_dim"])
                    dpg.add_slider_float(
                        tag=self._t("slider_shading_opacity"),
                        default_value=0.5,
                        min_value=0.0,
                        max_value=1.0,
                        format="%.2f",
                        width=-1,
                        callback=self._c.on_shading_opacity_changed,
                    )
                    build_beginner_tooltip(
                        self._t("slider_shading_opacity"),
                        "Opacity of the dose overlay or shading.",
                        api,
                    )

                dpg.add_spacer(height=2)

                # 2. Min threshold stepped slider
                build_stepped_slider(
                    "Min Thr:",
                    self._t("drag_dose_threshold"),
                    callback=self._c.on_dose_threshold_changed,
                    step_callback=self._c.on_step_button_clicked,
                    has_checkbox=True,
                    check_tag=self._t("check_dose_threshold"),
                    check_cb=self._c.on_dose_threshold_toggle,
                    gui=api,
                )
                build_beginner_tooltip(
                    self._t("drag_dose_threshold"),
                    "Threshold for the dose image. Voxels below this value are made transparent "
                    "so that background anatomy (e.g. CT/MRI) remains clearly visible.",
                    api,
                )

                dpg.add_spacer(height=2)

                # 3. Lines + Sub-Pixel + Reset defaults icon
                with dpg.group(horizontal=True):
                    dpg.add_checkbox(
                        label="Lines",
                        tag=self._t("check_isodose_enable"),
                        default_value=True,
                        callback=self._c.on_toggle_isocontours,
                    )
                    build_beginner_tooltip(
                        self._t("check_isodose_enable"),
                        "Displays isolines / isodose contours for the active dose image.",
                        api,
                    )

                    dpg.add_checkbox(
                        label="Sub-Pixel",
                        tag=self._t("check_isodose_subpixel"),
                        default_value=True,
                        callback=self._c.on_toggle_subpixel,
                    )
                    build_beginner_tooltip(
                        self._t("check_isodose_subpixel"),
                        "Uses marching squares linear interpolation for smooth sub-voxel curves.",
                        api,
                    )

                    build_icon_button(
                        icon="\uf0e2",  # arrow-rotate-left: back to the defaults
                        tag=self._t("btn_reset_levels"),
                        callback=self._c.on_reset_levels_clicked,
                        tooltip="Reset the default isodose levels (10% to 107%)",
                        api=api,
                    )

                dpg.add_spacer(height=4)
                dpg.add_text("Levels:", color=cfg_c["text_dim"])

                # Dynamic container for individual isodose levels
                dpg.add_group(tag=self._t("group_isodose_levels"))

                dpg.add_spacer(height=10)
                build_horizontal_separator()
                dpg.add_spacer(height=6)

                # --- Dose-Volume Histogram (DVH) Section ---
                build_section_title("Dose-Volume Histogram (DVH)", cfg_c["text_header"])
                btn_dvh = dpg.add_button(
                    label="Show DVH",
                    width=-FIELD_RIGHT_MARGIN,
                    callback=self.on_open_dvh_clicked,
                    tag=self._t("btn_open_dvh"),
                )
                build_beginner_tooltip(
                    btn_dvh,
                    "Shows / hides the Dose-Volume Histogram (DVH) window: cumulative and\n"
                    "differential curves of the ROIs, D98, D50, D2, and metrics export.",
                    api,
                )

    def on_open_dvh_clicked(
        self, sender=None, app_data=None, user_data=None, async_calc: bool = True
    ) -> None:
        """Shows the DVH window, or hides it when it is open."""
        if not self._api:
            return
        if self.dvh_win.is_open():
            self.dvh_win.on_window_close()
        else:
            self.dvh_win.show_window(self._api, async_calc=async_calc)

    def set_dvh_button_state(self, is_open: bool) -> None:
        """The DVH button shows whether the window is open (blue), like the sync links."""
        btn = self._t("btn_open_dvh")
        if not dpg.does_item_exist(btn):
            return
        dpg.configure_item(btn, label="Hide DVH" if is_open else "Show DVH")
        theme = "active_button_theme"
        dpg.bind_item_theme(btn, theme if is_open and dpg.does_item_exist(theme) else 0)

    def rebuild_levels_ui(self, api: PluginAPI) -> None:
        """Reconstructs the list of isodose level rows."""
        levels_group = self._t("group_isodose_levels")
        if not dpg.does_item_exist(levels_group):
            return

        dpg.delete_item(levels_group, children_only=True)

        is_active, target_vol, is_overlay, current_unit, target_id, target_vs = (
            self._c.get_dose_target_info()
        )
        if not is_active or not target_id:
            return

        state = self._c.get_isocontour_state(target_id)
        unit_str = "%"

        for idx, lvl in enumerate(state.levels):
            row_tag = self._t(f"row_level_{idx}")
            with dpg.group(horizontal=True, parent=levels_group, tag=row_tag):
                # Enable / Disable checkbox
                dpg.add_checkbox(
                    default_value=lvl.enabled,
                    user_data=idx,
                    callback=self._c.on_level_enabled_toggle,
                    tag=self._t(f"chk_lvl_{idx}"),
                )

                # Color picker
                dpg.add_color_edit(
                    default_value=lvl.color,
                    user_data=idx,
                    callback=self._c.on_level_color_changed,
                    no_inputs=True,
                    no_label=True,
                    no_alpha=True,
                    width=20,
                    height=20,
                    tag=self._t(f"col_lvl_{idx}"),
                )

                # Value input float
                dpg.add_input_float(
                    default_value=float(lvl.value),
                    user_data=idx,
                    format="%.4g",
                    step=0.0,
                    step_fast=0.0,
                    width=75,
                    callback=self._c.on_level_value_changed,
                    tag=self._t(f"input_lvl_{idx}"),
                )

                # Unit label
                dpg.add_text(unit_str, color=[255, 255, 255, 255])

                build_delete_button(
                    user_data=idx,
                    callback=self._c.on_delete_level_clicked,
                    tag=self._t(f"btn_del_lvl_{idx}"),
                    tooltip="Delete this isodose level",
                    api=self._api,
                )

    def update_ui(self, api: PluginAPI) -> None:
        if not dpg.does_item_exist(self._t("group_dose_requirement")):
            return

        is_active, target_vol, is_overlay, current_unit, target_id, target_vs = (
            self._c.get_dose_target_info()
        )

        if is_active and target_vol is not None and target_id is not None:
            # Show active tools container
            dpg.configure_item(self._t("group_dose_requirement"), show=False)
            set_controls_enabled(self._t("group_dose_content"), True)  # then per-control states below

            role = "Overlay" if is_overlay else "Base"
            display_name = getattr(target_vol, "name", "Image")
            target_str = f"[{role}] {display_name} ({current_unit})"
            if dpg.does_item_exist(self._t("text_target_dose_image")):
                dpg.set_value(self._t("text_target_dose_image"), target_str)

            # Update shared scaling component
            self.scaling_comp.update_ui(api)

            # Update threshold UI
            thr_tag = self._t("drag_dose_threshold")
            chk_thr_tag = self._t("check_dose_threshold")
            if dpg.does_item_exist(thr_tag) and target_vs:
                cur_thr = getattr(target_vs.display, "min_threshold", None)
                has_thr = cur_thr is not None
                if dpg.does_item_exist(chk_thr_tag) and not dpg.is_item_active(chk_thr_tag):
                    dpg.set_value(chk_thr_tag, has_thr)

                ww = getattr(target_vs.display, "ww", 100.0)
                _, dynamic_speed, dpg_fmt = compute_adaptive_step_and_speed(ww)
                dpg.configure_item(thr_tag, speed=dynamic_speed, format=dpg_fmt, enabled=has_thr)
                if dpg.does_item_exist(f"btn_{thr_tag}_minus"):
                    dpg.configure_item(f"btn_{thr_tag}_minus", enabled=has_thr)
                if dpg.does_item_exist(f"btn_{thr_tag}_plus"):
                    dpg.configure_item(f"btn_{thr_tag}_plus", enabled=has_thr)

                if has_thr and not dpg.is_item_active(thr_tag):
                    dpg.set_value(thr_tag, cur_thr)

            # Update isocontour checkbox values
            state = self._c.get_isocontour_state(target_id)
            if dpg.does_item_exist(self._t("check_isodose_enable")):
                dpg.set_value(self._t("check_isodose_enable"), state.is_enabled)
            if dpg.does_item_exist(self._t("check_isodose_shading")):
                dpg.set_value(self._t("check_isodose_shading"), state.colorwash_enabled)
            if dpg.does_item_exist(self._t("check_isodose_subpixel")):
                dpg.set_value(self._t("check_isodose_subpixel"), state.subpixel_accurate)
            slider_tag = self._t("slider_shading_opacity")
            if dpg.does_item_exist(slider_tag):
                dpg.configure_item(slider_tag, enabled=is_overlay or state.colorwash_enabled)
                if not dpg.is_item_active(slider_tag):
                    cur_op = state.colorwash_opacity
                    if is_overlay and api:
                        active_v = api.get_active_viewer()
                        if active_v and active_v.view_state and active_v.view_state.display.overlay:
                            cur_op = active_v.view_state.display.overlay.opacity
                            state.colorwash_opacity = cur_op
                    dpg.set_value(slider_tag, cur_op)

            # Check if levels rows need to be refreshed
            levels_group = self._t("group_isodose_levels")
            if dpg.does_item_exist(levels_group):
                children = dpg.get_item_children(levels_group, slot=1) or []
                if len(children) != len(state.levels):
                    self.rebuild_levels_ui(api)
                else:
                    for idx, lvl in enumerate(state.levels):
                        chk_tag = self._t(f"chk_lvl_{idx}")
                        inp_tag = self._t(f"input_lvl_{idx}")
                        if dpg.does_item_exist(chk_tag):
                            dpg.set_value(chk_tag, lvl.enabled)
                        if dpg.does_item_exist(inp_tag) and not dpg.is_item_active(inp_tag):
                            dpg.set_value(inp_tag, lvl.value)
        else:
            # Show requirement banner
            dpg.configure_item(self._t("group_dose_requirement"), show=True)
            set_controls_enabled(self._t("group_dose_content"), False)

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

        if hasattr(self, "dvh_win") and self.dvh_win:
            self.dvh_win.update_ui(api)
