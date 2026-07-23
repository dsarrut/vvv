import math
import dearpygui.dearpygui as dpg
from vvv.ui.ui_components import (
    build_section_title,
    build_help_button,
    build_beginner_tooltip,
    build_delete_button,
    build_name_filter_bar,
    build_batch_action_toolbar,
    build_renamable_input,
)
from vvv.plugins.plugin_api import PluginTagMixin
from .control_landmark import LandmarkPluginController


class LandmarkPluginUI(PluginTagMixin):
    """UI Layout for the Landmark Plugin inspired by the Profile UI structure."""

    def __init__(self, plugin_id: str, controller: LandmarkPluginController):
        self._plugin_id = plugin_id
        self._c = controller
        self._last_state_key = None
        self._api = None

    def _bind_icon_font(self, item):
        if dpg.does_item_exist("icon_font_tag"):
            dpg.bind_item_font(item, "icon_font_tag")

    def on_landmark_color_changed(self, sender, app_data, user_data):
        lm_id = user_data
        if not lm_id or not app_data:
            return
        scale = 255.0 if all(c <= 1.0 for c in app_data) else 1.0
        color_255 = [int(c * scale) for c in app_data[:3]] + [255]
        self._c.update_landmark_color(lm_id, color_255)

    def on_landmark_toggle_visible(self, sender, app_data, user_data):
        lm_id = user_data
        if not lm_id:
            return
        landmarks = self._c.get_landmarks()
        lm = landmarks.get(lm_id)
        if lm is None:
            return
        self._c.update_landmark_visible(lm_id, not lm.visible)
        self._last_state_key = None  # force table rebuild on next update
        if self._api:
            self._api.request_refresh()

    def on_landmark_toggle_show_name(self, sender, app_data, user_data):
        lm_id = user_data
        if not lm_id:
            return
        landmarks = self._c.get_landmarks()
        lm = landmarks.get(lm_id)
        if lm is None:
            return
        self._c.update_landmark_show_name(lm_id, not lm.show_name)
        self._last_state_key = None  # force table rebuild on next update
        if self._api:
            self._api.request_refresh()

    def on_toggle_all_show_names(self):
        self._c.toggle_all_show_names()
        self._last_state_key = None

    def create_ui(self, parent, api) -> None:
        self._api = api
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

            # --- Top Action Bar ---
            with dpg.group(horizontal=True):
                btn_add = dpg.add_button(
                    label="Add",
                    tag=self._t("btn_add"),
                    callback=self._c.on_btn_add_clicked,
                )
                build_beginner_tooltip(
                    btn_add,
                    "Adds a 3D landmark at the current physical crosshair coordinate.\n"
                    "Shortcut: Press Space bar while hovering over an active viewer.",
                    api,
                )

                btn_load = dpg.add_button(
                    label="\uf07c",
                    tag=self._t("btn_load"),
                    callback=self._c.on_btn_load_clicked,
                )
                self._bind_icon_font(btn_load)
                build_beginner_tooltip(
                    btn_load,
                    "Load landmarks from a .json or .csv file.",
                    api,
                )

                btn_save = dpg.add_button(
                    label="\uf0c7",
                    tag=self._t("btn_save"),
                    callback=self._c.on_btn_save_clicked,
                )
                self._bind_icon_font(btn_save)
                build_beginner_tooltip(
                    btn_save,
                    "Save landmarks to a .json or .csv file.",
                    api,
                )

                btn_snap_all = dpg.add_button(
                    label="Snap All",
                    tag=self._t("btn_snap_all"),
                    callback=self._c.on_btn_snap_all_clicked,
                )
                build_beginner_tooltip(
                    btn_snap_all,
                    "Snaps all landmarks to nearest physical voxel center.",
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

                build_help_button(
                    "Landmark Tool:\n\n"
                    "• Press Space bar to place a 3D point landmark at the crosshair.\n"
                    "• Filter landmarks by name and run batch actions.\n"
                    "• Click Goto (\uf05b) to jump the crosshair to any landmark.\n"
                    "• Click Snap (\uf076) to snap a landmark to nearest voxel center.",
                    api,
                )

            dpg.add_spacer(height=5)

            # --- Name Filter & Batch Action Toolbar ---
            build_name_filter_bar(
                group_tag=self._t("group_filter"),
                input_tag=self._t("input_filter"),
                btn_clear_tag=self._t("btn_clear_filter"),
                on_filter_changed=self._c.on_filter_changed,
                on_clear_clicked=self.on_clear_filter_clicked,
                hint="Filter landmarks by name...",
                width=180,
                api=api,
            )

            build_batch_action_toolbar(
                tag_prefix=self._t("lm"),
                on_color_changed=self._c.on_batch_color_changed,
                on_toggle_visible=self._c.on_batch_toggle_visible,
                on_toggle_names=self.on_toggle_all_show_names,
                on_delete_clicked=self._c.on_batch_delete_clicked,
                api=api,
            )

            dpg.add_spacer(height=5)

            # --- Scrollable Landmark Table (Inspired by Profile UI) ---
            with dpg.child_window(tag=self._t("list_window"), height=180, border=False):
                with dpg.table(
                    tag=self._t("list_table"),
                    header_row=False,
                    resizable=False,
                    scrollY=True,
                ):
                    dpg.add_table_column(width_fixed=True, init_width_or_weight=20)
                    dpg.add_table_column(width_stretch=True)
                    dpg.add_table_column(width_fixed=True, init_width_or_weight=20)
                    dpg.add_table_column(width_fixed=True, init_width_or_weight=20)
                    dpg.add_table_column(width_fixed=True, init_width_or_weight=20)
                    dpg.add_table_column(width_fixed=True, init_width_or_weight=20)
                    dpg.add_table_column(width_fixed=True, init_width_or_weight=20)

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
        self._api = api
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

        # Rebuild key to avoid unneeded redraws if nothing changed
        lm_tuples = tuple(
            (
                lm_id,
                lm.name,
                tuple(lm.pt_phys),
                tuple(lm.color),
                lm.visible,
                lm.show_name,
            )
            for lm_id, lm in landmarks.items()
        )
        state_key = (vs_id, filter_text, lm_tuples)

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

            with dpg.table_row(parent=table_id):
                # 1. Color Picker
                dpg.add_color_edit(
                    default_value=lm.color[:3] + [255],
                    no_inputs=True,
                    no_label=True,
                    no_alpha=True,
                    width=20,
                    height=20,
                    tag=self._t(f"color_picker_{lm_id}"),
                    user_data=lm_id,
                    callback=self.on_landmark_color_changed,
                )

                # 2. Name Input Field
                build_renamable_input(
                    tag=self._t(f"input_name_{lm_id}"),
                    default_value=lm.name,
                    callback=lambda s, a, u: self._c.update_landmark_name(u, a),
                    user_data=lm_id,
                    width=-1,
                )

                # 3. Show/Hide Toggle Button
                lbl_eye = "\uf06e" if lm.visible else "\uf070"
                btn_eye = dpg.add_button(
                    label=lbl_eye,
                    width=20,
                    user_data=lm_id,
                    callback=self.on_landmark_toggle_visible,
                )
                self._bind_icon_font(btn_eye)
                with dpg.tooltip(btn_eye):
                    dpg.add_text("Show" if not lm.visible else "Hide")

                # 4. Show/Hide Name Label Toggle
                lbl_tag = "\uf02b" if lm.show_name else "\uf02c"
                btn_tag = dpg.add_button(
                    label=lbl_tag,
                    width=20,
                    user_data=lm_id,
                    callback=self.on_landmark_toggle_show_name,
                )
                self._bind_icon_font(btn_tag)
                with dpg.tooltip(btn_tag):
                    dpg.add_text("Hide name" if lm.show_name else "Show name")

                # 5. Snap to Grid Button
                btn_snap = dpg.add_button(
                    label="\uf076",
                    user_data=lm_id,
                    callback=lambda s, a, u: self._c.snap_landmark_to_grid(u),
                )
                self._bind_icon_font(btn_snap)
                with dpg.tooltip(btn_snap):
                    dpg.add_text("Snap landmark to nearest voxel grid center")

                # 6. Goto Crosshair Button
                btn_goto = dpg.add_button(
                    label="\uf05b",
                    user_data=lm_id,
                    callback=lambda s, a, u: self._c.center_on_landmark(u),
                )
                self._bind_icon_font(btn_goto)
                with dpg.tooltip(btn_goto):
                    dpg.add_text("Jump crosshair to landmark position")

                # 7. Delete Button (Red cross)
                build_delete_button(
                    label="\uf00d",
                    width=20,
                    user_data=lm_id,
                    callback=lambda s, a, u: self._c.remove_landmark(u),
                    tooltip="Delete landmark",
                )

        # Update counter footer text
        if dpg.does_item_exist(footer_id):
            if filter_text:
                dpg.set_value(footer_id, f"Landmarks: {total_count} (Filtered: {filtered_count})")
            else:
                dpg.set_value(footer_id, f"Landmarks: {total_count}")
