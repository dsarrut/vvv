import dearpygui.dearpygui as dpg
from vvv.ui.ui_components import build_section_title
from vvv.utils import ViewMode
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
                dpg.add_button(label="Add Profile (P)", tag="btn_profile_add", enabled=False)
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
                btn_goto = dpg.add_button(label="Goto", user_data=p_id, callback=self.on_goto_clicked)
                
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
                dpg.add_line_series(distances, intensities, label=profile.name, parent=y_axis)
        
        profile.plot_open = True

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
            
        viewer.set_orientation(profile.orientation)
        viewer.slice_idx = profile.slice_idx
        
        # Also re-center camera on the profile mid-point
        mid_phys = (profile.pt1_phys + profile.pt2_phys) / 2.0
        viewer.center_on_physical_coord(mid_phys)
        viewer.update_crosshair_data(viewer.quad_w / 2.0, viewer.quad_h / 2.0)
        
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