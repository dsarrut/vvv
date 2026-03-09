import dearpygui.dearpygui as dpg
import os
import time
from vvv.utils import ViewMode, fmt
from vvv.file_dialog import open_file_dialog
from .resources import load_fonts, setup_themes
from .core import WL_PRESETS

def create_labeled_field(label, tag):
    """Helper to create a labeled read-only input field."""
    with dpg.group(horizontal=True):
        # Always create the label tag, even if label text is empty
        dpg.add_text(f"{label}:" if label else "", tag=f"{tag}_label")
        dpg.add_input_text(tag=tag, readonly=True, width=-1)


class MainGUI:
    """
    Manages the DearPyGui user interface for VVV.
    """

    def __init__(self, controller):
        self.controller = controller
        self.icon_font = None

        # windows elements
        self.drag_viewer = None
        self.context_viewer = None
        self.side_panel_width = 300
        self.last_window_size = None

        # tasks manager
        self.tasks = []

        # UI Status Message Tracker
        self.status_message_expire_time = float('inf')

        # Cache for auto-generated DPG tags to prevent deletion crashes
        self.image_label_tags = {}

        # Setup resources and UI
        self.icon_font = load_fonts()
        setup_themes()
        self.create_layout()
        self.register_handlers()

    def cleanup(self, sender=None, app_data=None, user_data=None):
        dpg.stop_dearpygui()

    def create_layout(self):
        """Builds the main window layout."""
        self.create_menu_bar()

        with dpg.window(tag="PrimaryWindow",
                        on_close=self.cleanup,
                        no_scrollbar=True,
                        no_scroll_with_mouse=True,
                        no_move=True,
                        no_resize=True,
                        no_collapse=True,
                        no_title_bar=True,
                        no_bring_to_front_on_focus=True):
            # Window resize handler
            with dpg.item_handler_registry(tag="window_resize_handler"):
                dpg.add_item_resize_handler(callback=lambda: self.on_window_resize())
            dpg.bind_item_handler_registry("PrimaryWindow", "window_resize_handler")

            with dpg.group(horizontal=True):
                self.create_left_panel()
                self.create_viewer_grid()

        # Bind themes
        dpg.bind_item_theme("viewers_container", "viewer_theme")
        for tag in ["V1", "V2", "V3", "V4"]:
            dpg.bind_item_theme(f"win_{tag}", "viewer_theme")

    def create_menu_bar(self):
        """Creates the top menu bar."""
        with dpg.viewport_menu_bar():
            with dpg.menu(label="File"):
                dpg.add_menu_item(label="Open Image...", callback=self.on_open_file_clicked)
                dpg.add_menu_item(label="Exit", callback=self.cleanup)
            with dpg.menu(label="Link"):
                dpg.add_menu_item(label="Link All", callback=lambda: self.controller.link_all())

            with dpg.menu(label="Window/Level"):
                for preset_name, vals in WL_PRESETS.items():
                    label = preset_name
                    if vals is not None:
                        label = f"{preset_name} ({vals['ww']}, {vals['wl']})"
                    dpg.add_menu_item(label=label, user_data=preset_name, callback=self.on_wl_preset_menu_clicked)

            # Status Message Area (pushes text slightly away from the menus)
            dpg.add_spacer(width=20)
            dpg.add_text("", tag="global_status_text", color=[150, 255, 150])

    def create_left_panel(self):
        """Creates the sidebar with image list and info."""
        with dpg.child_window(width=self.side_panel_width,
                              tag="side_panel",
                              no_scrollbar=True,
                              no_scroll_with_mouse=True,
                              border=True):
            dpg.add_spacer(height=5)
            self.create_left_panel_top_part()
            dpg.add_spacer(height=5)
            self.create_left_panel_bottom_part()

        dpg.bind_item_theme("image_info_group", "readonly_theme")
        dpg.bind_item_theme("image_crosshair_group", "readonly_theme")

    def create_left_panel_top_part(self):
        with dpg.child_window(tag="top_panel", height=300, resizable_y=True, border=False):
            with dpg.tab_bar(tag="sidebar_tabs"):
                # Tab 1: Image Management
                with dpg.tab(label="Images"):
                    dpg.add_spacer(height=5)
                    dpg.add_text("Loaded Images", color=[93, 93, 93])
                    dpg.add_separator()
                    dpg.add_group(tag="image_list_container")

                # Tab 2: Sync
                with dpg.tab(label="Sync"):
                    dpg.add_spacer(height=5)
                    dpg.add_text("Sync images", color=[93, 93, 93])
                    dpg.add_separator()
                    with dpg.group(tag="sync_list_container"):
                        # We will populate this programmatically
                        pass

                self.create_left_panel_settings()

    def create_left_panel_settings(self):
        # Tab 3: Settings
        with dpg.tab(label="Settings"):
            dpg.add_spacer(height=5)
            with dpg.group(tag="settings_container"):
                call = self.controller.update_setting
                settings = self.controller.settings.data

                dpg.add_text("Parameters", color=[93, 93, 93])
                dpg.add_input_int(label="Auto WL Radius", tag="set_search_radius",
                                  width=120,
                                  default_value=settings["physics"]["search_radius"],
                                  callback=lambda s, v: call(["physics", "search_radius"],
                                                             v))

                dpg.add_input_int(label="Strip Threshold", tag="set_strip_threshold",
                                  width=120,
                                  default_value=settings["physics"]["voxel_strip_threshold"],
                                  callback=lambda s, v: call(
                                      ["physics", "voxel_strip_threshold"], v))

                dpg.add_separator()

                dpg.add_text("Colors", color=[93, 93, 93])
                dpg.add_color_edit(label="Crosshair", tag="set_col_crosshair",
                                   default_value=settings["colors"]["crosshair"],
                                   callback=lambda s, v: call(["colors", "crosshair"], v))
                dpg.add_color_edit(label="Mouse tracker", tag="set_col_overlay_text",
                                   default_value=settings["colors"]["overlay_text"],
                                   callback=lambda s, v: call(["colors", "overlay_text"], v))
                dpg.add_color_edit(label="Grid", tag="set_col_grid",
                                   default_value=settings["colors"]["grid"],
                                   callback=lambda s, v: call(["colors", "grid"], v))

                dpg.add_spacer(height=10)

                with dpg.group(horizontal=True):
                    dpg.add_button(label="Save", width=100,
                                   callback=lambda: self.on_save_settings())
                    dpg.add_button(label="Reset to Defaults", width=-1,
                                   callback=lambda: self.on_reset_settings())

                dpg.add_text("", tag="save_status_text", color=[150, 150, 150])

    def create_left_panel_bottom_part(self):
        # Active Viewer Info Section
        with dpg.child_window(tag="bottom_panel", border=False):
            dpg.add_text("Active Viewer", color=[93, 93, 93])
            dpg.add_separator()

            with dpg.group(tag="image_info_group"):
                create_labeled_field("", tag="info_name")
                create_labeled_field("Type", tag="info_voxel_type")
                create_labeled_field("Size", tag="info_size")
                create_labeled_field("Spacing", tag="info_spacing")
                create_labeled_field("Origin", tag="info_origin")
                create_labeled_field("Matrix", tag="info_matrix")
                dpg.add_input_text(tag="info_memory", readonly=True, width=-1)
                self.create_window_level_controls()

            dpg.add_spacer(height=10)
            dpg.add_text("Crosshair", color=[93, 93, 93])
            dpg.add_separator()

            with dpg.group(tag="image_crosshair_group"):
                create_labeled_field("Voxel", tag="info_vox")
                create_labeled_field("Coord", tag="info_phys")
                create_labeled_field("Value", tag="info_val")
                create_labeled_field("ppm", tag="info_ppm")
                create_labeled_field("FOV", tag="info_scale")

    def create_window_level_controls(self):
        """Creates the window and level input fields and sync toggle."""

        # 2. Manual W/L Inputs
        with dpg.group(horizontal=True):
            with dpg.group(horizontal=True):
                dpg.add_text("Window")
                dpg.add_input_text(tag="info_window", width=65, on_enter=True,
                                   callback=lambda: self.on_sidebar_wl_change())
            dpg.add_spacer(width=5)
            with dpg.group(horizontal=True):
                dpg.add_text("Level")
                dpg.add_input_text(tag="info_level", width=65, on_enter=True,
                                   callback=lambda: self.on_sidebar_wl_change())

        dpg.add_spacer(height=5)

        # 3. Visibility Controls
        with dpg.group(tag="visibility_controls"):
            with dpg.table(header_row=False, policy=dpg.mvTable_SizingFixedFit):
                dpg.add_table_column()
                dpg.add_table_column()
                with dpg.table_row():
                    dpg.add_checkbox(label="Slice axis", tag="check_axis",
                                     callback=self.controller.on_visibility_toggle,
                                     user_data="axis", default_value=True)
                    dpg.add_checkbox(label="Pixels grid", tag="check_grid",
                                     callback=self.controller.on_visibility_toggle,
                                     user_data="grid", default_value=False)
                with dpg.table_row():
                    dpg.add_checkbox(label="Mouse tracker", tag="check_overlay",
                                     callback=self.controller.on_visibility_toggle,
                                     user_data="overlay", default_value=True)
                    dpg.add_checkbox(label="Crosshair", tag="check_crosshair",
                                     callback=self.controller.on_visibility_toggle,
                                     user_data="crosshair", default_value=True)
                with dpg.table_row():
                    dpg.add_checkbox(label="Scale bar", tag="check_scalebar",
                                     callback=self.controller.on_visibility_toggle,
                                     user_data="scalebar", default_value=False)
                    # Sync Toggle
                    dpg.add_checkbox(label="Sync W/L", tag="check_sync_wl", default_value=False,
                                     callback=self.on_sync_wl_toggle)

    def create_viewer_grid(self):
        """Creates the 2x2 grid of slice viewers."""
        with dpg.child_window(tag="viewers_container", border=False, no_scrollbar=True, no_scroll_with_mouse=True):
            with dpg.group(horizontal=True):
                self.create_viewer_widget("V1")
                self.create_viewer_widget("V2")
            with dpg.group(horizontal=True):
                self.create_viewer_widget("V3")
                self.create_viewer_widget("V4")

    def create_viewer_widget(self, tag):
        """Creates a single viewer widget."""
        viewer = self.controller.viewers[tag]
        with dpg.child_window(tag=f"win_{tag}", border=True, no_scrollbar=True, no_scroll_with_mouse=True):
            with dpg.drawlist(tag=f"drawlist_{tag}", width=-1, height=-1):
                dpg.add_draw_node(tag=viewer.img_node_tag)
                dpg.draw_image(viewer.texture_tag, [0, 0], [1, 1], tag=viewer.image_tag)

                # Draw nodes for strips (double buffering to avoid flickering)
                dpg.add_draw_node(tag=viewer.strips_a_tag)
                dpg.add_draw_node(tag=viewer.strips_b_tag)
                viewer.active_strips_node = viewer.strips_a_tag

                # Draw nodes for grid (double buffering to avoid flickering)
                dpg.add_draw_node(tag=viewer.grid_a_tag)
                dpg.add_draw_node(tag=viewer.grid_b_tag)
                viewer.active_grid_node = viewer.grid_a_tag

                # Draw nodes for axis (double buffering to avoid flickering)
                dpg.add_draw_node(tag=viewer.axis_a_tag)
                dpg.add_draw_node(tag=viewer.axis_b_tag)
                viewer.axes_nodes = [viewer.axis_a_tag, viewer.axis_b_tag]
                viewer.active_axes_idx = 0

                dpg.add_draw_node(tag=viewer.scale_bar_tag)
                dpg.add_draw_node(tag=viewer.crosshair_tag)

            col = self.controller.settings.data["colors"]["overlay_text"]
            dpg.add_text("", tag=viewer.overlay_tag, color=col, pos=[5, 5])

    def register_handlers(self):
        """Registers global input handlers."""
        with dpg.handler_registry():
            dpg.add_mouse_wheel_handler(callback=self.on_global_scroll)
            dpg.add_mouse_drag_handler(callback=self.on_global_drag)
            dpg.add_mouse_release_handler(callback=self.on_global_release)
            dpg.add_key_press_handler(callback=self.on_key_press)
            dpg.add_mouse_click_handler(callback=self.on_global_click)

    def sync_sidebar_checkboxes(self):
        viewer = self.context_viewer
        if not viewer or not viewer.view_state:
            return

        vs = viewer.view_state
        # Only push to the UI if the model state actually differs from the UI state
        if dpg.get_value("check_axis") != vs.show_axis:
            dpg.set_value("check_axis", vs.show_axis)

        if dpg.get_value("check_grid") != vs.grid_mode:
            dpg.set_value("check_grid", vs.grid_mode)

        if dpg.get_value("check_overlay") != vs.show_overlay:
            dpg.set_value("check_overlay", vs.show_overlay)

        if dpg.get_value("check_crosshair") != vs.show_crosshair:
            dpg.set_value("check_crosshair", vs.show_crosshair)

        if dpg.get_value("check_scalebar") != vs.show_scalebar:
            dpg.set_value("check_scalebar", vs.show_scalebar)

    def refresh_image_list_ui(self):
        container = "image_list_container"
        if not dpg.does_item_exist(container):
            return

        dpg.delete_item(container, children_only=True)
        self.image_label_tags.clear()  # Clear the old cached tags

        for vs_id, vs in self.controller.view_states.items():
            with dpg.group(parent=container):
                with dpg.group(horizontal=True):
                    # Let DPG generate a safe, unique integer ID and cache it!
                    lbl_id = dpg.add_text(f"{vs.volume.name}")
                    self.image_label_tags[vs_id] = lbl_id

                with dpg.group(horizontal=True):
                    dpg.add_spacer(width=10)
                    for v_tag in ["V1", "V2", "V3", "V4"]:
                        # Check if this image is currently in this viewer
                        is_active = self.controller.viewers[v_tag].image_id == vs_id
                        dpg.add_checkbox(
                            label="",
                            default_value=is_active,
                            user_data={"img_id": vs_id, "v_tag": v_tag},
                            callback=self.on_image_viewer_toggle
                        )
                    # Reload Button
                    btn_reload = dpg.add_button(label="\uf01e", width=20,
                                                callback=lambda s, a, u: self.controller.reload_image(u),
                                                user_data=vs_id)
                    # Close Button
                    btn_close = dpg.add_button(label="\uf00d", width=20,
                                               callback=lambda s, a, u: self.controller.close_image(u),
                                               user_data=vs_id)

                    # Bind the font to these specific buttons
                    if dpg.does_item_exist("icon_font_tag"):
                        dpg.bind_item_font(btn_reload, "icon_font_tag")
                        dpg.bind_item_font(btn_close, "icon_font_tag")

                    # Bind Themes for visual feedback
                    if dpg.does_item_exist("delete_button_theme"):
                        dpg.bind_item_theme(btn_close, "delete_button_theme")
                    if dpg.does_item_exist("icon_button_theme"):
                        dpg.bind_item_theme(btn_reload, "icon_button_theme")

        self.refresh_sync_ui()

    def highlight_active_image_in_list(self, active_img_id):
        """Binds a highlight theme to the text label in the sidebar matching the image."""
        for img_id, label_tag in self.image_label_tags.items():
            if dpg.does_item_exist(label_tag):
                if img_id == active_img_id:
                    dpg.bind_item_theme(label_tag, "active_image_list_theme")
                else:
                    dpg.bind_item_theme(label_tag, "")  # Reset to default

    def refresh_sync_ui(self):
        container = "sync_list_container"
        if not dpg.does_item_exist(container): return
        dpg.delete_item(container, children_only=True)

        # Table for alignment
        with dpg.table(parent=container, header_row=False):
            dpg.add_table_column(label="Image")
            dpg.add_table_column(label="Group", width_fixed=True)

            for vs_id, vs in self.controller.view_states.items():
                with dpg.table_row():
                    dpg.add_text(vs.volume.name)
                    # Dropdown to pick a group (0 = None)
                    dpg.add_combo(
                        items=["None", "Group 1", "Group 2", "Group 3"],
                        default_value="None" if not vs.sync_group else f"Group {vs.sync_group}",
                        width=100,
                        user_data=vs_id,
                        callback=self.controller.on_sync_group_change
                    )

    @property
    def hovered_viewer(self):
        """Returns the viewer currently under the mouse cursor."""
        for viewer in self.controller.viewers.values():
            if dpg.is_item_hovered(f"win_{viewer.tag}"):
                return viewer
        return None

    def update_overlays(self):
        """Updates sidebar context on hover and refreshes on-image overlays."""
        hover_viewer = self.hovered_viewer

        # Context Switch logic based on ViewState
        if hover_viewer and hover_viewer != self.context_viewer and not self.drag_viewer:
            # Remove highlight from the old viewer
            if self.context_viewer:
                dpg.bind_item_theme(f"win_{self.context_viewer.tag}", "viewer_theme")

            # Add highlight to the new viewer
            dpg.bind_item_theme(f"win_{hover_viewer.tag}", "active_viewer_theme")

            # Highlight the current image in the image list
            self.highlight_active_image_in_list(hover_viewer.image_id)

            # Update sidebar
            self.update_sidebar_info(hover_viewer)
            self.update_sidebar_crosshair(hover_viewer)
            self.context_viewer = hover_viewer

        # Always refresh the on-image text/crosshairs for all viewers
        for viewer in self.controller.viewers.values():
            viewer.update_overlay()

    def update_sidebar_info(self, viewer):
        """Pulls metadata from the active viewer and updates the sidebar."""
        if not viewer or viewer.image_id is None:
            for t in ["info_name", "info_size", "info_spacing", "info_origin", "info_memory"]:
                dpg.set_value(t, "")
            return

        vol = viewer.volume  # Immutable physical data
        dpg.set_value("info_name", vol.name)
        dpg.set_value("info_name_label", viewer.tag)
        dpg.set_value("info_voxel_type", f"{vol.pixel_type}")
        dpg.set_value("info_size", f"{vol.data.shape[2]} x {vol.data.shape[1]} x {vol.data.shape[0]}")
        dpg.set_value("info_spacing", fmt(vol.spacing, 4))
        dpg.set_value("info_origin", fmt(vol.origin, 2))
        dpg.set_value("info_matrix", fmt(vol.matrix, 1))
        dpg.set_value("info_memory", f"{vol.sitk_image.GetNumberOfPixels():,} px    {vol.memory_mb:g} MB")

        # RGB Locking Logic
        is_rgb = getattr(vol, 'is_rgb', False)
        if dpg.does_item_exist("info_window"): dpg.configure_item("info_window", enabled=not is_rgb)
        if dpg.does_item_exist("info_level"): dpg.configure_item("info_level", enabled=not is_rgb)

        if is_rgb:
            if dpg.does_item_exist("info_window"): dpg.set_value("info_window", "RGB")
            if dpg.does_item_exist("info_level"): dpg.set_value("info_level", "RGB")
        else:
            self.update_sidebar_window_level(viewer)

    def update_sidebar_window_level(self, viewer):
        """Updates the W/L inputs in the sidebar."""
        if not viewer or not viewer.view_state: return
        vol = viewer.volume
        vs = viewer.view_state
        if getattr(vol, 'is_rgb', False): return
        dpg.set_value("info_window", f"{vs.ww:g}")
        dpg.set_value("info_level", f"{vs.wl:g}")

    def update_sidebar_crosshair(self, viewer):
        """Updates the crosshair stats in the sidebar."""
        if not viewer or not viewer.view_state: return
        vs = viewer.view_state
        vol = viewer.volume

        if vs.crosshair_voxel is not None:
            dpg.set_value("info_vox", fmt(vs.crosshair_voxel, 1))
            dpg.set_value("info_phys", fmt(vs.crosshair_phys_coord, 1))
            val_str = (f"{vs.crosshair_value[0]:g} "
                       f"{vs.crosshair_value[1]:g} "
                       f"{vs.crosshair_value[2]:g}") \
                if getattr(vol, 'is_rgb', False) else f"{vs.crosshair_value:g}"
            dpg.set_value("info_val", val_str)

            ppm = viewer.get_pixels_per_mm()
            win_w = dpg.get_item_width(f"win_{viewer.tag}")
            win_h = dpg.get_item_height(f"win_{viewer.tag}")

            if ppm > 0 and win_w and win_h:
                fov_w = win_w / ppm
                fov_h = win_h / ppm
                dpg.set_value("info_scale", f"{fov_w:.0f}x{fov_h:.0f} mm  {ppm:.1f} px/mm")
            dpg.set_value("info_ppm", f"{ppm:g}")

    def on_window_resize(self):
        # Get current window dimensions
        window_width = dpg.get_item_width("PrimaryWindow")
        window_height = dpg.get_item_height("PrimaryWindow")
        if not window_width or not window_height:
            return  # Safety

        # Catch macOS phantom resize events on Alt-Tab
        if hasattr(self, "last_window_size") and self.last_window_size == (window_width, window_height):
            return
        self.last_window_size = (window_width, window_height)

        # Constants
        margin_height = 30
        margin_width = 30
        side_panel_width = self.side_panel_width
        available_width = window_width - side_panel_width - margin_width
        available_height = window_height - margin_height

        # Calculate the sizes for each quadrant (2x2)
        quad_w = available_width // 2
        quad_h = available_height // 2

        # Calculate the total height used by the 2 rows of viewers
        total_viewers_height = quad_h * 2

        if dpg.does_item_exist("viewers_container"):
            dpg.set_item_width("viewers_container", available_width)
            dpg.set_item_height("viewers_container", total_viewers_height)
            # 10 and 22 are "magic" values such that the panel does not have scrollbars
            # and the bottom viewers are aligned with the bottom left panel
            dpg.set_item_pos("viewers_container", [side_panel_width + 10, 22])

        # Resize all viewers
        for viewer in self.controller.viewers.values():
            viewer.resize(quad_w, quad_h)

    def on_global_click(self, sender, app_data, user_data):
        button = app_data
        if button != dpg.mvMouseButton_Left:
            return

        viewer = self.hovered_viewer
        if not viewer:
            return

        self.drag_viewer = viewer
        if viewer.orientation != ViewMode.HISTOGRAM:
            self.context_viewer = viewer

            # If no modifiers, update crosshair position
            if not dpg.is_key_down(dpg.mvKey_LShift) and not dpg.is_key_down(dpg.mvKey_LControl):
                px, py = viewer.get_mouse_slice_coords(ignore_hover=True)
                if px is not None:
                    viewer.update_crosshair_data(px, py)
                    self.controller.propagate_sync(viewer.image_id)

    def on_global_drag(self, sender, app_data, user_data):
        # Safety catch: If DPG sends an int (just the button) instead of the tuple, ignore it.
        if isinstance(app_data, int):
            return

        if self.drag_viewer:
            self.drag_viewer.on_drag(app_data)

    def on_global_release(self, sender, app_data, user_data):
        if self.drag_viewer:
            self.update_sidebar_crosshair(self.drag_viewer)
            self.update_sidebar_info(self.drag_viewer)

            # Reset the drag lock
            self.drag_viewer.last_dx = 0
            self.drag_viewer.last_dy = 0
            self.drag_viewer = None

    def on_global_scroll(self, sender, app_data, user_data):
        if self.hovered_viewer:
            # Check if either Left or Right Control is held down
            is_ctrl = dpg.is_key_down(dpg.mvKey_LControl) or dpg.is_key_down(dpg.mvKey_RControl)

            if is_ctrl:
                # app_data is positive when scrolling up (away), negative when scrolling down (towards)
                direction = "in" if app_data > 0 else "out"
                self.hovered_viewer.on_zoom(direction)
            else:
                # Default behavior: scroll through slices
                self.hovered_viewer.on_scroll(int(app_data))

    def on_key_press(self, sender, app_data, user_data):
        # app_data contains the pressed key code

        # Check for Control (Windows/Linux)
        is_ctrl = dpg.is_key_down(dpg.mvKey_LControl) or dpg.is_key_down(dpg.mvKey_RControl)

        # Check for Command (macOS) - DPG maps this to the 'Win' key constants
        is_cmd = dpg.is_key_down(dpg.mvKey_LWin) or dpg.is_key_down(dpg.mvKey_RWin)

        # Intercept Cmd+O / Ctrl+O globally
        if app_data == dpg.mvKey_O and (is_ctrl or is_cmd):
            self.on_open_file_clicked()
            return  # Stop processing so it doesn't get sent to the viewer

        # Otherwise, pass standard key presses down to the active viewer
        if self.hovered_viewer:
            self.hovered_viewer.on_key_press(app_data)

    def on_image_viewer_toggle(self, sender, value, user_data):
        img_id = user_data["img_id"]
        v_tag = user_data["v_tag"]
        viewer = self.controller.viewers[v_tag]

        # Rule: If the user tries to uncheck the active image, force it back to True
        if not value and viewer.image_id == img_id:
            dpg.set_value(sender, True)
            return

        if value:  # Checkbox checked
            viewer.set_image(img_id)
            # Update the sidebar info to reflect the newly selected image
            self.update_sidebar_info(viewer)

        # Refresh UI
        self.refresh_image_list_ui()

    def on_save_settings(self):
        path = self.controller.save_settings()
        self.show_status_message(f"Settings saved in: {path}")

        def clear_hint():
            time.sleep(3.0)
            if dpg.does_item_exist("save_status_text"):
                dpg.set_value("save_status_text", "")

        import threading
        threading.Thread(target=clear_hint, daemon=True).start()

    def on_reset_settings(self):
        self.controller.reset_settings()
        data = self.controller.settings.data

        # Update the UI inputs to match the newly reset backend data
        dpg.set_value("set_search_radius", data["physics"]["search_radius"])
        dpg.set_value("set_strip_threshold", data["physics"]["voxel_strip_threshold"])
        for key, value in data["colors"].items():
            tag = f"set_col_{key}"
            if dpg.does_item_exist(tag):
                dpg.set_value(tag, value)

    def on_sidebar_wl_change(self):
        context_viewer = self.context_viewer
        if not context_viewer or context_viewer.image_id is None:
            return

        # Get the new values from the UI
        try:
            new_ww = float(dpg.get_value("info_window"))
            new_wl = float(dpg.get_value("info_level"))
        except ValueError:
            # If the user typed something invalid (like letters), do nothing
            return

        # Update the state via the viewer
        context_viewer.update_window_level(new_ww, new_wl)

    def on_open_file_clicked(self, sender=None, app_data=None, user_data=None):
        """Triggers the native OS file browser and queues the load sequence."""
        file_path = open_file_dialog("Open Medical Image")
        if file_path and os.path.exists(file_path):
            self.tasks.append(self.load_single_image_sequence(file_path))

    def on_wl_preset_menu_clicked(self, sender, app_data, user_data):
        """Applies a WW/WL preset from the top menu to the currently active viewer."""
        viewer = self.context_viewer
        if not viewer or not viewer.view_state or getattr(viewer.volume, 'is_rgb', False):
            return

        preset_name = user_data
        viewer.view_state.apply_wl_preset(preset_name)
        self.update_sidebar_window_level(viewer)
        self.controller.propagate_window_level(viewer.image_id)

    def on_sync_wl_toggle(self, sender, app_data, user_data):
        """Immediately propagates window/level when the sync checkbox is turned on."""
        viewer = self.context_viewer
        if not viewer or not viewer.image_id:
            return

        # app_data is True if the box was just checked.
        # If checked, push the current active image's W/L to the rest of its sync group immediately.
        if app_data:
            self.controller.propagate_window_level(viewer.image_id)

    def load_single_image_sequence(self, file_path):
        """Generator that shows a loading progress bar while reading a large file."""
        filename = os.path.basename(file_path)

        with dpg.window(tag="loading_modal", modal=True, show=True, no_title_bar=True,
                        no_resize=True, no_move=True, width=350, height=100):
            dpg.add_text(f"Loading image...\n{filename}", tag="loading_text")
            dpg.add_spacer(height=5)
            # Set to 0.5 to indicate the file read is in progress
            dpg.add_progress_bar(tag="loading_progress", width=-1, default_value=0.5)

        vp_width = max(dpg.get_viewport_client_width(), 800)
        vp_height = max(dpg.get_viewport_client_height(), 600)
        dpg.set_item_pos("loading_modal", [vp_width // 2 - 175, vp_height // 2 - 50])

        # Yield multiple times so DPG physically renders the window to the screen
        for _ in range(3):
            yield

        try:
            # Read from disk (Blocks Python)
            img_id = self.controller.load_image(file_path)

            # Update UI to show completion safely before applying layouts
            if dpg.does_item_exist("loading_text"):
                dpg.set_value("loading_text", "Applying synchronization and layouts...")
            if dpg.does_item_exist("loading_progress"):
                dpg.set_value("loading_progress", 1.0)
            yield

            target_viewer = self.context_viewer if self.context_viewer else self.controller.viewers["V1"]
            target_viewer.set_image(img_id)

            same_image_viewers = [v.tag for v in self.controller.viewers.values() if v.image_id == img_id]
            if same_image_viewers:
                self.controller.unify_ppm(same_image_viewers)

            self.update_sidebar_info(target_viewer)
            self.refresh_image_list_ui()

            # Clean up safely on success
            if dpg.does_item_exist("loading_modal"):
                dpg.delete_item("loading_modal")
            yield

        except Exception as e:
            # Safely delete the loading modal and yield before showing the error modal
            if dpg.does_item_exist("loading_modal"):
                dpg.delete_item("loading_modal")

            yield
            self.show_message("File Load Error", f"Failed to load image:\n{filename}\n\nError: {str(e)}")

            # Keep generator alive until user acknowledges the error
            while dpg.does_item_exist("generic_message_modal"):
                yield

    def show_message(self, title, message):
        """Displays a reusable, centered modal dialog for errors and alerts."""
        modal_tag = "generic_message_modal"
        if dpg.does_item_exist(modal_tag):
            dpg.delete_item(modal_tag)

        with dpg.window(tag=modal_tag, modal=True, show=True, label=title,
                        no_collapse=True, width=450):
            dpg.add_text(message, wrap=430)
            dpg.add_spacer(height=10)
            with dpg.group(horizontal=True):
                dpg.add_spacer(width=160)
                dpg.add_button(label="OK", width=100, callback=lambda: dpg.delete_item(modal_tag))

        vp_width = max(dpg.get_viewport_client_width(), 800)
        vp_height = max(dpg.get_viewport_client_height(), 600)
        dpg.set_item_pos(modal_tag, [vp_width // 2 - 225, vp_height // 2 - 100])

    def show_status_message(self, message, duration=3.0, color=None):
        """Displays a temporary status message in the menu bar."""
        if color is None:
            color = [150, 255, 150] # FIXME in settings ?

        if dpg.does_item_exist("global_status_text"):
            dpg.set_value("global_status_text", f"[{message}]")
            dpg.configure_item("global_status_text", color=color)

        # Set the time when this message should disappear
        self.status_message_expire_time = time.time() + duration

    def create_boot_sequence(self, image_paths, sync=False, link_all=False):
        """Creates a generator for the boot sequence that loads images with progress UI."""
        if not image_paths:
            return

        total = len(image_paths)

        # Build the Loading Modal
        with dpg.window(tag="loading_modal", modal=True, show=True, no_title_bar=True,
                        no_resize=True, no_move=True, width=350, height=100):
            dpg.add_text("Initializing...", tag="loading_text")
            dpg.add_spacer(height=5)
            dpg.add_progress_bar(tag="loading_progress", width=-1, default_value=0.0)

        # Center the modal on the screen (with fallbacks if viewport isn't fully sized yet)
        vp_width = max(dpg.get_viewport_client_width(), 800)
        vp_height = max(dpg.get_viewport_client_height(), 600)
        dpg.set_item_pos("loading_modal", [vp_width // 2 - 175, vp_height // 2 - 50])

        yield  # Let DPG draw the empty modal

        # Load the images one by one
        img_ids = []
        for i, path in enumerate(image_paths):
            filename = os.path.basename(path)

            # Update UI state safely in case the modal had to be deleted previously
            if dpg.does_item_exist("loading_text"):
                dpg.set_value("loading_text", f"Loading image {i + 1}/{total}...\n{filename}")
            if dpg.does_item_exist("loading_progress"):
                dpg.set_value("loading_progress", i / total)

            yield  # Let DPG render the new text and progress bar BEFORE reading the file

            try:
                img_id = self.controller.load_image(path)
                img_ids.append(img_id)
            except Exception as e:
                # Safely delete the loading modal and yield to clear ImGui's modal stack
                if dpg.does_item_exist("loading_modal"):
                    dpg.delete_item("loading_modal")
                yield

                # Show the error message
                self.show_message("File Load Error", f"Failed to load image:\n{filename}")

                # Wait for user to acknowledge the modal
                while dpg.does_item_exist("generic_message_modal"):
                    yield

                # Rebuild the loading modal ONLY if there are more files to process
                if i < total - 1:
                    with dpg.window(tag="loading_modal", modal=True, show=True, no_title_bar=True,
                                    no_resize=True, no_move=True, width=350, height=100):
                        dpg.add_text("Resuming...", tag="loading_text")
                        dpg.add_spacer(height=5)
                        dpg.add_progress_bar(tag="loading_progress", width=-1, default_value=(i + 1) / total)

                    vp_w = max(dpg.get_viewport_client_width(), 800)
                    vp_h = max(dpg.get_viewport_client_height(), 600)
                    dpg.set_item_pos("loading_modal", [vp_w // 2 - 175, vp_h // 2 - 50])
                    yield
                continue

            if i == 0:
                for tag in ["V1", "V2", "V3", "V4"]:
                    self.controller.viewers[tag].set_image(img_id)
            elif i == 1:
                self.controller.viewers["V3"].set_image(img_id)
                self.controller.viewers["V4"].set_image(img_id)
            elif i == 2:
                self.controller.viewers["V2"].set_image(img_ids[1])
                self.controller.viewers["V3"].set_image(img_id)
                self.controller.viewers["V4"].set_image(img_id)
            elif i >= 3:
                self.controller.viewers["V4"].set_image(img_id)

        # Finalize and Sync
        # Safely check if items exist before updating them (prevents SystemError crashes if the last image failed)
        if dpg.does_item_exist("loading_text"):
            dpg.set_value("loading_text", "Applying synchronization and layouts...")
        if dpg.does_item_exist("loading_progress"):
            dpg.set_value("loading_progress", 1.0)

        yield  # Render the 100% completion state

        self.controller.default_viewers_orientation()

        # Unify the absolute scale across different orientations of the SAME image
        for img_id in img_ids:
            # Find all viewers showing this specific image
            same_image_viewers = [v.tag for v in self.controller.viewers.values() if v.image_id == img_id]
            if same_image_viewers:
                self.controller.unify_ppm(same_image_viewers)

        if sync or link_all:
            for img_id in img_ids:
                self.controller.on_sync_group_change(None, "Group 1", img_id)
            self.refresh_sync_ui()

        self.on_window_resize()
        self.refresh_image_list_ui()

        # Clean up
        if dpg.does_item_exist("loading_modal"):
            dpg.delete_item("loading_modal")

        yield  # Let DPG remove the modal before entering the main loop

    def run(self, boot_generator=None):
        dpg.setup_dearpygui()
        dpg.show_viewport()
        dpg.set_primary_window("PrimaryWindow", True)

        # Warm-up phase to establish geometry
        for _ in range(3):
            dpg.render_dearpygui_frame()

        # Step through the loading sequence, rendering a frame after every 'yield'
        if boot_generator:
            for _ in boot_generator:
                dpg.render_dearpygui_frame()

        # Clean render loop
        while dpg.is_dearpygui_running():

            # Clear status message if it has expired
            if time.time() > self.status_message_expire_time:
                if dpg.does_item_exist("global_status_text"):
                    dpg.set_value("global_status_text", "")
                self.status_message_expire_time = float('inf')

            if self.tasks:
                try:
                    next(self.tasks[0])
                except StopIteration:
                    self.tasks.pop(0)

            self.update_overlays()
            self.sync_sidebar_checkboxes()

            self.controller.tick()

            dpg.render_dearpygui_frame()