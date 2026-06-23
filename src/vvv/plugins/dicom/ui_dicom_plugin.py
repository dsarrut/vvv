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
        self.active_tree_nodes = []

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

        # Increase window width if needed
        with dpg.window(
            tag=self.window_tag,
            label="DICOM Series Browser (Plugin)",
            width=1000,
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
                    width=500,
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

            # --- SPLIT LAYOUT (Using a resizable table for horizontal split control) ---
            with dpg.table(
                tag=self._t("split_table"),
                header_row=False,
                resizable=True,
                width=-1,
                height=-1,
                borders_innerV=True,
                borders_outerV=False,
                borders_outerH=False,
                borders_innerH=False,
            ):
                dpg.add_table_column(
                    init_width_or_weight=450,
                    width_fixed=False,
                )
                dpg.add_table_column(
                    init_width_or_weight=550,
                    width_stretch=True,
                )

                with dpg.table_row():
                    # Left column: Series list
                    with dpg.group():
                        with dpg.group(horizontal=True):
                            dpg.add_text(
                                "Found Series",
                                color=cfg_c["text_header"],
                            )
                            dpg.add_text("", tag=self._t("scan_status"), color=[255, 255, 0])

                        # Fold/Unfold controls
                        with dpg.group(horizontal=True):
                            dpg.add_button(
                                label="Collapse All",
                                width=100,
                                callback=self.on_collapse_all_clicked,
                                tag=self._t("btn_collapse_all"),
                            )
                            dpg.add_button(
                                label="Expand All",
                                width=100,
                                callback=self.on_expand_all_clicked,
                                tag=self._t("btn_expand_all"),
                            )

                        # Progress bar hidden by default
                        dpg.add_progress_bar(
                            tag=self._t("scan_progress"),
                            width=-1,
                            default_value=0.0,
                            show=False,
                        )
                        dpg.add_separator()

                        # Put the scrollable list inside a child window to stretch vertically
                        with dpg.child_window(width=-1, height=-1, border=False):
                            dpg.add_group(tag=self._t("series_list"))

                    # Right column: Details & Action
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
        
        # Sort scanned series by date in reverse chronological order (most recent first)
        self.scanned_series.sort(key=lambda x: x.get('date', ''), reverse=True)

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

        # Group series by (patient_name, study_date, frame_of_ref_uid)
        # Group series by (patient_name, study_date, frame_of_ref_uid)
        groups = {}
        for idx, s in enumerate(self.scanned_series):
            # Fallback grouping keys if empty
            p_name = s.get("patient_name") or "Unknown Patient"
            
            # Normalize patient name to ignore trailing carets, spaces, and casing differences
            normalized_p_name = p_name.upper().replace("^", " ").strip()
            # Collapse double/multiple spaces to single spaces
            normalized_p_name = " ".join(normalized_p_name.split())

            f_ref = s.get("frame_of_ref_uid") or ""
            
            # Extract date (YYYY-MM-DD) from date string (which might contain time e.g., "YYYY-MM-DD HH:MM")
            raw_date = s.get("date") or "Unknown Date"
            study_date = raw_date.split(" ")[0] if " " in raw_date else raw_date

            # If there's no frame of reference (unpaired), we group them by study description
            # so different unpaired studies on the same day don't get merged,
            # but if they share a frame of reference (paired), we group them together.
            space_key = f_ref if f_ref else (s.get("study_desc") or "Unknown Study")

            group_key = (normalized_p_name, study_date, space_key)
            if group_key not in groups:
                groups[group_key] = []
            groups[group_key].append((idx, s))

        # Clear previous tree nodes list
        self.active_tree_nodes = []

        # Render each group under a tree node or collapsible header
        for (p_name, study_date, space_key), series_in_group in groups.items():
            # Find the most common study description in this group to display in the header
            study_descs = [s.get("study_desc") for _, s in series_in_group if s.get("study_desc")]
            display_study_desc = max(set(study_descs), key=study_descs.count) if study_descs else "Unknown Study"

            # Create a label for the group header
            group_label = f"{clean_string(p_name)} | {clean_string(study_date)} | {clean_string(display_study_desc)}"
            
            is_paired = False
            # Check if this space key is a frame_of_ref_uid (not a study description fallback)
            for _, s in series_in_group:
                if s.get("frame_of_ref_uid") == space_key and space_key:
                    is_paired = True
                    break

            if is_paired:
                # Indicate that the series inside this group share coordinate space
                group_label += " (Spatially Paired)"
            else:
                group_label += " (Unpaired Space)"

            tree_tag = self._t(f"tree_{len(self.active_tree_nodes)}")
            dpg.add_tree_node(
                label=group_label,
                parent=self._t("series_list"),
                default_open=True,
                tag=tree_tag,
            )
            self.active_tree_nodes.append(tree_tag)

            for idx, s in series_in_group:
                label = f"[{s['modality']}] {s['series_desc']}\n  {s['date']} | {len(s['files'])} files"
                dpg.add_selectable(
                    label=clean_string(label),
                    height=35,
                    parent=tree_tag,
                    user_data=idx,
                    tag=self._t(f"sel_{idx}"),
                    callback=self.on_series_selected,
                )

    def on_collapse_all_clicked(self, sender, app_data, user_data):
        for node in self.active_tree_nodes:
            if dpg.does_item_exist(node):
                dpg.configure_item(node, default_open=False)

    def on_expand_all_clicked(self, sender, app_data, user_data):
        for node in self.active_tree_nodes:
            if dpg.does_item_exist(node):
                dpg.configure_item(node, default_open=True)

    def on_series_selected(self, sender, app_data, user_data):
        # Deselect all selectables inside the entire list (traversing children of group tree nodes)
        for idx in range(len(self.scanned_series)):
            tag = self._t(f"sel_{idx}")
            if dpg.does_item_exist(tag) and tag != sender:
                dpg.set_value(tag, False)

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
