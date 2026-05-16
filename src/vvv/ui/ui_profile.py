import math
import json
import dearpygui.dearpygui as dpg
from vvv.ui.ui_components import build_section_title
from vvv.utils import ViewMode, fmt, voxel_to_slice, slice_to_voxel
from vvv.ui.file_dialog import save_file_dialog
from vvv.config import ROI_COLORS
import numpy as np


class ProfileUI:
    def __init__(self, gui, controller):
        self.gui = gui
        self.controller = controller

    def build_tab_profile(self, gui):
        cfg_c = gui.ui_cfg["colors"]

        with dpg.group(tag="tab_profile", show=False):
            build_section_title("Intensity Profiles", cfg_c["text_header"])

            dpg.add_text(
                "No Image Selected",
                tag="text_profile_active_title",
                color=cfg_c["text_active"],
            )

            with dpg.group(horizontal=True):
                dpg.add_button(
                    label="Add Profile (P)",
                    tag="btn_profile_add",
                    enabled=True,
                    callback=self.on_btn_add_clicked,
                )

            dpg.add_spacer(height=5)

            with dpg.child_window(tag="profile_list_window", height=200, border=True):
                with dpg.table(
                    tag="profile_list_table",
                    header_row=False,
                    resizable=False,
                    borders_innerH=True,
                    scrollY=True,
                ):
                    dpg.add_table_column(width_stretch=True)
                    dpg.add_table_column(width_fixed=True, init_width_or_weight=25)
                    dpg.add_table_column(width_fixed=True, init_width_or_weight=25)
                    dpg.add_table_column(width_fixed=True, init_width_or_weight=25)
                    dpg.add_table_column(width_fixed=True, init_width_or_weight=25)
                    dpg.add_table_column(width_fixed=True, init_width_or_weight=25)
                    dpg.add_table_column(width_fixed=True, init_width_or_weight=25)

    def refresh_profile_ui(self):
        viewer = self.gui.context_viewer
        has_image = bool(viewer and viewer.view_state and viewer.volume)

        if dpg.does_item_exist("text_profile_active_title"):
            if has_image:
                name_str, is_outdated = self.controller.get_image_display_name(
                    viewer.image_id
                )
                dpg.set_value("text_profile_active_title", name_str)
                col = (
                    self.gui.ui_cfg["colors"]["outdated"]
                    if is_outdated
                    else self.gui.ui_cfg["colors"]["text_active"]
                )
                dpg.configure_item("text_profile_active_title", color=col)
            else:
                dpg.set_value("text_profile_active_title", "No Image Selected")
                dpg.configure_item(
                    "text_profile_active_title",
                    color=self.gui.ui_cfg["colors"]["text_active"],
                )

        table_id = "profile_list_table"
        if not dpg.does_item_exist(table_id):
            return

        current_scroll = dpg.get_y_scroll(table_id)
        dpg.delete_item(table_id, children_only=True, slot=1)

        if not has_image:
            return

        vs = viewer.view_state
        for p_id, profile in vs.profiles.items():
            with dpg.table_row(parent=table_id):
                # Name (clickable)
                dpg.add_input_text(
                    tag=f"input_profile_name_{p_id}",
                    default_value=profile.name,
                    user_data=p_id,
                    callback=self.on_profile_name_changed,
                    on_enter=True,
                )

                # New window icon
                btn_plot = dpg.add_button(
                    label="\uf08e", user_data=p_id, callback=self.on_profile_clicked
                )
                if dpg.does_item_exist("icon_font_tag"):
                    dpg.bind_item_font(btn_plot, "icon_font_tag")
                with dpg.tooltip(btn_plot):
                    dpg.add_text("Open intensity plot")

                # Horizontal alignment
                btn_h = dpg.add_button(
                    label="\uf07e",
                    user_data=(p_id, "h"),
                    callback=self.on_align_clicked,
                )
                if dpg.does_item_exist("icon_font_tag"):
                    dpg.bind_item_font(btn_h, "icon_font_tag")
                with dpg.tooltip(btn_h):
                    dpg.add_text("Align purely horizontal on current slice")

                # Vertical alignment
                btn_v = dpg.add_button(
                    label="\uf07d",
                    user_data=(p_id, "v"),
                    callback=self.on_align_clicked,
                )
                if dpg.does_item_exist("icon_font_tag"):
                    dpg.bind_item_font(btn_v, "icon_font_tag")
                with dpg.tooltip(btn_v):
                    dpg.add_text("Align purely vertical on current slice")

                # Pixel snap
                btn_snap = dpg.add_button(
                    label="\uf076", user_data=p_id, callback=self.on_snap_clicked
                )
                if dpg.does_item_exist("icon_font_tag"):
                    dpg.bind_item_font(btn_snap, "icon_font_tag")
                with dpg.tooltip(btn_snap):
                    dpg.add_text("Snap endpoints to closest pixel center")

                # Goto button
                btn_goto = dpg.add_button(
                    label="\uf05b", user_data=p_id, callback=self.on_goto_clicked
                )
                if dpg.does_item_exist("icon_font_tag"):
                    dpg.bind_item_font(btn_goto, "icon_font_tag")
                with dpg.tooltip(btn_goto):
                    dpg.add_text("Center camera on this profile")

                # Delete icon
                btn_delete = dpg.add_button(
                    label="\uf00d",
                    width=20,
                    user_data=p_id,
                    callback=self.on_delete_clicked,
                )
                if dpg.does_item_exist("icon_font_tag"):
                    dpg.bind_item_font(btn_delete, "icon_font_tag")
                if dpg.does_item_exist("delete_button_theme"):
                    dpg.bind_item_theme(btn_delete, "delete_button_theme")

        dpg.set_y_scroll(table_id, current_scroll)

    def on_color_changed(self, sender, app_data, user_data):
        viewer = self.gui.context_viewer
        if not viewer or not viewer.view_state:
            return
        profile = viewer.view_state.profiles.get(user_data)
        if profile:
            scale = 255.0 if all(c <= 1.0 for c in app_data) else 1.0
            profile.color = [int(c * scale) for c in app_data[:4]]
            viewer.view_state.is_geometry_dirty = True
            self.controller.ui_needs_refresh = True

    def on_profile_name_changed(self, sender, app_data, user_data):
        viewer = self.gui.context_viewer
        if not viewer or not viewer.view_state:
            return
        profile = viewer.view_state.profiles.get(user_data)
        if profile:
            profile.name = app_data
            win_tag = f"plot_win_{profile.id}"
            if dpg.does_item_exist(win_tag):
                dpg.configure_item(win_tag, label=f"Profile: {profile.name}")

    def on_profile_clicked(self, sender, app_data, user_data):
        viewer = self.gui.context_viewer
        if not viewer or not viewer.view_state:
            return

        p_id = user_data
        win_tag = f"plot_win_{p_id}"
        if dpg.does_item_exist(win_tag):
            self.on_plot_closed(win_tag, None, p_id)
            return

        profile = viewer.view_state.profiles.get(p_id)
        if not profile:
            return

        with dpg.window(
            tag=win_tag,
            label=f"Profile: {profile.name}",
            width=450,
            height=550,
            on_close=self.on_plot_closed,
            user_data=profile.id,
        ):
            self._build_plot_window_contents(profile)

        # Position the window at the bottom right of the viewport
        vp_w = dpg.get_viewport_client_width()
        vp_h = dpg.get_viewport_client_height()
        win_w, win_h = 450, 550
        dpg.set_item_pos(
            win_tag, [max(10, vp_w - win_w - 20), max(10, vp_h - win_h - 40)]
        )

        profile.plot_open = True
        self.update_plot_info(viewer.image_id, profile)

    def _build_plot_window_contents(self, profile):
        viewer = self.gui.context_viewer
        if not viewer:
            return

        distances, intensities = self.controller.profiles.get_profile_data(
            viewer.image_id, profile
        )
        if distances is None or intensities is None:
            return

        p_id = profile.id
        icon_font = "icon_font_tag" if dpg.does_item_exist("icon_font_tag") else None

        # --- Header Toolbar (Matching the list row) ---
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
                callback=self.on_color_changed,
            )

            # 1. Plot Toggle (Closes current)
            btn_plot = dpg.add_button(
                label="\uf08e", user_data=p_id, callback=self.on_profile_clicked
            )
            if icon_font:
                dpg.bind_item_font(btn_plot, icon_font)
            with dpg.tooltip(btn_plot):
                dpg.add_text("Close plot window")

            # 2. Alignment
            btn_h = dpg.add_button(
                label="\uf07e", user_data=(p_id, "h"), callback=self.on_align_clicked
            )
            btn_v = dpg.add_button(
                label="\uf07d", user_data=(p_id, "v"), callback=self.on_align_clicked
            )
            if icon_font:
                dpg.bind_item_font(btn_h, icon_font)
                dpg.bind_item_font(btn_v, icon_font)
            with dpg.tooltip(btn_h):
                dpg.add_text("Align purely horizontal")
            with dpg.tooltip(btn_v):
                dpg.add_text("Align purely vertical")

            # 2b. Snap
            btn_snap = dpg.add_button(
                label="\uf076", user_data=p_id, callback=self.on_snap_clicked
            )
            if icon_font: dpg.bind_item_font(btn_snap, icon_font)
            with dpg.tooltip(btn_snap): dpg.add_text("Snap to pixel center")

            # 3. Goto
            btn_goto = dpg.add_button(
                label="\uf05b", callback=self.on_goto_clicked, user_data=p_id
            )
            if icon_font:
                dpg.bind_item_font(btn_goto, icon_font)
            with dpg.tooltip(btn_goto):
                dpg.add_text("Center camera on profile")

            # 4. Slice Navigation
            btn_prev = dpg.add_button(
                label="\uf062",
                user_data=(p_id, -1),
                callback=self.on_change_slice_clicked,
            )
            btn_next = dpg.add_button(
                label="\uf063",
                user_data=(p_id, 1),
                callback=self.on_change_slice_clicked,
            )
            if icon_font:
                dpg.bind_item_font(btn_prev, icon_font)
                dpg.bind_item_font(btn_next, icon_font)
            with dpg.tooltip(btn_prev):
                dpg.add_text("Move profile to previous slice")
            with dpg.tooltip(btn_next):
                dpg.add_text("Move profile to next slice")

            # 5. Delete
            btn_del = dpg.add_button(
                label="\uf00d", user_data=p_id, callback=self.on_delete_clicked
            )
            if icon_font:
                dpg.bind_item_font(btn_del, icon_font)
            if dpg.does_item_exist("delete_button_theme"):
                dpg.bind_item_theme(btn_del, "delete_button_theme")
            with dpg.tooltip(btn_del):
                dpg.add_text("Delete profile")

        # Orientation display
        ori_map = {
            ViewMode.AXIAL: "XY",
            ViewMode.SAGITTAL: "YZ",
            ViewMode.CORONAL: "XZ",
        }
        ori_str = ori_map.get(profile.orientation, "??")
        dpg.add_text(
            f"Orientation: {ori_str} | Slice: {profile.slice_idx}",
            tag=f"plot_header_text_{profile.id}",
            color=self.gui.ui_cfg["colors"]["text_dim"],
        )

        dpg.add_spacer(height=5)

        with dpg.plot(label="", height=300, width=-1):
            dpg.add_plot_axis(
                dpg.mvXAxis, label="Distance (mm)", tag=f"xaxis_{profile.id}"
            )
            y_axis = dpg.add_plot_axis(
                dpg.mvYAxis,
                label="Intensity",
                tag=f"yaxis_{profile.id}",
                log_scale=getattr(profile, "use_log", False),
            )
            dpg.add_line_series(
                distances,
                intensities,
                label=profile.name,
                parent=y_axis,
                tag=f"series_{profile.id}",
            )

        dpg.add_separator()

        for i in [1, 2]:
            with dpg.group(horizontal=True):
                dpg.add_text(f"P{i} (mm):")
                dpg.add_input_floatx(
                    tag=f"input_phys_p{i}_{profile.id}",
                    size=3,
                    width=-1,
                    callback=self.on_profile_coord_edited,
                    user_data={"id": profile.id, "pt": i},
                )
            dpg.add_text(
                "Voxel: [---]",
                tag=f"text_vox_p{i}_{profile.id}",
                color=self.gui.ui_cfg["colors"]["text_dim"],
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
                callback=self.on_toggle_log_clicked,
            )
            dpg.add_button(
                label="Export JSON",
                width=-1,
                callback=self.on_export_profile_clicked,
                user_data=profile.id,
            )

    def _update_plot_header(self, profile):
        header_tag = f"plot_header_text_{profile.id}"
        if dpg.does_item_exist(header_tag):
            ori_map = {
                ViewMode.AXIAL: "XY",
                ViewMode.SAGITTAL: "YZ",
                ViewMode.CORONAL: "XZ",
            }
            ori_str = ori_map.get(profile.orientation, "??")
            dpg.set_value(
                header_tag, f"Orientation: {ori_str} | Slice: {profile.slice_idx}"
            )

    def on_fit_plot_clicked(self, sender, app_data, user_data):
        p_id = user_data
        if dpg.does_item_exist(f"xaxis_{p_id}"):
            dpg.fit_axis_data(f"xaxis_{p_id}")
        if dpg.does_item_exist(f"yaxis_{p_id}"):
            dpg.fit_axis_data(f"yaxis_{p_id}")

    def on_toggle_log_clicked(self, sender, app_data, user_data):
        p_id = user_data
        viewer = self.gui.context_viewer
        if not viewer or not viewer.view_state:
            return
        profile = viewer.view_state.profiles.get(p_id)
        if not profile:
            return

        profile.use_log = not getattr(profile, "use_log", False)

        # Redo the whole plot window contents to correctly update the axis type
        win_tag = f"plot_win_{p_id}"
        if dpg.does_item_exist(win_tag):
            dpg.delete_item(win_tag, children_only=True)
            dpg.push_container_stack(win_tag)
            self._build_plot_window_contents(profile)
            dpg.pop_container_stack()
            self.update_plot_info(viewer.image_id, profile)
            self.on_fit_plot_clicked(None, None, p_id)

    def on_export_profile_clicked(self, sender, app_data, user_data):
        viewer = self.gui.context_viewer
        if not viewer or not viewer.image_id:
            return

        profile = viewer.view_state.profiles.get(user_data)
        if not profile:
            return

        default_name = f"profile_{profile.name.replace(' ', '_')}.json"
        file_path = save_file_dialog("Export Profile Data", default_name=default_name)

        if file_path:
            data = self.controller.profiles.get_full_export_data(
                viewer.image_id, profile
            )
            try:
                with open(file_path, "w") as f:
                    json.dump(data, f, indent=4)
                self.gui.show_status_message(f"Exported: {profile.name}")
            except Exception as e:
                self.gui.show_message("Export Failed", str(e))

    def update_plot_info(self, vs_id, profile):
        vs = self.controller.view_states.get(vs_id)
        if not vs or not profile:
            return

        for i, pt_phys in enumerate([profile.pt1_phys, profile.pt2_phys], 1):
            input_tag = f"input_phys_p{i}_{profile.id}"
            vox_tag = f"text_vox_p{i}_{profile.id}"

            if dpg.does_item_exist(input_tag) and not dpg.is_item_active(input_tag):
                dpg.set_value(input_tag, pt_phys.tolist())

            if dpg.does_item_exist(vox_tag):
                v_native = vs.world_to_display(pt_phys, is_buffered=False)
                vox_str = fmt(v_native, 1) if v_native is not None else "Out"
                dpg.set_value(vox_tag, f"Voxel: [{vox_str}]")

    def on_profile_coord_edited(self, sender, app_data, user_data):
        viewer = self.gui.context_viewer
        if not viewer or not viewer.view_state:
            return

        p_id, pt_idx = user_data["id"], user_data["pt"]
        profile = viewer.view_state.profiles.get(p_id)
        if not profile:
            return

        new_val = np.array(app_data)
        if pt_idx == 1:
            profile.pt1_phys = new_val
        else:
            profile.pt2_phys = new_val

        # Update plot and visual clues
        viewer.is_geometry_dirty = True
        self.update_plot_info(viewer.image_id, profile)
        distances, intensities = self.controller.profiles.get_profile_data(
            viewer.image_id, profile
        )
        if distances:
            dpg.set_value(f"series_{profile.id}", [distances, intensities])

    def on_align_clicked(self, sender, app_data, user_data):
        viewer = self.gui.context_viewer
        if not viewer or not viewer.view_state:
            return

        p_id, direction = user_data
        vs = viewer.view_state
        p = vs.profiles.get(p_id)
        if not p:
            return

        is_buf = viewer._is_buffered()
        shape = viewer.get_slice_shape()

        # 1. Map to display voxel space
        v1 = vs.world_to_display(p.pt1_phys, is_buffered=is_buf)
        v2 = vs.world_to_display(p.pt2_phys, is_buffered=is_buf)

        # 2. Map to 2D slice coordinates
        sx1, sy1 = voxel_to_slice(v1[0], v1[1], v1[2], viewer.orientation, shape)
        sx2, sy2 = voxel_to_slice(v2[0], v2[1], v2[2], viewer.orientation, shape)

        # 3. Calculate current center and length in pixel space
        cx, cy = (sx1 + sx2) / 2.0, (sy1 + sy2) / 2.0
        length = math.hypot(sx2 - sx1, sy2 - sy1)

        # 4. Snap based on center point
        if direction == "h":
            sx1, sy1 = cx - length / 2.0, cy
            sx2, sy2 = cx + length / 2.0, cy
        else:
            sx1, sy1 = cx, cy - length / 2.0
            sx2, sy2 = cx, cy + length / 2.0

        v1_new = slice_to_voxel(sx1, sy1, viewer.slice_idx, viewer.orientation, shape)
        v2_new = slice_to_voxel(sx2, sy2, viewer.slice_idx, viewer.orientation, shape)

        p.pt1_phys = vs.display_to_world(v1_new, is_buffered=is_buf)
        p.pt2_phys = vs.display_to_world(v2_new, is_buffered=is_buf)
        p.orientation = viewer.orientation
        p.slice_idx = viewer.slice_idx

        # 4. Refresh plot and viewer
        vs.is_geometry_dirty = True
        self._update_plot_header(p)
        self.update_plot_info(viewer.image_id, p)
        distances, intensities = self.controller.profiles.get_profile_data(
            viewer.image_id, p
        )
        if distances:
            dpg.set_value(f"series_{p.id}", [distances, intensities])
        self.controller.ui_needs_refresh = True

    def on_change_slice_clicked(self, sender, app_data, user_data):
        p_id, delta = user_data
        viewer = self.gui.context_viewer
        if not viewer or not viewer.view_state:
            return
        vs = viewer.view_state
        p = vs.profiles.get(p_id)
        if not p:
            return

        is_buf = viewer._is_buffered()
        v1 = vs.world_to_display(p.pt1_phys, is_buffered=is_buf)
        v2 = vs.world_to_display(p.pt2_phys, is_buffered=is_buf)

        v_idx, _, _, _ = viewer._ORIENTATION_MAP.get(
            p.orientation, (None, 0, None, None)
        )
        if v_idx is None:
            return

        # Clamp to image boundaries
        max_s = viewer.get_display_num_slices()
        new_idx = np.clip(p.slice_idx + delta, 0, max_s - 1)
        if new_idx == p.slice_idx:
            return

        actual_delta = new_idx - p.slice_idx
        v1[v_idx] += actual_delta
        v2[v_idx] += actual_delta
        p.slice_idx = int(new_idx)

        p.pt1_phys = vs.display_to_world(v1, is_buffered=is_buf)
        p.pt2_phys = vs.display_to_world(v2, is_buffered=is_buf)

        # Update Viewer to follow the profile nudge
        viewer.slice_idx = p.slice_idx
        self.controller.sync.propagate_sync(viewer.image_id)

        self._update_plot_header(p)

        # Refresh plot and geometry
        vs.is_geometry_dirty = True
        self.update_plot_info(viewer.image_id, p)
        distances, intensities = self.controller.profiles.get_profile_data(
            viewer.image_id, p
        )
        if distances:
            dpg.set_value(f"series_{p.id}", [distances, intensities])
        self.controller.ui_needs_refresh = True

    def on_snap_clicked(self, sender, app_data, user_data):
        viewer = self.gui.context_viewer
        if not viewer or not viewer.view_state:
            return

        p_id = user_data
        vs = viewer.view_state
        p = vs.profiles.get(p_id)
        if not p:
            return

        # Snap to closest voxel center in native space
        v1 = vs.world_to_display(p.pt1_phys, is_buffered=False)
        v2 = vs.world_to_display(p.pt2_phys, is_buffered=False)

        if v1 is not None and v2 is not None:
            v1_snapped = np.round(v1)
            v2_snapped = np.round(v2)

            p.pt1_phys = vs.display_to_world(v1_snapped, is_buffered=False)
            p.pt2_phys = vs.display_to_world(v2_snapped, is_buffered=False)

            vs.is_geometry_dirty = True
            self.update_plot_info(viewer.image_id, p)
            # Update plot data
            distances, intensities = self.controller.profiles.get_profile_data(
                viewer.image_id, p
            )
            if distances:
                dpg.set_value(f"series_{p.id}", [distances, intensities])
            self.controller.ui_needs_refresh = True

    def on_btn_add_clicked(self, sender, app_data, user_data):
        if self.gui.context_viewer:
            self.gui.context_viewer.on_key_press(dpg.mvKey_P)

    def on_plot_closed(self, sender, app_data, user_data):
        dpg.delete_item(sender)
        viewer = self.gui.context_viewer
        if viewer and viewer.view_state:
            profile = viewer.view_state.profiles.get(user_data)
            if profile:
                profile.plot_open = False

    def on_goto_clicked(self, sender, app_data, user_data):
        viewer = self.gui.context_viewer
        if not viewer or not viewer.view_state:
            return
        profile = viewer.view_state.profiles.get(user_data)
        if not profile:
            return

        vs = viewer.view_state
        viewer.set_orientation(profile.orientation)

        # 1. Calculate midpoint and physical length
        mid_phys = (profile.pt1_phys + profile.pt2_phys) / 2.0
        length_mm = np.linalg.norm(profile.pt2_phys - profile.pt1_phys)

        # 2. Adjust Zoom (60% FOV) and Center for ALL active viewers of this image via State Targets
        win_w = viewer.quad_w - (viewer.mapper.margin_left * 2)
        win_h = viewer.quad_h - (viewer.mapper.margin_top * 2)
        if length_mm > 1e-5 and win_w > 0 and win_h > 0:
            target_ppm = (min(win_w, win_h) * 0.60) / length_mm
            vs.camera.target_ppm = target_ppm

        # 2. Update physical center and slice index simultaneously
        viewer.slice_idx = profile.slice_idx
        vs.camera.target_center = mid_phys
        vs.update_crosshair_from_phys(mid_phys)

        self.controller.sync.propagate_sync(viewer.image_id)
        self.controller.ui_needs_refresh = True

    def on_delete_clicked(self, sender, app_data, user_data):
        viewer = self.gui.context_viewer
        if not viewer or not viewer.view_state:
            return
        profile_id = user_data
        if profile_id in viewer.view_state.profiles:
            del viewer.view_state.profiles[profile_id]

            win_tag = f"plot_win_{profile_id}"
            if dpg.does_item_exist(win_tag):
                dpg.delete_item(win_tag)

            viewer.view_state.is_geometry_dirty = True
            self.controller.ui_needs_refresh = True

    def on_debug_add_profiles(self, sender, app_data, user_data):
        viewer = self.gui.context_viewer
        if not viewer or not viewer.view_state or not viewer.volume:
            return

        vol = viewer.volume
        vs = viewer.view_state

        from vvv.core.view_state import ProfileLineState
        import random

        for i in range(10):
            p = ProfileLineState()
            p.id = dpg.generate_uuid()
            p.name = f"Profile {len(vs.profiles) + 1}"
            color_idx = len(vs.profiles)
            p.color = list(ROI_COLORS[color_idx % len(ROI_COLORS)]) + [255]

            # Random orientation
            p.orientation = random.choice(
                [ViewMode.AXIAL, ViewMode.SAGITTAL, ViewMode.CORONAL]
            )

            # Random slice inside bounds
            s_ax, h_ax, w_ax = 2, 0, 1
            if p.orientation == ViewMode.AXIAL:
                max_s = vol.shape3d[0]
                s_ax, h_ax, w_ax = 0, 1, 2
            elif p.orientation == ViewMode.SAGITTAL:
                max_s = vol.shape3d[2]
                s_ax, h_ax, w_ax = 2, 0, 1
            else:
                max_s = vol.shape3d[1]
                s_ax, h_ax, w_ax = 1, 0, 2

            # Random slice near the centroid (middle 50%)
            s_min = int(max_s * 0.25)
            s_max = max(s_min, int(max_s * 0.75) - 1)
            p.slice_idx = random.randint(s_min, s_max) if max_s > 1 else 0

            # Random points near the centroid of the slice (middle 50%)
            h, w = vol.shape3d[h_ax], vol.shape3d[w_ax]
            x1, y1 = random.uniform(w * 0.25, w * 0.75), random.uniform(
                h * 0.25, h * 0.75
            )
            x2, y2 = random.uniform(w * 0.25, w * 0.75), random.uniform(
                h * 0.25, h * 0.75
            )

            v1 = [0.0, 0.0, 0.0]
            v2 = [0.0, 0.0, 0.0]
            v1[w_ax], v1[h_ax], v1[s_ax] = x1, y1, p.slice_idx
            v2[w_ax], v2[h_ax], v2[s_ax] = x2, y2, p.slice_idx

            p.pt1_phys = vs.display_to_world(np.array(v1), is_buffered=False)
            p.pt2_phys = vs.display_to_world(np.array(v2), is_buffered=False)

            vs.profiles[p.id] = p

        vs.is_geometry_dirty = True
        self.controller.ui_needs_refresh = True
