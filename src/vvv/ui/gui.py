import os
import json
import time
import threading
from vvv.utils import fmt
from vvv.ui.ui_roi import RoiUI
import dearpygui.dearpygui as dpg
from vvv.config import WL_PRESETS, COLORMAPS
from vvv.ui.ui_settings import SettingsWindow
from vvv.ui.ui_dicom import DicomBrowserWindow
from vvv.ui.ui_registration import RegistrationUI
from vvv.resources import load_fonts, setup_themes
from vvv.ui.ui_interaction import InteractionManager
from vvv.ui.file_dialog import open_file_dialog, save_file_dialog
from vvv.ui.ui_theme import build_ui_config, register_dynamic_themes
from vvv.ui.ui_tabs import (
    build_tab_sync,
    build_tab_fusion,
    build_tab_rois,
    build_tab_reg,
)
from vvv.ui.ui_sequences import (
    load_single_image_sequence,
    load_batch_images_sequence,
    load_batch_rois_sequence,
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
        self._reg_debounce_timer = None

        # --- DATA BINDING DICTIONARY ---
        # Maps DPG tag -> ViewState property name
        self.bindings = {
            "check_axis": "camera.show_axis",
            "check_grid": "camera.show_grid",
            "check_tracker": "camera.show_tracker",
            "check_crosshair": "camera.show_crosshair",
            "check_legend": "camera.show_legend",
            "check_scalebar": "camera.show_scalebar",
            "info_window": "display.ww",
            "info_level": "display.wl",
            "info_base_threshold": "display.base_threshold",
            "slider_fusion_opacity": "display.overlay_opacity",
            "input_fusion_threshold": "display.overlay_threshold",
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
        self.roi_ui = RoiUI(self, self.controller)
        self.reg_ui = RegistrationUI(self, self.controller)

        # Go
        self.build_main_layout()
        self.register_handlers()

        # Force UI into the empty/disabled state on boot
        self.update_sidebar_info(None)
        self.refresh_recent_menu()

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
                with dpg.tab(label="Images", tag="tab_images"):
                    dpg.add_spacer(height=5)
                    dpg.add_text("Loaded Images", color=cfg_c["text_header"])
                    dpg.add_separator()
                    dpg.add_group(tag="image_list_container")

                build_tab_sync(self)
                build_tab_fusion(self)
                build_tab_rois(self)
                build_tab_reg(self)

    def build_sidebar_bottom(self):
        cfg_c = self.ui_cfg["colors"]

        # --- Panel 1: Active Viewer ---
        with dpg.child_window(tag="av_panel", border=False, no_scrollbar=True):
            dpg.add_text("Active Viewer", color=cfg_c["text_header"])
            dpg.add_separator()
            with dpg.group(tag="image_info_group"):
                self.create_labeled_field("", tag="info_name")

                with dpg.group(horizontal=True):
                    dpg.add_text("Path:", color=cfg_c["text_dim"])
                    btn_copy = dpg.add_button(
                        label="\uf0c5", callback=self.on_copy_path_clicked
                    )
                    if dpg.does_item_exist("icon_font_tag"):
                        dpg.bind_item_font(btn_copy, "icon_font_tag")
                    if dpg.does_item_exist("icon_button_theme"):
                        dpg.bind_item_theme(btn_copy, "icon_button_theme")
                    dpg.add_input_text(tag="info_path", readonly=True, width=-1)

                self.create_labeled_field("Type", tag="info_voxel_type")
                self.create_labeled_field("Size", tag="info_size")
                self.create_labeled_field("Spacing", tag="info_spacing")
                self.create_labeled_field("Origin", tag="info_origin")
                self.create_labeled_field("Matrix", tag="info_matrix")
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
            dpg.add_mouse_wheel_handler(callback=self.interaction.on_mouse_scroll)
            dpg.add_mouse_drag_handler(callback=self.interaction.on_mouse_drag)
            dpg.add_mouse_release_handler(callback=self.interaction.on_mouse_release)
            dpg.add_key_press_handler(callback=self.interaction.on_key_press)
            dpg.add_mouse_click_handler(callback=self.interaction.on_mouse_click)

    def cleanup(self, sender=None, app_data=None, user_data=None):
        # 1. Save auto-history for all currently open images
        if hasattr(self.controller, "history"):
            for vs_id in list(self.controller.view_states.keys()):
                self.controller.history.save_image_state(self.controller, vs_id)

        # 2. Save standard settings (like layout dimensions, etc.)
        self.controller.save_settings()

        # 3. Terminate UI
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
                        "ww",
                        "wl",
                        "base_threshold",
                    ]:
                        continue

                    formatted_val = f"{val:g}"
                    if current_ui_val != formatted_val:
                        dpg.set_value(tag, formatted_val)

                # Direct assignment for sliders, checkboxes, and combos
                else:
                    if current_ui_val != val:
                        dpg.set_value(tag, val)

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

                    is_outdated = getattr(vs.volume, "_is_outdated", False)
                    name_str = f"{vs.volume.name} *" if is_outdated else vs.volume.name

                    lbl_id = dpg.add_text(name_str)

                    # Color it warning-orange if outdated
                    cfg_c = self.ui_cfg["colors"]
                    if is_outdated:
                        dpg.configure_item(lbl_id, color=cfg_c["outdated"])

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

                    btn_save = dpg.add_button(
                        label="\uf0c7",
                        width=20,  # Floppy disk icon
                        callback=lambda s, a, u: self.on_save_image_clicked(u),
                        user_data=vs_id,
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
                        callback=lambda s, a, u: self.controller.file.close_image(u),
                        user_data=vs_id,
                    )

                    if dpg.does_item_exist("icon_font_tag"):
                        dpg.bind_item_font(btn_save, "icon_font_tag")
                        dpg.bind_item_font(btn_reload, "icon_font_tag")
                        dpg.bind_item_font(btn_close, "icon_font_tag")
                    if dpg.does_item_exist("delete_button_theme"):
                        dpg.bind_item_theme(btn_close, "delete_button_theme")
                    if dpg.does_item_exist("icon_button_theme"):
                        dpg.bind_item_theme(btn_reload, "icon_button_theme")

        self.refresh_sync_ui()
        self.refresh_recent_menu()
        if self.context_viewer and self.context_viewer.image_id:
            self.highlight_active_image_in_list(self.context_viewer.image_id)

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
                        callback=self.on_sync_group_change,
                    )

        # Re-evaluate sidebar states (so the Sync W/L checkbox dynamically toggles on/off)
        if self.context_viewer:
            self.update_sidebar_info(self.context_viewer)

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

                tokens = shlex.split(path_str[3:])
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

    def _pan_viewers_by_delta(self, vs_id, dtx, dty, dtz):
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

    def get_sync_wl_state(self):
        """Allows the backend to query the UI state without importing DearPyGui."""
        if dpg.does_item_exist("check_sync_wl"):
            return dpg.get_value("check_sync_wl")
        return False

    def update_sidebar_info(self, viewer):
        has_image = viewer is not None and viewer.image_id is not None
        has_rois = has_image and len(viewer.view_state.rois) > 0

        # Use a list of tuples to avoid boolean key collisions
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
                    "btn_roi_load",
                    "combo_roi_type",
                    "combo_roi_mode",
                    "input_roi_val",
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
                        "info_window",
                        "info_level",
                        "info_base_threshold",
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
                "text_fusion_base_image",
                "info_val",
                "info_vox",
                "info_phys",
                "info_ppm",
                "info_scale",
            ]
            for t in text_tags:
                if dpg.does_item_exist(t):
                    dpg.set_value(t, "")

            for t in ["group_fusion_checkerboard", "check_sync_wl"]:
                if dpg.does_item_exist(t):
                    dpg.configure_item(t, show=False)
            return

        vol = viewer.volume
        dpg.set_value("info_name", vol.name)
        raw_path = (
            vol.file_paths[0]
            if isinstance(vol.file_paths, list) and vol.file_paths
            else str(vol.path)
        )

        # 1. Resolve to a clean absolute path first
        abs_path = os.path.abspath(os.path.expanduser(raw_path))

        # 2. Check if it lives inside the user's home directory and replace it with ~
        home_dir = os.path.expanduser("~")
        if abs_path.startswith(home_dir):
            display_path = "~" + abs_path[len(home_dir) :]
        else:
            display_path = abs_path

        dpg.set_value("info_path", display_path)
        dpg.set_value("info_name_label", viewer.tag)
        dpg.set_value("info_voxel_type", f"{vol.pixel_type}")
        if vol.num_timepoints > 1:
            size_str = f"{vol.shape3d[2]} x {vol.shape3d[1]} x {vol.shape3d[0]} x {vol.num_timepoints}"
        else:
            size_str = f"{vol.shape3d[2]} x {vol.shape3d[1]} x {vol.shape3d[0]}"
        dpg.set_value("info_size", size_str)
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

        if dpg.does_item_exist("combo_fusion_select"):
            options = ["None"]
            for vid, ovs in self.controller.view_states.items():
                if vid != viewer.image_id:
                    options.append(f"{vid}: {ovs.volume.name}")

            dpg.configure_item("combo_fusion_select", items=options)
            dpg.configure_item("combo_fusion_select", enabled=True)

            # Evaluate if we currently have an overlay (Backend concept)
            current_sel = "None"
            has_overlay = False
            if viewer.view_state.display.overlay_id:
                has_overlay = True
                ovs_name = self.controller.view_states[
                    viewer.view_state.display.overlay_id
                ].volume.name
                current_sel = f"{viewer.view_state.display.overlay_id}: {ovs_name}"

            dpg.set_value("combo_fusion_select", current_sel)

            # Disable/Enable the controls dynamically
            is_chk = viewer.view_state.display.overlay_mode == "Checkerboard"
            dpg.configure_item(
                "slider_fusion_opacity", enabled=has_overlay and not is_chk
            )
            dpg.configure_item("input_fusion_threshold", enabled=has_overlay)
            if dpg.does_item_exist("combo_fusion_mode"):
                dpg.configure_item("combo_fusion_mode", enabled=has_overlay)

            # Show/Hide the extra row
            if dpg.does_item_exist("group_fusion_checkerboard"):
                dpg.configure_item(
                    "group_fusion_checkerboard", show=has_overlay and is_chk
                )

    def update_sidebar_crosshair(self, viewer):
        if not viewer or not viewer.view_state:
            return
        vs, vol = viewer.view_state, viewer.volume

        if vs.camera.crosshair_voxel is not None:
            if vol.num_timepoints > 1:
                dpg.set_value(
                    "info_vox",
                    f"{vs.camera.crosshair_voxel[0]:.1f} {vs.camera.crosshair_voxel[1]:.1f} "
                    f"{vs.camera.crosshair_voxel[2]:.1f} {vs.camera.crosshair_voxel[3]}",
                )
            else:
                dpg.set_value("info_vox", fmt(vs.camera.crosshair_voxel[:3], 1))

            dpg.set_value("info_phys", fmt(vs.camera.crosshair_phys_coord, 1))

            # --- THE NEW CONSOLIDATED CALL ---
            info = self.controller.get_pixel_values_at_voxel(
                viewer.image_id, vs.camera.crosshair_voxel
            )
            if info is not None:
                val = info["base_val"]
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
            # ---------------------------------

            ppm = viewer.get_pixels_per_mm()
            win_w, win_h = dpg.get_item_width(f"win_{viewer.tag}"), dpg.get_item_height(
                f"win_{viewer.tag}"
            )
            if ppm > 0 and win_w and win_h:
                dpg.set_value("info_scale", f"{win_w / ppm:.0f} x {win_h / ppm:.0f} mm")
            dpg.set_value("info_ppm", f"{round(ppm,2):g} px/mm")

    def set_context_viewer(self, viewer):
        """Centralized helper to switch the Active Menu/Sidebar target."""
        if self.context_viewer == viewer:
            return

        if self.context_viewer:
            dpg.bind_item_theme(f"win_{self.context_viewer.tag}", "black_viewer_theme")

        # Safely deselect ROI if it doesn't belong to the new image
        if getattr(self, "active_roi_id", None):
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

        for viewer in self.controller.viewers.values():
            viewer.resize(quad_w, quad_h)
            viewer.is_geometry_dirty = True

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

    def on_sync_wl_toggle(self, sender, app_data, user_data):
        viewer = self.context_viewer
        if viewer and viewer.image_id and app_data:
            self.controller.sync.propagate_window_level(viewer.image_id)

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

        self.controller.update_all_viewers_of_image(viewer.image_id)

    def on_sync_group_change(self, sender, value, user_data):
        vs_id = user_data
        vs = self.controller.view_states[vs_id]

        if value == "None":
            vs.sync_group = 0
            self.refresh_image_list_ui()
            return

        new_group_id = int(value.split(" ")[1])
        vs.sync_group = new_group_id

        master_vs_id = None
        for other_id, other_vs in self.controller.view_states.items():
            if other_id != vs_id and other_vs.sync_group == new_group_id:
                master_vs_id = other_id
                break

        group_viewer_tags = []
        for v in self.controller.viewers.values():
            if v.view_state and v.view_state.sync_group == new_group_id:
                group_viewer_tags.append(v.tag)

        if not group_viewer_tags:
            return

        self.controller.sync.propagate_ppm(group_viewer_tags)

        if master_vs_id:
            master_viewer = next(
                (
                    v
                    for v in self.controller.viewers.values()
                    if v.image_id == master_vs_id
                ),
                None,
            )
            if master_viewer:
                phys_center = master_viewer.get_center_physical_coord()
                if phys_center is not None:
                    for tag in group_viewer_tags:
                        self.controller.viewers[tag].center_on_physical_coord(
                            phys_center
                        )
            self.controller.sync.propagate_sync(master_vs_id)

        self.controller.update_all_viewers_of_image(vs_id)
        self.refresh_image_list_ui()

    def on_fusion_target_selected(self, sender, app_data, user_data):
        viewer = self.context_viewer
        if not viewer or not viewer.view_state:
            return

        if app_data == "None":
            viewer.view_state.set_overlay(None, None)
            self.update_sidebar_info(viewer)
        else:
            target_id = app_data.split(":")[0]
            target_vol = self.controller.volumes[target_id]
            self.show_status_message(f"Resampling overlay to physical grid...")

            def _resample():
                time.sleep(0.05)
                viewer.view_state.set_overlay(target_id, target_vol)
                self.show_status_message("Overlay applied")
                self.update_sidebar_info(viewer)

            threading.Thread(target=_resample, daemon=True).start()

    def on_fusion_mode_changed(self, sender, app_data, user_data):
        viewer = self.context_viewer
        if not viewer or not viewer.view_state:
            return
        viewer.view_state.display.overlay_mode = app_data
        viewer.view_state.is_data_dirty = True

        if app_data == "Registration":
            self.controller.sync.propagate_window_level(viewer.image_id)

        # Pushes the sync to other viewers and forces the UI to show/hide the checkerboard sliders
        self.controller.sync.propagate_overlay_mode(viewer.image_id)
        self.update_sidebar_info(viewer)

    def on_fusion_checkerboard_changed(self, sender, app_data, user_data):
        viewer = self.context_viewer
        if not viewer or not viewer.view_state:
            return

        if sender == "slider_fusion_chk_size":
            viewer.view_state.display.overlay_checkerboard_size = app_data
        elif sender == "check_fusion_chk_swap":
            viewer.view_state.display.overlay_checkerboard_swap = app_data

        viewer.view_state.is_data_dirty = True
        self.controller.sync.propagate_overlay_mode(viewer.image_id)

    def on_fusion_opacity_changed(self, sender, app_data, user_data):
        if self.context_viewer and self.context_viewer.view_state:
            self.context_viewer.view_state.display.overlay_opacity = app_data
            self.context_viewer.view_state.is_data_dirty = True

    def on_fusion_threshold_changed(self, sender, app_data, user_data):
        if self.context_viewer and self.context_viewer.view_state:
            self.context_viewer.view_state.display.overlay_threshold = app_data
            self.context_viewer.view_state.is_data_dirty = True

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
                try:
                    self.controller.save_image(vs_id, file_path)
                    self.show_status_message(f"Saved: {os.path.basename(file_path)}")
                except Exception as e:
                    self.show_message("Save Error", str(e))

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
            dpg.add_text("Shift + Drag       : Adjust Window/Level (X/Y axis)")

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
                if key_name == "open_file":
                    return f"Ctrl + {k}"
                if key_name == "hard_reset":
                    return f"Shift + {k}"
                return str(k)

            with dpg.table(
                header_row=False, borders_innerH=True, policy=dpg.mvTable_SizingFixedFit
            ):
                dpg.add_table_column(
                    width_fixed=True, init_width_or_weight=140
                )  # Wider for "Shift + R"
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

            self.interaction.update_trackers()
            self.sync_bound_ui()
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
