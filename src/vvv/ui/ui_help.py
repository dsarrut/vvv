import dearpygui.dearpygui as dpg


def show_help_window(gui):
    """Toggle the "Shortcuts & Controls" window."""
    window_tag = "help_window"
    if dpg.does_item_exist(window_tag):
        dpg.delete_item(window_tag)
        return

    active_col = gui.ui_cfg["colors"]["text_active"]
    ok_col = gui.ui_cfg["colors"]["text_status_ok"]

    with dpg.window(
        tag=window_tag,
        show=True,
        label="Shortcuts & Controls",
        width=520,  # Slightly wider to accommodate longer shortcut names
        height=750,  # Slightly taller for the new entry
        no_collapse=False,
        on_close=lambda: dpg.delete_item(window_tag),
    ):
        import sys

        is_mac = sys.platform == "darwin"
        cmd_name = "Cmd" if is_mac else "Ctrl"

        dpg.add_spacer(height=5)
        dpg.add_text("Mouse Controls", color=active_col)
        dpg.add_separator()
        if is_mac:
            dpg.add_text("Left Click         : Move crosshair")
            dpg.add_text("Scroll Wheel       : Change slice")
            dpg.add_text("Cmd/Ctrl + Scroll  : Zoom in/out")
            dpg.add_text("Cmd/Ctrl + L-Drag  : Pan view")
            dpg.add_text("Mid-Drag           : Pan view")
            dpg.add_text("Shift+Move / R-Drag: Adjust Window/Level")
        else:
            dpg.add_text("Left Click         : Move crosshair")
            dpg.add_text("Scroll Wheel       : Change slice")
            dpg.add_text("Ctrl + Scroll      : Zoom in/out")
            dpg.add_text("Ctrl+L-Drag / M-Drag: Pan view")
            dpg.add_text("Shift+Move / R-Drag: Adjust Window/Level")

        dpg.add_spacer(height=15)
        dpg.add_text("Keyboard Shortcuts", color=active_col)
        dpg.add_separator()

        shortcuts = gui.controller.settings.data["shortcuts"]
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
            "toggle_interp": "Toggle Pixelated Zoom (NN)",
            "toggle_grid": "Toggle Voxel Grid",
            "toggle_legend": "Toggle Legend",
            "toggle_axis": "Toggle Axis Guide",
            "toggle_scalebar": "Toggle Scalebar",
            "toggle_mip": "Toggle MIP (Max Intensity Projection)",
            "add_profile": "Add Profile Line",
            "add_landmark": "Add Landmark at Crosshair",
            "sync_all": "Sync All Viewers",
            "hide_all": "Show/Hide Overlays",
        }

        def format_key(key_name, k):
            if k == 517:
                return "Page Up"
            if k == 518:
                return "Page Down"
            if key_name == "open_file":
                return f"{cmd_name} + {k}"
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
                if not val:
                    continue

                with dpg.table_row():
                    dpg.add_text(format_key(key_id, val), color=ok_col)
                    dpg.add_text(desc)

        dpg.add_spacer(height=15)
        dpg.add_text("MIP Controls (when MIP is active)", color=active_col)
        dpg.add_separator()

        with dpg.table(header_row=False, borders_innerH=True):
            dpg.add_table_column(width_fixed=True, init_width_or_weight=140)
            dpg.add_table_column(width_stretch=True)

            mip_controls = [
                ("Left / Right", "Rotate MIP projection angle"),
                ("Up / Down", "Navigate 4D time frames"),
            ]
            for key_str, desc in mip_controls:
                with dpg.table_row():
                    dpg.add_text(key_str, color=ok_col)
                    dpg.add_text(desc)

        dpg.add_spacer(height=15)
        dpg.add_text("List & Table Navigation", color=active_col)
        dpg.add_separator()

        with dpg.table(header_row=False, borders_innerH=True):
            dpg.add_table_column(width_fixed=True, init_width_or_weight=140)
            dpg.add_table_column(width_stretch=True)

            list_controls = [
                (
                    "Up / Down",
                    "Navigate selection when hovering over ROI list or DICOM browser",
                ),
            ]
            for key_str, desc in list_controls:
                with dpg.table_row():
                    dpg.add_text(key_str, color=ok_col)
                    dpg.add_text(desc)

        dpg.add_spacer(height=15)
        dpg.add_text("Command Line Usage", color=active_col)
        dpg.add_separator()

        with dpg.table(header_row=False, borders_innerH=True):
            dpg.add_table_column(width_fixed=True, init_width_or_weight=220)
            dpg.add_table_column(width_stretch=True)

            cli_examples = [
                ("vvv image.nii", "Load a base image"),
                ("vvv ct.nii,pet.nii", "Load CT with transparent PET overlay"),
                (
                    "vvv ct.nii,pet.nii,hot,0.7",
                    "Overlay with custom colormap and opacity",
                ),
                ("vvv ct.nii + labels.nii", "Load label map ROIs on CT base image"),
                (
                    "vvv 1:ct.nii 1:pet.nii",
                    "Load and group images in spatial sync group 1",
                ),
                ("vvv 4D f1.nii f2.nii ...", "Load frames as a 4D sequence"),
            ]
            for cmd, desc in cli_examples:
                with dpg.table_row():
                    dpg.add_text(cmd, color=ok_col)
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
