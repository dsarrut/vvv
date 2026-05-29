import os
import threading
from typing import Optional
import dearpygui.dearpygui as dpg
from vvv.plugins.plugin_api import PluginAPI, PluginTagMixin
from vvv.ui.file_dialog import open_file_dialog
from vvv.ui.ui_notifications import show_message


class DicomPluginUI(PluginTagMixin):
    def __init__(self, plugin_id: str, controller):
        self._plugin_id = plugin_id
        self._c = controller
        self.window_tag = self._t("window")
        self.api: Optional[PluginAPI] = None

        # State Persistence
        self.last_folder = os.getcwd()
        self.scanned_series = []
        self.active_series = None
        self.active_idx = -1

        # Asynchronous State
        self.scan_progress = 0.0
        self.scan_status_text = ""
        self.scan_finished = False
        self.scan_errors: list[str] = []
        self._stop_event = threading.Event()

    def create_ui(self, parent, api) -> None:
        self.api = api

    def tick(self) -> None:
        if not dpg.does_item_exist(self.window_tag) or not dpg.is_item_shown(self.window_tag):
            return

        if self.scan_finished:
            if dpg.does_item_exist(self.window_tag):
                dpg.configure_item(self._t("scan_progress"), show=False)
                status = f"  ({len(self.scanned_series)} found)"
                if self.scan_errors:
                    status += f", {len(self.scan_errors)} dir(s) failed"
                dpg.set_value(self._t("scan_status"), status)
                dpg.configure_item(self._t("btn_scan"), enabled=True)
                self._populate_series_list()
                if self.scan_errors:
                    show_message(
                        "DICOM Scan Warnings",
                        "Some directories could not be scanned:\n\n" + "\n".join(self.scan_errors),
                    )
            self.scan_finished = False
            return

        # Update progress and status text while scanning
        if dpg.does_item_exist(self._t("scan_progress")):
            dpg.set_value(self._t("scan_progress"), self.scan_progress)
            dpg.set_value(self._t("scan_status"), self.scan_status_text)

    def show_window(self) -> None:
        if dpg.does_item_exist(self.window_tag):
            dpg.focus_item(self.window_tag)
            return

        assert self.api is not None
        cfg_c = self.api.get_ui_config()["colors"]

        with dpg.window(
            tag=self.window_tag,
            label="DICOM Series Browser (Plugin)",
            width=900,
            height=700,
            no_collapse=False,
            on_close=lambda: dpg.delete_item(self.window_tag),
        ):
            dpg.add_spacer(height=5)

            # --- TOP BAR ---
            with dpg.group(horizontal=True):
                btn_dir = dpg.add_button(
                    label="\uf07c", width=30, callback=self.on_select_folder, tag=self._t("btn_select_dir")
                )
                if dpg.does_item_exist("icon_font_tag"):
                    dpg.bind_item_font(btn_dir, "icon_font_tag")

                dpg.add_input_text(
                    default_value=self.last_folder,
                    hint="Select a folder to scan...",
                    width=450,
                    tag=self._t("folder_path"),
                )
                dpg.add_checkbox(
                    label="Recurse Subfolders",
                    default_value=True,
                    tag=self._t("check_recurse"),
                )
                from vvv.ui.ui_components import build_beginner_tooltip
                build_beginner_tooltip(self._t("check_recurse"), "Scan all nested directories inside the selected directory.", self.api)
                dpg.add_spacer(width=10)
                dpg.add_button(
                    label="Scan Folder",
                    width=120,
                    callback=self.on_scan_clicked,
                    tag=self._t("btn_scan"),
                )

            dpg.add_separator()
            dpg.add_spacer(height=5)

            # --- SPLIT LAYOUT ---
            with dpg.group(horizontal=True):
                # Left panel: Series list
                with dpg.child_window(width=350, height=-1, border=True, tag=self._t("list_panel")):
                    with dpg.group(horizontal=True):
                        dpg.add_text(
                            "Found Series",
                            color=cfg_c["text_header"],
                        )
                        dpg.add_text("", tag=self._t("scan_status"), color=[255, 255, 0])

                    # Progress bar hidden by default
                    dpg.add_progress_bar(
                        tag=self._t("scan_progress"),
                        width=-1,
                        default_value=0.0,
                        show=False,
                    )
                    dpg.add_separator()

                    dpg.add_group(tag=self._t("series_list"))

                # Right panel: Details & Action
                with dpg.child_window(width=-1, height=-1, border=False, tag=self._t("details_panel")):

                    with dpg.group(horizontal=True):
                        dpg.add_text(
                            "Path:    ", color=cfg_c["text_dim"]
                        )
                        dpg.add_input_text(
                            default_value="---", tag=self._t("lbl_dir"), readonly=True
                        )

                    with dpg.group(horizontal=True):
                        dpg.add_text(
                            "File:    ", color=cfg_c["text_dim"]
                        )
                        dpg.add_input_text(
                            default_value="---", tag=self._t("lbl_file"), readonly=True
                        )
                    with dpg.group(horizontal=True):
                        dpg.add_text(
                            "Patient: ", color=cfg_c["text_dim"]
                        )
                        dpg.add_text("---", tag=self._t("lbl_patient"))
                        dpg.add_spacer(width=20)
                        dpg.add_text(
                            "Study: ", color=cfg_c["text_dim"]
                        )
                        dpg.add_text("---", tag=self._t("lbl_study"))

                    with dpg.group(horizontal=True):
                        dpg.add_text(
                            "Size:    ", color=cfg_c["text_dim"]
                        )
                        dpg.add_text("---", tag=self._t("lbl_size"))
                        dpg.add_spacer(width=20)
                        dpg.add_text(
                            "Spacing: ", color=cfg_c["text_dim"]
                        )
                        dpg.add_text("---", tag=self._t("lbl_spacing"))

                    dpg.add_spacer(height=10, tag=self._t("metadata_spacer"))
                    dpg.add_separator(tag=self._t("metadata_sep"))
                    dpg.add_text(
                        "DICOM Metadata", color=cfg_c["text_header"], tag=self._t("metadata_header")
                    )

                    # Middle: Tags Table
                    with dpg.child_window(height=-45, border=True, tag=self._t("table_panel")):
                        with dpg.table(
                            tag=self._t("tags_table"),
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
                        tag=self._t("btn_open")
                    )
                    from vvv.ui.ui_components import build_beginner_tooltip
                    build_beginner_tooltip(btn_open, "Load the selected DICOM series files as a 3D volume.", self.api)
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

        assert self.api is not None

        # Re-populate state if reopened!
        if self.scanned_series:
            dpg.set_value(self._t("scan_status"), f"  ({len(self.scanned_series)} found)")
            self._populate_series_list()

    def on_select_folder(self) -> None:
        folder = open_file_dialog("Select DICOM Directory", is_directory=True)
        if folder:
            self.last_folder = folder
            dpg.set_value(self._t("folder_path"), folder)

    def on_scan_clicked(self) -> None:
        folder = dpg.get_value(self._t("folder_path"))
        if not folder or not os.path.exists(folder):
            dpg.set_value(self._t("scan_status"), "  (Invalid Path)")
            return

        self.last_folder = folder
        self.scanned_series = []
        self.active_series = None
        self.active_idx = -1
        recurse = dpg.get_value(self._t("check_recurse"))
        dpg.set_value(self._t("scan_status"), "  (Scanning...)")
        dpg.configure_item(self._t("scan_progress"), show=True)
        dpg.configure_item(self._t("btn_scan"), enabled=False)
        dpg.delete_item(self._t("series_list"), children_only=True)

        self._stop_event.clear()
        # Run scan in background so UI doesn't freeze
        threading.Thread(
            target=self._run_scan, args=(folder, recurse), daemon=True
        ).start()

    def _run_scan(self, folder, recurse):
        assert self.api is not None
        self.scan_errors = []
        # Consume the generator yielded from PluginAPI (which delegates to controller/file.py)
        for result in self.api.scan_dicom_folder(folder, recursive=recurse):
            if self._stop_event.is_set():
                return
            if len(result) == 2:
                pct, dirname = result
                self.scan_progress = pct
                label = dirname if len(dirname) <= 30 else dirname[:27] + "..."
                self.scan_status_text = f"  {label}"
            elif len(result) == 4:
                _, _, self.scanned_series, self.scan_errors = result

        # Signal completion
        self.scan_finished = True

    def destroy(self) -> None:
        self._stop_event.set()
        if dpg.does_item_exist(self.window_tag):
            dpg.delete_item(self.window_tag)

    def _populate_series_list(self):
        if not dpg.does_item_exist(self._t("series_list")):
            return
        dpg.delete_item(self._t("series_list"), children_only=True)

        def clean_string(val):
            if val is None:
                return ""
            try:
                val_str = str(val).replace('\x00', '')
                val_str = "".join(c for c in val_str if not (0xD800 <= ord(c) <= 0xDFFF))
                return val_str.encode('utf-8', 'ignore').decode('utf-8')
            except Exception:
                return "Unknown"

        for idx, s in enumerate(self.scanned_series):
            label = f"[{s['modality']}] {s['series_desc']}\n  {s['date']} | {len(s['files'])} files"
            dpg.add_selectable(
                label=clean_string(label),
                height=35,
                parent=self._t("series_list"),
                user_data=idx,
                tag=self._t(f"sel_{idx}"),
                callback=self.on_series_selected,
            )

    def on_series_selected(self, sender, app_data, user_data):
        # Deselect all others safely (Comparing Aliases and Integer IDs)
        children = dpg.get_item_children(self._t("series_list"), 1)
        if children:
            for child in children:
                if child != sender and dpg.get_item_alias(child) != sender:
                    dpg.set_value(child, False)

        # Force active highlight (Essential for Keyboard arrows!)
        if dpg.does_item_exist(sender):
            dpg.set_value(sender, True)

        self.active_idx = user_data
        self.active_series = self.scanned_series[user_data]
        s = self.active_series

        def clean_string(val):
            if val is None:
                return ""
            try:
                val_str = str(val).replace('\x00', '')
                val_str = "".join(c for c in val_str if not (0xD800 <= ord(c) <= 0xDFFF))
                return val_str.encode('utf-8', 'ignore').decode('utf-8')
            except Exception:
                return "Unknown"

        dpg.set_value(self._t("lbl_patient"), clean_string(s["patient_name"]))
        dpg.set_value(self._t("lbl_study"), clean_string(s["study_desc"]))
        dpg.set_value(self._t("lbl_size"), clean_string(s["size"]))
        dpg.set_value(self._t("lbl_spacing"), clean_string(s["spacing"]))

        first_file = os.path.basename(s["files"][0]) if s["files"] else "Unknown"
        dir_path = os.path.dirname(s["files"][0]) if s["files"] else "Unknown"
        dpg.set_value(self._t("lbl_file"), clean_string(first_file))
        dpg.set_value(self._t("lbl_dir"), clean_string(dir_path))

        # --- DYNAMIC TABLE POPULATION ---
        if dpg.does_item_exist(self._t("tags_table")):
            # Delete all existing rows
            rows = dpg.get_item_children(self._t("tags_table"), 1)
            if rows:
                for row in rows:
                    dpg.delete_item(row)

            assert self.api is not None
            cfg_c = self.api.get_ui_config()["colors"]
            # Generate fresh rows only for tags that actually exist
            for tag, name, val in s["tags"]:
                with dpg.table_row(parent=self._t("tags_table")):
                    dpg.add_text(clean_string(tag), color=[150, 255, 150])
                    dpg.add_text(clean_string(name), color=cfg_c["text_dim"])
                    dpg.add_text(clean_string(val))

    def on_open_clicked(self) -> None:
        if not self.active_series:
            return

        # Cast the SimpleITK tuple into a standard list
        file_list = list(self.active_series["files"])

        # Call load_dicom_series via PluginAPI to register task on main thread
        assert self.api is not None
        self.api.load_dicom_series(file_list)
        
        # Delete window
        dpg.delete_item(self.window_tag)

    def move_selection(self, delta):
        """Called by the Interaction Manager to shift selection up/down via arrows."""
        if not self.scanned_series:
            return

        idx = max(0, min(len(self.scanned_series) - 1, self.active_idx + delta))
        sender = self._t(f"sel_{idx}")
        if dpg.does_item_exist(sender):
            dpg.set_value(sender, True)
            self.on_series_selected(sender, None, idx)
            dpg.focus_item(sender)

    def update(self, api) -> None:
        pass
