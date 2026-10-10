import dearpygui.dearpygui as dpg
from typing import TYPE_CHECKING
from vvv.plugins.plugin_api import PluginTagMixin, PluginAPI
from vvv.ui.ui_components import build_section_title, build_beginner_tooltip, build_help_button
from vvv.ui.ui_scaling import IntensityScalingComponent

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

    def _get_scaling_target(self):
        is_active, target_vol, is_ov, unit_str, target_id, target_vs = (
            self._c.get_dose_target_info()
        )
        if not is_active or not target_vol:
            return None, None, False, None, None
        return target_vol, target_vs, is_ov, unit_str, target_id

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
                    color=[255, 255, 255, 255],
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

                # --- Shared Intensity Scaling & Normalization Component ---
                self.scaling_comp.create_ui(parent=None, api=api)

    def update_ui(self, api: PluginAPI) -> None:
        if not dpg.does_item_exist(self._t("group_dose_requirement")):
            return

        is_active, target_vol, is_overlay, current_unit, target_id, target_vs = (
            self._c.get_dose_target_info()
        )

        if is_active and target_vol is not None and target_id is not None:
            # Show active tools container
            dpg.configure_item(self._t("group_dose_requirement"), show=False)
            dpg.configure_item(self._t("group_dose_content"), show=True)

            role = "Overlay" if is_overlay else "Base"
            display_name = getattr(target_vol, "name", "Image")
            target_str = f"[{role}] {display_name} ({current_unit})"
            if dpg.does_item_exist(self._t("text_target_dose_image")):
                dpg.set_value(self._t("text_target_dose_image"), target_str)

            # Update shared scaling component
            self.scaling_comp.update_ui(api)
        else:
            # Show requirement banner
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
