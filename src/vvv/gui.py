import dearpygui.dearpygui as dpg
import os
import time


def create_labeled_field(label, tag):
    """Helper to create a labeled read-only input field."""
    with dpg.group(horizontal=True):
        # Always create the label tag, even if label text is empty
        dpg.add_text(f"{label}:" if label else "", tag=f"{tag}_label")
        dpg.add_input_text(tag=tag, readonly=True, width=-1)


def setup_themes():
    """Defines and binds themes for various UI components."""
    # Viewer Theme
    with dpg.theme(tag="viewer_theme"):
        with dpg.theme_component(dpg.mvAll):
            dpg.add_theme_color(dpg.mvThemeCol_ChildBg, [0, 0, 0], category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_Border, [50, 50, 50], category=dpg.mvThemeCat_Core)
            dpg.add_theme_style(dpg.mvStyleVar_WindowPadding, 0, 0, category=dpg.mvThemeCat_Core)
            dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing, 0, 0, category=dpg.mvThemeCat_Core)
            dpg.add_theme_style(dpg.mvStyleVar_FramePadding, 0, 0, category=dpg.mvThemeCat_Core)

    # Icon Button Theme
    with dpg.theme(tag="icon_button_theme"):
        with dpg.theme_component(dpg.mvButton):
            dpg.add_theme_color(dpg.mvThemeCol_Button, [0, 0, 0, 0])
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, [60, 60, 60])
            dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 3)

    # Delete Button Theme
    with dpg.theme(tag="delete_button_theme"):
        with dpg.theme_component(dpg.mvButton):
            dpg.add_theme_color(dpg.mvThemeCol_Button, [0, 0, 0, 0])
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, [150, 40, 40])
            dpg.add_theme_color(dpg.mvThemeCol_Text, [200, 100, 100])

    # Read-only Input Theme (for sidebar info)
    with dpg.theme(tag="readonly_theme"):
        with dpg.theme_component(dpg.mvInputText):
            dpg.add_theme_color(dpg.mvThemeCol_FrameBg, [0, 0, 0, 0])
            dpg.add_theme_style(dpg.mvStyleVar_FrameBorderSize, 0)
            dpg.add_theme_color(dpg.mvThemeCol_Text, [0, 246, 7])

    # Active Viewer Theme (Bright border)
    with dpg.theme(tag="active_viewer_theme"):
        with dpg.theme_component(dpg.mvAll):
            dpg.add_theme_color(dpg.mvThemeCol_Border, [0, 246, 7, 50],
                                category=dpg.mvThemeCat_Core)  # Match your green crosshair
            dpg.add_theme_style(dpg.mvStyleVar_ChildBorderSize, 2, category=dpg.mvThemeCat_Core)
            # Keep other styles consistent with viewer_theme
            dpg.add_theme_style(dpg.mvStyleVar_WindowPadding, 0, 0, category=dpg.mvThemeCat_Core)

    # Active Image List Theme (Green background)
    with dpg.theme(tag="active_image_list_theme"):
        with dpg.theme_component(dpg.mvAll):
            # Change text to green and make it bold-ish if font supports it
            dpg.add_theme_color(dpg.mvThemeCol_Text, [0, 246, 7], category=dpg.mvThemeCat_Core)


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

        # Setup resources and UI
        self.load_resources()
        setup_themes()
        self.create_layout()
        self.register_handlers()

    def load_resources(self):
        """Loads fonts and other external resources."""
        current_dir = os.path.dirname(__file__)
        font_path = os.path.join(current_dir, "fonts", "Font Awesome 7 Free-Solid-900.otf")

        if not os.path.exists(font_path):
            print(f"WARNING: Font file not found at {font_path}")
            return

        with dpg.font_registry():
            with dpg.font(font_path, 14, tag="icon_font_tag") as self.icon_font:
                dpg.add_font_range(0xf00d, 0xf021)
                dpg.add_font_range_hint(dpg.mvFontRangeHint_Default)

    def cleanup(self):
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
                dpg.add_menu_item(label="Open Image...")
                dpg.add_menu_item(label="Exit")
            with dpg.menu(label="Link"):
                dpg.add_menu_item(label="Link All", callback=lambda: self.controller.link_all())

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
        with dpg.child_window(tag="top_panel", height=350, resizable_y=True, border=False):
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
                # with dpg.group(horizontal=True):
                #        dpg.add_text(f"{self.controller.settings.config_path}")

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

            '''with dpg.group(horizontal=True):
                dpg.add_text("Performance:", color=[93, 93, 93])
                dpg.add_text("0 FPS", tag="fps_display", color=[0, 255, 255])
            dpg.add_separator()'''

    def create_window_level_controls(self):
        """Creates the window and level input fields."""
        with dpg.group(horizontal=True):
            with dpg.group(horizontal=True):
                dpg.add_text("Window")
                dpg.add_input_text(tag="info_window", width=70, on_enter=True,
                                   callback=lambda: self.on_sidebar_wl_change())
            dpg.add_spacer(width=5)

            with dpg.group(horizontal=True):
                dpg.add_text("Level")
                dpg.add_input_text(tag="info_level", width=-1, on_enter=True,
                                   callback=lambda: self.on_sidebar_wl_change())

        # Visibility Toggles
        with dpg.group(tag="visibility_controls"):
            # Use a table with 2 columns to ensure perfect alignment
            with dpg.table(header_row=False, policy=dpg.mvTable_SizingFixedFit):
                dpg.add_table_column()
                dpg.add_table_column()

                # Row 1
                with dpg.table_row():
                    dpg.add_checkbox(label="Slice axis", tag="check_axis",
                                     callback=self.controller.on_visibility_toggle,
                                     user_data="axis", default_value=True)
                    dpg.add_checkbox(label="Pixels grid", tag="check_grid",
                                     callback=self.controller.on_visibility_toggle,
                                     user_data="grid", default_value=False)

                # Row 2
                with dpg.table_row():
                    dpg.add_checkbox(label="Mouse tracker", tag="check_overlay",
                                     callback=self.controller.on_visibility_toggle,
                                     user_data="overlay", default_value=True)
                    dpg.add_checkbox(label="Crosshair", tag="check_crosshair",
                                     callback=self.controller.on_visibility_toggle,
                                     user_data="crosshair", default_value=True)

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
        if not viewer or not viewer.image_model:
            return

        img = viewer.image_model
        # Only push to the UI if the model state actually differs from the UI state
        if dpg.get_value("check_axis") != img.show_axis:
            dpg.set_value("check_axis", img.show_axis)

        if dpg.get_value("check_grid") != img.grid_mode:
            dpg.set_value("check_grid", img.grid_mode)

        if dpg.get_value("check_overlay") != img.show_overlay:
            dpg.set_value("check_overlay", img.show_overlay)

        if dpg.get_value("check_crosshair") != img.show_crosshair:
            dpg.set_value("check_crosshair", img.show_crosshair)

    def refresh_image_list_ui(self):
        container = "image_list_container"
        if not dpg.does_item_exist(container):
            return

        dpg.delete_item(container, children_only=True)

        for img_id, img_model in self.controller.images.items():
            with dpg.group(parent=container):
                with dpg.group(horizontal=True):
                    dpg.add_text(f"{img_model.name}", tag=f"img_label_{img_id}")

                with dpg.group(horizontal=True):
                    dpg.add_spacer(width=10)
                    for v_tag in ["V1", "V2", "V3", "V4"]:
                        # Check if this image is currently in this viewer
                        is_active = self.controller.viewers[v_tag].image_id == img_id
                        dpg.add_checkbox(
                            label="",
                            default_value=is_active,
                            user_data={"img_id": img_id, "v_tag": v_tag},
                            callback=self.on_image_viewer_toggle
                        )
                    # Reload Button
                    btn_reload = dpg.add_button(label="\uf01e", width=20,
                                                callback=lambda s, a, u: self.controller.reload_image(u),
                                                user_data=img_id)
                    # Close Button
                    btn_close = dpg.add_button(label="\uf00d", width=20,
                                               callback=lambda s, a, u: self.controller.close_image(u),
                                               user_data=img_id)

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

    def refresh_sync_ui(self):
        container = "sync_list_container"
        if not dpg.does_item_exist(container): return
        dpg.delete_item(container, children_only=True)

        # Table for alignment
        with dpg.table(parent=container, header_row=False):
            dpg.add_table_column(label="Image")
            dpg.add_table_column(label="Group", width_fixed=True)

            for img_id, img in self.controller.images.items():
                with dpg.table_row():
                    dpg.add_text(img.name)
                    # Dropdown to pick a group (0 = None)
                    dpg.add_combo(
                        items=["None", "Group 1", "Group 2", "Group 3"],
                        default_value="None" if not img.sync_group else f"Group {img.sync_group}",
                        width=100,
                        user_data=img_id,
                        callback=self.controller.on_sync_group_change
                    )

    @property
    def hovered_viewer(self):
        """Returns the viewer currently under the mouse cursor."""
        for viewer in self.controller.viewers.values():
            if dpg.is_item_hovered(f"win_{viewer.tag}"):
                return viewer
        return None

    def highlight_active_image_in_list(self, active_img_id):
        """Binds a highlight theme to the text label in the sidebar matching the image."""
        for img_id in self.controller.images.keys():
            label_tag = f"img_label_{img_id}"
            if dpg.does_item_exist(label_tag):
                if img_id == active_img_id:
                    dpg.bind_item_theme(label_tag, "active_image_list_theme")
                else:
                    dpg.bind_item_theme(label_tag, "")  # Reset to default

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
            hover_viewer.update_sidebar_info()
            hover_viewer.update_sidebar_crosshair()
            self.context_viewer = hover_viewer

        # Always refresh the on-image text/crosshairs for all viewers
        for viewer in self.controller.viewers.values():
            viewer.update_overlay()

    def on_window_resize(self):
        # Get current window dimensions
        window_width = dpg.get_item_width("PrimaryWindow")
        window_height = dpg.get_item_height("PrimaryWindow")
        if not window_width or not window_height:
            return  # Safety

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
        if viewer.orientation != "Histogram":
            self.context_viewer = viewer

            # If no modifiers, update crosshair position
            if not dpg.is_key_down(dpg.mvKey_LShift) and not dpg.is_key_down(dpg.mvKey_LControl):
                px, py = viewer.get_mouse_to_pixel_coords(ignore_hover=True)
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
            self.drag_viewer.update_sidebar_crosshair()
            self.drag_viewer.update_sidebar_info()

            # Reset the drag lock
            self.drag_viewer.last_dx = 0
            self.drag_viewer.last_dy = 0
            self.drag_viewer = None

    def on_global_scroll(self, sender, app_data, user_data):
        if self.hovered_viewer:
            self.hovered_viewer.on_scroll(app_data)

    def on_key_press(self, sender, app_data, user_data):
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
            viewer.update_sidebar_info()

        # Refresh UI
        self.refresh_image_list_ui()

    def on_save_settings(self):
        path = self.controller.save_settings()
        dpg.set_value("save_status_text", f"Saved in: {path}")

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

        # Update the ImageModel via the viewer
        context_viewer.update_window_level(max(1.0, new_ww), new_wl)

    def run(self):
        dpg.setup_dearpygui()
        dpg.show_viewport()
        dpg.set_primary_window("PrimaryWindow", True)

        while dpg.is_dearpygui_running():
            # Update overlays (mouse tracking)
            self.update_overlays()

            self.sync_sidebar_checkboxes()

            # Render: only update what is actually "dirty"
            for viewer in self.controller.viewers.values():
                if not viewer.image_model:
                    continue

                # 1. Check if geometry needs recalculation (Pan/Zoom/Center)
                if viewer.needs_refresh:
                    win_w = dpg.get_item_width(f"win_{viewer.tag}")
                    win_h = dpg.get_item_height(f"win_{viewer.tag}")
                    viewer.resize(win_w, win_h)  # This updates current_pmin/pmax
                    viewer.needs_refresh = False

                # If the DATA changed (W/L, new slice), we must re-calculate the texture
                if viewer.image_model.needs_render:
                    viewer.update_render()
                    viewer.draw_crosshair()

                    # If THIS viewer is the one the user is currently looking at in the sidebar
                    if viewer == self.context_viewer:
                        viewer.update_sidebar_crosshair()
                        viewer.update_sidebar_window_level()

                    viewer.needs_refresh = False

            # Reset the Global flags after all viewers have processed them
            for img in self.controller.images.values():
                img.needs_render = False

            dpg.render_dearpygui_frame()
