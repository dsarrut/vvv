import dearpygui.dearpygui as dpg
import os
import time
from vvv.utils import ViewMode, fmt
from vvv.file_dialog import open_file_dialog
from .resources import load_fonts, setup_themes
from .core import WL_PRESETS, COLORMAPS
import numpy as np


def create_labeled_field(label, tag):
    """Helper to create a labeled read-only input field."""
    with dpg.group(horizontal=True):
        # Dim the label text so the data values pop out more
        dpg.add_text(
            f"{label}:" if label else "", tag=f"{tag}_label", color=[140, 140, 140]
        )
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
        self.side_panel_width = self.controller.settings.data["layout"][
            "side_panel_width"
        ]
        self.last_window_size = None

        self.layout_cfg = {
            "menu_h": 28,
            # Independent Floating Menu Margins
            "menu_m_top": 0,
            "menu_m_bottom": 15,
            "menu_m_left": 0,
            "menu_m_right": 0,
            "side_panel_w": self.side_panel_width,
            "gap_center": 10,  # Black vertical gap
            "left_m_left": 10,  # Black margin far left
            "left_m_bottom": 10,
            "left_m_top": 0,  # unsure if used ?
            # Internal Gray Padding
            "left_inner_m": 10,  # Margin before text/lines start on the left
            "right_inner_m": 10,  # Margin where lines/text stop on the right
            # Right margins
            "right_m_right": 10,  # 18,
            "right_m_bottom": 10,
            "right_m_top": 0,
            "rounding": 8,
        }

        # tasks manager
        self.tasks = []

        # UI Status Message Tracker
        self.status_message_expire_time = float("inf")

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
        # 1. Start the window container FIRST, and enable its menubar
        with dpg.window(
            tag="PrimaryWindow",
            menubar=False,
            on_close=self.cleanup,
            no_scrollbar=True,
            no_scroll_with_mouse=True,
            no_move=True,
            no_resize=True,
            no_collapse=True,
            no_title_bar=True,
            no_bring_to_front_on_focus=True,
        ):
            # 2. Call the menu bar creation INSIDE the window block!
            self.create_menu_bar()

            # Window resize handler
            with dpg.item_handler_registry(tag="window_resize_handler"):
                dpg.add_item_resize_handler(callback=lambda: self.on_window_resize())
            dpg.bind_item_handler_registry("PrimaryWindow", "window_resize_handler")

            # with dpg.group(horizontal=True):
            self.create_left_panel()
            self.create_viewer_grid()

        # --- Create Pure Black Themes for the Right Panel ---
        cfg = self.layout_cfg
        with dpg.theme(tag="black_viewer_theme"):
            with dpg.theme_component(dpg.mvAll):
                dpg.add_theme_color(dpg.mvThemeCol_ChildBg, [0, 0, 0, 255])
                dpg.add_theme_color(dpg.mvThemeCol_Border, [0, 0, 0, 255])
                dpg.add_theme_style(dpg.mvStyleVar_WindowPadding, 0, 0)
                dpg.add_theme_style(dpg.mvStyleVar_ChildBorderSize, 1)
                # Remove the invisible 8px gaps between items to kill the scrollbar
                dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing, 0, 0)
                # Use ChildRounding for the quadrants
                dpg.add_theme_style(dpg.mvStyleVar_ChildRounding, cfg["rounding"])

        with dpg.theme(tag="active_black_viewer_theme"):
            with dpg.theme_component(dpg.mvAll):
                dpg.add_theme_color(dpg.mvThemeCol_ChildBg, [0, 0, 0, 255])
                c = self.controller.settings.data["colors"]["viewer"]
                dpg.add_theme_color(dpg.mvThemeCol_Border, c)
                dpg.add_theme_style(dpg.mvStyleVar_WindowPadding, 0, 0)
                dpg.add_theme_style(dpg.mvStyleVar_ChildBorderSize, 1)
                dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing, 0, 0)
                # Set thickness to 2 so the rounded corner is clearly visible
                dpg.add_theme_style(dpg.mvStyleVar_ChildBorderSize, 2)
                dpg.add_theme_style(dpg.mvStyleVar_ChildRounding, cfg["rounding"])

        # Bind the black themes globally to the right side
        dpg.bind_item_theme("viewers_container", "black_viewer_theme")
        for tag in ["V1", "V2", "V3", "V4"]:
            dpg.bind_item_theme(f"win_{tag}", "black_viewer_theme")

        # Force the underlying 'floor' to be black
        if not dpg.does_item_exist("primary_black_theme"):
            with dpg.theme(tag="primary_black_theme"):
                with dpg.theme_component(dpg.mvAll):
                    dpg.add_theme_color(dpg.mvThemeCol_WindowBg, [0, 0, 0, 255])
                    dpg.add_theme_style(dpg.mvStyleVar_WindowPadding, 0, 0)

        dpg.bind_item_theme("PrimaryWindow", "primary_black_theme")

    def create_menu_bar(self):
        """Creates a floating, rounded top menu bar using native ImGui menus."""
        cfg = self.layout_cfg
        bg_color = [45, 45, 48, 255]

        if not dpg.does_item_exist("floating_menu_theme"):
            with dpg.theme(tag="floating_menu_theme"):

                # 1. FramePadding MUST be in mvAll to affect the menu text
                with dpg.theme_component(dpg.mvAll):
                    dpg.add_theme_color(dpg.mvThemeCol_ChildBg, bg_color)
                    dpg.add_theme_style(dpg.mvStyleVar_FramePadding, 8, 10)

                # 2. Style the Capsule Background
                with dpg.theme_component(dpg.mvChildWindow):
                    dpg.add_theme_color(dpg.mvThemeCol_ChildBg, bg_color)
                    dpg.add_theme_style(dpg.mvStyleVar_ChildRounding, cfg["rounding"])
                    dpg.add_theme_style(dpg.mvStyleVar_ChildBorderSize, 0)
                    dpg.add_theme_style(dpg.mvStyleVar_WindowPadding, 0, 0)

                # 3. Style the Native Menu Bar inside it
                with dpg.theme_component(dpg.mvMenuBar):
                    dpg.add_theme_color(dpg.mvThemeCol_MenuBarBg, bg_color)
                    dpg.add_theme_color(dpg.mvThemeCol_Border, [0, 0, 0, 0])
                    dpg.add_theme_style(dpg.mvStyleVar_WindowBorderSize, 0)

        # 3. Create the Container
        with dpg.child_window(
            tag="menu_container",
            height=cfg["menu_h"],
            border=False,
            menubar=True,
            no_scrollbar=True,
        ):
            # ... keep your with dpg.menu_bar() and menus exactly the same
            with dpg.menu_bar(tag="main_menu_bar"):
                with dpg.menu(label="File"):
                    dpg.add_menu_item(
                        label="Open Image...", callback=self.on_open_file_clicked
                    )
                    dpg.add_menu_item(label="Exit", callback=self.cleanup)

                with dpg.menu(label="Window/Level"):
                    for preset_name, vals in WL_PRESETS.items():
                        dpg.add_menu_item(
                            label=preset_name,
                            user_data=preset_name,
                            callback=self.on_wl_preset_menu_clicked,
                        )

                with dpg.menu(label="Colormap"):
                    for cmap_name in COLORMAPS.keys():
                        dpg.add_menu_item(
                            label=cmap_name,
                            user_data=cmap_name,
                            callback=self.on_colormap_menu_clicked,
                        )

                dpg.add_spacer(width=20)
                dpg.add_text("", tag="global_status_text", color=[150, 255, 150])

        dpg.bind_item_theme("menu_container", "floating_menu_theme")

    def create_left_panel(self):
        """Creates the sidebar with image list and info."""
        cfg = self.layout_cfg
        # Theme to make the sidebar gray and add a subtle black border on the right
        if not dpg.does_item_exist("sidebar_bg_theme"):
            with dpg.theme(tag="sidebar_bg_theme"):
                with dpg.theme_component(dpg.mvChildWindow):
                    dpg.add_theme_color(dpg.mvThemeCol_ChildBg, [37, 37, 38, 255])
                    # Add a 1px black border strictly to the right side
                    dpg.add_theme_color(dpg.mvThemeCol_Border, [0, 0, 0, 255])
                    dpg.add_theme_style(dpg.mvStyleVar_ChildBorderSize, 1)
                    # Controls the 'roundness'
                    dpg.add_theme_style(dpg.mvStyleVar_ChildRounding, cfg["rounding"])

        # OUTER CONTAINER (Matches the global black window)
        with dpg.group(tag="side_panel_outer"):
            # INNER FLOATING PANEL (The actual gray sidebar)
            # Subtracting 4px from width creates the black 'canyon' gap on the right
            with dpg.child_window(
                width=self.side_panel_width - 4,
                tag="side_panel",
                no_scrollbar=True,
                no_scroll_with_mouse=True,
                border=True,  # Border enabled to show the black line on the right
            ):
                # Add a 10px indent group so text doesn't touch the left edge
                with dpg.group(indent=cfg["left_inner_m"]):
                    dpg.add_spacer(height=5)
                    self.create_left_panel_top_part()
                    self.create_left_panel_bottom_part()

        # Create a sleek, transparent theme for read-only text fields
        if not dpg.does_item_exist("sleek_readonly_theme"):
            with dpg.theme(tag="sleek_readonly_theme"):
                with dpg.theme_component(dpg.mvInputText):
                    dpg.add_theme_color(dpg.mvThemeCol_FrameBg, [0, 0, 0, 0])
                    dpg.add_theme_style(dpg.mvStyleVar_FrameBorderSize, 0)
                    dpg.add_theme_style(dpg.mvStyleVar_FramePadding, 0, 3)

        # Create a theme to highlight the active image in the list
        if not dpg.does_item_exist("active_image_list_theme"):
            with dpg.theme(tag="active_image_list_theme"):
                with dpg.theme_component(dpg.mvText):
                    # Cyan/Blue to perfectly match the active right-panel viewer border
                    dpg.add_theme_color(dpg.mvThemeCol_Text, [100, 200, 255, 255])

        # Create a theme to add breathing room (padding) inside the left panels
        if not dpg.does_item_exist("left_panel_padding_theme"):
            with dpg.theme(tag="left_panel_padding_theme"):
                with dpg.theme_component(dpg.mvAll):
                    # This drops the tabs 12px from the top, and indents the separators 12px!
                    # dpg.add_theme_style(dpg.mvStyleVar_WindowPadding, 12, 12)
                    dpg.add_theme_style(dpg.mvStyleVar_WindowPadding, 0, 12)
                    # Reset FramePadding back to ImGui defaults (4, 3) so the
                    # sidebar buttons don't inherit the huge Menu Bar padding!
                    dpg.add_theme_style(dpg.mvStyleVar_FramePadding, 4, 3)

        dpg.bind_item_theme("image_info_group", "sleek_readonly_theme")
        dpg.bind_item_theme("image_crosshair_group", "sleek_readonly_theme")

        # Apply the padding to both the top and bottom sections
        dpg.bind_item_theme("top_panel", "left_panel_padding_theme")
        dpg.bind_item_theme("bottom_panel", "left_panel_padding_theme")
        dpg.bind_item_theme("side_panel", "sidebar_bg_theme")

    def create_left_panel_top_part(self):
        # We no longer hardcode width here; it's updated in on_window_resize
        with dpg.child_window(
            tag="top_panel",
            height=370,
            resizable_y=True,
            border=False,
            no_scrollbar=True,
        ):
            with dpg.tab_bar(tag="sidebar_tabs"):
                # Tab 1: Image Management
                with dpg.tab(label="Images"):
                    dpg.add_spacer(height=5)
                    dpg.add_text("Loaded Images", color=[93, 93, 93])
                    dpg.add_separator()
                    dpg.add_group(tag="image_list_container")

                self.create_tab_sync()
                self.create_tab_fusion()
                self.create_tab_settings()

    def create_tab_sync(self):
        # Tab 2: Sync
        with dpg.tab(label="Sync"):
            dpg.add_spacer(height=5)
            with dpg.group(horizontal=True):
                dpg.add_button(
                    label="Link All",
                    callback=lambda: self.controller.link_all(),
                    width=80,
                )
                dpg.add_button(
                    label="Unlink All",
                    callback=lambda: self.controller.unlink_all(),
                    width=80,
                )
            dpg.add_spacer(height=5)
            dpg.add_text("Sync Groups", color=[93, 93, 93])
            dpg.add_separator()
            with dpg.group(tag="sync_list_container"):
                # We will populate this programmatically
                pass

    def create_tab_fusion(self):
        # Tab 3: Fusion
        with dpg.tab(label="Fusion"):
            dpg.add_spacer(height=5)
            dpg.add_text("Active Overlay", color=[93, 93, 93])
            dpg.add_separator()

            with dpg.group(tag="image_fusion_group"):
                with dpg.group(horizontal=True):
                    dpg.add_text("Target ")
                    dpg.add_combo(
                        ["None"],
                        tag="combo_overlay_select",
                        width=-1,
                        callback=self.on_overlay_selected,
                    )
                with dpg.group(horizontal=True):
                    dpg.add_text("Opacity")
                    dpg.add_slider_float(
                        tag="slider_overlay_opacity",
                        min_value=0.0,
                        max_value=1.0,
                        width=-1,
                        callback=self.on_opacity_changed,
                    )
                with dpg.group(horizontal=True):
                    dpg.add_text("Min Thr")
                    dpg.add_input_float(
                        tag="input_overlay_threshold",
                        width=-1,
                        step=10,
                        callback=self.on_threshold_changed,
                    )

    def create_tab_settings(self):
        # Tab 3: Settings
        with dpg.tab(label="Settings"):
            dpg.add_spacer(height=5)
            with dpg.group(tag="settings_container"):
                call = self.controller.update_setting
                settings = self.controller.settings.data

                dpg.add_text("Parameters", color=[93, 93, 93])
                dpg.add_input_float(
                    label="Auto WL FOV",
                    tag="set_auto_window_fov",
                    width=120,
                    format="%.2f",
                    step=0.05,
                    default_value=settings["physics"].get("auto_window_fov", 0.20),
                    callback=lambda s, v: call(["physics", "auto_window_fov"], v),
                )

                dpg.add_input_int(
                    label="Strip Threshold",
                    tag="set_strip_threshold",
                    width=120,
                    default_value=settings["physics"]["voxel_strip_threshold"],
                    callback=lambda s, v: call(["physics", "voxel_strip_threshold"], v),
                )

                dpg.add_separator()

                dpg.add_text("Colors", color=[93, 93, 93])
                dpg.add_color_edit(
                    label="Crosshair",
                    tag="set_col_crosshair",
                    default_value=settings["colors"]["crosshair"],
                    callback=lambda s, v: call(["colors", "crosshair"], v),
                )
                dpg.add_color_edit(
                    label="Mouse tracker",
                    tag="set_col_tracker_text",
                    default_value=settings["colors"]["tracker_text"],
                    callback=lambda s, v: call(["colors", "tracker_text"], v),
                )
                dpg.add_color_edit(
                    label="Grid",
                    tag="set_col_grid",
                    default_value=settings["colors"]["grid"],
                    callback=lambda s, v: call(["colors", "grid"], v),
                )
                """dpg.add_color_edit(
                    label="Hover",
                    tag="set_col_hover",
                    default_value=settings["colors"]["viewer"],
                    callback=lambda s, v: call(["colors", "viewer"], v),
                )"""  # FIXME why not update ?

                dpg.add_spacer(height=10)

                with dpg.group(horizontal=True):
                    dpg.add_button(
                        label="Save",
                        width=100,
                        callback=lambda: self.on_save_settings(),
                    )
                    dpg.add_button(
                        label="Reset",
                        width=-1,
                        callback=lambda: self.on_reset_settings(),
                    )

                def copy_and_notify():
                    dpg.set_clipboard_text(str(self.controller.settings.config_path))
                    self.show_status_message("Path copied to clipboard!")

                dpg.add_spacer(height=10)
                dpg.add_text(f"Edit settings in :", color=[150, 150, 150])
                with dpg.group(horizontal=True):
                    btn_copy = dpg.add_button(label="\uf0c5", callback=copy_and_notify)
                    dpg.add_input_text(
                        default_value=str(self.controller.settings.config_path),
                        readonly=True,
                        width=230,
                    )

                # Bind the custom icon font to this specific button
                if dpg.does_item_exist("icon_font_tag"):
                    dpg.bind_item_font(btn_copy, "icon_font_tag")

    def create_left_panel_bottom_part(self):
        # Active Viewer Info Section
        panel_w = self.side_panel_width - 15
        with dpg.child_window(
            tag="bottom_panel", width=panel_w, border=False, no_scrollbar=True
        ):
            dpg.add_text("Active Viewer", color=[93, 93, 93])
            dpg.add_separator()

            with dpg.group(tag="image_info_group"):
                create_labeled_field("", tag="info_name")
                create_labeled_field("Type", tag="info_voxel_type")
                create_labeled_field("Size", tag="info_size")
                create_labeled_field("Spacing", tag="info_spacing")
                create_labeled_field("Origin", tag="info_origin")
                create_labeled_field("Matrix", tag="info_matrix")
                self.create_window_level_controls()
                dpg.add_input_text(tag="info_memory", readonly=True, width=-1)
                dpg.add_spacer(height=5)
                self.create_visibility_controls()

            dpg.add_spacer(height=10)
            dpg.add_text("Crosshair", color=[93, 93, 93])
            dpg.add_separator()

            with dpg.group(tag="image_crosshair_group"):
                create_labeled_field("Value", tag="info_val")
                create_labeled_field("Voxel", tag="info_vox")
                create_labeled_field("Coord", tag="info_phys")
                create_labeled_field("ppm", tag="info_ppm")
                create_labeled_field("FOV", tag="info_scale")

    def create_window_level_controls(self):
        """Creates the window and level input fields and sync toggle."""
        with dpg.group(horizontal=True):
            with dpg.group(horizontal=True):
                dpg.add_text("Window")
                dpg.add_input_text(
                    tag="info_window",
                    width=65,
                    on_enter=True,
                    callback=lambda: self.on_sidebar_wl_change(),
                )
            dpg.add_spacer(width=5)
            with dpg.group(horizontal=True):
                dpg.add_text("Level")
                dpg.add_input_text(
                    tag="info_level",
                    width=65,
                    on_enter=True,
                    callback=lambda: self.on_sidebar_wl_change(),
                )

    def create_visibility_controls(self):
        with dpg.group(tag="visibility_controls"):
            with dpg.table(header_row=False, policy=dpg.mvTable_SizingFixedFit):
                dpg.add_table_column()
                dpg.add_table_column()
                with dpg.table_row():
                    dpg.add_checkbox(
                        label="Slice axis",
                        tag="check_axis",
                        callback=self.controller.on_visibility_toggle,
                        user_data="axis",
                        default_value=True,
                    )
                    dpg.add_checkbox(
                        label="Pixels grid",
                        tag="check_grid",
                        callback=self.controller.on_visibility_toggle,
                        user_data="grid",
                        default_value=False,
                    )
                with dpg.table_row():
                    dpg.add_checkbox(
                        label="Mouse tracker",
                        tag="check_tracker",
                        callback=self.controller.on_visibility_toggle,
                        user_data="tracker",
                        default_value=True,
                    )
                    dpg.add_checkbox(
                        label="Crosshair",
                        tag="check_crosshair",
                        callback=self.controller.on_visibility_toggle,
                        user_data="crosshair",
                        default_value=True,
                    )
                with dpg.table_row():
                    dpg.add_checkbox(
                        label="Scale bar",
                        tag="check_scalebar",
                        callback=self.controller.on_visibility_toggle,
                        user_data="scalebar",
                        default_value=False,
                    )
                    # Sync Toggle
                    dpg.add_checkbox(
                        label="Sync W/L",
                        tag="check_sync_wl",
                        default_value=False,
                        callback=self.on_sync_wl_toggle,
                    )

    def create_viewer_grid(self):
        """Creates the 2x2 grid of slice viewers."""
        with dpg.child_window(
            tag="viewers_container",
            border=False,
            no_scrollbar=True,
            no_scroll_with_mouse=True,
        ):
            with dpg.group(horizontal=True):
                self.create_viewer_widget("V1")
                self.create_viewer_widget("V2")
            with dpg.group(horizontal=True):
                self.create_viewer_widget("V3")
                self.create_viewer_widget("V4")

    def create_viewer_widget(self, tag):
        """Creates a single viewer widget."""
        viewer = self.controller.viewers[tag]
        with dpg.child_window(
            tag=f"win_{tag}", border=True, no_scrollbar=True, no_scroll_with_mouse=True
        ):
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

            col = self.controller.settings.data["colors"]["tracker_text"]
            dpg.add_text("", tag=viewer.tracker_tag, color=col, pos=[5, 5])

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

        if dpg.get_value("check_tracker") != vs.show_tracker:
            dpg.set_value("check_tracker", vs.show_tracker)

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
                    # Subtle Sync Group Indicator (No color, just dimmed gray)
                    if vs.sync_group > 0:
                        dpg.add_text(f"[{vs.sync_group}]", color=[150, 150, 150])
                    else:
                        dpg.add_text(
                            "   ", color=[0, 0, 0, 0]
                        )  # Invisible spacer for alignment

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
                            callback=self.on_image_viewer_toggle,
                        )
                    # Reload Button
                    btn_reload = dpg.add_button(
                        label="\uf01e",
                        width=20,
                        callback=lambda s, a, u: self.controller.reload_image(u),
                        user_data=vs_id,
                    )
                    # Close Button
                    btn_close = dpg.add_button(
                        label="\uf00d",
                        width=20,
                        callback=lambda s, a, u: self.controller.close_image(u),
                        user_data=vs_id,
                    )

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
        # Re-apply the highlight because the text labels were just recreated!
        if self.context_viewer and self.context_viewer.image_id:
            self.highlight_active_image_in_list(self.context_viewer.image_id)

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
        if not dpg.does_item_exist(container):
            return
        dpg.delete_item(container, children_only=True)

        # Safely determine the max group needed, even if images were closed
        max_active_group = max(
            [vs.sync_group for vs in self.controller.view_states.values()] + [0]
        )
        num_groups = max(3, len(self.controller.view_states), max_active_group)

        combo_items = ["None"] + [f"Group {i}" for i in range(1, num_groups + 1)]

        # Table for alignment
        with dpg.table(parent=container, header_row=False):
            dpg.add_table_column(label="Image")
            dpg.add_table_column(label="Group", width_fixed=True)

            for vs_id, vs in self.controller.view_states.items():
                with dpg.table_row():
                    dpg.add_text(vs.volume.name)
                    # Dropdown to pick a group (0 = None)
                    dpg.add_combo(
                        items=combo_items,
                        default_value=(
                            "None" if not vs.sync_group else f"Group {vs.sync_group}"
                        ),
                        width=100,
                        user_data=vs_id,
                        callback=self.controller.on_sync_group_change,
                    )

    @property
    def hovered_viewer(self):
        """Returns the viewer currently under the mouse cursor."""
        for viewer in self.controller.viewers.values():
            if dpg.is_item_hovered(f"win_{viewer.tag}"):
                return viewer
        return None

    def update_trackers(self):
        """Updates sidebar context on hover and refreshes on-image trackers."""
        hover_viewer = self.hovered_viewer

        # Context Switch logic based on ViewState
        if (
            hover_viewer
            and hover_viewer != self.context_viewer
            and not self.drag_viewer
        ):
            # Remove highlight from the old viewer
            if self.context_viewer:
                dpg.bind_item_theme(
                    f"win_{self.context_viewer.tag}", "black_viewer_theme"
                )

            # Add highlight to the new viewer
            dpg.bind_item_theme(f"win_{hover_viewer.tag}", "active_black_viewer_theme")

            # Tell the UI list to highlight the image we just hovered over!
            self.highlight_active_image_in_list(hover_viewer.image_id)

            # Update sidebar
            self.update_sidebar_info(hover_viewer)
            self.update_sidebar_crosshair(hover_viewer)
            self.context_viewer = hover_viewer

        # Always refresh the on-image text/crosshairs for all viewers
        for viewer in self.controller.viewers.values():
            viewer.update_tracker()

    def update_sidebar_info(self, viewer):
        """Pulls metadata from the active viewer and updates the sidebar."""
        if not viewer or viewer.image_id is None:
            for t in [
                "info_name",
                "info_size",
                "info_spacing",
                "info_origin",
                "info_memory",
            ]:
                dpg.set_value(t, "")
            return

        vol = viewer.volume  # Immutable physical data
        dpg.set_value("info_name", vol.name)
        dpg.set_value("info_name_label", viewer.tag)
        dpg.set_value("info_voxel_type", f"{vol.pixel_type}")
        dpg.set_value(
            "info_size",
            f"{vol.data.shape[2]} x {vol.data.shape[1]} x {vol.data.shape[0]}",
        )
        dpg.set_value("info_spacing", fmt(vol.spacing, 4))
        dpg.set_value("info_origin", fmt(vol.origin, 2))
        dpg.set_value("info_matrix", fmt(vol.matrix, 1))
        dpg.set_value(
            "info_memory",
            f"{vol.sitk_image.GetNumberOfPixels():,} voxels    {vol.memory_mb:g} MB",
        )

        # RGB Locking Logic
        is_rgb = getattr(vol, "is_rgb", False)
        if dpg.does_item_exist("info_window"):
            dpg.configure_item("info_window", enabled=not is_rgb)
        if dpg.does_item_exist("info_level"):
            dpg.configure_item("info_level", enabled=not is_rgb)

        if is_rgb:
            if dpg.does_item_exist("info_window"):
                dpg.set_value("info_window", "RGB")
            if dpg.does_item_exist("info_level"):
                dpg.set_value("info_level", "RGB")
        else:
            self.update_sidebar_window_level(viewer)

        # Update Overlay Dropdown Options
        if dpg.does_item_exist("combo_overlay_select"):
            options = ["None"]
            for vid, ovs in self.controller.view_states.items():
                if vid != viewer.image_id:  # Don't let an image overlay itself
                    options.append(f"{vid}: {ovs.volume.name}")

            dpg.configure_item("combo_overlay_select", items=options)

            current_sel = "None"
            if viewer.view_state.overlay_id:
                ovs_name = self.controller.view_states[
                    viewer.view_state.overlay_id
                ].volume.name
                current_sel = f"{viewer.view_state.overlay_id}: {ovs_name}"
            dpg.set_value("combo_overlay_select", current_sel)
            dpg.set_value("slider_overlay_opacity", viewer.view_state.overlay_opacity)
            dpg.set_value(
                "input_overlay_threshold", viewer.view_state.overlay_threshold
            )

    def update_sidebar_window_level(self, viewer):
        """Updates the W/L inputs in the sidebar."""
        if not viewer or not viewer.view_state:
            return
        vol = viewer.volume
        vs = viewer.view_state
        if getattr(vol, "is_rgb", False):
            return
        dpg.set_value("info_window", f"{vs.ww:g}")
        dpg.set_value("info_level", f"{vs.wl:g}")

    def update_sidebar_crosshair(self, viewer):
        """Updates the crosshair stats in the sidebar."""
        if not viewer or not viewer.view_state:
            return
        vs = viewer.view_state
        vol = viewer.volume

        if vs.crosshair_voxel is not None:
            dpg.set_value("info_vox", fmt(vs.crosshair_voxel, 1))
            dpg.set_value("info_phys", fmt(vs.crosshair_phys_coord, 1))
            val_str = (
                (
                    f"{vs.crosshair_value[0]:g} "
                    f"{vs.crosshair_value[1]:g} "
                    f"{vs.crosshair_value[2]:g}"
                )
                if getattr(vol, "is_rgb", False)
                else f"{vs.crosshair_value:g}"
            )

            # Safely fetch the fused value using the exact same grid indices
            if vs.overlay_data is not None:
                ix, iy, iz = [
                    int(np.clip(np.floor(c + 0.5), 0, limit - 1))
                    for c, limit in zip(
                        vs.crosshair_voxel,
                        [vol.data.shape[2], vol.data.shape[1], vol.data.shape[0]],
                    )
                ]
                val_str += f" ({vs.overlay_data[iz, iy, ix]:g})"
            dpg.set_value("info_val", val_str)

            ppm = viewer.get_pixels_per_mm()
            win_w = dpg.get_item_width(f"win_{viewer.tag}")
            win_h = dpg.get_item_height(f"win_{viewer.tag}")

            if ppm > 0 and win_w and win_h:
                fov_w = win_w / ppm
                fov_h = win_h / ppm
                dpg.set_value(
                    "info_scale", f"{fov_w:.0f}x{fov_h:.0f} mm  {ppm:.1f} px/mm"
                )
            dpg.set_value("info_ppm", f"{ppm:g}")

    def on_window_resize(self):
        window_width = dpg.get_viewport_client_width()
        window_height = dpg.get_viewport_client_height()
        if not window_width or not window_height:
            return

        cfg = self.layout_cfg

        # 1. Position the Menu Bar (using separate margins)
        m_t, m_l, m_r = cfg["menu_m_top"], cfg["menu_m_left"], cfg["menu_m_right"]
        if dpg.does_item_exist("menu_container"):
            dpg.set_item_pos("menu_container", [m_l, m_t])
            dpg.set_item_width("menu_container", window_width - m_l - m_r)

        # 2. Panels Y position = Top Margin + Menu Height + Bottom Menu Margin
        panels_y = cfg["menu_m_top"] + cfg["menu_h"] + cfg["menu_m_bottom"]

        # Left Panel
        l_x = cfg["left_m_left"]
        l_w = cfg["side_panel_w"]
        l_h = window_height - panels_y - cfg["left_m_bottom"]

        if dpg.does_item_exist("side_panel_outer"):
            dpg.set_item_pos("side_panel_outer", [l_x, panels_y])
            dpg.set_item_width("side_panel", l_w - cfg["gap_center"])
            dpg.set_item_height("side_panel", l_h)

            inner_w = (
                l_w - cfg["gap_center"] - cfg["left_inner_m"] - cfg["right_inner_m"]
            )
            if dpg.does_item_exist("top_panel"):
                dpg.set_item_width("top_panel", inner_w)
            if dpg.does_item_exist("bottom_panel"):
                dpg.set_item_width("bottom_panel", inner_w)

        # Right Viewers
        r_x = l_x + l_w
        avail_w = window_width - r_x - cfg["right_m_right"]
        avail_h = window_height - panels_y - cfg["right_m_bottom"]
        quad_w, quad_h = avail_w // 2, avail_h // 2

        if dpg.does_item_exist("viewers_container"):
            dpg.set_item_pos("viewers_container", [r_x, panels_y])
            dpg.set_item_width("viewers_container", quad_w * 2)
            dpg.set_item_height("viewers_container", quad_h * 2)

        for viewer in self.controller.viewers.values():
            # viewer.resize(quad_w - 28, quad_h - 28)  # Gap for rounding visibility
            viewer.resize(quad_w, quad_h)  # Gap for rounding visibility

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
            if not dpg.is_key_down(dpg.mvKey_LShift) and not dpg.is_key_down(
                dpg.mvKey_LControl
            ):
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
            is_ctrl = dpg.is_key_down(dpg.mvKey_LControl) or dpg.is_key_down(
                dpg.mvKey_RControl
            )

            if is_ctrl:
                # app_data is positive when scrolling up (away), negative when scrolling down (towards)
                direction = "in" if app_data > 0 else "out"
                self.hovered_viewer.on_zoom(direction)
            else:
                # Default behavior: scroll through slices
                self.hovered_viewer.on_scroll(int(app_data))

    def on_key_press(self, sender, app_data, user_data):
        # app_data contains the pressed key code

        # Check for Command (macOS) - DPG maps this to the 'Win' key constants
        is_cmd = dpg.is_key_down(dpg.mvKey_LWin) or dpg.is_key_down(dpg.mvKey_RWin)
        is_ctrl = dpg.is_key_down(dpg.mvKey_LControl) or dpg.is_key_down(
            dpg.mvKey_RControl
        )

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

    def on_reset_settings(self):
        self.controller.reset_settings()
        data = self.controller.settings.data

        # Update the UI inputs to match the newly reset backend data
        dpg.set_value("set_auto_window_fov", data["physics"]["auto_window_fov"])
        dpg.set_value("set_strip_threshold", data["physics"]["voxel_strip_threshold"])
        for key, value in data["colors"].items():
            tag = f"set_col_{key}"
            if dpg.does_item_exist(tag):
                dpg.set_value(tag, value)

        self.show_status_message(f"Settings reset")

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
        if (
            not viewer
            or not viewer.view_state
            or getattr(viewer.volume, "is_rgb", False)
        ):
            return

        preset_name = user_data
        viewer.view_state.apply_wl_preset(preset_name)
        self.update_sidebar_window_level(viewer)
        self.controller.propagate_window_level(viewer.image_id)

    def on_colormap_menu_clicked(self, sender, app_data, user_data):
        viewer = self.context_viewer
        if (
            not viewer
            or not viewer.view_state
            or getattr(viewer.volume, "is_rgb", False)
        ):
            return

        viewer.view_state.colormap = user_data
        self.controller.propagate_colormap(viewer.image_id)

    def on_sync_wl_toggle(self, sender, app_data, user_data):
        """Immediately propagates window/level when the sync checkbox is turned on."""
        viewer = self.context_viewer
        if not viewer or not viewer.image_id:
            return

        # app_data is True if the box was just checked.
        # If checked, push the current active image's W/L to the rest of its sync group immediately.
        if app_data:
            self.controller.propagate_window_level(viewer.image_id)

    def on_overlay_selected(self, sender, app_data, user_data):
        viewer = self.context_viewer
        if not viewer or not viewer.view_state:
            return

        if app_data == "None":
            viewer.view_state.set_overlay(None, None)
        else:
            # Extract the raw ID from the dropdown string "ID: Name"
            target_id = app_data.split(":")[0]
            target_vol = self.controller.volumes[target_id]

            # Show a brief loading message because SimpleITK resampling might take 1-2 seconds
            self.show_status_message(f"Resampling overlay to physical grid...")

            # Use a tiny threading hack to allow the UI to draw the "Resampling..." message
            # before we block the python thread with the heavy math.
            def _resample():
                time.sleep(0.05)
                viewer.view_state.set_overlay(target_id, target_vol)
                self.show_status_message("Overlay applied!")

            import threading

            threading.Thread(target=_resample, daemon=True).start()

    def on_opacity_changed(self, sender, app_data, user_data):
        viewer = self.context_viewer
        if not viewer or not viewer.view_state:
            return
        viewer.view_state.overlay_opacity = app_data
        viewer.view_state.is_data_dirty = True

    def on_threshold_changed(self, sender, app_data, user_data):
        viewer = self.context_viewer
        if not viewer or not viewer.view_state:
            return
        viewer.view_state.overlay_threshold = app_data
        viewer.view_state.is_data_dirty = True

    def load_single_image_sequence(self, file_path):
        """Generator that shows a loading progress bar while reading a large file."""
        filename = os.path.basename(file_path)

        with dpg.window(
            tag="loading_modal",
            modal=True,
            show=True,
            no_title_bar=True,
            no_resize=True,
            no_move=True,
            width=350,
            height=100,
        ):
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

            target_viewer = (
                self.context_viewer
                if self.context_viewer
                else self.controller.viewers["V1"]
            )
            target_viewer.set_image(img_id)

            same_image_viewers = [
                v.tag for v in self.controller.viewers.values() if v.image_id == img_id
            ]
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
            self.show_message("File Load Error", f"Failed to load image:\n{filename}")

            # Keep generator alive until user acknowledges the error
            while dpg.does_item_exist("generic_message_modal"):
                yield

    def show_message(self, title, message):
        """Displays a reusable, centered modal dialog for errors and alerts."""
        modal_tag = "generic_message_modal"
        if dpg.does_item_exist(modal_tag):
            dpg.delete_item(modal_tag)

        with dpg.window(
            tag=modal_tag,
            modal=True,
            show=True,
            label=title,
            no_collapse=True,
            width=450,
        ):
            dpg.add_text(message, wrap=430)
            dpg.add_spacer(height=10)
            with dpg.group(horizontal=True):
                dpg.add_spacer(width=160)
                dpg.add_button(
                    label="OK", width=100, callback=lambda: dpg.delete_item(modal_tag)
                )

        vp_width = max(dpg.get_viewport_client_width(), 800)
        vp_height = max(dpg.get_viewport_client_height(), 600)
        dpg.set_item_pos(modal_tag, [vp_width // 2 - 225, vp_height // 2 - 100])

    def show_status_message(self, message, duration=3.0, color=None):
        """Displays a temporary status message in the menu bar."""
        if color is None:
            color = [150, 255, 150]  # FIXME in settings ?

        if dpg.does_item_exist("global_status_text"):
            dpg.set_value("global_status_text", f"[{message}]")
            dpg.configure_item("global_status_text", color=color)

        # Set the time when this message should disappear
        self.status_message_expire_time = time.time() + duration

    def show_help_window(self):
        """Displays a dynamic floating window with mouse controls and current keyboard shortcuts."""
        window_tag = "help_window"
        if dpg.does_item_exist(window_tag):
            dpg.delete_item(window_tag)

        # Removed modal=True, enabled collapsing, added on_close cleanup
        with dpg.window(
            tag=window_tag,
            show=True,
            label="Shortcuts & Controls",
            width=500,
            height=520,
            no_collapse=False,
            on_close=lambda: dpg.delete_item(window_tag),
        ):
            dpg.add_spacer(height=5)
            dpg.add_text("Mouse Controls", color=[100, 200, 255])
            dpg.add_separator()
            dpg.add_text("Left Click         : Move crosshair")
            dpg.add_text("Scroll Wheel       : Change slice")
            dpg.add_text("Ctrl + Scroll      : Zoom in/out")
            dpg.add_text("Ctrl + Drag        : Pan view")
            dpg.add_text("Shift + Drag       : Adjust Window/Level (X/Y axis)")

            dpg.add_spacer(height=15)
            dpg.add_text("Keyboard Shortcuts", color=[100, 200, 255])
            dpg.add_separator()

            shortcuts = self.controller.settings.data["shortcuts"]
            descriptions = {
                "open_file": "Open File",
                "next_image": "Next Image in List",
                "auto_window": "Auto Window/Level (Base)",
                "auto_window_overlay": "Auto Window/Level (Overlay)",
                "scroll_up": "Scroll Slice Up",
                "scroll_down": "Scroll Slice Down",
                "fast_scroll_up": "Fast Scroll Up",
                "fast_scroll_down": "Fast Scroll Down",
                "zoom_in": "Zoom In",
                "zoom_out": "Zoom Out",
                "reset_view": "Reset Zoom & Pan",
                "center_view": "Center View on Crosshair",
                "view_axial": "Axial View",
                "view_sagittal": "Sagittal View",
                "view_coronal": "Coronal View",
                "view_histogram": "Histogram View",
                "toggle_interp": "Toggle strip pixels at zoom",
                "toggle_grid": "Toggle Voxel Grid",
                "hide_all": "Show/Hide Overlays",
            }

            def format_key(key_name, k):
                if k == 517:
                    return "Page Up"
                if k == 518:
                    return "Page Down"

                # Explicitly add the modifier for the open file command
                res = str(k)
                if key_name == "open_file":
                    return f"Ctrl + {res}"
                return res

            with dpg.table(
                header_row=False, borders_innerH=True, policy=dpg.mvTable_SizingFixedFit
            ):
                dpg.add_table_column(width_fixed=True, init_width_or_weight=120)
                dpg.add_table_column(width_stretch=True)
                for key_id, desc in descriptions.items():
                    val = shortcuts.get(key_id, "N/A")
                    with dpg.table_row():
                        dpg.add_text(format_key(key_id, val), color=[150, 255, 150])
                        dpg.add_text(desc)

            dpg.add_spacer(height=15)
            with dpg.group(horizontal=True):
                dpg.add_spacer(width=200)
                dpg.add_button(
                    label="Close",
                    width=100,
                    callback=lambda: dpg.delete_item(window_tag),
                )

        # Spawn the window neatly in the top-right corner so it doesn't block the images
        vp_width = max(dpg.get_viewport_client_width(), 800)
        dpg.set_item_pos(window_tag, [vp_width - 520, 40])

    def create_boot_sequence(self, image_tasks, sync=False, link_all=False):
        """Creates a generator for the boot sequence that loads images and parses fusion tasks."""
        if not image_tasks:
            return

        # Calculate total files to read (bases + fusions)
        total_files = len(image_tasks) + sum(1 for t in image_tasks if t["fusion"])

        with dpg.window(
            tag="loading_modal",
            modal=True,
            show=True,
            no_title_bar=True,
            no_resize=True,
            no_move=True,
            width=350,
            height=100,
        ):
            dpg.add_text("Initializing...", tag="loading_text")
            dpg.add_spacer(height=5)
            dpg.add_progress_bar(tag="loading_progress", width=-1, default_value=0.0)

        vp_width = max(dpg.get_viewport_client_width(), 800)
        vp_height = max(dpg.get_viewport_client_height(), 600)
        dpg.set_item_pos("loading_modal", [vp_width // 2 - 175, vp_height // 2 - 50])
        yield

        loaded_ids = []
        files_processed = 0

        for task in image_tasks:
            base_path = task["base"]
            filename = os.path.basename(base_path)

            # 1. Load Base Image
            if dpg.does_item_exist("loading_text"):
                dpg.set_value("loading_text", f"Loading base...\n{filename}")
            if dpg.does_item_exist("loading_progress"):
                dpg.set_value("loading_progress", files_processed / total_files)
            yield

            try:
                base_id = self.controller.load_image(base_path)
                loaded_ids.append(base_id)
                files_processed += 1
            except Exception as e:
                self.show_message("Load Error", f"Failed to load:\n{filename}")
                continue

            # 2. Handle Fusion Overlay (if requested)
            if task["fusion"]:
                fuse_path = task["fusion"]["path"]
                fuse_name = os.path.basename(fuse_path)

                if dpg.does_item_exist("loading_text"):
                    dpg.set_value("loading_text", f"Resampling overlay...\n{fuse_name}")
                if dpg.does_item_exist("loading_progress"):
                    dpg.set_value("loading_progress", files_processed / total_files)
                yield

                try:
                    # Load the overlay as a full image in the system
                    fuse_id = self.controller.load_image(fuse_path)
                    loaded_ids.append(fuse_id)
                    files_processed += 1

                    # Apply the requested modifiers
                    fuse_vs = self.controller.view_states[fuse_id]
                    fuse_vs.colormap = task["fusion"]["cmap"]
                    fuse_vs.is_data_dirty = True

                    # Bind it to the base image
                    base_vs = self.controller.view_states[base_id]
                    base_vs.set_overlay(fuse_id, fuse_vs.volume)
                    base_vs.overlay_opacity = task["fusion"]["opacity"]
                    base_vs.overlay_threshold = task["fusion"]["threshold"]

                except Exception as e:
                    self.show_message(
                        "Overlay Error", f"Failed to load/fuse:\n{fuse_name}"
                    )
                    continue

        if dpg.does_item_exist("loading_text"):
            dpg.set_value("loading_text", "Applying synchronization and layouts...")
        if dpg.does_item_exist("loading_progress"):
            dpg.set_value("loading_progress", 1.0)
        yield

        self.controller.default_viewers_orientation()

        # Distribute the loaded images across the 4 viewers
        for i, img_id in enumerate(loaded_ids):
            if i == 0:
                for tag in ["V1", "V2", "V3", "V4"]:
                    self.controller.viewers[tag].set_image(img_id)
            elif i == 1:
                self.controller.viewers["V3"].set_image(img_id)
                self.controller.viewers["V4"].set_image(img_id)
            elif i == 2:
                self.controller.viewers["V2"].set_image(loaded_ids[1])
                self.controller.viewers["V3"].set_image(img_id)
                self.controller.viewers["V4"].set_image(img_id)
            elif i >= 3:
                self.controller.viewers["V4"].set_image(img_id)

        # Unify scales for same-image viewers
        for img_id in loaded_ids:
            same_viewers = [
                v.tag for v in self.controller.viewers.values() if v.image_id == img_id
            ]
            if same_viewers:
                self.controller.unify_ppm(same_viewers)

        if sync or link_all:
            for img_id in loaded_ids:
                self.controller.on_sync_group_change(None, "Group 1", img_id)
            self.refresh_sync_ui()

        self.on_window_resize()
        self.refresh_image_list_ui()

        if dpg.does_item_exist("loading_modal"):
            dpg.delete_item("loading_modal")
        yield

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
                self.status_message_expire_time = float("inf")

            if self.tasks:
                try:
                    next(self.tasks[0])
                except StopIteration:
                    self.tasks.pop(0)

            self.update_trackers()
            self.sync_sidebar_checkboxes()

            self.controller.tick()

            dpg.render_dearpygui_frame()
