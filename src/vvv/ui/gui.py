import os
import json
import time
import threading
import numpy as np
from vvv.utils import fmt
from vvv.ui.ui_roi import RoiUI
import dearpygui.dearpygui as dpg
from vvv.ui.ui_fusion import FusionUI
from vvv.config import WL_PRESETS, COLORMAPS
from vvv.ui.ui_settings import SettingsWindow
from vvv.ui.ui_dicom import DicomBrowserWindow
from vvv.ui.ui_registration import RegistrationUI
from vvv.resources import load_fonts, setup_themes
from vvv.ui.ui_interaction import InteractionManager
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
        self.ui_cfg = None

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
            "info_window": "display.ww",
            "info_level": "display.wl",
            "info_base_threshold": "display.base_threshold",
            "slider_fusion_opacity": "display.overlay_opacity",
            "combo_fusion_mode": "display.overlay_mode",
            "slider_fusion_chk_size": "display.overlay_checkerboard_size",
            "check_fusion_chk_swap": "display.overlay_checkerboard_swap",
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
        self.roi_ui = RoiUI(self, self.controller)
        self.reg_ui = RegistrationUI(self, self.controller)

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

                    dpg.add_menu_item(
                        label="Open Workspace...",
                        callback=self.on_open_workspace_clicked,
                    )
                    dpg.add_menu_item(
                        label="Save Workspace As...",
                        callback=self.on_save_workspace_clicked,
                    )

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

        # Target the two new panels instead of 'bottom_panel'
        dpg.bind_item_theme("av_panel", "left_panel_padding_theme")
        dpg.bind_item_theme("ch_panel", "left_panel_padding_theme")

        dpg.bind_item_theme("image_info_group", "sleek_readonly_theme")
        dpg.bind_item_theme("image_crosshair_group", "sleek_readonly_theme")

    def build_sidebar_top(self):
        cfg_c = self.ui_cfg["colors"]

        with dpg.child_window(
            tag="top_panel",
            border=False,
            no_scrollbar=True,
        ):
            with dpg.tab_bar(tag="sidebar_tabs", callback=self.on_tab_changed):
                build_tab_images(self)
                build_tab_sync(self)  # <--- ADD IT BACK HERE
                self.fusion_ui.build_tab_fusion(self)
                self.roi_ui.build_tab_rois(self)
                self.reg_ui.build_tab_reg(self)

    def build_sidebar_bottom(self):
        cfg_c = self.ui_cfg["colors"]

        # --- Panel 1: Active Viewer ---
        with dpg.child_window(tag="av_panel", border=False, no_scrollbar=True):
            dpg.add_text("Active Viewer", color=cfg_c["text_header"])
            dpg.add_separator()
            with dpg.group(tag="image_info_group"):
                self.create_labeled_field("", tag="info_name")

                """ with dpg.group(horizontal=True):
                    dpg.add_text("Path:", color=cfg_c["text_dim"])
                    btn_copy = dpg.add_button(
                        label="\uf0c5", callback=self.on_copy_path_clicked
                    )
                    if dpg.does_item_exist("icon_font_tag"):
                        dpg.bind_item_font(btn_copy, "icon_font_tag")
                    if dpg.does_item_exist("icon_button_theme"):
                        dpg.bind_item_theme(btn_copy, "icon_button_theme")
                    dpg.add_input_text(tag="info_path", readonly=True, width=-1)"""

                self.create_labeled_field("Type", tag="info_voxel_type")
                self.create_labeled_field("Size", tag="info_size")
                self.create_labeled_field("Spacing", tag="info_spacing")
                self.create_labeled_field("Origin", tag="info_origin")
                self.create_labeled_field("Matrix", tag="info_matrix")
                with dpg.tooltip("info_matrix"):
                    dpg.add_text("...", tag="info_matrix_tooltip")
                self.build_window_level_controls()
                dpg.add_input_text(tag="info_memory", readonly=True, width=-1)
                dpg.add_spacer(height=5)
                self.build_visibility_controls()

        # --- Panel 2: Crosshair ---
        with dpg.child_window(tag="ch_panel", border=False, no_scrollbar=True):
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

        # Sync the Fusion overlay values (For when hotkeys like 'X' are used)
        if hasattr(self, "fusion_ui"):
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
                import shlex

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
        from vvv.utils import ViewMode

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
            and viewer.view_state is not None
            and len(viewer.view_state.rois) > 0
        )
        is_rgb = getattr(viewer.volume, "is_rgb", False) if has_image else False

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
                    "btn_roi_load",
                    "combo_roi_type",
                    "combo_roi_mode",
                    "input_roi_val",
                ],
            ),
            (
                has_image
                and not is_rgb,  # Explicitly enable W/L and Threshold if not RGB!
                [
                    "info_window",
                    "info_level",
                    "info_base_threshold",
                ],
            ),
            (
                has_rois,
                ["btn_roi_show_all", "btn_roi_hide_all", "btn_roi_export_stats"],
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
                "info_path",
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

        vol = viewer.volume
        dpg.set_value("info_name", vol.name)
        raw_path = (
            vol.file_paths[0]
            if isinstance(vol.file_paths, list) and vol.file_paths
            else str(vol.path)
        )
        # with dpg.tooltip("info_name"):
        #    dpg.add_text(vol.get_human_readable_file_path())

        # 1. Resolve to a clean absolute path first
        abs_path = os.path.abspath(os.path.expanduser(raw_path))

        # 2. Check if it lives inside the user's home directory and replace it with ~
        home_dir = os.path.expanduser("~")
        if abs_path.startswith(home_dir):
            display_path = "~" + abs_path[len(home_dir) :]
        else:
            display_path = abs_path

        # dpg.set_value("info_path", display_path)
        dpg.set_value("info_name_label", viewer.tag)
        dpg.set_value("info_voxel_type", f"{vol.pixel_type}")
        if vol.num_timepoints > 1:
            size_str = f"{vol.shape3d[2]} x {vol.shape3d[1]} x {vol.shape3d[0]} x {vol.num_timepoints}"
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
            dpg.set_value("info_phys", "---")
            dpg.set_value("info_vox", "---")
            dpg.set_value("info_val", "---")
            return

        try:
            # 1. Update Voxel & Physical Coords
            if vs.camera.crosshair_voxel is not None:
                if vol.num_timepoints > 1:
                    dpg.set_value(
                        "info_vox",
                        f"{vs.camera.crosshair_voxel[0]:.1f} {vs.camera.crosshair_voxel[1]:.1f} "
                        f"{vs.camera.crosshair_voxel[2]:.1f} {vs.camera.crosshair_voxel[3]}",
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
                    val_str = (
                        f"{val[0]:g} {val[1]:g} {val[2]:g}"
                        if getattr(vol, "is_rgb", False)
                        else f"{val:g}"
                    )

                if info["overlay_val"] is not None:
                    val_str += f" ({info['overlay_val']:g})"

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
            dpg.set_value("info_phys", "---")
            dpg.set_value("info_vox", "---")
            dpg.set_value("info_val", "---")

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
            self.refresh_rois_ui()
            self.reg_ui.refresh_reg_ui()
            self.reg_ui.pull_reg_sliders_from_transform()

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

            # --- THE COMPUTED LAYOUT ENGINE ---
            hide_av = getattr(self, "_hide_av_panel", False)

            ch_h = cfg["panel_ch_h"]
            av_h = cfg["panel_av_h"]
            margin_bot = cfg["sidebar_margin_bot"]

            # DearPyGui vertically stacks items with an invisible 4px ItemSpacing gap.
            # We explicitly calculate the exact pixel height taken by everything else.
            if hide_av:
                # Sequence: Spacer(5) + Gap(4) + TopPanel(top_h) + Gap(4) + Crosshair(ch_h) + Margin(10)
                # 5 + 4 + 4 + 10 = 23 static pixels
                top_h = l_h - ch_h - margin_bot - 13
            else:
                # Sequence: Spacer(5) + Gap(4) + TopPanel(top_h) + Gap(4) + ActiveViewer(av_h) + Gap(4) + Crosshair(ch_h) + Margin(10)
                # 5 + 4 + 4 + 4 + 10 = 27 static pixels
                top_h = l_h - av_h - ch_h - margin_bot - 17

            top_h = max(100, top_h)

            if dpg.does_item_exist("top_panel"):
                dpg.set_item_width("top_panel", inner_w)
                dpg.set_item_height("top_panel", top_h)

            # We explicitly calculate the list height and set it BEFORE the frame renders!
            if dpg.does_item_exist("roi_list_window"):
                # Total Top Panel Height MINUS the Detail Panel MINUS the static text/buttons (~195px)
                list_h = top_h - cfg["roi_detail_h"] - 195
                dpg.set_item_width("roi_list_window", inner_w)
                dpg.set_item_height("roi_list_window", max(50, list_h))

            if dpg.does_item_exist("av_panel"):
                dpg.set_item_width("av_panel", inner_w)
                dpg.set_item_height("av_panel", av_h)

            if dpg.does_item_exist("ch_panel"):
                dpg.set_item_width("ch_panel", inner_w)
                dpg.set_item_height("ch_panel", ch_h)
            # ----------------------------------

        r_x = l_x + l_w
        avail_w = window_w - r_x - cfg["right_m_right"]
        avail_h = window_h - panels_y - cfg["right_m_bottom"]
        quad_w, quad_h = avail_w // 2, avail_h // 2

        if dpg.does_item_exist("viewers_container"):
            dpg.set_item_pos("viewers_container", [r_x, panels_y])
            dpg.set_item_width("viewers_container", quad_w * 2)
            dpg.set_item_height("viewers_container", quad_h * 2)

        # Only adjust the container boundaries. The Viewers will autonomously
        # detect the size change in their next tick() and recalculate their math.
        for tag in ["V1", "V2", "V3", "V4"]:
            if dpg.does_item_exist(f"win_{tag}"):
                dpg.set_item_width(f"win_{tag}", quad_w)
                dpg.set_item_height(f"win_{tag}", quad_h)

    def on_image_viewer_toggle(self, sender, value, user_data):
        img_id, v_tag = user_data["img_id"], user_data["v_tag"]

        if not value and self.controller.layout[v_tag] == img_id:
            dpg.set_value(sender, True)
            return

        if value:
            self.controller.layout[v_tag] = img_id

    def on_sidebar_wl_change(self):
        if not self.context_viewer or not self.context_viewer.view_state:
            return
        try:
            new_ww = float(dpg.get_value("info_window"))
            new_wl = float(dpg.get_value("info_level"))

            thr_str = dpg.get_value("info_base_threshold")
            new_thr = float(thr_str) if thr_str.strip() else -1e9

            self.context_viewer.view_state.display.ww = max(1e-20, new_ww)
            self.context_viewer.view_state.display.wl = new_wl
            self.context_viewer.view_state.display.base_threshold = new_thr

            self.controller.sync.propagate_window_level(self.context_viewer.image_id)
        except ValueError:
            pass

    def on_open_file_clicked(self, sender=None, app_data=None, user_data=None):
        file_paths = open_file_dialog("Open Medical Image(s)", multiple=True)
        if not file_paths:
            return

        if isinstance(file_paths, str):
            file_paths = [file_paths]

        # Route the whole list to the batch loader!
        self.tasks.append(load_batch_images_sequence(self, self.controller, file_paths))

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

    def on_wl_preset_menu_clicked(self, sender, app_data, user_data):
        viewer = self.context_viewer
        if (
            not viewer
            or not viewer.view_state
            or getattr(viewer.volume, "is_rgb", False)
        ):
            return
        viewer.view_state.apply_wl_preset(user_data)
        self.controller.sync.propagate_window_level(viewer.image_id)

    def on_colormap_menu_clicked(self, sender, app_data, user_data):
        viewer = self.context_viewer
        if (
            not viewer
            or not viewer.view_state
            or getattr(viewer.volume, "is_rgb", False)
        ):
            return
        viewer.view_state.display.colormap = user_data
        self.controller.sync.propagate_colormap(viewer.image_id)

    def on_visibility_toggle(self, sender, value, user_data):
        viewer = self.context_viewer
        if not viewer or not viewer.view_state:
            return
        vs = viewer.view_state

        if user_data == "axis":
            vs.camera.show_axis = value
        elif user_data == "grid":
            vs.camera.show_grid = value
        elif user_data == "tracker":
            vs.camera.show_tracker = value
        elif user_data == "crosshair":
            vs.camera.show_crosshair = value
        elif user_data == "scalebar":
            vs.camera.show_scalebar = value
        elif user_data == "legend":
            vs.camera.show_legend = value
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
        # app_data holds the new boolean state of the checkbox
        if "behavior" not in self.controller.settings.data:
            self.controller.settings.data["behavior"] = {}

        self.controller.settings.data["behavior"]["auto_save_history"] = app_data

    def on_save_image_clicked(self, vs_id):
        vol = self.controller.volumes[vs_id]
        file_path = save_file_dialog("Save Image As", default_name=f"{vol.name}.nii.gz")

        if file_path:
            self.show_status_message(f"Saving {vol.name}...")

            # Run in a thread so the UI doesn't freeze during heavy compression!
            def _save():
                self.controller.save_image(vs_id, file_path)
                self.controller.status_message = f"Saved: {os.path.basename(file_path)}"
                self.controller.ui_needs_refresh = True

            threading.Thread(target=_save, daemon=True).start()

    def on_copy_path_clicked(self, sender, app_data, user_data):
        path = dpg.get_value("info_path")
        if path and path != "---":
            dpg.set_clipboard_text(path)
            self.show_status_message("Path copied to clipboard!", color=[0, 255, 255])

    def on_save_workspace_clicked(self, sender=None, app_data=None, user_data=None):
        file_path = save_file_dialog("Save VVV Workspace", default_name="workspace.vvw")

        if file_path:
            # Ensure it has the correct extension
            if not file_path.endswith(".vvw"):
                file_path += ".vvw"

            self.controller.file.save_workspace(file_path)
            self.show_status_message(f"Workspace saved: {os.path.basename(file_path)}")

    def on_open_workspace_clicked(self, sender=None, app_data=None, user_data=None):
        file_path = open_file_dialog(
            "Open VVV Workspace", multiple=False, is_workspace=True
        )

        if file_path:
            # open_file_dialog returns a string when multiple=False
            self.tasks.append(load_workspace_sequence(self, self.controller, file_path))

    def on_tab_changed(self, sender, app_data, user_data):
        tab_tag = app_data
        if isinstance(app_data, int):
            tab_tag = dpg.get_item_alias(app_data) or app_data

        is_roi = tab_tag == "tab_rois"
        self._is_roi_tab_active = is_roi

        # Hide the Active Viewer panel for the ROI and Reg tabs
        hide_av = tab_tag in ["tab_rois", "tab_reg"]
        self._hide_av_panel = hide_av

        if dpg.does_item_exist("av_panel"):
            dpg.configure_item("av_panel", show=not hide_av)

        self.on_window_resize()

    def on_recent_file_clicked(self, sender, app_data, user_data):
        path = user_data

        # Route the request to the correct sequence loader based on the type
        if isinstance(path, list):
            self.tasks.append(load_batch_images_sequence(self, self.controller, [path]))
        elif isinstance(path, str) and path.startswith("4D:"):
            from vvv.ui.ui_sequences import load_single_image_sequence

            self.tasks.append(load_single_image_sequence(self, self.controller, path))
        else:
            self.tasks.append(load_batch_images_sequence(self, self.controller, [path]))

    def on_clear_recent_clicked(self, sender, app_data, user_data):
        if "behavior" not in self.controller.settings.data:
            self.controller.settings.data["behavior"] = {}
        self.controller.settings.data["behavior"]["recent_files"] = []
        self.refresh_recent_menu()

    # ==========================================
    # 5. MODALS & POPUPS
    # ==========================================

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
        return load_workspace_sequence(self, self.controller, file_path)

    def create_boot_sequence(self, image_tasks, sync=False, link_all=False):
        """Wrapper to pass the CLI boot request into the external Sequence Manager."""
        return create_boot_sequence(self, self.controller, image_tasks, sync, link_all)

    def run(self, boot_generator=None):
        dpg.setup_dearpygui()

        if not dpg.does_item_exist("global_texture_registry"):
            with dpg.texture_registry(show=False, tag="global_texture_registry"):
                pass

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

            if getattr(self.controller, "ui_needs_refresh", False):
                self.refresh_image_list_ui()
                if hasattr(self, "refresh_sync_ui"):
                    self.refresh_sync_ui()
                self.refresh_rois_ui()

                if hasattr(self, "fusion_ui"):
                    self.fusion_ui.refresh_fusion_ui()
                if hasattr(self, "reg_ui"):
                    self.reg_ui.refresh_reg_ui()

                # Safely update the sidebar between frames when the DPG stack is completely empty!
                self.update_sidebar_info(self.context_viewer)

                # Check for asynchronous status updates
                if getattr(self.controller, "status_message", None):
                    self.show_status_message(self.controller.status_message)
                    self.controller.status_message = None

                self.controller.ui_needs_refresh = False

            self.interaction.update_trackers()
            self.sync_bound_ui()

            if hasattr(self, "dicom_window") and self.dicom_window:
                self.dicom_window.tick()

            self.controller.tick()

            dpg.render_dearpygui_frame()

        # Shutdown sequence
        auto_save = self.controller.settings.data.get("behavior", {}).get(
            "auto_save_history", True
        )

        if auto_save and hasattr(self.controller, "history"):
            for vs_id in list(self.controller.view_states.keys()):
                self.controller.history.save_image_state(self.controller, vs_id)

        self.controller.save_settings()
        dpg.destroy_context()
