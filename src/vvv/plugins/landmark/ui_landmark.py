import math
import dearpygui.dearpygui as dpg
from vvv.ui.ui_components import (
    build_section_title,
    build_help_button,
    build_beginner_tooltip,
)
from vvv.plugins.plugin_api import PluginTagMixin
from .control_landmark import LandmarkPluginController


class LandmarkPluginUI(PluginTagMixin):
    """UI Layout for the Landmark Plugin with dynamic table rendering."""

    def __init__(self, plugin_id: str, controller: LandmarkPluginController):
        self._plugin_id = plugin_id
        self._c = controller
        self._last_state_key = None

    def create_ui(self, parent, api) -> None:
        cfg_c = api.get_ui_config()["colors"]

        with dpg.group(parent=parent or 0, tag=self._plugin_id):
            build_section_title("Landmarks Plugin", cfg_c["text_header"])

            active_title = dpg.add_text(
                "No Image Selected",
                tag=self._t("active_title"),
                color=cfg_c["text_active"],
            )
            build_beginner_tooltip(
                active_title,
                "The currently active image. Landmarks belong to this image volume.",
                api,
            )

            # --- Top Action Buttons ---
            with dpg.group(horizontal=True):
                btn_add = dpg.add_button(
                    label="Add Landmark (Space)",
                    tag=self._t("btn_add"),
                    callback=self._c.on_btn_add_clicked,
                )
                build_beginner_tooltip(
                    btn_add,
                    "Adds a 3D landmark at the current physical crosshair coordinate.\n"
                    "Shortcut: Press Space while hovering over an active viewer.",
                    api,
                )
                btn_load = dpg.add_button(
                    label="Load File",
                    tag=self._t("btn_load"),
                    callback=self._c.on_btn_load_clicked,
                )
                build_beginner_tooltip(
                    btn_load,
                    "Loads landmarks from a .json or .csv file into the active image.",
                    api,
                )
                btn_save = dpg.add_button(
                    label="Save File",
                    tag=self._t("btn_save"),
                    callback=self._c.on_btn_save_clicked,
                )
                build_beginner_tooltip(
                    btn_save,
                    "Saves landmarks to a .json or .csv file (auto-detected from file extension).",
                    api,
                )

            with dpg.group(horizontal=True):
                btn_snap_all = dpg.add_button(
                    label="Snap All to Grid",
                    tag=self._t("btn_snap_all"),
                    callback=self._c.on_btn_snap_all_clicked,
                )
                build_beginner_tooltip(
                    btn_snap_all,
                    "Snaps all landmarks of the active image to the nearest physical voxel center.",
                    api,
                )
                btn_clear_all = dpg.add_button(
                    label="Clear All",
                    tag=self._t("btn_clear_all"),
                    callback=self._c.on_btn_clear_all_clicked,
                )
                build_beginner_tooltip(
                    btn_clear_all,
                    "Clears all landmarks for the active image.",
                    api,
                )
                chk_show = dpg.add_checkbox(
                    label="Show on Image",
                    tag=self._t("check_show_landmarks"),
                    default_value=True,
                )
                build_beginner_tooltip(
                    chk_show,
                    "Toggles drawing landmark markers on 2D slice viewers.",
                    api,
                )
                build_help_button(
                    "Landmark Tool:\n\n"
                    "• Press Space bar to place a 3D point landmark at the crosshair.\n"
                    "• Filter landmarks by name and run batch actions.\n"
                    "• Click 'Goto' to jump the crosshair to any landmark.\n"
                    "• Distance (mm) displays live 3D physical offset from crosshair.\n"
                    "• Landmarks automatically dim on adjacent slices.",
                    api,
                )

            dpg.add_spacer(height=5)

            # --- Name Filter & Batch Action Toolbar ---
            with dpg.group(horizontal=True, tag=self._t("group_filter")):
                dpg.add_input_text(
                    hint="Filter landmarks by name...",
                    tag=self._t("input_filter"),
                    width=180,
                    callback=lambda s, a: self._c.on_filter_changed(a),
                )
                btn_clear_filter = dpg.add_button(
                    label="X",
                    tag=self._t("btn_clear_filter"),
                    width=24,
                    callback=lambda: self.on_clear_filter_clicked(),
                )
                build_beginner_tooltip(
                    btn_clear_filter,
                    "Clears the landmark name filter.",
                    api,
                )

            with dpg.group(horizontal=True, tag=self._t("group_batch_actions")):
                dpg.add_button(
                    label="Show Filtered",
                    tag=self._t("btn_batch_show"),
                    callback=self._c.on_batch_show_clicked,
                )
                dpg.add_button(
                    label="Hide Filtered",
                    tag=self._t("btn_batch_hide"),
                    callback=self._c.on_batch_hide_clicked,
                )
                dpg.add_button(
                    label="Delete Filtered",
                    tag=self._t("btn_batch_delete"),
                    callback=self._c.on_batch_delete_clicked,
                )

            dpg.add_spacer(height=5)

            # --- Scrollable Landmark Table ---
            with dpg.child_window(tag=self._t("list_window"), height=180, border=True):
                with dpg.table(
                    tag=self._t("list_table"),
                    header_row=True,
                    resizable=True,
                    scrollY=True,
                ):
                    dpg.add_table_column(label="Vis", width_fixed=True, init_width_or_weight=26)
                    dpg.add_table_column(label="Name", width_stretch=True, init_width_or_weight=90)
                    dpg.add_table_column(label="Coords (mm)", width_fixed=True, init_width_or_weight=115)
                    dpg.add_table_column(label="Dist (mm)", width_fixed=True, init_width_or_weight=65)
                    dpg.add_table_column(label="Color", width_fixed=True, init_width_or_weight=45)
                    dpg.add_table_column(label="Goto", width_fixed=True, init_width_or_weight=35)
                    dpg.add_table_column(label="Snap", width_fixed=True, init_width_or_weight=35)
                    dpg.add_table_column(label="Del", width_fixed=True, init_width_or_weight=30)

            dpg.add_spacer(height=3)

            # --- Footer Landmark Counter ---
            dpg.add_text(
                "Landmarks: 0",
                tag=self._t("footer_counter"),
                color=cfg_c["text_dim"],
            )

    def on_clear_filter_clicked(self):
        if dpg.does_item_exist(self._t("input_filter")):
            dpg.set_value(self._t("input_filter"), "")
        self._c.on_clear_filter_clicked()

    def update_ui(self, api) -> None:
        viewer = api.get_active_viewer()
        has_image = bool(viewer and viewer.view_state and viewer.volume)

        # Update active image title
        active_title = self._t("active_title")
        if dpg.does_item_exist(active_title):
            if has_image:
                name_str, is_outdated = api.get_image_display_name(viewer.image_id)
                dpg.set_value(active_title, name_str)
            else:
                dpg.set_value(active_title, "No Image Selected")

        table_id = self._t("list_table")
        footer_id = self._t("footer_counter")
        if not dpg.does_item_exist(table_id):
            return

        if not has_image:
            dpg.delete_item(table_id, children_only=True, slot=1)
            if dpg.does_item_exist(footer_id):
                dpg.set_value(footer_id, "Landmarks: 0")
            self._last_state_key = None
            return

        vs_id = viewer.image_id
        landmarks = self._c.get_landmarks(vs_id)
        filter_text = self._c.landmark_filters.get(vs_id, "").lower()

        # Compute crosshair physical position for live distance calculation
        crosshair_phys = viewer.view_state.camera.crosshair_phys_coord

        # Rebuild key to avoid unneeded redraws if nothing changed
        lm_tuples = tuple(
            (
                lm_id,
                lm.name,
                tuple(lm.pt_phys),
                tuple(lm.color),
                lm.visible,
            )
            for lm_id, lm in landmarks.items()
        )
        crosshair_tuple = tuple(crosshair_phys) if crosshair_phys is not None else None
        state_key = (vs_id, filter_text, lm_tuples, crosshair_tuple)

        if state_key == self._last_state_key:
            return
        self._last_state_key = state_key

        # Re-render table rows
        dpg.delete_item(table_id, children_only=True, slot=1)

        total_count = len(landmarks)
        filtered_count = 0

        for lm_id, lm in landmarks.items():
            if filter_text and filter_text not in lm.name.lower():
                continue

            filtered_count += 1

            # Distance to current crosshair
            dist_str = "-"
            if crosshair_phys is not None:
                dx = lm.pt_phys[0] - crosshair_phys[0]
                dy = lm.pt_phys[1] - crosshair_phys[1]
                dz = lm.pt_phys[2] - crosshair_phys[2]
                dist = math.sqrt(dx * dx + dy * dy + dz * dz)
                dist_str = f"{dist:.1f}"

            coords_str = f"[{lm.pt_phys[0]:.1f}, {lm.pt_phys[1]:.1f}, {lm.pt_phys[2]:.1f}]"

            with dpg.table_row(parent=table_id):
                # 1. Vis
                dpg.add_checkbox(
                    default_value=lm.visible,
                    user_data=lm_id,
                    callback=lambda s, a, u: self._c.update_landmark_visible(u, a),
                )
                # 2. Name
                dpg.add_input_text(
                    default_value=lm.name,
                    width=-1,
                    user_data=lm_id,
                    callback=lambda s, a, u: self._c.update_landmark_name(u, a),
                )
                # 3. Coords
                dpg.add_text(coords_str)
                # 4. Dist
                dpg.add_text(dist_str)
                # 5. Color
                col_rgba = [c / 255.0 for c in lm.color] if max(lm.color) > 1.0 else lm.color
                dpg.add_color_edit(
                    default_value=col_rgba,
                    no_inputs=True,
                    no_alpha=False,
                    width=35,
                    user_data=lm_id,
                    callback=lambda s, a, u: self._c.update_landmark_color(
                        u, [int(c * 255) for c in a[:4]]
                    ),
                )
                # 6. Goto
                dpg.add_button(
                    label="->",
                    width=28,
                    user_data=lm_id,
                    callback=lambda s, a, u: self._c.center_on_landmark(u),
                )
                # 7. Snap
                dpg.add_button(
                    label="S",
                    width=28,
                    user_data=lm_id,
                    callback=lambda s, a, u: None,
                )
                # 8. Del
                dpg.add_button(
                    label="X",
                    width=24,
                    user_data=lm_id,
                    callback=lambda s, a, u: self._c.remove_landmark(u),
                )

        # Update counter footer text
        if dpg.does_item_exist(footer_id):
            if filter_text:
                dpg.set_value(footer_id, f"Landmarks: {total_count} (Filtered: {filtered_count})")
            else:
                dpg.set_value(footer_id, f"Landmarks: {total_count}")
