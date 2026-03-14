import dearpygui.dearpygui as dpg
import os
import time
import threading
import numpy as np
from vvv.utils import ViewMode, fmt
from vvv.file_dialog import open_file_dialog
from .resources import load_fonts, setup_themes
from .core import WL_PRESETS, COLORMAPS
from .settings_ui import SettingsWindow


class MainGUI:
    """
    Manages the DearPyGui user interface for VVV.
    """

    # ==========================================
    # 1. INITIALIZATION & CONFIGURATION
    # ==========================================

    def __init__(self, controller):
        self.controller = controller

        # State variables
        self.icon_font = None
        self.drag_viewer = None
        self.context_viewer = None
        self.last_window_size = None
        self.tasks = []
        self.status_message_expire_time = float("inf")
        self.image_label_tags = {}
        self.sync_label_tags = {}
        self.ui_cfg = None

        # Initialization pipeline
        self.init_config()
        self.icon_font = load_fonts()
        setup_themes()  # From resources.py (static themes)
        self.register_dynamic_themes()
        self.settings_window = SettingsWindow(self.controller)

        self.build_main_layout()
        self.register_handlers()

    def init_config(self):
        """Centralizes all layout dimensions, margins, and colors."""
        shared_margin = 7
        self.ui_cfg = {
            "layout": {
                "menu_h": 27,
                "menu_m_top": 0,
                "menu_m_bottom": 5 + shared_margin,
                "menu_m_left": 0,
                "menu_m_right": 0,
                "side_panel_w": self.controller.settings.data["layout"][
                    "side_panel_width"
                ],
                "gap_center": shared_margin,  # Black vertical gap
                "left_m_left": shared_margin,  # Black margin far left
                "left_m_bottom": shared_margin,
                "left_m_top": 0,
                "left_inner_m": shared_margin,  # Margin before text/lines start on the left
                "right_inner_m": shared_margin,  # Margin where lines/text stop on the right
                "right_m_right": shared_margin,
                "right_m_bottom": shared_margin,
                "right_m_top": 0,
                "rounding": 8,
                # Chunky padding for top menu items
                "pad_frame_menu": [8, 10],
                # Sleek vertical-only padding for sidebar text
                "pad_frame_readonly": [0, 3],
                # Standard button padding for sidebar
                "pad_frame_sidebar": [4, 3],
                # Menu Dropdown Spacing (Left/Right and Top/Bottom border margin)
                "pad_menu_popup": [12, 12],
                # Gap between menu items
                "space_menu_item": [10, 6],
            },
            "colors": {
                "bg_window": [0, 0, 0, 255],
                "bg_menubar": [37, 37, 38, 255],
                "bg_menu": [27, 27, 28, 255],
                "bg_menu_hover": [70, 70, 75, 255],
                "bg_menu_active": [80, 80, 85, 255],
                "bg_sidebar": [37, 37, 38, 255],
                "border_black": [0, 0, 0, 255],
                "text_dim": [140, 140, 140],
                # "text_header": [140, 140, 140],
                "text_header": [93, 93, 93],
                # "text_active": [100, 200, 255, 255],  # Cyan/Blue
                "text_active": [0, 246, 7, 255],
                "text_status_ok": [150, 255, 150],
                "text_muted": [150, 150, 150],
                "transparent": [0, 0, 0, 0],
            },
        }

    def register_dynamic_themes(self):
        """Builds and registers all UI themes dynamically based on the ui_cfg."""
        cfg_l = self.ui_cfg["layout"]
        cfg_c = self.ui_cfg["colors"]

        # Base black background theme for the primary window
        if not dpg.does_item_exist("primary_black_theme"):
            with dpg.theme(tag="primary_black_theme"):
                with dpg.theme_component(dpg.mvAll):
                    dpg.add_theme_color(dpg.mvThemeCol_WindowBg, cfg_c["bg_window"])
                    dpg.add_theme_style(dpg.mvStyleVar_WindowPadding, 0, 0)

        # Right side: Viewer quadrants (Idle)
        if not dpg.does_item_exist("black_viewer_theme"):
            with dpg.theme(tag="black_viewer_theme"):
                with dpg.theme_component(dpg.mvAll):
                    dpg.add_theme_color(dpg.mvThemeCol_ChildBg, cfg_c["bg_window"])
                    dpg.add_theme_color(dpg.mvThemeCol_Border, cfg_c["border_black"])
                    dpg.add_theme_style(dpg.mvStyleVar_WindowPadding, 0, 0)
                    dpg.add_theme_style(dpg.mvStyleVar_ChildBorderSize, 1)
                    dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing, 0, 0)
                    dpg.add_theme_style(dpg.mvStyleVar_ChildRounding, cfg_l["rounding"])

        # Right side: Viewer quadrants (Active)
        if not dpg.does_item_exist("active_black_viewer_theme"):
            with dpg.theme(tag="active_black_viewer_theme"):
                with dpg.theme_component(dpg.mvAll):
                    dpg.add_theme_color(dpg.mvThemeCol_ChildBg, cfg_c["bg_window"])
                    v_col = self.controller.settings.data["colors"]["viewer"]
                    dpg.add_theme_color(dpg.mvThemeCol_Border, v_col)
                    dpg.add_theme_style(dpg.mvStyleVar_WindowPadding, 0, 0)
                    dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing, 0, 0)
                    dpg.add_theme_style(dpg.mvStyleVar_ChildBorderSize, 2)
                    dpg.add_theme_style(dpg.mvStyleVar_ChildRounding, cfg_l["rounding"])

        # Top menu bar theme
        if not dpg.does_item_exist("floating_menu_theme"):
            with dpg.theme(tag="floating_menu_theme"):
                with dpg.theme_component(dpg.mvAll):
                    dpg.add_theme_style(
                        dpg.mvStyleVar_FramePadding, *cfg_l["pad_frame_menu"]
                    )
                    dpg.add_theme_color(dpg.mvThemeCol_PopupBg, cfg_c["bg_menu"])
                    dpg.add_theme_color(dpg.mvThemeCol_WindowBg, cfg_c["bg_menu"])
                    dpg.add_theme_color(
                        dpg.mvThemeCol_HeaderHovered, cfg_c["bg_menu_hover"]
                    )
                    dpg.add_theme_color(
                        dpg.mvThemeCol_HeaderActive, cfg_c["bg_menu_active"]
                    )

                with dpg.theme_component(dpg.mvMenu):
                    dpg.add_theme_style(
                        dpg.mvStyleVar_WindowPadding, *cfg_l["pad_menu_popup"]
                    )
                    dpg.add_theme_style(
                        dpg.mvStyleVar_ItemSpacing, *cfg_l["space_menu_item"]
                    )

                # THE FIX: Apply MenuBarBg directly to the ChildWindow component!
                with dpg.theme_component(dpg.mvChildWindow):
                    dpg.add_theme_color(dpg.mvThemeCol_ChildBg, cfg_c["bg_menubar"])
                    dpg.add_theme_color(dpg.mvThemeCol_MenuBarBg, cfg_c["bg_menubar"])
                    dpg.add_theme_color(dpg.mvThemeCol_Border, cfg_c["transparent"])
                    dpg.add_theme_style(dpg.mvStyleVar_ChildRounding, cfg_l["rounding"])
                    dpg.add_theme_style(dpg.mvStyleVar_ChildBorderSize, 0)
                    dpg.add_theme_style(dpg.mvStyleVar_WindowPadding, 0, 0)

                with dpg.theme_component(dpg.mvMenuBar):
                    dpg.add_theme_color(dpg.mvThemeCol_MenuBarBg, cfg_c["bg_menubar"])
                    dpg.add_theme_color(dpg.mvThemeCol_Border, cfg_c["transparent"])
                    dpg.add_theme_style(dpg.mvStyleVar_WindowBorderSize, 0)

        # Left panel: Sidebar container
        if not dpg.does_item_exist("sidebar_bg_theme"):
            with dpg.theme(tag="sidebar_bg_theme"):
                with dpg.theme_component(dpg.mvChildWindow):
                    dpg.add_theme_color(dpg.mvThemeCol_ChildBg, cfg_c["bg_sidebar"])
                    dpg.add_theme_color(dpg.mvThemeCol_Border, cfg_c["border_black"])
                    dpg.add_theme_style(dpg.mvStyleVar_ChildBorderSize, 1)
                    dpg.add_theme_style(dpg.mvStyleVar_ChildRounding, cfg_l["rounding"])

        # Left panel: Info inputs (read-only)
        if not dpg.does_item_exist("sleek_readonly_theme"):
            with dpg.theme(tag="sleek_readonly_theme"):
                with dpg.theme_component(dpg.mvInputText):
                    dpg.add_theme_color(dpg.mvThemeCol_FrameBg, cfg_c["transparent"])
                    dpg.add_theme_style(dpg.mvStyleVar_FrameBorderSize, 0)
                    dpg.add_theme_style(
                        dpg.mvStyleVar_FramePadding, *cfg_l["pad_frame_readonly"]
                    )

        # Left panel: Active image list item
        if not dpg.does_item_exist("active_image_list_theme"):
            with dpg.theme(tag="active_image_list_theme"):
                with dpg.theme_component(dpg.mvText):
                    dpg.add_theme_color(dpg.mvThemeCol_Text, cfg_c["text_active"])

        # Left panel: Inner padding
        if not dpg.does_item_exist("left_panel_padding_theme"):
            with dpg.theme(tag="left_panel_padding_theme"):
                with dpg.theme_component(dpg.mvAll):
                    dpg.add_theme_style(dpg.mvStyleVar_WindowPadding, 0, 12)
                    dpg.add_theme_style(
                        dpg.mvStyleVar_FramePadding, *cfg_l["pad_frame_sidebar"]
                    )

    # ==========================================
    # 2. LAYOUT BUILDERS
    # ==========================================

    def build_main_layout(self):
        """Constructs the root window and main subdivisions."""
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
            self.build_menu_bar()

            with dpg.item_handler_registry(tag="window_resize_handler"):
                dpg.add_item_resize_handler(callback=lambda: self.on_window_resize())
            dpg.bind_item_handler_registry("PrimaryWindow", "window_resize_handler")

            self.build_sidebar()
            self.build_viewer_grid()

        # Bind Global Themes
        dpg.bind_item_theme("PrimaryWindow", "primary_black_theme")
        dpg.bind_item_theme("viewers_container", "black_viewer_theme")
        for tag in ["V1", "V2", "V3", "V4"]:
            dpg.bind_item_theme(f"win_{tag}", "black_viewer_theme")

    def build_menu_bar(self):
        """Builds the floating top menu bar."""
        cfg_l = self.ui_cfg["layout"]

        with dpg.child_window(
            tag="menu_container",
            height=cfg_l["menu_h"],
            border=False,
            menubar=True,
            no_scrollbar=True,
        ):
            with dpg.menu_bar(tag="main_menu_bar"):
                with dpg.menu(label="File"):
                    dpg.add_menu_item(
                        label="Open Image...", callback=self.on_open_file_clicked
                    )
                    dpg.add_menu_item(
                        label="Settings...",
                        callback=lambda: self.settings_window.show(),
                    )
                    dpg.add_menu_item(label="Exit", callback=self.cleanup)

                with dpg.menu(label="Window/Level"):
                    for preset_name in WL_PRESETS.keys():
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

                with dpg.menu(label="Help"):
                    dpg.add_menu_item(
                        label="Shortcuts & Controls", callback=self.show_help_window
                    )

                dpg.add_spacer(width=20)
                dpg.add_text(
                    "",
                    tag="global_status_text",
                    color=self.ui_cfg["colors"]["text_status_ok"],
                )

        dpg.bind_item_theme("menu_container", "floating_menu_theme")

    def build_sidebar(self):
        """Constructs the left side panel."""
        cfg_l = self.ui_cfg["layout"]

        with dpg.group(tag="side_panel_outer"):
            with dpg.child_window(
                width=cfg_l["side_panel_w"] - 4,
                tag="side_panel",
                no_scrollbar=True,
                no_scroll_with_mouse=True,
                border=True,
            ):
                with dpg.group(indent=cfg_l["left_inner_m"]):
                    dpg.add_spacer(height=5)
                    self.build_sidebar_top()
                    self.build_sidebar_bottom()

        # Bind Sidebar Themes
        dpg.bind_item_theme("side_panel", "sidebar_bg_theme")
        dpg.bind_item_theme("top_panel", "left_panel_padding_theme")
        dpg.bind_item_theme("bottom_panel", "left_panel_padding_theme")
        dpg.bind_item_theme("image_info_group", "sleek_readonly_theme")
        dpg.bind_item_theme("image_crosshair_group", "sleek_readonly_theme")

    def build_sidebar_top(self):
        """Builds the upper half of the sidebar containing the tabs."""
        cfg_c = self.ui_cfg["colors"]

        with dpg.child_window(
            tag="top_panel",
            height=370,
            resizable_y=True,
            border=False,
            no_scrollbar=True,
        ):
            with dpg.tab_bar(tag="sidebar_tabs"):
                with dpg.tab(label="Images"):
                    dpg.add_spacer(height=5)
                    dpg.add_text("Loaded Images", color=cfg_c["text_header"])
                    dpg.add_separator()
                    dpg.add_group(tag="image_list_container")

                self.build_tab_sync(cfg_c)
                self.build_tab_fusion(cfg_c)

    def build_tab_sync(self, cfg_c):
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
            dpg.add_text("Sync Groups", color=cfg_c["text_header"])
            dpg.add_separator()
            dpg.add_group(tag="sync_list_container")

    def build_tab_fusion(self, cfg_c):
        with dpg.tab(label="Fusion"):
            dpg.add_spacer(height=5)
            dpg.add_text("Active Overlay", color=cfg_c["text_header"])
            dpg.add_separator()

            with dpg.group(tag="image_fusion_group"):

                with dpg.group(horizontal=True):
                    dpg.add_text("Base   ")
                    dpg.add_text(
                        "-", tag="text_fusion_base_image", color=cfg_c["text_active"]
                    )

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
                with dpg.group(horizontal=True):
                    dpg.add_text("Mode   ")
                    dpg.add_combo(
                        ["Alpha", "Registration"],
                        tag="combo_overlay_mode",
                        width=-1,
                        callback=self.on_overlay_mode_changed,
                    )

    def build_sidebar_bottom(self):
        """Builds the lower half of the sidebar for Active Viewer info."""
        cfg_l = self.ui_cfg["layout"]
        cfg_c = self.ui_cfg["colors"]
        panel_w = cfg_l["side_panel_w"] - 15

        with dpg.child_window(
            tag="bottom_panel", width=panel_w, border=False, no_scrollbar=True
        ):
            dpg.add_text("Active Viewer", color=cfg_c["text_header"])
            dpg.add_separator()

            with dpg.group(tag="image_info_group"):
                self.create_labeled_field("", tag="info_name")
                self.create_labeled_field("Type", tag="info_voxel_type")
                self.create_labeled_field("Size", tag="info_size")
                self.create_labeled_field("Spacing", tag="info_spacing")
                self.create_labeled_field("Origin", tag="info_origin")
                self.create_labeled_field("Matrix", tag="info_matrix")
                self.build_window_level_controls()
                dpg.add_input_text(tag="info_memory", readonly=True, width=-1)
                dpg.add_spacer(height=5)
                self.build_visibility_controls()

            dpg.add_spacer(height=10)
            dpg.add_text("Crosshair", color=cfg_c["text_header"])
            dpg.add_separator()

            with dpg.group(tag="image_crosshair_group"):
                self.create_labeled_field("Value", tag="info_val")
                self.create_labeled_field("Voxel", tag="info_vox")
                self.create_labeled_field("Coord", tag="info_phys")
                self.create_labeled_field("ppm", tag="info_ppm")
                self.create_labeled_field("FOV", tag="info_scale")

    def create_labeled_field(self, label, tag):
        """Helper to create a labeled read-only input field."""
        dim_col = self.ui_cfg["colors"]["text_dim"]
        with dpg.group(horizontal=True):
            dpg.add_text(
                f"{label}:" if label else "", tag=f"{tag}_label", color=dim_col
            )
            dpg.add_input_text(tag=tag, readonly=True, width=-1)

    def build_window_level_controls(self):
        dim_color = self.ui_cfg["colors"]["text_dim"]
        with dpg.group(horizontal=True):
            with dpg.group(horizontal=True):
                dpg.add_text("Window", color=dim_color)
                dpg.add_input_text(
                    tag="info_window",
                    width=65,
                    on_enter=True,
                    callback=lambda: self.on_sidebar_wl_change(),
                )
            dpg.add_spacer(width=5)
            with dpg.group(horizontal=True):
                dpg.add_text("Level", color=dim_color)
                dpg.add_input_text(
                    tag="info_level",
                    width=65,
                    on_enter=True,
                    callback=lambda: self.on_sidebar_wl_change(),
                )

        with dpg.group(horizontal=True):
            dpg.add_text("Min Threshold", color=dim_color)
            dpg.add_input_text(
                tag="info_base_threshold",
                width=65,
                on_enter=True,
                callback=lambda: self.on_sidebar_wl_change(),
            )
            # dpg.add_text("(< val = black)", color=self.ui_cfg["colors"]["text_dim"])

    def build_visibility_controls(self):
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
                    dpg.add_checkbox(
                        label="Legend",
                        tag="check_legend",
                        callback=self.controller.on_visibility_toggle,
                        user_data="legend",
                        default_value=False,
                    )
                with dpg.table_row():
                    dpg.add_checkbox(
                        label="Sync W/L",
                        tag="check_sync_wl",
                        default_value=False,
                        callback=self.on_sync_wl_toggle,
                    )

    def build_viewer_grid(self):
        """Creates the 2x2 grid of slice viewers."""
        with dpg.child_window(
            tag="viewers_container",
            border=False,
            no_scrollbar=True,
            no_scroll_with_mouse=True,
        ):
            with dpg.group(horizontal=True):
                self.build_viewer_widget("V1")
                self.build_viewer_widget("V2")
            with dpg.group(horizontal=True):
                self.build_viewer_widget("V3")
                self.build_viewer_widget("V4")

    def build_viewer_widget(self, tag):
        viewer = self.controller.viewers[tag]
        with dpg.child_window(
            tag=f"win_{tag}", border=True, no_scrollbar=True, no_scroll_with_mouse=True
        ):
            with dpg.drawlist(tag=f"drawlist_{tag}", width=-1, height=-1):
                dpg.add_draw_node(tag=viewer.img_node_tag)
                dpg.draw_image(viewer.texture_tag, [0, 0], [1, 1], tag=viewer.image_tag)

                dpg.add_draw_node(tag=viewer.strips_a_tag)
                dpg.add_draw_node(tag=viewer.strips_b_tag)
                viewer.active_strips_node = viewer.strips_a_tag

                dpg.add_draw_node(tag=viewer.grid_a_tag)
                dpg.add_draw_node(tag=viewer.grid_b_tag)
                viewer.active_grid_node = viewer.grid_a_tag

                dpg.add_draw_node(tag=viewer.axis_a_tag)
                dpg.add_draw_node(tag=viewer.axis_b_tag)
                viewer.axes_nodes = [viewer.axis_a_tag, viewer.axis_b_tag]
                viewer.active_axes_idx = 0

                dpg.add_draw_node(tag=viewer.scale_bar_tag)
                dpg.add_draw_node(tag=viewer.crosshair_tag)
                dpg.add_draw_node(tag=viewer.legend_tag)

            col = self.controller.settings.data["colors"]["tracker_text"]
            dpg.add_text("", tag=viewer.tracker_tag, color=col, pos=[5, 5])

    def register_handlers(self):
        with dpg.handler_registry():
            dpg.add_mouse_wheel_handler(callback=self.on_global_scroll)
            dpg.add_mouse_drag_handler(callback=self.on_global_drag)
            dpg.add_mouse_release_handler(callback=self.on_global_release)
            dpg.add_key_press_handler(callback=self.on_key_press)
            dpg.add_mouse_click_handler(callback=self.on_global_click)

    def cleanup(self, sender=None, app_data=None, user_data=None):
        dpg.stop_dearpygui()

    # ==========================================
    # 3. UI UPDATERS / SYNC LOGIC
    # ==========================================

    def sync_sidebar_checkboxes(self):
        viewer = self.context_viewer
        if not viewer or not viewer.view_state:
            return

        vs = viewer.view_state
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
        if (
            dpg.does_item_exist("check_legend")
            and dpg.get_value("check_legend") != vs.show_legend
        ):
            dpg.set_value("check_legend", vs.show_legend)

    def refresh_image_list_ui(self):
        container = "image_list_container"
        if not dpg.does_item_exist(container):
            return

        dpg.delete_item(container, children_only=True)
        self.image_label_tags.clear()

        muted_col = self.ui_cfg["colors"]["text_muted"]
        transparent = self.ui_cfg["colors"]["transparent"]

        for vs_id, vs in self.controller.view_states.items():
            with dpg.group(parent=container):
                with dpg.group(horizontal=True):
                    if vs.sync_group > 0:
                        dpg.add_text(f"[{vs.sync_group}]", color=muted_col)
                    else:
                        dpg.add_text("   ", color=transparent)

                    lbl_id = dpg.add_text(f"{vs.volume.name}")
                    self.image_label_tags[vs_id] = lbl_id

                with dpg.group(horizontal=True):
                    dpg.add_spacer(width=10)
                    for v_tag in ["V1", "V2", "V3", "V4"]:
                        is_active = self.controller.viewers[v_tag].image_id == vs_id
                        dpg.add_checkbox(
                            label="",
                            default_value=is_active,
                            user_data={"img_id": vs_id, "v_tag": v_tag},
                            callback=self.on_image_viewer_toggle,
                        )

                    btn_reload = dpg.add_button(
                        label="\uf01e",
                        width=20,
                        callback=lambda s, a, u: self.controller.reload_image(u),
                        user_data=vs_id,
                    )
                    btn_close = dpg.add_button(
                        label="\uf00d",
                        width=20,
                        callback=lambda s, a, u: self.controller.close_image(u),
                        user_data=vs_id,
                    )

                    if dpg.does_item_exist("icon_font_tag"):
                        dpg.bind_item_font(btn_reload, "icon_font_tag")
                        dpg.bind_item_font(btn_close, "icon_font_tag")
                    if dpg.does_item_exist("delete_button_theme"):
                        dpg.bind_item_theme(btn_close, "delete_button_theme")
                    if dpg.does_item_exist("icon_button_theme"):
                        dpg.bind_item_theme(btn_reload, "icon_button_theme")

        self.refresh_sync_ui()
        if self.context_viewer and self.context_viewer.image_id:
            self.highlight_active_image_in_list(self.context_viewer.image_id)

    def highlight_active_image_in_list(self, active_img_id):
        for img_id, label_tag in self.image_label_tags.items():
            if dpg.does_item_exist(label_tag):
                if img_id == active_img_id:
                    dpg.bind_item_theme(label_tag, "active_image_list_theme")
                else:
                    dpg.bind_item_theme(label_tag, "")

        for img_id, label_tag in self.sync_label_tags.items():
            if dpg.does_item_exist(label_tag):
                if img_id == active_img_id:
                    dpg.bind_item_theme(label_tag, "active_image_list_theme")
                else:
                    dpg.bind_item_theme(label_tag, "")

    def refresh_sync_ui(self):
        container = "sync_list_container"
        if not dpg.does_item_exist(container):
            return
        dpg.delete_item(container, children_only=True)
        self.sync_label_tags.clear()  # <-- Clear the tags

        max_active_group = max(
            [vs.sync_group for vs in self.controller.view_states.values()] + [0]
        )
        num_groups = max(3, len(self.controller.view_states), max_active_group)
        combo_items = ["None"] + [f"Group {i}" for i in range(1, num_groups + 1)]

        with dpg.table(parent=container, header_row=False):
            dpg.add_table_column(label="Image")
            dpg.add_table_column(label="Group", width_fixed=True)

            for vs_id, vs in self.controller.view_states.items():
                with dpg.table_row():
                    lbl_id = dpg.add_text(vs.volume.name)
                    self.sync_label_tags[vs_id] = lbl_id  # <-- Track the label
                    dpg.add_combo(
                        items=combo_items,
                        default_value=(
                            "None" if not vs.sync_group else f"Group {vs.sync_group}"
                        ),
                        width=100,
                        user_data=vs_id,
                        callback=self.controller.on_sync_group_change,
                    )

        # Re-evaluate sidebar states (so the Sync W/L checkbox dynamically toggles on/off)
        if self.context_viewer:
            self.update_sidebar_info(self.context_viewer)

    @property
    def hovered_viewer(self):
        for viewer in self.controller.viewers.values():
            if dpg.is_item_hovered(f"win_{viewer.tag}"):
                return viewer
        return None

    def update_trackers(self):
        mode = self.controller.settings.data["interaction"].get(
            "active_viewer_mode", "hybrid"
        )
        hover_viewer = self.hovered_viewer

        # If strict hover mode is engaged, the Menu target actively follows the mouse
        if mode == "hover":
            if (
                hover_viewer
                and hover_viewer != self.context_viewer
                and not self.drag_viewer
            ):
                self.set_context_viewer(hover_viewer)

        # The green on-image text always dynamically updates for all viewers
        for viewer in self.controller.viewers.values():
            viewer.update_tracker()

            # Update the sidebar's crosshair stats for the Active Menu Target
            if self.context_viewer and not self.drag_viewer:
                # Continuously check if 'Hide Everything' is engaged to strip the active contour!
                show_xh = (
                    self.context_viewer.view_state.show_crosshair
                    if self.context_viewer.view_state
                    else False
                )
                theme = "active_black_viewer_theme" if show_xh else "black_viewer_theme"
                dpg.bind_item_theme(f"win_{self.context_viewer.tag}", theme)

                self.update_sidebar_crosshair(self.context_viewer)

    def update_sidebar_info(self, viewer):
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

        vol = viewer.volume
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

        # 1. Update Fusion tab base image name
        if dpg.does_item_exist("text_fusion_base_image"):
            dpg.set_value("text_fusion_base_image", vol.name)

            # 2. Toggle the Sync W/L checkbox (Hide if alone or Group 0)
            group = viewer.view_state.sync_group
            can_sync_wl = False
            if group != 0:
                members = sum(
                    1
                    for vs in self.controller.view_states.values()
                    if vs.sync_group == group
                )
                can_sync_wl = members > 1

            if dpg.does_item_exist("check_sync_wl"):
                # Force uncheck it if it becomes invalid, and completely hide it from the UI
                if not can_sync_wl:
                    dpg.set_value("check_sync_wl", False)
                dpg.configure_item("check_sync_wl", show=can_sync_wl)

        is_rgb = getattr(vol, "is_rgb", False)
        for t in ["info_window", "info_level", "info_base_threshold"]:
            if dpg.does_item_exist(t):
                dpg.configure_item(t, enabled=not is_rgb)
                if is_rgb:
                    dpg.set_value(t, "RGB")

        if not is_rgb:
            self.update_sidebar_window_level(viewer)

        if dpg.does_item_exist("combo_overlay_select"):
            options = ["None"]
            for vid, ovs in self.controller.view_states.items():
                if vid != viewer.image_id:
                    options.append(f"{vid}: {ovs.volume.name}")

            dpg.configure_item("combo_overlay_select", items=options)

            # Evaluate if we currently have an overlay
            current_sel = "None"
            has_overlay = False
            if viewer.view_state.overlay_id:
                has_overlay = True
                ovs_name = self.controller.view_states[
                    viewer.view_state.overlay_id
                ].volume.name
                current_sel = f"{viewer.view_state.overlay_id}: {ovs_name}"
            dpg.set_value("combo_overlay_select", current_sel)

            # Setup fusion controls
            dpg.set_value("slider_overlay_opacity", viewer.view_state.overlay_opacity)
            dpg.set_value(
                "input_overlay_threshold", viewer.view_state.overlay_threshold
            )
            if dpg.does_item_exist("combo_overlay_mode"):
                dpg.set_value("combo_overlay_mode", viewer.view_state.overlay_mode)

            # 3. Disable/Enable the controls dynamically
            dpg.configure_item("slider_overlay_opacity", enabled=has_overlay)
            dpg.configure_item("input_overlay_threshold", enabled=has_overlay)
            if dpg.does_item_exist("combo_overlay_mode"):
                dpg.configure_item("combo_overlay_mode", enabled=has_overlay)

    def update_sidebar_window_level(self, viewer):
        if not viewer or not viewer.view_state:
            return
        vol, vs = viewer.volume, viewer.view_state
        if getattr(vol, "is_rgb", False):
            return
        dpg.set_value("info_window", f"{vs.ww:g}")
        dpg.set_value("info_level", f"{vs.wl:g}")
        dpg.set_value(
            "info_base_threshold",
            # "" if vs.base_threshold <= -1e8 else f"{vs.base_threshold:g}",
            f"{vs.base_threshold:g}",
        )

    def update_sidebar_crosshair(self, viewer):
        if not viewer or not viewer.view_state:
            return
        vs, vol = viewer.view_state, viewer.volume

        if vs.crosshair_voxel is not None:
            dpg.set_value("info_vox", fmt(vs.crosshair_voxel, 1))
            dpg.set_value("info_phys", fmt(vs.crosshair_phys_coord, 1))
            val_str = (
                f"{vs.crosshair_value[0]:g} {vs.crosshair_value[1]:g} {vs.crosshair_value[2]:g}"
                if getattr(vol, "is_rgb", False)
                else f"{vs.crosshair_value:g}"
            )

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
            win_w, win_h = dpg.get_item_width(f"win_{viewer.tag}"), dpg.get_item_height(
                f"win_{viewer.tag}"
            )
            if ppm > 0 and win_w and win_h:
                dpg.set_value(
                    "info_scale",
                    f"{win_w / ppm:.0f} x {win_h / ppm:.0f} mm",
                )
            dpg.set_value("info_ppm", f"{ppm:g} px/mm")

    def set_context_viewer(self, viewer):
        """Centralized helper to switch the Active Menu/Sidebar target."""
        if self.context_viewer == viewer:
            return

        # Drop highlight from the old viewer
        if self.context_viewer:
            dpg.bind_item_theme(f"win_{self.context_viewer.tag}", "black_viewer_theme")

        self.context_viewer = viewer

        # Apply highlight and update sidebar logic for the new viewer
        if self.context_viewer:
            # FIX: Protect against empty view_state if image failed to load
            show_xh = (
                self.context_viewer.view_state.show_crosshair
                if self.context_viewer.view_state
                else False
            )
            theme = "active_black_viewer_theme" if show_xh else "black_viewer_theme"

            dpg.bind_item_theme(f"win_{self.context_viewer.tag}", theme)

            self.highlight_active_image_in_list(viewer.image_id)
            self.update_sidebar_info(viewer)
            self.update_sidebar_crosshair(viewer)

    def get_interaction_target(self):
        """Resolves which viewer receives spatial shortcuts (Keys, Scrolls)."""
        mode = self.controller.settings.data["interaction"].get(
            "active_viewer_mode", "hybrid"
        )
        if mode == "click":
            return self.context_viewer
        return self.hovered_viewer or self.context_viewer

    # ==========================================
    # 4. EVENT HANDLERS
    # ==========================================

    def on_window_resize(self):
        window_w = dpg.get_viewport_client_width()
        window_h = dpg.get_viewport_client_height()
        if not window_w or not window_h:
            return

        cfg = self.ui_cfg["layout"]
        m_t, m_l, m_r = cfg["menu_m_top"], cfg["menu_m_left"], cfg["menu_m_right"]

        if dpg.does_item_exist("menu_container"):
            dpg.set_item_pos("menu_container", [m_l, m_t])
            dpg.set_item_width("menu_container", window_w - m_l - m_r)

        panels_y = m_t + cfg["menu_h"] + cfg["menu_m_bottom"]
        l_x, l_w, l_h = (
            cfg["left_m_left"],
            cfg["side_panel_w"],
            window_h - panels_y - cfg["left_m_bottom"],
        )

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

        r_x = l_x + l_w
        avail_w = window_w - r_x - cfg["right_m_right"]
        avail_h = window_h - panels_y - cfg["right_m_bottom"]
        quad_w, quad_h = avail_w // 2, avail_h // 2

        if dpg.does_item_exist("viewers_container"):
            dpg.set_item_pos("viewers_container", [r_x, panels_y])
            dpg.set_item_width("viewers_container", quad_w * 2)
            dpg.set_item_height("viewers_container", quad_h * 2)

        for viewer in self.controller.viewers.values():
            viewer.resize(quad_w, quad_h)
            viewer.is_geometry_dirty = True  # update the legend

    def on_global_click(self, sender, app_data, user_data):
        if app_data != dpg.mvMouseButton_Left:
            return
        viewer = self.hovered_viewer
        if not viewer:
            return

        self.drag_viewer = viewer

        # Click instantly sets the Active Menu Target!
        self.set_context_viewer(viewer)

        if viewer.orientation != ViewMode.HISTOGRAM:
            if not dpg.is_key_down(dpg.mvKey_LShift) and not dpg.is_key_down(
                dpg.mvKey_LControl
            ):
                px, py = viewer.get_mouse_slice_coords(ignore_hover=True)
                if px is not None:
                    viewer.update_crosshair_data(px, py)
                    self.controller.propagate_sync(viewer.image_id)

    def on_global_scroll(self, sender, app_data, user_data):
        target = self.get_interaction_target()
        if target:
            is_ctrl = dpg.is_key_down(dpg.mvKey_LControl) or dpg.is_key_down(
                dpg.mvKey_RControl
            )
            if is_ctrl:
                target.on_zoom("in" if app_data > 0 else "out")
            else:
                target.on_scroll(int(app_data))

    def on_key_press(self, sender, app_data, user_data):
        is_cmd = dpg.is_key_down(dpg.mvKey_LWin) or dpg.is_key_down(dpg.mvKey_RWin)
        is_ctrl = dpg.is_key_down(dpg.mvKey_LControl) or dpg.is_key_down(
            dpg.mvKey_RControl
        )

        if app_data == dpg.mvKey_O and (is_ctrl or is_cmd):
            self.on_open_file_clicked()
            return

        target = self.get_interaction_target()
        if target:
            target.on_key_press(app_data)

    def on_global_drag(self, sender, app_data, user_data):
        if isinstance(app_data, int):
            return
        if self.drag_viewer:
            self.drag_viewer.on_drag(app_data)

    def on_global_release(self, sender, app_data, user_data):
        if self.drag_viewer:
            self.update_sidebar_crosshair(self.drag_viewer)
            self.update_sidebar_info(self.drag_viewer)
            self.drag_viewer.last_dx, self.drag_viewer.last_dy = 0, 0
            self.drag_viewer = None

    def on_image_viewer_toggle(self, sender, value, user_data):
        img_id, v_tag = user_data["img_id"], user_data["v_tag"]
        viewer = self.controller.viewers[v_tag]

        if not value and viewer.image_id == img_id:
            dpg.set_value(sender, True)
            return

        if value:
            viewer.set_image(img_id)
            self.update_sidebar_info(viewer)

        self.refresh_image_list_ui()

    def on_sidebar_wl_change(self):
        if not self.context_viewer or self.context_viewer.image_id is None:
            return
        try:
            new_ww = float(dpg.get_value("info_window"))
            new_wl = float(dpg.get_value("info_level"))

            thr_str = dpg.get_value("info_base_threshold")
            new_thr = float(thr_str) if thr_str.strip() else -1e9

            self.context_viewer.view_state.ww = max(1e-5, new_ww)
            self.context_viewer.view_state.wl = new_wl
            self.context_viewer.view_state.base_threshold = new_thr

            self.controller.propagate_window_level(self.context_viewer.image_id)
            # self.context_viewer.update_window_level(new_ww, new_wl)
        except ValueError:
            pass

    def on_open_file_clicked(self, sender=None, app_data=None, user_data=None):
        file_path = open_file_dialog("Open Medical Image")
        if file_path and os.path.exists(file_path):
            self.tasks.append(self.load_single_image_sequence(file_path))

    def on_wl_preset_menu_clicked(self, sender, app_data, user_data):
        viewer = self.context_viewer
        if (
            not viewer
            or not viewer.view_state
            or getattr(viewer.volume, "is_rgb", False)
        ):
            return
        viewer.view_state.apply_wl_preset(user_data)
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
        viewer = self.context_viewer
        if viewer and viewer.image_id and app_data:
            self.controller.propagate_window_level(viewer.image_id)

    def on_overlay_selected(self, sender, app_data, user_data):
        viewer = self.context_viewer
        if not viewer or not viewer.view_state:
            return

        if app_data == "None":
            viewer.view_state.set_overlay(None, None)
        else:
            target_id = app_data.split(":")[0]
            target_vol = self.controller.volumes[target_id]
            self.show_status_message(f"Resampling overlay to physical grid...")

            def _resample():
                time.sleep(0.05)
                viewer.view_state.set_overlay(target_id, target_vol)
                self.show_status_message("Overlay applied")

            threading.Thread(target=_resample, daemon=True).start()

    def on_overlay_mode_changed(self, sender, app_data, user_data):
        viewer = self.context_viewer
        if not viewer or not viewer.view_state:
            return
        viewer.view_state.overlay_mode = app_data
        viewer.view_state.overlay_cmap_name = (
            "Registration" if app_data == "Registration" else "Hot"
        )
        viewer.view_state.is_data_dirty = True

    def on_opacity_changed(self, sender, app_data, user_data):
        if self.context_viewer and self.context_viewer.view_state:
            self.context_viewer.view_state.overlay_opacity = app_data
            self.context_viewer.view_state.is_data_dirty = True

    def on_threshold_changed(self, sender, app_data, user_data):
        if self.context_viewer and self.context_viewer.view_state:
            self.context_viewer.view_state.overlay_threshold = app_data
            self.context_viewer.view_state.is_data_dirty = True

    # ==========================================
    # 5. MODALS & POPUPS
    # ==========================================

    def load_single_image_sequence(self, file_path):
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
            dpg.add_progress_bar(tag="loading_progress", width=-1, default_value=0.5)

        vp_width = max(dpg.get_viewport_client_width(), 800)
        vp_height = max(dpg.get_viewport_client_height(), 600)
        dpg.set_item_pos("loading_modal", [vp_width // 2 - 175, vp_height // 2 - 50])

        for _ in range(3):
            yield

        try:
            img_id = self.controller.load_image(file_path)
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

            # self.update_sidebar_info(target_viewer)
            self.set_context_viewer(target_viewer)
            self.refresh_image_list_ui()

            if dpg.does_item_exist("loading_modal"):
                dpg.delete_item("loading_modal")
            yield

        except Exception as e:
            if dpg.does_item_exist("loading_modal"):
                dpg.delete_item("loading_modal")
            yield
            self.show_message("File Load Error", f"Failed to load image:\n{filename}")
            while dpg.does_item_exist("generic_message_modal"):
                yield

    def show_message(self, title, message):
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
        if color is None:
            color = self.ui_cfg["colors"]["text_status_ok"]

        if dpg.does_item_exist("global_status_text"):
            dpg.set_value("global_status_text", f"[{message}]")
            dpg.configure_item("global_status_text", color=color)

        self.status_message_expire_time = time.time() + duration

    def show_help_window(self):
        window_tag = "help_window"
        if dpg.does_item_exist(window_tag):
            dpg.delete_item(window_tag)

        active_col = self.ui_cfg["colors"]["text_active"]
        ok_col = self.ui_cfg["colors"]["text_status_ok"]

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
            dpg.add_text("Mouse Controls", color=active_col)
            dpg.add_separator()
            dpg.add_text("Left Click         : Move crosshair")
            dpg.add_text("Scroll Wheel       : Change slice")
            dpg.add_text("Ctrl + Scroll      : Zoom in/out")
            dpg.add_text("Ctrl + Drag        : Pan view")
            dpg.add_text("Shift + Drag       : Adjust Window/Level (X/Y axis)")

            dpg.add_spacer(height=15)
            dpg.add_text("Keyboard Shortcuts", color=active_col)
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
                "toggle_legend": "Toggle Legend",
                "hide_all": "Show/Hide Overlays",
            }

            def format_key(key_name, k):
                if k == 517:
                    return "Page Up"
                if k == 518:
                    return "Page Down"
                return f"Ctrl + {k}" if key_name == "open_file" else str(k)

            with dpg.table(
                header_row=False, borders_innerH=True, policy=dpg.mvTable_SizingFixedFit
            ):
                dpg.add_table_column(width_fixed=True, init_width_or_weight=120)
                dpg.add_table_column(width_stretch=True)
                for key_id, desc in descriptions.items():
                    val = shortcuts.get(key_id, "N/A")
                    with dpg.table_row():
                        dpg.add_text(format_key(key_id, val), color=ok_col)
                        dpg.add_text(desc)

            dpg.add_spacer(height=15)
            with dpg.group(horizontal=True):
                dpg.add_spacer(width=200)
                dpg.add_button(
                    label="Close",
                    width=100,
                    callback=lambda: dpg.delete_item(window_tag),
                )

        vp_width = max(dpg.get_viewport_client_width(), 800)
        dpg.set_item_pos(window_tag, [vp_width - 520, 40])

    def create_boot_sequence(self, image_tasks, sync=False, link_all=False):
        if not image_tasks:
            return
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

        loaded_ids, files_processed = [], 0
        id_to_group = {}  # Tracks the specific sync group mapping

        for task in image_tasks:
            base_path = task["base"]
            filename = os.path.basename(base_path)
            sync_group = task.get("sync_group", 0)

            if dpg.does_item_exist("loading_text"):
                dpg.set_value("loading_text", f"Loading base...\n{filename}")
            if dpg.does_item_exist("loading_progress"):
                dpg.set_value("loading_progress", files_processed / total_files)
            yield

            try:
                base_id = self.controller.load_image(base_path)
                loaded_ids.append(base_id)
                id_to_group[base_id] = sync_group  # Register the group

                if task.get("base_cmap"):
                    self.controller.view_states[base_id].colormap = task["base_cmap"]
                    self.controller.view_states[base_id].is_data_dirty = True

                files_processed += 1
            except Exception as e:
                self.show_message("Load Error", f"Failed to load:\n{filename}")
                continue

            if task["fusion"]:
                fuse_path = task["fusion"]["path"]
                fuse_name = os.path.basename(fuse_path)

                if dpg.does_item_exist("loading_text"):
                    dpg.set_value("loading_text", f"Resampling overlay...\n{fuse_name}")
                if dpg.does_item_exist("loading_progress"):
                    dpg.set_value("loading_progress", files_processed / total_files)
                yield

                try:
                    fuse_id = self.controller.load_image(fuse_path)
                    loaded_ids.append(fuse_id)
                    id_to_group[fuse_id] = sync_group  # Register overlay to same group
                    files_processed += 1

                    fuse_vs = self.controller.view_states[fuse_id]
                    fuse_vs.colormap = task["fusion"]["cmap"]
                    fuse_vs.is_data_dirty = True

                    base_vs = self.controller.view_states[base_id]
                    base_vs.set_overlay(fuse_id, fuse_vs.volume)
                    base_vs.overlay_opacity = task["fusion"]["opacity"]
                    base_vs.overlay_threshold = task["fusion"]["threshold"]

                    if "mode" in task["fusion"]:
                        base_vs.overlay_mode = task["fusion"]["mode"]

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

        for img_id in loaded_ids:
            same_viewers = [
                v.tag for v in self.controller.viewers.values() if v.image_id == img_id
            ]
            if same_viewers:
                self.controller.unify_ppm(same_viewers)

        # --- SYNC ASSIGNMENT ---
        group_applied = False
        for img_id in loaded_ids:
            if sync or link_all:
                # Global sync overrides specific prefixes
                self.controller.on_sync_group_change(None, "Group 1", img_id)
                group_applied = True
            elif id_to_group.get(img_id, 0) > 0:
                # Apply the specific prefix group requested
                self.controller.on_sync_group_change(
                    None, f"Group {id_to_group[img_id]}", img_id
                )
                group_applied = True

        if group_applied:
            self.refresh_sync_ui()
        # ------------------------

        self.on_window_resize()

        # Ensure V1 is the guaranteed Active Viewer target upon loading
        self.set_context_viewer(self.controller.viewers["V1"])
        self.refresh_image_list_ui()

        if dpg.does_item_exist("loading_modal"):
            dpg.delete_item("loading_modal")
        yield

    def run(self, boot_generator=None):
        dpg.setup_dearpygui()
        dpg.show_viewport()
        dpg.set_primary_window("PrimaryWindow", True)

        for _ in range(3):
            dpg.render_dearpygui_frame()

        if boot_generator:
            for _ in boot_generator:
                dpg.render_dearpygui_frame()

        while dpg.is_dearpygui_running():
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
