import dearpygui.dearpygui as dpg
from vvv.ui.ui_components import build_section_title, build_beginner_tooltip
from vvv.plugins.plugin_api import PluginTagMixin


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

            # Projection Axis Choice
            with dpg.group(horizontal=True):
                dpg.add_text("Axis: ")
                dpg.add_combo(
                    ["X", "Y", "Z"],
                    default_value="Y",
                    tag=self._t("combo_projection_axis"),
                    width=-1,
                    callback=self._c.on_axis_changed,
                )

            # Checkbox: Depth Cueing
            chk_depth = dpg.add_checkbox(
                label="Depth Cueing",
                tag=self._t("check_depth_cueing"),
                callback=self._c.on_depth_cueing_toggle,
                default_value=False,
            )
            build_beginner_tooltip(
                chk_depth,
                "Dim intensities of voxels further away from the projection plane.",
                api,
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
        combo_axis = self._t("combo_projection_axis")
        chk_depth = self._t("check_depth_cueing")
        chk_invert = self._t("check_invert_contrast")

        for item in [chk_mip, combo_axis, chk_depth, chk_invert]:
            if dpg.does_item_exist(item):
                dpg.configure_item(item, enabled=has_image)

        if has_image:
            state = self._c.get_image_state(viewer.image_id)
            if dpg.does_item_exist(chk_mip) and not dpg.is_item_active(chk_mip):
                dpg.set_value(chk_mip, state.mip_enabled)
            if dpg.does_item_exist(combo_axis) and not dpg.is_item_active(combo_axis):
                dpg.set_value(combo_axis, state.projection_axis)
            if dpg.does_item_exist(chk_depth) and not dpg.is_item_active(chk_depth):
                dpg.set_value(chk_depth, state.depth_cueing)
            if dpg.does_item_exist(chk_invert) and not dpg.is_item_active(chk_invert):
                dpg.set_value(chk_invert, state.invert_contrast)
