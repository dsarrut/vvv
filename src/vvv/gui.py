import dearpygui.dearpygui as dpg
import os


class MainGUI:
    """
    Manages the DearPyGui user interface for VVV.
    """

    def __init__(self, controller):
        self.controller = controller
        self.icon_font = None

        # Setup resources and UI
        self.load_resources()
        self.setup_themes()
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

    def setup_themes(self):
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

    def create_layout(self):
        """Builds the main window layout."""
        self.create_menu_bar()

        with dpg.window(tag="PrimaryWindow",
                        on_close=self.controller.main_windows.cleanup,
                        no_scrollbar=True,
                        no_scroll_with_mouse=True,
                        no_move=True,
                        no_resize=True,
                        no_collapse=True,
                        no_title_bar=True,
                        no_bring_to_front_on_focus=True):
            # Window resize handler
            with dpg.item_handler_registry(tag="window_resize_handler"):
                dpg.add_item_resize_handler(callback=lambda: self.controller.main_windows.on_window_resize())
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
        with dpg.child_window(width=self.controller.main_windows.side_panel_width,
                              tag="side_panel",
                              no_scrollbar=True,
                              no_scroll_with_mouse=True,
                              border=True):
            dpg.add_spacer(height=3)
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

                # Tab 2: Future Analysis/Commands (Placeholder)
                with dpg.tab(label="Analysis"):
                    dpg.add_spacer(height=5)
                    dpg.add_text("Processing Tools", color=[93, 93, 93])
                    dpg.add_separator()
                    dpg.add_button(label="Run Reconstruction", width=-1)
                    dpg.add_button(label="Monte Carlo Setup", width=-1)

                # Tab 3: Settings
                with dpg.tab(label="Settings"):
                    dpg.add_spacer(height=5)
                    dpg.add_text("Viewer Settings", color=[93, 93, 93])
                    dpg.add_separator()
                    dpg.add_checkbox(label="Show Orientation Axes", default_value=True)

    def create_left_panel_bottom_part(self):
        # Active Viewer Info Section
        with dpg.child_window(tag="bottom_panel", border=False):
            dpg.add_text("Active Viewer", color=[93, 93, 93])
            dpg.add_separator()

            with dpg.group(tag="image_info_group"):
                self.create_labeled_field("", tag="info_name")
                self.create_labeled_field("Type", tag="info_voxel_type")
                self.create_labeled_field("Size", tag="info_size")
                self.create_labeled_field("Spacing", tag="info_spacing")
                self.create_labeled_field("Origin", tag="info_origin")
                self.create_labeled_field("Matrix", tag="info_matrix")
                dpg.add_input_text(tag="info_memory", readonly=True, width=-1)
                self.create_window_level_controls()

            dpg.add_spacer(height=10)
            dpg.add_text("Crosshair", color=[93, 93, 93])
            dpg.add_separator()

            with dpg.group(tag="image_crosshair_group"):
                self.create_labeled_field("Voxel", tag="info_vox")
                self.create_labeled_field("Coord", tag="info_phys")
                self.create_labeled_field("Value", tag="info_val")

    def create_left_panel_initial(self):
        """Creates the sidebar with image list and info."""
        with dpg.child_window(width=self.controller.main_windows.side_panel_width,
                              tag="side_panel",
                              no_scrollbar=True,
                              no_scroll_with_mouse=True,
                              border=True):
            dpg.add_spacer(height=3)

            # Loaded Images Section
            with dpg.child_window(tag="top_panel", height=300, resizable_y=True, border=False):
                dpg.add_text("Loaded Images", color=[93, 93, 93])
                dpg.add_separator()
                dpg.add_group(tag="image_list_container")

            dpg.add_spacer(height=5)

            # Active Viewer Info Section
            with dpg.child_window(tag="bottom_panel", border=False):
                dpg.add_text("Active Viewer", color=[93, 93, 93])
                dpg.add_separator()

                with dpg.group(tag="image_info_group"):
                    self.create_labeled_field("", tag="info_name")
                    self.create_labeled_field("Type", tag="info_voxel_type")
                    self.create_labeled_field("Size", tag="info_size")
                    self.create_labeled_field("Spacing", tag="info_spacing")
                    self.create_labeled_field("Origin", tag="info_origin")
                    self.create_labeled_field("Matrix", tag="info_matrix")
                    dpg.add_input_text(tag="info_memory", readonly=True, width=-1)
                    self.create_window_level_controls()

                dpg.add_spacer(height=10)
                dpg.add_text("Crosshair", color=[93, 93, 93])
                dpg.add_separator()

                with dpg.group(tag="image_crosshair_group"):
                    self.create_labeled_field("Voxel", tag="info_vox")
                    self.create_labeled_field("Coord", tag="info_phys")
                    self.create_labeled_field("Value", tag="info_val")

        dpg.bind_item_theme("image_info_group", "readonly_theme")
        dpg.bind_item_theme("image_crosshair_group", "readonly_theme")

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

            dpg.add_text("", tag=viewer.overlay_tag, color=[0, 246, 7], pos=[5, 5])

    def create_labeled_field(self, label, tag):
        """Helper to create a labeled read-only input field."""
        with dpg.group(horizontal=True):
            # Always create the label tag, even if label text is empty
            dpg.add_text(f"{label}:" if label else "", tag=f"{tag}_label")
            dpg.add_input_text(tag=tag, readonly=True, width=-1)

    def create_window_level_controls(self):
        """Creates the window and level input fields."""
        with dpg.group(horizontal=True):
            with dpg.group(horizontal=True):
                dpg.add_text("Window")
                dpg.add_input_text(tag="info_window", width=70, on_enter=True,
                                   callback=lambda: self.controller.on_sidebar_wl_change())
            dpg.add_spacer(width=5)
            with dpg.group(horizontal=True):
                dpg.add_text("Level")
                dpg.add_input_text(tag="info_level", width=-1, on_enter=True,
                                   callback=lambda: self.controller.on_sidebar_wl_change())

    def register_handlers(self):
        """Registers global input handlers."""
        with dpg.handler_registry():
            dpg.add_mouse_wheel_handler(callback=lambda s, d: self.controller.main_windows.on_global_scroll(d))
            dpg.add_mouse_drag_handler(callback=lambda s, d: self.controller.main_windows.on_global_drag(d))
            dpg.add_mouse_release_handler(callback=lambda: self.controller.main_windows.on_global_release())
            dpg.add_key_press_handler(callback=lambda s, d: self.controller.main_windows.on_key_press(d))
            dpg.add_mouse_click_handler(callback=lambda s, d: self.controller.main_windows.on_global_click(d))

    def run(self):
        """Starts the DearPyGui event loop."""
        dpg.setup_dearpygui()
        dpg.show_viewport()
        dpg.set_primary_window("PrimaryWindow", True)

        # --- MANUAL MAIN LOOP ---
        while dpg.is_dearpygui_running():
            # Update coordinate/pixel_value value probe
            self.controller.main_windows.update_overlays()
            # Standard DPG render call
            dpg.render_dearpygui_frame()

        dpg.destroy_context()
