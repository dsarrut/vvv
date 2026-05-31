import dearpygui.dearpygui as dpg
from vvv.ui.ui_components import build_section_title, build_beginner_tooltip, build_stepped_slider
from vvv.plugins.plugin_api import PluginTagMixin
from vvv.utils import ViewMode


class MIPPluginUI(PluginTagMixin):
    def __init__(self, plugin_id: str, controller):
        self._plugin_id = plugin_id
        self._c = controller

    def create_ui(self, parent, api) -> None:
        cfg_c = api.get_ui_config()["colors"]

        with dpg.group(parent=parent or 0, tag=self._plugin_id):
            build_section_title("MIP Viewer", cfg_c["text_header"])

            active_title = dpg.add_text(
                "No Image Selected",
                tag=self._t("active_title"),
                color=cfg_c["text_active"],
            )
            build_beginner_tooltip(
                active_title,
                "The currently active image.",
                api,
            )

            # Checkbox: MIP Mode
            chk_mip = dpg.add_checkbox(
                label="MIP Mode",
                tag=self._t("check_mip_mode"),
                callback=self._c.on_mip_toggle,
                default_value=False,
            )
            build_beginner_tooltip(
                chk_mip,
                "Enables Maximum Intensity Projection rendering.",
                api,
            )

            # Current orientation display
            axis_text = dpg.add_text(
                "Projection Axis: Y", tag=self._t("text_projection_axis")
            )
            build_beginner_tooltip(
                axis_text,
                "The current projection axis, determined by the active viewer orientation (changed with F1, F2).",
                api,
            )

            # Slider: Depth Cueing
            sld_depth = dpg.add_slider_float(
                label="Depth Cueing",
                tag=self._t("slider_depth_cueing"),
                min_value=0.0,
                max_value=1.0,
                default_value=0.0,
                callback=self._c.on_depth_cueing_changed,
                format="%.2f",
            )
            build_beginner_tooltip(
                sld_depth,
                "Dim intensities of voxels further away from the projection plane (0.0=none, 1.0=full).",
                api,
            )

            # Stepped slider: Rotation Angle
            build_stepped_slider(
                "Rotation Angle",
                self._t("slider_rotation_angle"),
                callback=self._c.on_rotation_changed,
                step_callback=self._c.on_rotation_step_button,
                min_val=-180.0,
                max_val=180.0,
                default_val=0.0,
                format="%.1f deg",
            )

            # Stepped slider: Angle Step
            build_stepped_slider(
                "Angle Step",
                self._t("slider_rotation_step"),
                callback=self._c.on_step_changed,
                step_callback=self._c.on_step_size_button,
                min_val=1.0,
                max_val=45.0,
                default_val=5.0,
                format="%.1f deg",
            )

            # Checkbox / Toggle: Invert Contrast
            chk_invert = dpg.add_checkbox(
                label="Black on White",
                tag=self._t("check_invert_contrast"),
                callback=self._c.on_invert_toggle,
                default_value=False,
            )
            build_beginner_tooltip(
                chk_invert,
                "Invert contrast to render hot-spots as dark areas on a light background.",
                api,
            )

    def update_ui(self, api) -> None:
        viewer = api.get_active_viewer()
        has_image = bool(viewer and viewer.view_state and viewer.volume)

        # Update active image title
        active_title = self._t("active_title")
        if dpg.does_item_exist(active_title):
            if has_image:
                name_str, is_outdated = api.get_image_display_name(viewer.image_id)
                dpg.set_value(active_title, name_str)
                col = (
                    api.get_ui_config()["colors"]["outdated"]
                    if is_outdated
                    else api.get_ui_config()["colors"]["text_active"]
                )
                dpg.configure_item(active_title, color=col)
            else:
                dpg.set_value(active_title, "No Image Selected")
                dpg.configure_item(
                    active_title,
                    color=api.get_ui_config()["colors"]["text_active"],
                )

        # Sync checkboxes/combos with state
        chk_mip = self._t("check_mip_mode")
        axis_text = self._t("text_projection_axis")
        slider_depth = self._t("slider_depth_cueing")
        slider_rot = self._t("slider_rotation_angle")
        slider_step = self._t("slider_rotation_step")
        chk_invert = self._t("check_invert_contrast")

        all_items = [
            chk_mip, slider_depth, slider_rot, slider_step, chk_invert,
            f"btn_{slider_rot}_minus", f"btn_{slider_rot}_plus",
            f"btn_{slider_step}_minus", f"btn_{slider_step}_plus",
        ]
        for item in all_items:
            if dpg.does_item_exist(item):
                dpg.configure_item(item, enabled=has_image)

        if has_image:
            state = self._c.get_viewer_state(viewer.image_id, viewer.tag)

            # Map active orientation back to MIP axis if we are in MIP mode or just to sync
            orientation_map = {
                ViewMode.AXIAL: "Z",
                ViewMode.CORONAL: "Y",
                ViewMode.SAGITTAL: "Y",
            }
            orientation_name = {
                ViewMode.AXIAL: "Z (Axial)",
                ViewMode.CORONAL: "Y (Coronal)",
                ViewMode.SAGITTAL: "Y (Sagittal)",
            }.get(viewer.orientation, "Unknown")

            current_axis = orientation_map.get(viewer.orientation)
            if current_axis and state.projection_axis != current_axis:
                state.projection_axis = current_axis

            if dpg.does_item_exist(axis_text):
                dpg.set_value(axis_text, f"Projection Axis: {orientation_name}")
            if dpg.does_item_exist(chk_mip) and not dpg.is_item_active(chk_mip):
                dpg.set_value(chk_mip, state.mip_enabled)
            if dpg.does_item_exist(slider_depth) and not dpg.is_item_active(slider_depth):
                dpg.set_value(slider_depth, state.depth_cueing)
            if dpg.does_item_exist(slider_rot) and not dpg.is_item_active(slider_rot):
                current_angle = state.rotation_angles.get(current_axis, 0.0) if current_axis else 0.0
                dpg.set_value(slider_rot, current_angle)
            if dpg.does_item_exist(slider_step) and not dpg.is_item_active(slider_step):
                dpg.set_value(slider_step, state.rotation_step)
            if dpg.does_item_exist(chk_invert) and not dpg.is_item_active(chk_invert):
                dpg.set_value(chk_invert, state.invert_contrast)
        else:
            if dpg.does_item_exist(axis_text):
                dpg.set_value(axis_text, "Projection Axis: None")
