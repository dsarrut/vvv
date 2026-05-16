import dearpygui.dearpygui as dpg
from vvv.ui.ui_components import build_section_title
from vvv.utils import ViewMode, fmt
import numpy as np

class ProfileUI:
    def __init__(self, gui, controller):
        self.gui = gui
        self.controller = controller

    def build_tab_profile(self, gui):
        cfg_c = gui.ui_cfg["colors"]
        
        with dpg.group(tag="tab_profile", show=False):
            build_section_title("Intensity Profiles", cfg_c["text_header"])
            
            dpg.add_text("No Image Selected", tag="text_profile_active_title", color=cfg_c["text_active"])
            
            with dpg.group(horizontal=True):
                dpg.add_button(label="Add Profile (P)", tag="btn_profile_add", enabled=True, callback=self.on_btn_add_clicked)
                dpg.add_button(label="Debug: Add 10 Profiles", tag="btn_profile_debug", callback=self.on_debug_add_profiles)
                
            dpg.add_spacer(height=5)
            
            with dpg.child_window(tag="profile_list_window", height=200, border=True):
                with dpg.table(tag="profile_list_table", header_row=False, resizable=False, borders_innerH=True, scrollY=True):
                    dpg.add_table_column(width_fixed=True, init_width_or_weight=20)
                    dpg.add_table_column(width_stretch=True)
                    dpg.add_table_column(width_fixed=True, init_width_or_weight=40)
                    dpg.add_table_column(width_fixed=True, init_width_or_weight=20)

    def refresh_profile_ui(self):
        viewer = self.gui.context_viewer
        has_image = bool(viewer and viewer.view_state and viewer.volume)

        if dpg.does_item_exist("text_profile_active_title"):
            if has_image:
                name_str, is_outdated = self.controller.get_image_display_name(viewer.image_id)
                dpg.set_value("text_profile_active_title", name_str)
                col = self.gui.ui_cfg["colors"]["outdated"] if is_outdated else self.gui.ui_cfg["colors"]["text_active"]
                dpg.configure_item("text_profile_active_title", color=col)
            else:
                dpg.set_value("text_profile_active_title", "No Image Selected")
                dpg.configure_item("text_profile_active_title", color=self.gui.ui_cfg["colors"]["text_active"])

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
                # Color picker
                dpg.add_color_edit(
                    default_value=profile.color,
                    no_inputs=True,
                    no_label=True,
                    no_alpha=True,
                    width=20,
                    height=20,
                    user_data=p_id,
                    callback=self.on_color_changed
                )
                
                # Name (clickable)
                dpg.add_selectable(
                    label=profile.name,
                    user_data=p_id,
                    callback=self.on_profile_clicked
                )
                
                # Goto button
                btn_goto = dpg.add_button(label="\uf05b", user_data=p_id, callback=self.on_goto_clicked)
                if dpg.does_item_exist("icon_font_tag"):
                    dpg.bind_item_font(btn_goto, "icon_font_tag")
                with dpg.tooltip(btn_goto):
                    dpg.add_text("Center camera on this profile")
                
                # Delete icon
                btn_delete = dpg.add_button(label="\uf00d", width=20, user_data=p_id, callback=self.on_delete_clicked)
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

    def on_profile_clicked(self, sender, app_data, user_data):
        viewer = self.gui.context_viewer
        if not viewer or not viewer.view_state:
            return
            
        profile = viewer.view_state.profiles.get(user_data)
        if not profile:
            return
            
        win_tag = f"plot_win_{profile.id}"
        if dpg.does_item_exist(win_tag):
            dpg.focus_item(win_tag)
            return

        distances, intensities = self.controller.profiles.get_profile_data(viewer.image_id, profile)
        if distances is None or intensities is None:
            return

        with dpg.window(tag=win_tag, label=f"Profile: {profile.name}", width=400, height=300, on_close=self.on_plot_closed, user_data=profile.id):
            with dpg.plot(label="", height=-1, width=-1):
                dpg.add_plot_axis(dpg.mvXAxis, label="Distance (mm)", tag=f"xaxis_{profile.id}")
                y_axis = dpg.add_plot_axis(dpg.mvYAxis, label="Intensity", tag=f"yaxis_{profile.id}")
                dpg.add_line_series(distances, intensities, label=profile.name, parent=y_axis, tag=f"series_{profile.id}")
            
            dpg.add_separator()
            dpg.add_text("P1: ---", tag=f"text_info_p1_{profile.id}")
            dpg.add_text("P2: ---", tag=f"text_info_p2_{profile.id}")
        
        profile.plot_open = True
        self.update_plot_info(viewer.image_id, profile)

    def update_plot_info(self, vs_id, profile):
        vs = self.controller.view_states.get(vs_id)
        if not vs or not profile:
            return
            
        for i, pt_phys in enumerate([profile.pt1_phys, profile.pt2_phys], 1):
            tag = f"text_info_p{i}_{profile.id}"
            if dpg.does_item_exist(tag):
                # Physical coords
                phys_str = fmt(pt_phys, 1)
                # Native Voxel coords
                v_native = vs.world_to_display(pt_phys, is_buffered=False)
                vox_str = fmt(v_native, 1) if v_native is not None else "Out"
                
                dpg.set_value(tag, f"P{i}: {phys_str} mm | Voxel: [{vox_str}]")

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

        # 2. Adjust Zoom and Center for ALL active viewers of this image via State Targets
        win_w = viewer.quad_w - (viewer.mapper.margin_left * 2)
        win_h = viewer.quad_h - (viewer.mapper.margin_top * 2)
        if length_mm > 1e-5 and win_w > 0 and win_h > 0:
            target_ppm = (min(win_w, win_h) * 0.75) / length_mm
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
            p.color = [random.randint(50, 255) for _ in range(3)] + [255]
            
            # Random orientation
            p.orientation = random.choice([ViewMode.AXIAL, ViewMode.SAGITTAL, ViewMode.CORONAL])
            
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
            x1, y1 = random.uniform(w * 0.25, w * 0.75), random.uniform(h * 0.25, h * 0.75)
            x2, y2 = random.uniform(w * 0.25, w * 0.75), random.uniform(h * 0.25, h * 0.75)
            
            v1 = [0.0, 0.0, 0.0]
            v2 = [0.0, 0.0, 0.0]
            v1[w_ax], v1[h_ax], v1[s_ax] = x1, y1, p.slice_idx
            v2[w_ax], v2[h_ax], v2[s_ax] = x2, y2, p.slice_idx
            
            p.pt1_phys = vs.display_to_world(np.array(v1), is_buffered=False)
            p.pt2_phys = vs.display_to_world(np.array(v2), is_buffered=False)
            
            vs.profiles[p.id] = p
            
        vs.is_geometry_dirty = True
        self.controller.ui_needs_refresh = True