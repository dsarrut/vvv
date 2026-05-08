import os
import json
import shlex
import time
import threading
import collections
import numpy as np
from vvv.utils import fmt, ViewMode
from vvv.ui.ui_roi import RoiUI
import dearpygui.dearpygui as dpg
from vvv.ui.ui_fusion import FusionUI
from vvv.ui.ui_contours import ContoursUI
from vvv.ui.ui_extraction import ExtractionUI
from vvv.ui.ui_settings import SettingsWindow
from vvv.ui.ui_dicom import DicomBrowserWindow
from vvv.ui.ui_intensities import IntensitiesUI
from vvv.ui.ui_registration import RegistrationUI
from vvv.resources import load_fonts, setup_themes
from vvv.ui.ui_dvf import DvfUI
from vvv.ui.ui_interaction import InteractionManager
from vvv.ui.ui_components import build_section_title
from vvv.ui.ui_sync import build_tab_sync, refresh_sync_ui
from vvv.ui.file_dialog import open_file_dialog, save_file_dialog
from vvv.ui.ui_theme import build_ui_config, register_dynamic_themes
from vvv.ui.ui_notifications import show_message, show_status_message
from vvv.ui.ui_image_list import (
    build_tab_images,
    refresh_image_list_ui,
    highlight_active_image_in_list,
)
from vvv.ui.ui_sequences import (
    load_single_image_sequence,
    load_batch_images_sequence,
    load_workspace_sequence,
    create_boot_sequence,
)
from vvv.ui.ui_drop import install_os_drop, cleanup_os_drop
from vvv.ui.ui_workspace import build_workspace_nav_icons


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
        self.context_viewer = None
        self.last_window_size = None
        self.tasks = []
        self.status_message_expire_time = float("inf")
        self.image_label_tags = {}
        self.sync_label_tags = {}
        self.current_workspace_path: str | None = None

        # internal states
        self._is_roi_tab_active = None
        self._hide_av_panel = None

        # --- DATA BINDING DICTIONARY ---
        # Maps DPG tag -> ViewState property name
        self.bindings = {
            "check_axis": "camera.show_axis",
            "check_grid": "camera.show_grid",
            "check_tracker": "camera.show_tracker",
            "check_crosshair": "camera.show_crosshair",
            "check_legend": "camera.show_legend",
            "check_scalebar": "camera.show_scalebar",
            "check_filename": "camera.show_filename",
            "drag_ww": "display.ww",
            "drag_wl": "display.wl",
            "combo_colormap": "display.colormap",
            "slider_fusion_opacity": "display.overlay_opacity",
            "combo_fusion_mode": "display.overlay_mode",
            "slider_fusion_chk_size": "display.overlay_checkerboard_size",
            "check_fusion_chk_swap": "display.overlay_checkerboard_swap",
            "check_show_contour": "camera.show_contour",
        }

        # Initialization pipeline
        self.ui_cfg = build_ui_config(self.controller)
        self.icon_font = load_fonts()
        setup_themes()
        register_dynamic_themes(self.ui_cfg, self.controller)
        self.settings_window = SettingsWindow(self.controller)
        self.dicom_window = DicomBrowserWindow(self.controller, self)
        self.interaction = InteractionManager(self, self.controller)
        self.fusion_ui = FusionUI(self, self.controller)
        self.intensities_ui = IntensitiesUI(self, self.controller)
        self.roi_ui = RoiUI(self, self.controller)
        self.reg_ui = RegistrationUI(self, self.controller)
        self.contours_ui = ContoursUI(self, self.controller)
        self.extraction_ui = ExtractionUI(self, self.controller)
        self.dvf_ui = DvfUI(self, self.controller)

        # Go
        self.build_main_layout()
        self.register_handlers()

        # Force UI into the empty/disabled state on boot
        self.update_sidebar_info(None)
        self.refresh_recent_menu()
        self.controller.ui_needs_refresh = True

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
                        label="Open Image(s)...", callback=self.on_open_file_clicked
                    )
                    with dpg.menu(label="Open Recent...", tag="menu_recent_files"):
                        pass
                    dpg.add_menu_item(
                        label="Open DICOM Browser...",
                        callback=lambda: self.dicom_window.show(),
                    )
                    dpg.add_menu_item(
                        label="Open a 4D Sequence...",
                        callback=self.on_open_4d_sequence_clicked,
                    )

                    dpg.add_separator()

                    # Fetch the current setting state
                    auto_save = self.controller.settings.data.get("behavior", {}).get(
                        "auto_save_history", True
                    )

                    dpg.add_menu_item(
                        label="Auto-Save History on Exit",
                        check=True,
                        default_value=auto_save,
                        callback=self.on_toggle_auto_save,
                    )

                    dpg.add_separator()

                    dpg.add_menu_item(
                        label="Settings...",
                        callback=lambda: self.settings_window.show(),
                    )
                    dpg.add_menu_item(label="Exit", callback=self.cleanup)

                with dpg.menu(label="Workspace"):
                    dpg.add_menu_item(
                        label="Open Workspace...",
                        callback=self.on_open_workspace_clicked,
                    )
                    dpg.add_menu_item(
                        label="Save Workspace As...",
                        callback=self.on_save_workspace_clicked,
                    )
                    dpg.add_menu_item(
                        label="Save Workspace",
                        tag="menu_save_workspace",
                        show=False,
                        callback=self.on_save_workspace_current_clicked,
                    )

                dpg.add_spacer(width=20)
                dpg.add_text(
                    "",
                    tag="global_status_text",
                    color=self.ui_cfg["colors"]["text_status_ok"],
                )

        dpg.bind_item_theme("menu_container", "floating_menu_theme")

    def build_sidebar(self):
        """Constructs the left side panel with the new Vertical Navigation."""
        cfg_l = self.ui_cfg["layout"]
        nav_w = cfg_l["nav_panel_w"]

        with dpg.group(tag="side_panel_outer", horizontal=True, horizontal_spacing=5):
            # --- 1. The Vertical Navigation Column ---
            with dpg.child_window(
                tag="nav_panel", width=nav_w, no_scrollbar=True, border=False
            ):
                pass
            self.build_vertical_nav()

            # --- 2. The Main Tool Panel (Shifted Right) ---
            gap = cfg_l.get("sidebar_gap", 5)
            with dpg.group(tag="sidebar_right_col"):
                self.build_sidebar_top()

                dpg.add_spacer(height=gap, tag="spacer_av")
                self.build_sidebar_active_viewer()

                dpg.add_spacer(height=gap, tag="spacer_ch")
                self.build_sidebar_crosshair()

        # Themes
        dpg.bind_item_theme("sidebar_right_col", "no_spacing_theme")
        dpg.bind_item_theme("nav_panel", "nav_panel_bg_theme")
        dpg.bind_item_theme("top_panel", "sidebar_bg_theme")
        dpg.bind_item_theme("av_panel", "sidebar_bg_theme")
        dpg.bind_item_theme("ch_panel", "sidebar_bg_theme")
        dpg.bind_item_theme("image_info_group", "sleek_readonly_theme")
        dpg.bind_item_theme("image_crosshair_group", "sleek_readonly_theme")

        self.on_nav_clicked("nav_btn_tab_images", None, "tab_images")

    def build_vertical_nav(self):
        """Creates the vertical tool buttons."""
        cfg_l = self.ui_cfg["layout"]

        dpg.push_container_stack("nav_panel")

        self.nav_items = [
            ("Images", "tab_images"),
            ("Sync", "tab_sync"),
            ("Fusion", "tab_fusion"),
            ("Intensity", "tab_intensities"),
            ("ROIs", "tab_rois"),
            ("Reg", "tab_reg"),
            ("Threshold", "tab_extraction"),
            ("DVF", "tab_dvf"),
        ]

        with dpg.group(tag="nav_top_group"):
            for i, (name, tag) in enumerate(self.nav_items):
                btn = dpg.add_button(
                    label=name,
                    tag=f"nav_btn_{tag}",
                    width=-1,
                    height=cfg_l["nav_btn_h"],
                    user_data=tag,
                    callback=self.on_nav_clicked,
                )
                dpg.bind_item_theme(btn, "theme_rounded_nav")
                # Highlight the first tool by default using your existing active theme
                if i == 0 and dpg.does_item_exist("active_nav_button_theme"):
                    dpg.bind_item_theme(btn, "active_nav_button_theme")

            # Workspace icons sit inside nav_top_group so they flow naturally
            # after the last tool button (DVF) without needing absolute positioning.
            build_workspace_nav_icons(self)

        # --- System & Utility Buttons ---
        with dpg.group(tag="nav_bot_group"):
            btn_settings = dpg.add_button(
                label="\uf013",
                width=-1,
                height=cfg_l["nav_btn_h"],
                callback=lambda: self.settings_window.show(),
            )
            dpg.bind_item_theme(btn_settings, "theme_rounded_nav")
            if dpg.does_item_exist("icon_font_tag"):
                dpg.bind_item_font(btn_settings, "icon_font_tag")
            with dpg.tooltip(btn_settings):
                dpg.add_text("Settings")

            btn_help = dpg.add_button(
                label="\uf059",
                width=-1,
                height=cfg_l["nav_btn_h"],
                callback=self.show_help_window,
            )
            dpg.bind_item_theme(btn_help, "theme_rounded_nav")
            if dpg.does_item_exist("icon_font_tag"):
                dpg.bind_item_font(btn_help, "icon_font_tag")
            with dpg.tooltip(btn_help):
                dpg.add_text("Help & Shortcuts")

        dpg.pop_container_stack()

    def build_sidebar_top(self):
        """Builds the content containers without the native tab_bar."""
        cfg_l = self.ui_cfg["layout"]
        with dpg.child_window(tag="top_panel", border=True, no_scrollbar=True):
            with dpg.group(indent=cfg_l["left_inner_m"]):
                dpg.add_spacer(height=5)
                build_tab_images(self)
                build_tab_sync(self)
                self.fusion_ui.build_tab_fusion(self)
                self.intensities_ui.build_tab_intensities(self)
                self.roi_ui.build_tab_rois(self)
                self.reg_ui.build_tab_reg(self)
                self.extraction_ui.build_tab_extraction(self)
                self.dvf_ui.build_tab_dvf(self)

    def build_sidebar_active_viewer(self):
        cfg_c = self.ui_cfg["colors"]
        cfg_l = self.ui_cfg["layout"]

        # --- Panel 1: Active Viewer ---
        with dpg.child_window(tag="av_panel", border=True, no_scrollbar=True):
            with dpg.group(indent=cfg_l["left_inner_m"]):
                dpg.add_spacer(height=5)
                build_section_title("Active Viewer", cfg_c["text_header"])
                with dpg.group(tag="image_info_group"):
                    self.create_labeled_field("", tag="info_name")
                    self.create_labeled_field("Type", tag="info_voxel_type")
                    self.create_labeled_field("Size", tag="info_size")
                    self.create_labeled_field("Spacing", tag="info_spacing")
                    self.create_labeled_field("Origin", tag="info_origin")
                    self.create_labeled_field("Matrix", tag="info_matrix")
                    with dpg.tooltip("info_matrix"):
                        dpg.add_text("...", tag="info_matrix_tooltip")
                    dpg.add_input_text(tag="info_memory", readonly=True, width=-1)
                dpg.add_spacer(height=5)
                self.build_visibility_controls()

    def build_sidebar_crosshair(self):
        cfg_c = self.ui_cfg["colors"]
        cfg_l = self.ui_cfg["layout"]

        with dpg.child_window(tag="ch_panel", border=True, no_scrollbar=True):
            with dpg.group(indent=cfg_l["left_inner_m"]):
                dpg.add_spacer(height=5)
                build_section_title("Crosshair", cfg_c["text_header"])
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

    def build_visibility_controls(self):
        dim_col = self.ui_cfg["colors"]["text_dim"]
        with dpg.group(tag="visibility_controls"):
            with dpg.table(header_row=False, policy=dpg.mvTable_SizingFixedFit):
                dpg.add_table_column()
                dpg.add_table_column()
                with dpg.table_row():
                    dpg.add_checkbox(
                        label="Slice axis",
                        tag="check_axis",
                        callback=self.on_visibility_toggle,
                        user_data="axis",
                        default_value=True,
                    )
                    dpg.add_checkbox(
                        label="Pixels grid",
                        tag="check_grid",
                        callback=self.on_visibility_toggle,
                        user_data="grid",
                        default_value=False,
                    )
                with dpg.table_row():
                    dpg.add_checkbox(
                        label="Mouse tracker",
                        tag="check_tracker",
                        callback=self.on_visibility_toggle,
                        user_data="tracker",
                        default_value=True,
                    )
                    dpg.add_checkbox(
                        label="Crosshair",
                        tag="check_crosshair",
                        callback=self.on_visibility_toggle,
                        user_data="crosshair",
                        default_value=True,
                    )
                with dpg.table_row():
                    dpg.add_checkbox(
                        label="Scale bar",
                        tag="check_scalebar",
                        callback=self.on_visibility_toggle,
                        user_data="scalebar",
                        default_value=False,
                    )
                    dpg.add_checkbox(
                        label="Legend",
                        tag="check_legend",
                        callback=self.on_visibility_toggle,
                        user_data="legend",
                        default_value=False,
                    )
                with dpg.table_row():
                    with dpg.group(horizontal=True):
                        dpg.add_text("Filename:", color=dim_col)
                        dpg.add_selectable(
                            label="Off",
                            tag="check_filename",
                            callback=self.on_visibility_toggle,
                            user_data="filename",
                            width=45,
                        )
                    with dpg.group(horizontal=True):
                        dpg.add_text("Interp:", color=dim_col)
                        dpg.add_selectable(
                            label="Linear",
                            tag="check_interpolation",
                            callback=self.on_visibility_toggle,
                            user_data="interpolation",
                            width=55,
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
                with dpg.draw_node(tag=viewer.img_node_tag):
                    dpg.draw_image(
                        viewer.texture_tag, [0, 0], [1, 1], tag=viewer.image_tag
                    )

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
                dpg.add_draw_node(tag=viewer.contour_node_tag)
                dpg.add_draw_node(tag=viewer.vector_field_node_tag)

            col = self.controller.settings.data["colors"]["tracker_text"]
            dpg.add_text("", tag=viewer.tracker_tag, color=col, pos=[5, 5])

            # filename
            dpg.add_text("", tag=f"filename_text_{tag}", color=col, show=False)

    def register_handlers(self):
        with dpg.handler_registry():
            dpg.add_mouse_wheel_handler(callback=self.interaction.on_mouse_scroll)
            dpg.add_mouse_drag_handler(callback=self.interaction.on_mouse_drag)
            dpg.add_mouse_release_handler(callback=self.interaction.on_mouse_release)
            dpg.add_key_press_handler(callback=self.interaction.on_key_press)
            dpg.add_mouse_click_handler(callback=self.interaction.on_mouse_click)
            dpg.add_mouse_move_handler(callback=self.interaction.on_mouse_move)

    def cleanup(self, sender=None, app_data=None, user_data=None):
        # Terminate UI.
        # Note: History and Settings are automatically safely saved at the end of run()
        # when is_dearpygui_running() evaluates to False.
        dpg.stop_dearpygui()

    # ==========================================
    # 3. UI UPDATERS / SYNC LOGIC
    # ==========================================

    def sync_bound_ui(self):
        """Automatically pushes backend state to the UI based on the bindings dictionary."""
        viewer = self.context_viewer
        if not viewer or not viewer.view_state:
            return

        vs = viewer.view_state

        for tag, prop_name in self.bindings.items():
            if not dpg.does_item_exist(tag):
                continue

            # Safeguard: Do not overwrite text inputs if the user is currently typing in them
            if dpg.get_item_type(
                tag
            ) == "mvAppItemType::mvInputText" and dpg.is_item_focused(tag):
                continue

            if dpg.get_item_type(
                tag
            ) == "mvAppItemType::mvDragFloat" and dpg.is_item_active(tag):
                continue

            parts = prop_name.split(".")
            val = vs
            for p in parts:
                val = getattr(val, p, None)
                if val is None:
                    break

            if val is not None:
                current_ui_val = dpg.get_value(tag)

                # Format floats to clean strings for text boxes (like Window/Level)
                if isinstance(current_ui_val, str) and isinstance(val, (float, int)):
                    # Skip WW/WL if the image is RGB
                    if getattr(viewer.volume, "is_rgb", False) and prop_name in [
                        "display.ww",
                        "display.wl",
                        "display.base_threshold",
                    ]:
                        continue

                    formatted_val = f"{val:g}"
                    if current_ui_val != formatted_val:
                        dpg.set_value(tag, formatted_val)

                # Direct assignment for sliders, checkboxes, and combos
                else:
                    # TRI-STATE
                    if tag == "check_filename":
                        states = ["Off", "Short", "Full"]
                        dpg.configure_item(tag, label=states[val])
                    else:
                        # SAFEGUARD: If UI is a boolean checkbox but the value is an int, coerce to bool
                        if isinstance(current_ui_val, bool) and not isinstance(
                            val, bool
                        ):
                            val = bool(val)

                        if current_ui_val != val:
                            dpg.set_value(tag, val)

        # Sync the Fusion overlay values
        self.fusion_ui.sync_fusion_ui()

        # Sync Interpolation mode text
        if dpg.does_item_exist("check_interpolation"):
            if vs.display.use_voxel_strips:
                dpg.configure_item("check_interpolation", label="Stripe")
            elif vs.display.pixelated_zoom:
                dpg.configure_item("check_interpolation", label="NN")
            else:
                dpg.configure_item("check_interpolation", label="Linear")

    def highlight_active_image_in_list(self, active_img_id):
        highlight_active_image_in_list(self, active_img_id)

    def refresh_image_list_ui(self):
        refresh_image_list_ui(self)

    def refresh_sync_ui(self):
        refresh_sync_ui(self)

    def refresh_rois_ui(self):
        """Pass-through bridge to the delegated ROI UI."""
        self.roi_ui.refresh_rois_ui()

    def refresh_recent_menu(self):
        if not dpg.does_item_exist("menu_recent_files"):
            return

        dpg.delete_item("menu_recent_files", children_only=True)
        recent = self.controller.settings.data.get("behavior", {}).get(
            "recent_files", []
        )

        if not recent:
            dpg.add_menu_item(
                label="No recent files", parent="menu_recent_files", enabled=False
            )
            return

        for path_str in recent:
            # Safely attempt to decode DICOM lists
            try:
                path_obj = (
                    json.loads(path_str) if path_str.startswith("[") else path_str
                )
            except:
                path_obj = path_str

            # Create a clean display name
            if isinstance(path_obj, list) and len(path_obj) > 0:
                display_name = (
                    os.path.basename(os.path.dirname(path_obj[0])) + " (DICOM Series)"
                )
            elif isinstance(path_str, str) and path_str.startswith("4D:"):
                path_for_shlex = (
                    path_str[3:].replace("\\", "\\\\")
                    if os.name == "nt"
                    else path_str[3:]
                )
                tokens = shlex.split(path_for_shlex)
                display_name = (
                    "4D: " + os.path.basename(tokens[0]) + "..."
                    if tokens
                    else "4D Sequence"
                )
            else:
                display_name = os.path.basename(path_str)

            dpg.add_menu_item(
                label=display_name,
                parent="menu_recent_files",
                user_data=path_obj,
                callback=self.on_recent_file_clicked,
            )

        dpg.add_separator(parent="menu_recent_files")
        dpg.add_menu_item(
            label="Clear Recent Files",
            parent="menu_recent_files",
            callback=self.on_clear_recent_clicked,
        )

    def pan_viewers_by_delta(self, vs_id, dtx, dty, dtz):
        """Translates the 2D cameras to perfectly match the physical 3D shift."""
        for v in self.controller.viewers.values():
            if v.image_id == vs_id:
                ppm = v.get_pixels_per_mm()
                if v.orientation == ViewMode.AXIAL:
                    v.pan_offset[0] += dtx * ppm
                    v.pan_offset[1] += dty * ppm
                elif v.orientation == ViewMode.SAGITTAL:
                    v.pan_offset[0] += -dty * ppm
                    v.pan_offset[1] += -dtz * ppm
                elif v.orientation == ViewMode.CORONAL:
                    v.pan_offset[0] += dtx * ppm
                    v.pan_offset[1] += -dtz * ppm

    def update_sidebar_info(self, viewer):
        has_image = (
            viewer is not None and getattr(viewer, "view_state", None) is not None
        )
        has_rois = (
            has_image
            and viewer is not None
            and viewer.view_state is not None
            and len(viewer.view_state.rois) > 0
        )

        ui_states = [
            (
                has_image,
                [
                    "check_axis",
                    "check_grid",
                    "check_tracker",
                    "check_crosshair",
                    "check_scalebar",
                    "check_legend",
                    "check_filename",
                    "check_interpolation",
                    "check_show_contour",
                    "btn_roi_load",
                    "combo_roi_mode",
                    "input_roi_val",
                ],
            ),
            (
                has_rois,
                [
                    "btn_roi_show_all",
                    "btn_roi_contour_all",
                    "btn_roi_hide_all",
                    "btn_roi_export_stats",
                    "slider_roi_global_opacity",
                    "slider_roi_global_thickness",
                ],
            ),
            (
                False,
                (
                    [
                        "combo_fusion_select",
                        "slider_fusion_opacity",
                        "input_fusion_threshold",
                        "combo_fusion_mode",
                    ]
                    if not has_image
                    else []
                ),
            ),
        ]

        # Apply enabled/disabled states
        for state, tags in ui_states:
            for t in tags:
                if dpg.does_item_exist(t):
                    dpg.configure_item(t, enabled=state)

        # Handle early exit UI clearing
        if not has_image:
            text_tags = [
                "info_name",
                "info_size",
                "info_spacing",
                "info_origin",
                "info_memory",
                "info_voxel_type",
                "info_matrix",
                "info_val",
                "info_vox",
                "info_phys",
                "info_ppm",
                "info_scale",
            ]
            for t in text_tags:
                if dpg.does_item_exist(t):
                    dpg.set_value(t, "")

            self.fusion_ui.refresh_fusion_ui()
            return

        assert viewer is not None
        vol = viewer.volume
        dpg.set_value("info_name", vol.name)
        dpg.set_value("info_name_label", viewer.tag)
        dpg.set_value("info_voxel_type", f"{vol.pixel_type}")
        if vol.num_timepoints > 1:
            size_str = f"{vol.shape3d[2]} x {vol.shape3d[1]} x {vol.shape3d[0]} x {vol.num_timepoints}"
            if getattr(vol, "is_dvf", False):
                size_str += " (DVF)"
        else:
            size_str = f"{vol.shape3d[2]} x {vol.shape3d[1]} x {vol.shape3d[0]}"
        dpg.set_value("info_size", size_str)
        dpg.set_value("info_spacing", fmt(vol.spacing, 4))
        dpg.set_value("info_origin", fmt(vol.origin, 2))
        dpg.set_value("info_matrix", vol.matrix_display_str)
        if dpg.does_item_exist("info_matrix_tooltip"):
            dpg.set_value("info_matrix_tooltip", vol.matrix_tooltip_str)

        num_pixels = (
            vol.sitk_image.GetNumberOfPixels()
            if getattr(vol, "sitk_image", None)
            else getattr(vol.data, "size", 0)
        )
        dpg.set_value(
            "info_memory",
            f"{num_pixels:,} voxels    {vol.memory_mb:g} MB",
        )

        # 1. Update Fusion tab base image name
        self.fusion_ui.refresh_fusion_ui()

    def _reset_crosshair_info(self):
        for tag in ("info_phys", "info_vox", "info_val"):
            dpg.set_value(tag, "---")

    def update_sidebar_crosshair(self, viewer):
        if not viewer or not viewer.view_state:
            return
        vs, vol = viewer.view_state, viewer.volume
        phys = vs.camera.crosshair_phys_coord

        # Bulletproof Validation (Rule 2)
        if (
            phys is None
            or np.isscalar(phys)
            or len(np.shape(phys)) == 0
            or len(phys) < 3
        ):
            self._reset_crosshair_info()
            return

        try:
            # 1. Update Voxel & Physical Coords
            if vs.camera.crosshair_voxel is not None:
                if vol.num_timepoints > 1:
                    t_val = int(vs.camera.crosshair_voxel[3])
                    t_str = str(t_val)
                    if getattr(vol, "is_dvf", False):
                        t_str = ["dx", "dy", "dz"][t_val] if t_val < 3 else t_str
                    dpg.set_value(
                        "info_vox",
                        f"{vs.camera.crosshair_voxel[0]:.1f} {vs.camera.crosshair_voxel[1]:.1f} "
                        f"{vs.camera.crosshair_voxel[2]:.1f} {t_str}",
                    )
                else:
                    dpg.set_value("info_vox", fmt(vs.camera.crosshair_voxel[:3], 1))

            dpg.set_value("info_phys", fmt(phys, 1))

            # 2. Update Pixel Value (The Consolidated Call)
            info = self.controller.get_pixel_values_at_phys(
                viewer.image_id, phys, vs.camera.time_idx
            )

            if info is not None:
                val = info["base_val"]
                if val is None:
                    val_str = "-"
                else:
                    if getattr(vol, "is_rgb", False):
                        val_str = f"{val[0]:g} {val[1]:g} {val[2]:g}"
                    elif getattr(vol, "is_dvf", False):
                        mag = np.linalg.norm(val)
                        comps = []
                        for i, v in enumerate(val):
                            comps.append(
                                f"*{v:g}" if i == vs.camera.time_idx else f"{v:g}"
                            )
                        val_str = f"[{' '.join(comps)}] L:{mag:g}"
                    else:
                        val_str = f"{val:g}"

                if info["overlay_val"] is not None:
                    ov_val = info["overlay_val"]
                    ov_id = vs.display.overlay_id
                    ov_vol = self.controller.volumes.get(ov_id)
                    if ov_vol and getattr(ov_vol, "is_dvf", False):
                        mag = np.linalg.norm(ov_val)
                        comps = []
                        for i, v in enumerate(ov_val):
                            comps.append(
                                f"*{v:g}" if i == vs.camera.time_idx else f"{v:g}"
                            )
                        val_str += f" ([{' '.join(comps)}] L:{mag:g})"
                    elif ov_vol and getattr(ov_vol, "is_rgb", False):
                        val_str += f" ({ov_val[0]:g} {ov_val[1]:g} {ov_val[2]:g})"
                    else:
                        val_str += f" ({ov_val:g})"

                if info["rois"]:
                    val_str += f"  {', '.join(info['rois'])}"

                dpg.set_value("info_val", val_str)
            else:
                dpg.set_value("info_val", "---")

            # 3. Update FOV and PPM
            ppm = getattr(vs.camera, "target_ppm", None)
            if ppm is None:
                ppm = viewer.get_pixels_per_mm()

            win_w, win_h = dpg.get_item_width(f"win_{viewer.tag}"), dpg.get_item_height(
                f"win_{viewer.tag}"
            )

            if ppm and ppm > 0 and win_w and win_h:
                dpg.set_value("info_scale", f"{win_w / ppm:.0f} x {win_h / ppm:.0f} mm")

            if ppm is not None:
                dpg.set_value("info_ppm", f"{round(ppm, 2):g} px/mm")

        except Exception:
            # If ANY math fails during rapid mouse manipulation, safely default to "---"
            self._reset_crosshair_info()

    def set_context_viewer(self, viewer):
        """Centralized helper to switch the Active Menu/Sidebar target."""
        if self.context_viewer == viewer:
            return

        if self.context_viewer:
            dpg.bind_item_theme(f"win_{self.context_viewer.tag}", "black_viewer_theme")

        # Safely deselect ROI if it doesn't belong to the new image
        if getattr(self.roi_ui, "active_roi_id", None):
            if (
                viewer.view_state
                and self.roi_ui.active_roi_id not in viewer.view_state.rois
            ):
                self.roi_ui.active_roi_id = None

        self.context_viewer = viewer

        if self.context_viewer:
            show_xh = (
                self.context_viewer.view_state.camera.show_crosshair
                if self.context_viewer.view_state
                else False
            )
            theme = "active_black_viewer_theme" if show_xh else "black_viewer_theme"

            dpg.bind_item_theme(f"win_{self.context_viewer.tag}", theme)

            self.highlight_active_image_in_list(viewer.image_id)
            self.update_sidebar_info(viewer)
            self.update_sidebar_crosshair(viewer)
            self.reg_ui.pull_reg_sliders_from_transform()

            # Defer full panel refresh to next frame loop
            self.controller.ui_needs_refresh = True

    # ==========================================
    # 4. EVENT HANDLERS
    # ==========================================

    def on_nav_clicked(self, sender, app_data, user_data):
        """Replaces on_tab_changed. Handles hiding/showing the content groups."""
        target_tab_tag = user_data

        # 1. Update Button Highlighting & Show/Hide Content
        for name, tag in self.nav_items:
            btn_tag = f"nav_btn_{tag}"

            # Button theme
            if dpg.does_item_exist(btn_tag):
                dpg.bind_item_theme(btn_tag, "theme_rounded_nav")

            # Show the selected tool group, hide the rest
            if dpg.does_item_exist(tag):
                dpg.configure_item(tag, show=(tag == target_tab_tag))

        # Highlight the clicked button
        if dpg.does_item_exist("active_nav_button_theme"):
            dpg.bind_item_theme(sender, "active_nav_button_theme")

        # 2. Trigger the old UI layout logic
        is_roi = target_tab_tag == "tab_rois"
        self._is_roi_tab_active = is_roi

        hide_av = target_tab_tag in ["tab_rois", "tab_reg"]
        self._hide_av_panel = hide_av

        if dpg.does_item_exist("av_panel"):
            dpg.configure_item("av_panel", show=not hide_av)

        self.on_window_resize()

    def on_window_resize(self):
        try:
            window_w = dpg.get_viewport_client_width()
            window_h = dpg.get_viewport_client_height()
        except Exception:
            return

        if not window_w or not window_h:
            return

        cfg = self.ui_cfg["layout"]
        m_t, m_l, m_r = cfg["menu_m_top"], cfg["menu_m_left"], cfg["menu_m_right"]

        if dpg.does_item_exist("menu_container"):
            dpg.set_item_pos("menu_container", [m_l, m_t])
            dpg.set_item_width("menu_container", window_w - m_l - m_r)

        panels_y = m_t + cfg["menu_h"] + cfg["menu_m_bottom"]
        nav_w = cfg["nav_panel_w"]  # MUST match the width defined in build_sidebar

        l_x, l_w, l_h = (
            cfg["left_m_left"],
            cfg["side_panel_w"],
            window_h - panels_y - cfg["left_m_bottom"],
        )

        if dpg.does_item_exist("side_panel_outer"):
            dpg.set_item_pos("side_panel_outer", [l_x, panels_y])

            # --- Size the Nav Column ---
            if dpg.does_item_exist("nav_panel"):
                dpg.set_item_height("nav_panel", l_h)
                dpg.set_item_width("nav_panel", nav_w)

                if dpg.does_item_exist("nav_top_group"):
                    dpg.set_item_pos("nav_top_group", [4, 1])  # 1px perfect nudge down

                bot_h = (
                    2 * cfg["nav_btn_h"]
                ) + 8  # 2 buttons (35px) + 1 gap (8px) = 78px
                if dpg.does_item_exist("nav_bot_group"):
                    dpg.set_item_pos("nav_bot_group", [4, l_h - bot_h])

            # --- THE COMPUTED LAYOUT ENGINE ---
            hide_av = getattr(self, "_hide_av_panel", False)
            ch_h = cfg["panel_ch_h"] + 15
            av_h = cfg["panel_av_h"]
            gap = cfg.get("sidebar_gap", 5)

            # Size the Tool Column
            col_w = l_w - nav_w - 2

            if hide_av:
                if dpg.does_item_exist("av_panel"):
                    dpg.configure_item("av_panel", show=False)
                if dpg.does_item_exist("spacer_av"):
                    dpg.configure_item("spacer_av", show=False)
                top_h = l_h - ch_h - gap - 4
            else:
                if dpg.does_item_exist("av_panel"):
                    dpg.configure_item("av_panel", show=True)
                    dpg.set_item_height("av_panel", av_h)
                if dpg.does_item_exist("spacer_av"):
                    dpg.configure_item("spacer_av", show=True, height=gap)
                top_h = l_h - av_h - ch_h - (gap * 2) - (4 + 5)

            if dpg.does_item_exist("spacer_ch"):
                dpg.configure_item("spacer_ch", height=gap)

            top_h = max(100, int(top_h))

            if dpg.does_item_exist("top_panel"):
                dpg.set_item_width("top_panel", col_w)
                dpg.set_item_height("top_panel", top_h)

            if dpg.does_item_exist("av_panel"):
                dpg.set_item_width("av_panel", col_w)

            if dpg.does_item_exist("ch_panel"):
                dpg.set_item_width("ch_panel", col_w)
                dpg.set_item_height("ch_panel", ch_h)

            # Recalculate inner width for all the sliders to adapt!
            inner_w = col_w - cfg["left_inner_m"] - cfg["right_inner_m"]

            if dpg.does_item_exist("roi_list_window"):
                list_h = top_h - cfg["roi_detail_h"] - 195
                dpg.set_item_width("roi_list_window", inner_w)

        r_x = l_x + l_w + cfg["gap_center"]
        avail_w = window_w - r_x - cfg["right_m_right"]
        avail_h = window_h - panels_y - cfg["right_m_bottom"]
        quad_w, quad_h = avail_w // 2, avail_h // 2

        if dpg.does_item_exist("viewers_container"):
            dpg.set_item_pos("viewers_container", [r_x, panels_y])
            dpg.set_item_width("viewers_container", avail_w)
            dpg.set_item_height("viewers_container", avail_h)

        for i, tag in enumerate(["V1", "V2", "V3", "V4"]):
            if dpg.does_item_exist(f"win_{tag}"):
                # Distribute remainder pixels to the bottom/right viewers
                # to prevent 1px truncation gaps when the window size is odd!
                w = quad_w if i in [0, 2] else avail_w - quad_w
                h = quad_h if i in [0, 1] else avail_h - quad_h
                dpg.set_item_width(f"win_{tag}", w)
                dpg.set_item_height(f"win_{tag}", h)

    def on_image_viewer_toggle(self, sender, value, user_data):
        img_id, v_tag = user_data["img_id"], user_data["v_tag"]

        if not value and self.controller.layout[v_tag] == img_id:
            # Checkbox was already active. Keep it checked and loop orientation.
            dpg.set_value(sender, True)

            viewer = self.controller.viewers.get(v_tag)
            if viewer:
                _cycle = {
                    ViewMode.AXIAL: ViewMode.SAGITTAL,
                    ViewMode.SAGITTAL: ViewMode.CORONAL,
                    ViewMode.CORONAL: ViewMode.AXIAL,
                }
                viewer.set_orientation(_cycle.get(viewer.orientation, ViewMode.AXIAL))
            return

        if value:
            self.controller.layout[v_tag] = img_id
            self.controller.ui_needs_refresh = True

    def on_open_file_clicked(self, sender=None, app_data=None, user_data=None):
        file_paths = open_file_dialog("Open Medical Image(s)", multiple=True)
        if not file_paths:
            return

        if isinstance(file_paths, str):
            file_paths = [file_paths]

        # Route the whole list to the batch loader!
        self.tasks.append(load_batch_images_sequence(self, self.controller, file_paths))

    def on_file_drop(self, sender, app_data, user_data):
        if not app_data:
            return
        file_paths = list(app_data) if not isinstance(app_data, list) else app_data
        workspace_files = [p for p in file_paths if p.endswith(".vvw")]
        image_files = [p for p in file_paths if not p.endswith(".vvw")]
        if workspace_files:
            path = workspace_files[0]
            self.current_workspace_path = path
            self.refresh_workspace_bar()
            self.tasks.append(load_workspace_sequence(self, self.controller, path))
        if image_files:
            self.tasks.append(
                load_batch_images_sequence(self, self.controller, image_files)
            )

    def on_open_4d_sequence_clicked(self, sender=None, app_data=None, user_data=None):
        file_paths = open_file_dialog(
            "Select multiple images for 4D Sequence", multiple=True
        )
        if not file_paths:
            return

        if isinstance(file_paths, str):
            file_paths = [file_paths]

        if len(file_paths) > 0:
            # We bundle the files into the "4D:" magic string for the VolumeData parser!
            # Using quotes around each path ensures shlex handles spaces in filenames perfectly.
            magic_path_string = "4D:" + " ".join(f'"{p}"' for p in file_paths)
            self.tasks.append(
                load_single_image_sequence(self, self.controller, magic_path_string)
            )

    def on_visibility_toggle(self, sender, value, user_data):
        viewer = self.context_viewer
        if not viewer or not viewer.view_state:
            return
        vs = viewer.view_state

        if user_data in ("axis", "grid", "tracker", "crosshair", "scalebar", "legend"):
            setattr(vs.camera, f"show_{user_data}", value)
        elif user_data == "filename":
            current = getattr(vs.camera, "show_filename", 0)
            vs.camera.show_filename = (current + 1) % 3
            dpg.set_value(sender, False)
        elif user_data == "interpolation":
            if vs.display.use_voxel_strips:
                vs.display.use_voxel_strips = False
                vs.display.pixelated_zoom = False
            elif vs.display.pixelated_zoom:
                vs.display.pixelated_zoom = False
                vs.display.use_voxel_strips = True
            else:
                vs.display.pixelated_zoom = True
                vs.display.use_voxel_strips = False
            dpg.set_value(sender, False)

    def on_toggle_auto_save(self, sender, app_data, user_data):
        self.controller.settings.data.setdefault("behavior", {})[
            "auto_save_history"
        ] = app_data

    def on_save_image_clicked(self, vs_id):
        vol = self.controller.volumes[vs_id]

        start_dir = None
        if vol.file_paths and os.path.exists(vol.file_paths[0]):
            start_dir = os.path.dirname(os.path.abspath(vol.file_paths[0]))

        default_name = vol.name
        valid_exts = [
            ".nii",
            ".nii.gz",
            ".mhd",
            ".mha",
            ".nrrd",
            ".dcm",
            ".tif",
            ".png",
            ".jpg",
            ".his",
        ]
        if not any(default_name.lower().endswith(ext) for ext in valid_exts):
            default_name += ".nii.gz"

        file_path = save_file_dialog(
            "Save Image As", default_name=default_name, start_dir=start_dir
        )

        if file_path:
            self.show_status_message(f"Saving {vol.name}...")

            # Run in a thread so the UI doesn't freeze during heavy compression!
            def _save():
                self.controller.save_image(vs_id, file_path)
                self.controller.status_message = f"Saved: {os.path.basename(file_path)}"
                self.controller.ui_needs_refresh = True

            threading.Thread(target=_save, daemon=True).start()

    def on_save_workspace_clicked(self, sender=None, app_data=None, user_data=None):
        file_path = save_file_dialog("Save VVV Workspace", default_name="workspace.vvw")

        if file_path:
            # Ensure it has the correct extension
            if not file_path.endswith(".vvw"):
                file_path += ".vvw"

            self.controller.file.save_workspace(file_path)
            self.current_workspace_path = file_path
            self.refresh_workspace_bar()
            self.show_status_message(f"Workspace saved: {os.path.basename(file_path)}")

    def on_open_workspace_clicked(self, sender=None, app_data=None, user_data=None):
        file_path = open_file_dialog(
            "Open VVV Workspace", multiple=False, is_workspace=True
        )

        if isinstance(file_path, str):
            self.current_workspace_path = file_path
            self.refresh_workspace_bar()
            self.tasks.append(load_workspace_sequence(self, self.controller, file_path))

    def on_save_workspace_current_clicked(
        self, sender=None, app_data=None, user_data=None
    ):
        if self.current_workspace_path:
            self.controller.file.save_workspace(self.current_workspace_path)
            self.show_status_message(
                f"Workspace saved: {os.path.basename(self.current_workspace_path)}"
            )

    def refresh_workspace_bar(self):
        """Sync the nav-column workspace icons and the menu item with current state."""
        has_path = bool(self.current_workspace_path)

        # --- Nav: enable/disable Save icon and show current filename ---
        if dpg.does_item_exist("ws_nav_btn_save"):
            dpg.configure_item("ws_nav_btn_save", enabled=has_path)
        if dpg.does_item_exist("ws_nav_filename_text"):
            if self.current_workspace_path:
                name = os.path.splitext(os.path.basename(self.current_workspace_path))[
                    0
                ]
            else:
                name = ""
            dpg.set_value("ws_nav_filename_text", name)
            # Left align the text with 5pt spacing
            dpg.configure_item("ws_nav_filename_text", indent=5)
        if dpg.does_item_exist("ws_nav_path_tooltip"):
            dpg.set_value("ws_nav_path_tooltip", self.current_workspace_path or "")

        # --- Nav: update Save tooltip with filename + content summary ---
        if dpg.does_item_exist("ws_save_tooltip_text"):
            if self.current_workspace_path:
                name = os.path.basename(self.current_workspace_path)
                n_images = len(getattr(self.controller, "volumes", {}))
                n_rois = sum(
                    len(getattr(vs, "rois", []))
                    for vs in getattr(self.controller, "view_states", {}).values()
                )
                parts = []
                if n_images:
                    parts.append(f"{n_images} image{'s' if n_images != 1 else ''}")
                if n_rois:
                    parts.append(f"{n_rois} ROI{'s' if n_rois != 1 else ''}")
                summary = "  ·  ".join(parts) if parts else ""
                dpg.set_value(
                    "ws_save_tooltip_text", f"Save Workspace\n{name}\n{summary}"
                )
            else:
                dpg.set_value(
                    "ws_save_tooltip_text", "Save Workspace\n(no workspace open)"
                )

        # --- Menu item ---
        if dpg.does_item_exist("menu_save_workspace"):
            if self.current_workspace_path:
                display_name = os.path.basename(self.current_workspace_path)
                dpg.configure_item(
                    "menu_save_workspace",
                    show=True,
                    label=f"Save Workspace ({display_name})",
                )
            else:
                dpg.configure_item("menu_save_workspace", show=False)

    def on_recent_file_clicked(self, sender, app_data, user_data):
        path = user_data
        if isinstance(path, str) and path.startswith("4D:"):
            self.tasks.append(load_single_image_sequence(self, self.controller, path))
        else:
            self.tasks.append(load_batch_images_sequence(self, self.controller, [path]))

    def on_clear_recent_clicked(self, sender, app_data, user_data):
        self.controller.settings.data.setdefault("behavior", {})["recent_files"] = []
        self.refresh_recent_menu()

    def on_global_reset_clicked(self, sender=None, app_data=None, user_data=None):
        for vs_id in self.controller.view_states:
            self.controller.reset_image_view(vs_id, hard=False)
        self.controller.ui_needs_refresh = True

    def on_global_center_clicked(self, sender=None, app_data=None, user_data=None):
        if self.context_viewer:
            self.context_viewer.action_center_view()
        else:
            for v in self.controller.viewers.values():
                if v.image_id:
                    v.action_center_view()

    # ==========================================
    # 5. MODALS & POPUPS
    # ==========================================

    def show_message(self, title, message):
        show_message(title, message)

    def show_status_message(self, message, duration=3.0, color=None):
        show_status_message(self, message, duration, color)

    def show_help_window(self):
        window_tag = "help_window"
        if dpg.does_item_exist(window_tag):
            dpg.delete_item(window_tag)
            return

        active_col = self.ui_cfg["colors"]["text_active"]
        ok_col = self.ui_cfg["colors"]["text_status_ok"]

        with dpg.window(
            tag=window_tag,
            show=True,
            label="Shortcuts & Controls",
            width=520,  # Slightly wider to accommodate longer shortcut names
            height=600,  # Slightly taller for the new entry
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
            dpg.add_text("Shift + Move       : Adjust Window/Level (X/Y axis)")

            dpg.add_spacer(height=15)
            dpg.add_text("Keyboard Shortcuts", color=active_col)
            dpg.add_separator()

            shortcuts = self.controller.settings.data["shortcuts"]
            descriptions = {
                "open_file": "Open File(s)",
                "next_image": "Next Image in List",
                "auto_window": "Auto Window/Level (Base)",
                "auto_window_overlay": "Auto Window/Level (Overlay)",
                "scroll_up": "Scroll Slice Up",
                "scroll_down": "Scroll Slice Down",
                "fast_scroll_up": "Fast Scroll Up",
                "fast_scroll_down": "Fast Scroll Down",
                "time_backward": "Previous Time Frame (4D)",
                "time_forward": "Next Time Frame (4D)",
                "zoom_in": "Zoom In",
                "zoom_out": "Zoom Out",
                "reset_view": "Reset Zoom & Pan",
                "hard_reset": "Hard Reset (Zoom, W/L, Defaults)",
                "center_view": "Center View on Crosshair",
                "view_axial": "Axial View",
                "view_sagittal": "Sagittal View",
                "view_coronal": "Coronal View",
                "view_histogram": "Histogram View",
                "toggle_interp": "Toggle Pixelated Zoom (NN)",
                "toggle_experimental_nn": "Toggle NN Overlay Mode",
                "toggle_strips": "Toggle Voxel Strips",
                "toggle_grid": "Toggle Voxel Grid",
                "toggle_legend": "Toggle Legend",
                "hide_all": "Show/Hide Overlays",
            }

            def format_key(key_name, k):
                if k == 517:
                    return "Page Up"
                if k == 518:
                    return "Page Down"
                if key_name == "open_file":
                    return f"Ctrl + {k}"
                if key_name == "hard_reset":
                    return f"Shift + {k}"
                return str(k)

            # Removed the conflicting policy=dpg.mvTable_SizingFixedFit!
            with dpg.table(header_row=False, borders_innerH=True):
                dpg.add_table_column(width_fixed=True, init_width_or_weight=140)
                dpg.add_table_column(width_stretch=True)

                for key_id, desc in descriptions.items():
                    # Map the virtual "hard_reset" action to the physical "reset_view" key
                    lookup_key = "reset_view" if key_id == "hard_reset" else key_id
                    val = shortcuts.get(lookup_key, "N/A")

                    with dpg.table_row():
                        dpg.add_text(format_key(key_id, val), color=ok_col)
                        dpg.add_text(desc)

            dpg.add_spacer(height=15)
            with dpg.group(horizontal=True):
                dpg.add_spacer(width=210)
                dpg.add_button(
                    label="Close",
                    width=100,
                    callback=lambda: dpg.delete_item(window_tag),
                )

        vp_width = max(dpg.get_viewport_client_width(), 800)
        dpg.set_item_pos(window_tag, [vp_width - 540, 40])

    def load_workspace_sequence(self, file_path):
        """Wrapper to pass the CLI workspace request into the external Sequence Manager."""
        self.current_workspace_path = file_path
        self.refresh_workspace_bar()
        return load_workspace_sequence(self, self.controller, file_path)

    def create_boot_sequence(self, image_tasks, sync=False, link_all=False):
        """Wrapper to pass the CLI boot request into the external Sequence Manager."""
        return create_boot_sequence(self, self.controller, image_tasks, sync, link_all)

    def _refresh_all_ui_panels(self):
        """Consolidated handler to rebuild all dynamic side panels."""
        self.refresh_image_list_ui()
        self.refresh_sync_ui()
        self.refresh_rois_ui()
        self.fusion_ui.refresh_fusion_ui()
        self.reg_ui.refresh_reg_ui()
        self.intensities_ui.refresh_intensities_ui()
        self.contours_ui.refresh_contours_ui()
        self.extraction_ui.refresh_extraction_ui()
        self.dvf_ui.refresh_dvf_ui()

        # Safely update the sidebar between frames when the DPG stack is completely empty!
        self.update_sidebar_info(self.context_viewer)

    def run(self, boot_generator=None, debug=False):
        self.controller.debug_mode = debug
        dpg.setup_dearpygui()

        if not dpg.does_item_exist("global_texture_registry"):
            with dpg.texture_registry(show=False, tag="global_texture_registry"):
                pass

        dpg.show_viewport()
        dpg.set_primary_window("PrimaryWindow", True)

        # Force the initial layout calculation now that the viewport has physical dimensions!
        self.on_window_resize()

        for _ in range(3):
            dpg.render_dearpygui_frame()

        install_os_drop(self.on_file_drop)

        if boot_generator:
            for _ in boot_generator:
                dpg.render_dearpygui_frame()

        # --- DEBUG FPS + RENDER-ROUTE OVERLAY ---
        import platform as _plat
        from vvv.ui.render_strategy import GL_NEAREST_SUPPORTED, NNMode

        fps_label = fps_series = x_axis = y_axis = render_input = None
        fps_data = time_data = None
        if debug:
            fps_data = collections.deque(maxlen=600)
            time_data = collections.deque(maxlen=600)
            with dpg.window(
                label="Debug",
                tag="fps_debug_window",
                width=480,
                height=370,
                pos=[10, 30],
            ):
                fps_label = dpg.add_text("FPS: --   Avg: --   Min: --")
                # Multiline readonly input_text → user can select & copy the text
                render_input = dpg.add_input_text(
                    default_value="...",
                    multiline=True,
                    readonly=True,
                    width=-1,
                    height=120,
                    tag="debug_render_info",
                )
                with dpg.plot(
                    label="",
                    height=180,
                    width=-1,
                    no_menus=True,
                    no_title=True,
                ):
                    x_axis = dpg.add_plot_axis(
                        dpg.mvXAxis, label="Time (s)", no_gridlines=True
                    )
                    y_axis = dpg.add_plot_axis(dpg.mvYAxis, label="FPS")
                    dpg.set_axis_limits(y_axis, 0, 125)
                    fps_series = dpg.add_line_series([], [], label="FPS", parent=y_axis)

        while dpg.is_dearpygui_running():
            if debug:
                assert fps_data is not None and time_data is not None
                assert fps_label is not None and fps_series is not None
                assert x_axis is not None and render_input is not None

                delta = dpg.get_delta_time()
                t_now = dpg.get_total_time()
                if 0.0001 < delta < 5.0:
                    fps = 1.0 / delta
                    fps_data.append(fps)
                    time_data.append(t_now)
                    avg = sum(fps_data) / len(fps_data)
                    mn = min(fps_data)
                    dpg.set_value(
                        fps_label, f"FPS: {fps:.1f}   Avg: {avg:.1f}   Min: {mn:.1f}"
                    )
                    xs = list(time_data)
                    dpg.set_value(fps_series, [xs, list(fps_data)])
                    dpg.set_axis_limits(x_axis, max(0.0, t_now - 10.0), t_now + 0.2)

                # ---- render-route info (copyable text, updated every frame) ----
                _nn_labels = {
                    NNMode.HW_GL_NEAREST:     "HW GL_NEAREST",
                    NNMode.SW_DUAL_NATIVE:    "SW Dual-Native",
                    NNMode.SW_DUAL_RESAMPLED: "SW Dual-Resampled",
                    NNMode.SW_SINGLE_MERGED:  "SW Single-Merged",
                    NNMode.SW_SINGLE_NATIVE:  "SW Single-Native",
                }
                # Summarise lazy state across all viewers for a quick top-level read
                def _lazy_summary(attr):
                    vs = self.controller.viewers.values()
                    a = all(getattr(v, attr, False) for v in vs)
                    n = any(getattr(v, attr, False) for v in vs)
                    return "ALL ON" if a else ("SOME ON" if n else "OFF")
                lines = [
                    f"Platform: {_plat.system()}   GL: {'ON' if GL_NEAREST_SUPPORTED else 'OFF'}   debug: {getattr(self.controller, 'debug_mode', False)}",
                    f"Lazy-NN (E): {_lazy_summary('lazy_nn')}   Lazy-Lin (T): {_lazy_summary('lazy_lin')}",
                ]
                for vtag, viewer in self.controller.viewers.items():
                    vs = viewer.view_state
                    pix = bool(vs and vs.display.pixelated_zoom) if vs else False
                    tex = getattr(viewer, "texture_tag", "?")
                    nn_mode   = getattr(viewer, "nn_mode", None)
                    lazy_nn   = getattr(viewer, "lazy_nn", False)
                    lazy_lin  = getattr(viewer, "lazy_lin", False)
                    settled   = getattr(viewer, "_nn_settle_done", True)
                    live_s    = "" if settled else " LIVE"
                    lazy_tag  = ""
                    if lazy_lin:
                        lazy_tag = f"  [lazy-lin{live_s}]"
                    elif lazy_nn:
                        lazy_tag = f"  [lazy-nn{live_s}]"
                    if pix and nn_mode is not None:
                        mode = _nn_labels.get(nn_mode, f"mode-{nn_mode}") + lazy_tag
                    elif pix:
                        mode = "NN" + lazy_tag
                    else:
                        mode = "Bilinear"
                    lines.append(f"  {vtag}: {mode}")
                dpg.set_value(render_input, "\n".join(lines))

            if time.time() > self.status_message_expire_time:
                if dpg.does_item_exist("global_status_text"):
                    dpg.set_value("global_status_text", "")
                self.status_message_expire_time = float("inf")

            if self.tasks:
                try:
                    next(self.tasks[0])
                except StopIteration:
                    self.tasks.pop(0)

            if getattr(self.controller, "ui_needs_refresh", False):
                self._refresh_all_ui_panels()

                # Check for asynchronous status updates
                if getattr(self.controller, "status_message", None):
                    self.show_status_message(self.controller.status_message)
                    self.controller.status_message = None

                self.controller.ui_needs_refresh = False

            self.interaction.update_trackers()
            self.sync_bound_ui()

            self.dicom_window.tick()

            self.controller.tick()

            dpg.render_dearpygui_frame()

        # Shutdown sequence
        cleanup_os_drop()  # null GLFW drop callback before DPG destroys the window

        auto_save = self.controller.settings.data.get("behavior", {}).get(
            "auto_save_history", True
        )

        if auto_save and hasattr(self.controller, "history"):
            for vs_id in list(self.controller.view_states.keys()):
                self.controller.history.save_image_state(self.controller, vs_id)

        self.controller.save_settings()
        dpg.destroy_context()
