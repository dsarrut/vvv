import dearpygui.dearpygui as dpg
from vvv.ui.ui_components import build_section_title, build_help_button
from vvv.utils import ViewMode, fmt
from .control_profile import ProfilePluginController

ORI_MAP = {ViewMode.AXIAL: "XY", ViewMode.SAGITTAL: "YZ", ViewMode.CORONAL: "XZ"}


class ProfilePluginUI:
    def __init__(self, plugin_id: str, controller: ProfilePluginController):
        self._plugin_id = plugin_id
        self._c = controller

    def _t(self, name: str) -> str:
        return f"{self._plugin_id}_{name}"

    def _bind_icon_font(self, item):
        if dpg.does_item_exist("icon_font_tag"):
            dpg.bind_item_font(item, "icon_font_tag")

    def create_ui(self, parent, api) -> None:
        cfg_c = api.get_ui_config()["colors"]

        with dpg.group(parent=parent or 0, tag=self._plugin_id):
            build_section_title("Profiles Plugin", cfg_c["text_header"])

            dpg.add_text(
                "No Image Selected",
                tag=self._t("active_title"),
                color=cfg_c["text_active"],
            )

            with dpg.group(horizontal=True):
                dpg.add_button(
                    label="Add Profile (P)",
                    tag=self._t("btn_add"),
                    callback=self._c.on_btn_add_clicked,
                )
                build_help_button(
                    "Press P (configurable in Settings > Shortcuts) to add a new\n"
                    "intensity profile on the active slice. A horizontal line will\n"
                    "appear at the center of the view.\n\n"
                    "Drag the endpoints directly on the image to reposition it.\n"
                    "Click the plot icon () in the list to open the intensity curve.",
                    api,
                )

            dpg.add_spacer(height=5)

            with dpg.child_window(tag=self._t("list_window"), height=200, border=True):
                with dpg.table(
                    tag=self._t("list_table"),
                    header_row=False,
                    resizable=False,
                    borders_innerH=True,
                    scrollY=True,
                ):
                    dpg.add_table_column(width_fixed=True, init_width_or_weight=20)
                    dpg.add_table_column(width_stretch=True)
                    dpg.add_table_column(width_fixed=True, init_width_or_weight=25)
                    dpg.add_table_column(width_fixed=True, init_width_or_weight=25)
                    dpg.add_table_column(width_fixed=True, init_width_or_weight=25)
                    dpg.add_table_column(width_fixed=True, init_width_or_weight=25)
                    dpg.add_table_column(width_fixed=True, init_width_or_weight=25)
                    dpg.add_table_column(width_fixed=True, init_width_or_weight=25)

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

        table_id = self._t("list_table")
        if not dpg.does_item_exist(table_id):
            return

        current_scroll = dpg.get_y_scroll(table_id)
        dpg.delete_item(table_id, children_only=True, slot=1)

        if not has_image:
            return

        for p_id, profile in viewer.view_state.profiles.items():
            with dpg.table_row(parent=table_id):
                # Color picker
                dpg.add_color_edit(
                    default_value=profile.color,
                    no_inputs=True,
                    no_label=True,
                    no_alpha=True,
                    width=20,
                    height=20,
                    user_data=p_id,
                    callback=self._c.on_color_changed,
                )

                # Name
                dpg.add_input_text(
                    tag=self._t(f"input_name_{p_id}"),
                    default_value=profile.name,
                    user_data=p_id,
                    callback=self._c.on_profile_name_changed,
                    on_enter=True,
                )

                # Plot button
                btn_plot = dpg.add_button(
                    label="\uf08e", user_data=p_id, callback=self.on_plot_clicked
                )
                self._bind_icon_font(btn_plot)
                with dpg.tooltip(btn_plot):
                    dpg.add_text("Open intensity plot")

                # Horizontal alignment
                btn_h = dpg.add_button(
                    label="\uf07e",
                    user_data=(p_id, "h"),
                    callback=self._c.on_align_clicked,
                )
                self._bind_icon_font(btn_h)
                with dpg.tooltip(btn_h):
                    dpg.add_text("Align purely horizontal on current slice")

                # Vertical alignment
                btn_v = dpg.add_button(
                    label="\uf07d",
                    user_data=(p_id, "v"),
                    callback=self._c.on_align_clicked,
                )
                self._bind_icon_font(btn_v)
                with dpg.tooltip(btn_v):
                    dpg.add_text("Align purely vertical on current slice")

                # Pixel snap
                btn_snap = dpg.add_button(
                    label="\uf076", user_data=p_id, callback=self._c.on_snap_clicked
                )
                self._bind_icon_font(btn_snap)
                with dpg.tooltip(btn_snap):
                    dpg.add_text("Snap endpoints to closest pixel center")

                # Goto button
                btn_goto = dpg.add_button(
                    label="\uf05b", user_data=p_id, callback=self._c.on_goto_clicked
                )
                self._bind_icon_font(btn_goto)
                with dpg.tooltip(btn_goto):
                    dpg.add_text("Center camera on this profile")

                # Delete icon
                btn_delete = dpg.add_button(
                    label="\uf00d",
                    width=20,
                    user_data=p_id,
                    callback=self._c.on_delete_clicked,
                )
                self._bind_icon_font(btn_delete)
                if dpg.does_item_exist("delete_button_theme"):
                    dpg.bind_item_theme(btn_delete, "delete_button_theme")

        dpg.set_y_scroll(table_id, current_scroll)

    def on_plot_clicked(self, sender, app_data, user_data):
        viewer = self._c._api.get_active_viewer() if self._c._api else None
        if not viewer or not viewer.image_id:
            return

        p_id = user_data
        win_tag = f"profile_plugin_plot_win_{p_id}"
        if dpg.does_item_exist(win_tag):
            self.on_plot_closed(win_tag, None, p_id)
            return

        profile = viewer.view_state.profiles.get(p_id)
        if not profile:
            return

        with dpg.window(
            tag=win_tag,
            label=f"Profile: {profile.name} (Plugin)",
            width=450,
            height=550,
            on_close=self.on_plot_closed,
            user_data=profile.id,
        ):
            self.build_plot_window_contents(profile)

        # Position the window at the bottom right of the viewport
        vp_w = dpg.get_viewport_client_width()
        vp_h = dpg.get_viewport_client_height()
        win_w, win_h = 450, 550
        dpg.set_item_pos(
            win_tag, [max(10, vp_w - win_w - 20), max(10, vp_h - win_h - 40)]
        )

        profile.plot_open = True
        self.update_plot_info(profile)

    def build_plot_window_contents(self, profile):
        viewer = self._c._api.get_active_viewer() if self._c._api else None
        if not viewer or not viewer.image_id:
            return

        distances, intensities = self._c._api.get_profile_data(viewer.image_id, profile)
        if distances is None or intensities is None:
            return

        p_id = profile.id
        cfg_c = self._c._api.get_ui_config()["colors"]

        # --- Header Toolbar ---
        with dpg.group(horizontal=True):
            # 0. Color picker
            dpg.add_color_edit(
                default_value=profile.color,
                no_inputs=True,
                no_label=True,
                no_alpha=True,
                width=20,
                height=20,
                user_data=p_id,
                callback=self._c.on_color_changed,
            )

            # 1. Plot Toggle (Closes current)
            btn_plot = dpg.add_button(
                label="\uf08e", user_data=p_id, callback=self.on_plot_clicked
            )
            self._bind_icon_font(btn_plot)
            with dpg.tooltip(btn_plot):
                dpg.add_text("Close plot window")

            # 2. Alignment
            btn_h = dpg.add_button(
                label="\uf07e", user_data=(p_id, "h"), callback=self._c.on_align_clicked
            )
            btn_v = dpg.add_button(
                label="\uf07d", user_data=(p_id, "v"), callback=self._c.on_align_clicked
            )
            self._bind_icon_font(btn_h)
            self._bind_icon_font(btn_v)
            with dpg.tooltip(btn_h):
                dpg.add_text("Align purely horizontal")
            with dpg.tooltip(btn_v):
                dpg.add_text("Align purely vertical")

            # 2b. Snap
            btn_snap = dpg.add_button(
                label="\uf076", user_data=p_id, callback=self._c.on_snap_clicked
            )
            self._bind_icon_font(btn_snap)
            with dpg.tooltip(btn_snap):
                dpg.add_text("Snap to pixel center")

            # 3. Goto
            btn_goto = dpg.add_button(
                label="\uf05b", callback=self._c.on_goto_clicked, user_data=p_id
            )
            self._bind_icon_font(btn_goto)
            with dpg.tooltip(btn_goto):
                dpg.add_text("Center camera on profile")

            # 4. Slice Navigation
            btn_prev = dpg.add_button(
                label="\uf062",
                user_data=(p_id, -1),
                callback=self._c.on_change_slice_clicked,
            )
            btn_next = dpg.add_button(
                label="\uf063",
                user_data=(p_id, 1),
                callback=self._c.on_change_slice_clicked,
            )
            self._bind_icon_font(btn_prev)
            self._bind_icon_font(btn_next)
            with dpg.tooltip(btn_prev):
                dpg.add_text("Move profile to previous slice")
            with dpg.tooltip(btn_next):
                dpg.add_text("Move profile to next slice")

            # 5. Delete
            btn_del = dpg.add_button(
                label="\uf00d", user_data=p_id, callback=self._c.on_delete_clicked
            )
            self._bind_icon_font(btn_del)
            if dpg.does_item_exist("delete_button_theme"):
                dpg.bind_item_theme(btn_del, "delete_button_theme")
            with dpg.tooltip(btn_del):
                dpg.add_text("Delete profile")

            build_help_button(
                "Toolbar buttons (left to right):\n"
                "  [color]  : Change the profile line color\n"
                "  [close]  : Close this plot window\n"
                "  [H / V]  : Force the profile horizontal or vertical\n"
                "  [snap]   : Snap both endpoints to the nearest voxel center\n"
                "  [goto]   : Center the camera on this profile and zoom to fit\n"
                "  [up/dn]  : Move the profile up or down one slice\n"
                "  [delete] : Remove this profile\n\n"
                "You can also drag the endpoints or the midpoint directly on the image.",
                self._c._api,
            )

        # Orientation display
        ori_str = ORI_MAP.get(profile.orientation, "??")
        dpg.add_text(
            f"Orientation: {ori_str} | Slice: {profile.slice_idx}",
            tag=f"profile_plugin_plot_header_text_{profile.id}",
            color=cfg_c["text_dim"],
        )

        dpg.add_spacer(height=5)

        with dpg.plot(label="", height=300, width=-1):
            dpg.add_plot_axis(
                dpg.mvXAxis, label="Distance (mm)", tag=f"profile_plugin_xaxis_{profile.id}"
            )
            y_axis = dpg.add_plot_axis(
                dpg.mvYAxis,
                label="Intensity",
                tag=f"profile_plugin_yaxis_{profile.id}",
                log_scale=getattr(profile, "use_log", False),
            )
            dpg.add_line_series(
                distances,
                intensities,
                label=profile.name,
                parent=y_axis,
                tag=f"profile_plugin_series_{profile.id}",
            )

        dpg.add_separator()

        for i in [1, 2]:
            with dpg.group(horizontal=True):
                dpg.add_text(f"P{i} (mm):")
                dpg.add_input_floatx(
                    tag=f"profile_plugin_input_phys_p{i}_{profile.id}",
                    size=3,
                    width=-1,
                    callback=self._c.on_profile_coord_edited,
                    user_data={"id": profile.id, "pt": i},
                )
            dpg.add_text(
                "Voxel: [---]",
                tag=f"profile_plugin_text_vox_p{i}_{profile.id}",
                color=cfg_c["text_dim"],
            )

        dpg.add_spacer(height=5)
        with dpg.group(horizontal=True):
            dpg.add_button(
                label="Fit Plot",
                user_data=profile.id,
                callback=self.on_fit_plot_clicked,
            )
            dpg.add_button(
                label="Linear / Log",
                user_data=profile.id,
                callback=self._c.on_toggle_log_clicked,
            )
            dpg.add_button(
                label="Export JSON",
                width=-1,
                callback=self._c.on_export_profile_clicked,
                user_data=profile.id,
            )
            build_help_button(
                "Fit Plot    : Auto-scales both axes to the current data range\n"
                "Linear / Log: Toggles the Y axis between linear and log scale\n"
                "Export JSON : Saves the full profile data (distance, intensity,\n"
                "              physical coordinates, voxel indices) to a JSON file\n\n"
                "P1 / P2 (mm): The 3D physical coordinates of each endpoint.\n"
                "              You can type values directly to reposition precisely.",
                self._c._api,
            )

    def rebuild_plot_window_contents(self, profile):
        win_tag = f"profile_plugin_plot_win_{profile.id}"
        if dpg.does_item_exist(win_tag):
            dpg.delete_item(win_tag, children_only=True)
            dpg.push_container_stack(win_tag)
            self.build_plot_window_contents(profile)
            dpg.pop_container_stack()
            self.update_plot_info(profile)
            self.on_fit_plot_clicked(None, None, profile.id)

    def update_plot_info(self, profile):
        viewer = self._c._api.get_active_viewer() if self._c._api else None
        if not viewer or not viewer.view_state:
            return
        vs = viewer.view_state
        for i, pt_phys in enumerate([profile.pt1_phys, profile.pt2_phys], 1):
            input_tag = f"profile_plugin_input_phys_p{i}_{profile.id}"
            vox_tag = f"profile_plugin_text_vox_p{i}_{profile.id}"

            if dpg.does_item_exist(input_tag) and not dpg.is_item_active(input_tag):
                dpg.set_value(input_tag, pt_phys.tolist())

            if dpg.does_item_exist(vox_tag):
                v_native = vs.world_to_display(pt_phys, is_buffered=False)
                vox_str = fmt(v_native, 1) if v_native is not None else "Out"
                dpg.set_value(vox_tag, f"Voxel: [{vox_str}]")

    def update_plot_header(self, profile):
        header_tag = f"profile_plugin_plot_header_text_{profile.id}"
        if dpg.does_item_exist(header_tag):
            ori_str = ORI_MAP.get(profile.orientation, "??")
            dpg.set_value(header_tag, f"Orientation: {ori_str} | Slice: {profile.slice_idx}")

    def refresh_plot_series(self, profile):
        viewer = self._c._api.get_active_viewer() if self._c._api else None
        if not viewer or not viewer.image_id:
            return
        distances, intensities = self._c._api.get_profile_data(viewer.image_id, profile)
        series_tag = f"profile_plugin_series_{profile.id}"
        if dpg.does_item_exist(series_tag) and distances is not None:
            dpg.set_value(series_tag, [distances, intensities])

    def on_fit_plot_clicked(self, sender, app_data, user_data):
        p_id = user_data
        if dpg.does_item_exist(f"profile_plugin_xaxis_{p_id}"):
            dpg.fit_axis_data(f"profile_plugin_xaxis_{p_id}")
        if dpg.does_item_exist(f"profile_plugin_yaxis_{p_id}"):
            dpg.fit_axis_data(f"profile_plugin_yaxis_{p_id}")

    def on_plot_closed(self, sender, app_data, user_data):
        dpg.delete_item(sender)
        viewer = self._c._api.get_active_viewer() if self._c._api else None
        if viewer and viewer.view_state:
            profile = viewer.view_state.profiles.get(user_data)
            if profile:
                profile.plot_open = False
