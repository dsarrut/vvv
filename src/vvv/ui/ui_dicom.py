import os
import threading
import dearpygui.dearpygui as dpg
from vvv.ui.file_dialog import open_file_dialog


class DicomBrowserWindow:
    def __init__(self, controller, gui):
        self.controller = controller
        self.gui = gui
        self.window_tag = "dicom_browser_window"

        # State Persistence
        self.last_folder = os.getcwd()
        self.scanned_series = []
        self.active_series = None

        # Asynchronous State
        self.scan_progress = 0.0
        self.scan_status_text = ""
        self.scan_finished = False

    def tick(self):
        if not dpg.does_item_exist(self.window_tag) or not dpg.is_item_shown(self.window_tag):
            return

        if self.scan_finished:
            if dpg.does_item_exist(self.window_tag):
                dpg.configure_item("dicom_scan_progress", show=False)
                dpg.set_value("dicom_scan_status", f"  ({len(self.scanned_series)} found)")
                dpg.configure_item("dicom_btn_scan", enabled=True)
                self._populate_series_list()
            self.scan_finished = False
            return

        # Update progress and status text while scanning
        if dpg.does_item_exist("dicom_scan_progress"):
            dpg.set_value("dicom_scan_progress", self.scan_progress)
            dpg.set_value("dicom_scan_status", self.scan_status_text)

    def show(self):
        if dpg.does_item_exist(self.window_tag):
            dpg.focus_item(self.window_tag)
            return

        with dpg.window(
            tag=self.window_tag,
            label="DICOM Series Browser",
            width=900,
            height=700,
            no_collapse=False,
            on_close=lambda: dpg.delete_item(self.window_tag),
        ):
            dpg.add_spacer(height=5)

            # --- TOP BAR ---
            with dpg.group(horizontal=True):
                btn_dir = dpg.add_button(
                    label="\uf07c", width=30, callback=self.on_select_folder
                )
                if dpg.does_item_exist("icon_font_tag"):
                    dpg.bind_item_font(btn_dir, "icon_font_tag")

                dpg.add_input_text(
                    default_value=self.last_folder,
                    hint="Select a folder to scan...",
                    width=450,
                    tag="dicom_folder_path",
                )
                dpg.add_checkbox(
                    label="Recurse Subfolders",
                    default_value=True,
                    tag="dicom_check_recurse",
                )
                dpg.add_spacer(width=10)
                dpg.add_button(
                    label="Scan Folder",
                    width=120,
                    callback=self.on_scan_clicked,
                    tag="dicom_btn_scan",
                )

            dpg.add_separator()
            dpg.add_spacer(height=5)

            # --- SPLIT LAYOUT ---
            with dpg.group(horizontal=True):
                # Left panel: Series list
                with dpg.child_window(width=350, height=-1, border=True):
                    with dpg.group(horizontal=True):
                        dpg.add_text(
                            "Found Series",
                            color=self.gui.ui_cfg["colors"]["text_header"],
                        )
                        dpg.add_text("", tag="dicom_scan_status", color=[255, 255, 0])

                        # Progress bar hidden by default
                    dpg.add_progress_bar(
                        tag="dicom_scan_progress",
                        width=-1,
                        default_value=0.0,
                        show=False,
                    )
                    dpg.add_separator()

                    dpg.add_group(tag="dicom_series_list")

                # Right panel: Details & Action
                with dpg.child_window(width=-1, height=-1, border=False):

                    with dpg.group(horizontal=True):
                        dpg.add_text(
                            "Path:    ", color=self.gui.ui_cfg["colors"]["text_dim"]
                        )
                        dpg.add_input_text(
                            default_value="---", tag="dicom_lbl_dir", readonly=True
                        )

                    with dpg.group(horizontal=True):
                        dpg.add_text(
                            "File:    ", color=self.gui.ui_cfg["colors"]["text_dim"]
                        )
                        dpg.add_input_text(
                            default_value="---", tag="dicom_lbl_file", readonly=True
                        )
                    with dpg.group(horizontal=True):
                        dpg.add_text(
                            "Patient: ", color=self.gui.ui_cfg["colors"]["text_dim"]
                        )
                        dpg.add_text("---", tag="dicom_lbl_patient")
                        dpg.add_spacer(width=20)
                        dpg.add_text(
                            "Study: ", color=self.gui.ui_cfg["colors"]["text_dim"]
                        )
                        dpg.add_text("---", tag="dicom_lbl_study")

                    with dpg.group(horizontal=True):
                        dpg.add_text(
                            "Size:    ", color=self.gui.ui_cfg["colors"]["text_dim"]
                        )
                        dpg.add_text("---", tag="dicom_lbl_size")
                        dpg.add_spacer(width=20)
                        dpg.add_text(
                            "Spacing: ", color=self.gui.ui_cfg["colors"]["text_dim"]
                        )
                        dpg.add_text("---", tag="dicom_lbl_spacing")

                    dpg.add_spacer(height=10)
                    dpg.add_separator()
                    dpg.add_text(
                        "DICOM Metadata", color=self.gui.ui_cfg["colors"]["text_header"]
                    )

                    # Middle: Tags Table
                    with dpg.child_window(height=-45, border=True):
                        with dpg.table(
                            tag="dicom_tags_table",
                            header_row=True,
                            resizable=True,
                            borders_innerH=True,
                            borders_innerV=True,
                        ):
                            dpg.add_table_column(
                                label="Tag", width_fixed=True, init_width_or_weight=90
                            )
                            dpg.add_table_column(
                                label="Name", width_fixed=True, init_width_or_weight=150
                            )
                            dpg.add_table_column(label="Value", width_stretch=True)

                    dpg.add_spacer(height=5)
                    btn_open = dpg.add_button(
                        label="Open Series as Image",
                        width=-1,
                        height=30,
                        callback=self.on_open_clicked,
                    )
                    if dpg.does_item_exist("icon_button_theme"):
                        dpg.bind_item_theme(btn_open, "icon_button_theme")

        vp_width, vp_height = (
            dpg.get_viewport_client_width(),
            dpg.get_viewport_client_height(),
        )
        dpg.set_item_pos(
            self.window_tag,
            [max(50, vp_width // 2 - 450), max(50, vp_height // 2 - 300)],
        )

        # Re-populate state if reopened!
        if self.scanned_series:
            dpg.set_value("dicom_scan_status", f"  ({len(self.scanned_series)} found)")
            self._populate_series_list()

    def on_select_folder(self):
        folder = open_file_dialog("Select DICOM Directory", is_directory=True)
        if folder:
            self.last_folder = folder
            dpg.set_value("dicom_folder_path", folder)

    def on_scan_clicked(self):
        folder = dpg.get_value("dicom_folder_path")
        if not folder or not os.path.exists(folder):
            dpg.set_value("dicom_scan_status", "  (Invalid Path)")
            return

        self.last_folder = folder
        recurse = dpg.get_value("dicom_check_recurse")
        dpg.set_value("dicom_scan_status", "  (Scanning...)")
        dpg.configure_item("dicom_scan_progress", show=True)
        dpg.configure_item("dicom_btn_scan", enabled=False)
        dpg.delete_item("dicom_series_list", children_only=True)

        # Run scan in background so UI doesn't freeze
        threading.Thread(
            target=self._run_scan, args=(folder, recurse), daemon=True
        ).start()

    def _run_scan(self, folder, recurse):
        # Consume the generator yielded from controller.py
        for result in self.controller.file.scan_dicom_folder(folder, recursive=recurse):
            if len(result) == 2:
                pct, dirname = result
                self.scan_progress = pct
                self.scan_status_text = f"  Scanning: {dirname[:20]}..."
            elif len(result) == 3:
                _, _, self.scanned_series = result

        # Signal completion
        self.scan_finished = True

    def _populate_series_list(self):
        if not dpg.does_item_exist("dicom_series_list"):
            return
        dpg.delete_item("dicom_series_list", children_only=True)

        for idx, s in enumerate(self.scanned_series):
            label = f"[{s['modality']}] {s['series_desc']}\n  {s['date']} | {len(s['files'])} files"
            dpg.add_selectable(
                label=label,
                height=35,
                parent="dicom_series_list",
                user_data=idx,
                tag=f"dicom_sel_{idx}",
                callback=self.on_series_selected,
            )

    def on_series_selected(self, sender, app_data, user_data):
        # Deselect all others safely (Comparing Aliases and Integer IDs)
        for child in dpg.get_item_children("dicom_series_list", 1):
            if child != sender and dpg.get_item_alias(child) != sender:
                dpg.set_value(child, False)

        # Force active highlight (Essential for Keyboard arrows!)
        if dpg.does_item_exist(sender):
            dpg.set_value(sender, True)

        self.active_series = self.scanned_series[user_data]
        s = self.active_series

        dpg.set_value("dicom_lbl_patient", s["patient_name"])
        dpg.set_value("dicom_lbl_study", s["study_desc"])
        dpg.set_value("dicom_lbl_size", s["size"])
        dpg.set_value("dicom_lbl_spacing", s["spacing"])

        first_file = os.path.basename(s["files"][0]) if s["files"] else "Unknown"
        dir_path = os.path.dirname(s["files"][0]) if s["files"] else "Unknown"
        dpg.set_value("dicom_lbl_file", first_file)
        dpg.set_value("dicom_lbl_dir", dir_path)

        # --- DYNAMIC TABLE POPULATION ---
        if dpg.does_item_exist("dicom_tags_table"):
            # Delete all existing rows
            for row in dpg.get_item_children("dicom_tags_table", 1):
                dpg.delete_item(row)

            # Generate fresh rows only for tags that actually exist
            for tag, name, val in s["tags"]:
                with dpg.table_row(parent="dicom_tags_table"):
                    dpg.add_text(tag, color=[150, 255, 150])
                    dpg.add_text(name, color=self.gui.ui_cfg["colors"]["text_dim"])
                    dpg.add_text(val)

    def on_open_clicked(self):
        if not self.active_series:
            return

        # Cast the SimpleITK tuple into a standard list
        file_list = list(self.active_series["files"])

        from vvv.ui.ui_sequences import load_batch_images_sequence

        self.gui.tasks.append(
            load_batch_images_sequence(self.gui, self.controller, [file_list])
        )
        dpg.delete_item(self.window_tag)

    def move_selection(self, delta):
        """Called by the Interaction Manager to shift selection up/down via arrows."""
        if not self.scanned_series:
            return

        idx = 0
        if self.active_series:
            idx = self.scanned_series.index(self.active_series) + delta
            idx = max(0, min(len(self.scanned_series) - 1, idx))

        sender = f"dicom_sel_{idx}"
        if dpg.does_item_exist(sender):
            dpg.set_value(sender, True)
            self.on_series_selected(sender, None, idx)
            # Auto-scroll the UI so the selection never goes off-screen!
            dpg.focus_item(sender)
