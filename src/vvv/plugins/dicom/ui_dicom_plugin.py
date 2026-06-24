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
        self.collapsed_nodes = {}  # Tracks node labels to collapsed state (bool)
        self.open_image_tabs = {}  # Tracks open DICOM image tabs by image_id
        self.last_pos = None
        self.last_size = (1000, 700)
        self.last_split_width = 450

        # Asynchronous State
        self.scan_progress = 0.0
        self.scan_status_text = ""
        self.scan_finished = False
        self.scan_errors: list[str] = []
        self._stop_event = threading.Event()

    def create_ui(self, parent, api) -> None:
        self.api = api

    def tick(self) -> None:
        if not dpg.does_item_exist(self.window_tag) or not dpg.is_item_shown(
            self.window_tag
        ):
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
                        "Some directories could not be scanned:\n\n"
                        + "\n".join(self.scan_errors),
                    )
            self.scan_finished = False
            return

        # Update progress and status text while scanning
        if dpg.does_item_exist(self._t("scan_progress")):
            dpg.set_value(self._t("scan_progress"), self.scan_progress)
            dpg.set_value(self._t("scan_status"), self.scan_status_text)

    def _save_ui_state(self):
        if dpg.does_item_exist(self.window_tag):
            self.last_pos = dpg.get_item_pos(self.window_tag)
            size = dpg.get_item_rect_size(self.window_tag)
            if size and len(size) >= 2:
                self.last_size = (size[0], size[1])

        # Save collapse states of tree nodes by matching label
        self.collapsed_nodes = {}
        for node in self.active_tree_nodes:
            if dpg.does_item_exist(node):
                lbl = dpg.get_item_configuration(node).get("label", "")
                is_open = dpg.get_value(node)
                self.collapsed_nodes[lbl] = is_open

        # Save split width
        if dpg.does_item_exist(self._t("col_list")):
            rect = dpg.get_item_rect_size(self._t("col_list"))
            if rect and rect[0] > 0:
                self.last_split_width = rect[0]

    def _get_modality_theme(self, modality: str):
        theme_tag = f"dicom_modality_theme_{modality}"
        if dpg.does_item_exist(theme_tag):
            return theme_tag

        # Define text color based on modality
        mod = modality.upper()
        if "CT" in mod:
            text_color = [160, 190, 220, 255]  # Slate Blue
            hover_color = [50, 70, 95, 255]
            select_color = [70, 95, 130, 255]
        elif "PT" in mod or "PET" in mod:
            text_color = [200, 170, 230, 255]  # Soft Violet
            hover_color = [70, 50, 95, 255]
            select_color = [95, 70, 130, 255]
        elif "NM" in mod or "SPECT" in mod:
            text_color = [140, 210, 180, 255]  # Muted Teal
            hover_color = [40, 75, 60, 255]
            select_color = [55, 105, 85, 255]
        elif "MR" in mod:
            text_color = [230, 190, 140, 255]  # Muted Amber
            hover_color = [75, 60, 40, 255]
            select_color = [105, 85, 55, 255]
        else:
            text_color = [220, 220, 220, 255]  # Light Gray
            hover_color = [60, 60, 65, 255]
            select_color = [80, 80, 85, 255]

        with dpg.theme(tag=theme_tag):
            # Styling for the selectable itself
            with dpg.theme_component(dpg.mvSelectable):
                dpg.add_theme_color(dpg.mvThemeCol_Text, text_color)
                dpg.add_theme_color(dpg.mvThemeCol_HeaderHovered, hover_color)
                dpg.add_theme_color(dpg.mvThemeCol_Header, select_color)
                dpg.add_theme_color(dpg.mvThemeCol_HeaderActive, select_color)
                # Keep selectable padding tight
                dpg.add_theme_style(dpg.mvStyleVar_FramePadding, 8, 4)

        return theme_tag

    def on_window_close(self):
        self._save_ui_state()
        dpg.delete_item(self.window_tag)

    def show_window(self) -> None:
        if dpg.does_item_exist(self.window_tag):
            dpg.focus_item(self.window_tag)
            return

        assert self.api is not None
        cfg_c = self.api.get_ui_config()["colors"]

        # Restore window dimensions or default
        w = self.last_size[0] if self.last_size else 1000
        h = self.last_size[1] if self.last_size else 700

        with dpg.window(
            tag=self.window_tag,
            label="DICOM Series Browser",
            width=w,
            height=h,
            no_collapse=False,
            on_close=self.on_window_close,
        ):
            dpg.add_spacer(height=5)

            with dpg.tab_bar(
                tag=self._t("main_tab_bar"), callback=self._on_tab_bar_callback
            ):
                with dpg.tab(
                    label="Browser", tag=self._t("browser_tab"), closable=False
                ):
                    # --- TOP BAR ---
                    with dpg.group(horizontal=True):
                        btn_dir = dpg.add_button(
                            label="\uf07c",
                            width=30,
                            callback=self.on_select_folder,
                            tag=self._t("btn_select_dir"),
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

                        build_beginner_tooltip(
                            self._t("check_recurse"),
                            "Scan all nested directories inside the selected directory.",
                            self.api,
                        )
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
                            init_width_or_weight=self.last_split_width,
                            width_fixed=False,
                            tag=self._t("col_list"),
                        )
                        dpg.add_table_column(
                            init_width_or_weight=w - self.last_split_width,
                            width_stretch=True,
                            tag=self._t("col_details"),
                        )

                        with dpg.table_row():
                            # Left column: Series list
                            with dpg.group():
                                with dpg.group(horizontal=True):
                                    dpg.add_text(
                                        "Found Series",
                                        color=cfg_c["text_header"],
                                    )
                                    dpg.add_text(
                                        "",
                                        tag=self._t("scan_status"),
                                        color=[255, 255, 0],
                                    )

                                # Fold/Unfold controls & Modality Legend
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
                                    dpg.add_spacer(width=10)
                                    dpg.add_text("CT", color=[160, 190, 220, 255])
                                    dpg.add_text("|", color=[80, 80, 80, 255])
                                    dpg.add_text("PET", color=[200, 170, 230, 255])
                                    dpg.add_text("|", color=[80, 80, 80, 255])
                                    dpg.add_text("NM", color=[140, 210, 180, 255])
                                    dpg.add_text("|", color=[80, 80, 80, 255])
                                    dpg.add_text("MR", color=[230, 190, 140, 255])

                                # Progress bar hidden by default
                                dpg.add_progress_bar(
                                    tag=self._t("scan_progress"),
                                    width=-1,
                                    default_value=0.0,
                                    show=False,
                                )
                                dpg.add_separator()

                                # Put the scrollable list inside a child window to stretch vertically
                                with dpg.child_window(
                                    width=-1, height=-1, border=False
                                ):
                                    dpg.add_group(tag=self._t("series_list"))

                            # Right column: Details & Action
                            with dpg.child_window(
                                width=-1,
                                height=-1,
                                border=False,
                                tag=self._t("details_panel"),
                            ):
                                with dpg.group(horizontal=True):
                                    dpg.add_text("Path:    ", color=cfg_c["text_dim"])
                                    dpg.add_input_text(
                                        default_value="---",
                                        tag=self._t("lbl_dir"),
                                        readonly=True,
                                    )

                                with dpg.group(horizontal=True):
                                    dpg.add_text("File:    ", color=cfg_c["text_dim"])
                                    dpg.add_input_text(
                                        default_value="---",
                                        tag=self._t("lbl_file"),
                                        readonly=True,
                                    )
                                with dpg.group(horizontal=True):
                                    dpg.add_text("Patient: ", color=cfg_c["text_dim"])
                                    dpg.add_text("---", tag=self._t("lbl_patient"))
                                    dpg.add_spacer(width=20)
                                    dpg.add_text("Study: ", color=cfg_c["text_dim"])
                                    dpg.add_text("---", tag=self._t("lbl_study"))

                                with dpg.group(horizontal=True):
                                    dpg.add_text("Size:    ", color=cfg_c["text_dim"])
                                    dpg.add_text("---", tag=self._t("lbl_size"))
                                    dpg.add_spacer(width=20)
                                    dpg.add_text("Spacing: ", color=cfg_c["text_dim"])
                                    dpg.add_text("---", tag=self._t("lbl_spacing"))

                                dpg.add_spacer(
                                    height=10, tag=self._t("metadata_spacer")
                                )
                                dpg.add_separator(tag=self._t("metadata_sep"))
                                dpg.add_text(
                                    "DICOM Metadata",
                                    color=cfg_c["text_header"],
                                    tag=self._t("metadata_header"),
                                )

                                # Middle: Tags Table
                                with dpg.child_window(
                                    height=-45, border=True, tag=self._t("table_panel")
                                ):
                                    with dpg.table(
                                        tag=self._t("tags_table"),
                                        header_row=True,
                                        resizable=True,
                                        borders_innerH=True,
                                        borders_innerV=True,
                                    ):
                                        dpg.add_table_column(
                                            label="Tag",
                                            width_fixed=True,
                                            init_width_or_weight=90,
                                        )
                                        dpg.add_table_column(
                                            label="Name",
                                            width_fixed=True,
                                            init_width_or_weight=150,
                                        )
                                        dpg.add_table_column(
                                            label="Value", width_stretch=True
                                        )

                                dpg.add_spacer(height=5)
                                btn_open = dpg.add_button(
                                    label="Open Series as Image",
                                    width=-1,
                                    height=30,
                                    callback=self.on_open_clicked,
                                    tag=self._t("btn_open"),
                                )
                                from vvv.ui.ui_components import build_beginner_tooltip

                                build_beginner_tooltip(
                                    btn_open,
                                    "Load the selected DICOM series files as a 3D volume.",
                                    self.api,
                                )
                                if dpg.does_item_exist("icon_button_theme"):
                                    dpg.bind_item_theme(btn_open, "icon_button_theme")

        if self.last_pos:
            dpg.set_item_pos(self.window_tag, self.last_pos)
        else:
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
            dpg.set_value(
                self._t("scan_status"), f"  ({len(self.scanned_series)} found)"
            )
            self._populate_series_list()
            # Restore selection if active
            if self.active_idx >= 0:
                sel_tag = self._t(f"sel_{self.active_idx}")
                if dpg.does_item_exist(sel_tag):
                    dpg.set_value(sel_tag, True)
                    self.on_series_selected(sel_tag, None, self.active_idx)

        # Restore open image tabs!
        for img_id, info in self.open_image_tabs.items():
            self._create_image_tab(img_id, info["title"], info["tags"])

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
        self.scanned_series.sort(key=lambda x: x.get("date", ""), reverse=True)

        dpg.delete_item(self._t("series_list"), children_only=True)

        def clean_string(val):
            if val is None:
                return ""
            try:
                val_str = str(val).replace("\x00", "")
                val_str = "".join(
                    c for c in val_str if not (0xD800 <= ord(c) <= 0xDFFF)
                )
                return val_str.encode("utf-8", "ignore").decode("utf-8")
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

        # Define table theme for alternating row backgrounds
        table_theme = "dicom_table_theme"
        if not dpg.does_item_exist(table_theme):
            with dpg.theme(tag=table_theme):
                with dpg.theme_component(dpg.mvTable):
                    # Set custom alternating row backgrounds
                    dpg.add_theme_color(dpg.mvThemeCol_TableRowBg, [28, 29, 31, 255])
                    dpg.add_theme_color(dpg.mvThemeCol_TableRowBgAlt, [36, 37, 40, 255])

        # Render each group under a tree node or collapsible header
        for (p_name, study_date, space_key), series_in_group in groups.items():
            # Find the most common study description in this group to display in the header
            study_descs = [
                s.get("study_desc") for _, s in series_in_group if s.get("study_desc")
            ]
            display_study_desc = (
                max(set(study_descs), key=study_descs.count)
                if study_descs
                else "Unknown Study"
            )

            # Create a label for the group header
            group_label = f"{clean_string(p_name)} | {clean_string(study_date)} | {clean_string(display_study_desc)}"

            is_paired = False
            # Check if this space key is a frame_of_ref_uid (not a study description fallback)
            for _, s in series_in_group:
                if s.get("frame_of_ref_uid") == space_key and space_key:
                    is_paired = True
                    break

            # Restore collapsed/expanded state if previously saved
            default_open = self.collapsed_nodes.get(group_label, True)

            tree_tag = self._t(f"tree_{len(self.active_tree_nodes)}")
            dpg.add_tree_node(
                label=group_label,
                parent=self._t("series_list"),
                default_open=default_open,
                tag=tree_tag,
            )
            self.active_tree_nodes.append(tree_tag)

            # Create a table for the series in this group to get native alternating backgrounds
            table_tag = self._t(f"table_group_{len(self.active_tree_nodes)}")
            with dpg.table(
                parent=tree_tag,
                header_row=False,
                row_background=True,
                width=-1,
                tag=table_tag,
            ):
                dpg.add_table_column(width_stretch=True)

                for idx, s in series_in_group:
                    label = f"[{s['modality']}] {s['series_desc']}\n  {s['date']} | {len(s['files'])} files"

                    # Get or create custom theme based on modality
                    theme_tag = self._get_modality_theme(s.get("modality", "Unknown"))

                    with dpg.table_row():
                        sel = dpg.add_selectable(
                            label=clean_string(label),
                            height=35,
                            user_data=idx,
                            tag=self._t(f"sel_{idx}"),
                            callback=self.on_series_selected,
                        )
                        dpg.bind_item_theme(sel, theme_tag)

            dpg.bind_item_theme(table_tag, table_theme)

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
                val_str = str(val).replace("\x00", "")
                val_str = "".join(
                    c for c in val_str if not (0xD800 <= ord(c) <= 0xDFFF)
                )
                return val_str.encode("utf-8", "ignore").decode("utf-8")
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
                row = dpg.add_table_row(parent=self._t("tags_table"))
                dpg.add_text(clean_string(tag), color=[150, 255, 150], parent=row)
                dpg.add_text(clean_string(name), color=cfg_c["text_dim"], parent=row)
                dpg.add_text(clean_string(val), parent=row)

    def on_open_clicked(self) -> None:
        if not self.active_series:
            return

        # Cast the SimpleITK tuple into a standard list
        file_list = list(self.active_series["files"])

        # Call load_dicom_series via PluginAPI to register task on main thread
        assert self.api is not None
        self.api.load_dicom_series(file_list)

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

    def on_image_loaded(self, image_id: str) -> None:
        if self.api is None:
            return

        def async_load():
            vol = self.api.get_volumes().get(image_id)
            if not vol or not vol.file_paths:
                return

            # Find the first valid DICOM file path
            dcm_file = None
            for p in vol.file_paths:
                if not p:
                    continue
                if os.path.isdir(p):
                    for root, dirs, files in os.walk(p):
                        for f in files:
                            candidate = os.path.join(root, f)
                            if (
                                os.path.isfile(candidate)
                                and not f.startswith(".")
                                and not f.lower().endswith(".json")
                            ):
                                dcm_file = candidate
                                break
                        if dcm_file:
                            break
                elif os.path.isfile(p) and not p.lower().endswith(".json"):
                    dcm_file = p
                    break

            if not dcm_file:
                return

            # Try to read all DICOM tags using pydicom
            try:
                import pydicom

                def parse_elem(elem):
                    tag_str = f"({elem.tag.group:04X},{elem.tag.element:04X})"
                    name = elem.name
                    if isinstance(elem.value, pydicom.sequence.Sequence):
                        nested_items = []
                        for sub_ds in elem.value:
                            nested_item = []
                            for sub_elem in sub_ds:
                                nested_item.append(parse_elem(sub_elem))
                            nested_items.append(nested_item)
                        return {
                            "tag": tag_str,
                            "name": name,
                            "value": f"{len(elem.value)} item(s)",
                            "is_seq": True,
                            "nested": nested_items,
                        }
                    else:
                        val_str = str(elem.value)
                        val_str = val_str.replace("\x00", "")
                        val_str = "".join(
                            c for c in val_str if not (0xD800 <= ord(c) <= 0xDFFF)
                        )
                        return {
                            "tag": tag_str,
                            "name": name,
                            "value": val_str,
                            "is_seq": False,
                            "nested": [],
                        }

                ds = pydicom.dcmread(dcm_file, stop_before_pixels=True)
                tags_list = [parse_elem(elem) for elem in ds]
            except Exception:
                # Not a DICOM file (or pydicom read failed)
                return

            title, _ = self.api.get_image_display_name(image_id)
            self.open_image_tabs[image_id] = {"title": title, "tags": tags_list}

            # If DICOM window is currently open, build the tab and focus it
            def build_ui():
                if dpg.does_item_exist(self.window_tag) and dpg.does_item_exist(
                    self._t("main_tab_bar")
                ):
                    dpg.focus_item(self.window_tag)
                    self._create_image_tab(image_id, title, tags_list)

                    tab_tag = self._t(f"tab_img_{image_id}")
                    if dpg.does_item_exist(tab_tag):
                        dpg.set_value(self._t("main_tab_bar"), tab_tag)

            self.api.run_on_main_thread(build_ui)

        threading.Thread(target=async_load, daemon=True).start()

    def on_image_removed(self, image_id: str) -> None:
        if image_id in self.open_image_tabs:
            del self.open_image_tabs[image_id]

        def remove_ui():
            tab_tag = self._t(f"tab_img_{image_id}")
            if dpg.does_item_exist(tab_tag):
                dpg.delete_item(tab_tag)

        if self.api:
            self.api.run_on_main_thread(remove_ui)

    def _create_image_tab(self, image_id: str, title: str, tags: list):
        tab_tag = self._t(f"tab_img_{image_id}")
        if dpg.does_item_exist(tab_tag):
            return
        if not dpg.does_item_exist(self._t("main_tab_bar")):
            return

        # Create tab directly
        dpg.add_tab(
            label=title,
            tag=tab_tag,
            parent=self._t("main_tab_bar"),
            closable=True,
        )

        # Create filter inside the tab
        filter_tag = self._t(f"filter_img_{image_id}")
        dpg.add_input_text(
            label="Filter Tags",
            tag=filter_tag,
            width=300,
            callback=self._on_filter_tags,
            user_data=image_id,
            parent=tab_tag,
        )
        dpg.add_spacer(height=5, parent=tab_tag)

        # Create scrollable child window inside the tab
        child_tag = self._t(f"child_img_{image_id}")
        dpg.add_child_window(
            tag=child_tag,
            width=-1,
            height=-1,
            border=True,
            parent=tab_tag,
        )

        # Create table inside the child window
        table_tag = self._t(f"table_img_{image_id}")
        dpg.add_table(
            tag=table_tag,
            header_row=True,
            resizable=True,
            borders_innerH=True,
            borders_innerV=True,
            width=-1,
            height=-1,
            parent=child_tag,
        )

        dpg.add_table_column(
            label="Tag", width_fixed=True, init_width_or_weight=90, parent=table_tag
        )
        dpg.add_table_column(
            label="Name", width_fixed=True, init_width_or_weight=200, parent=table_tag
        )
        dpg.add_table_column(label="Value", width_stretch=True, parent=table_tag)

        self._populate_tags_table(table_tag, tags, "")

    def _populate_tags_table(self, table_tag, tags, filter_text):
        # Clear existing rows (preserve columns!)
        children = dpg.get_item_children(table_tag, 1)
        if children:
            for child in children:
                if dpg.get_item_type(child) == "mvAppItemType::mvTableRow":
                    dpg.delete_item(child)

        filter_text = filter_text.lower()
        cfg_c = self.api.get_ui_config()["colors"]

        def matches_filter(it):
            if isinstance(it, dict):
                t = it.get("tag", "").lower()
                n = it.get("name", "").lower()
                v = it.get("value", "").lower()
                if filter_text in t or filter_text in n or filter_text in v:
                    return True
                for sub_list in it.get("nested", []):
                    for sub_it in sub_list:
                        if matches_filter(sub_it):
                            return True
                return False
            else:
                t, n, v = it
                return (
                    filter_text in t.lower()
                    or filter_text in n.lower()
                    or filter_text in v.lower()
                )

        def render_tags_recursive(parent_table, items):
            for item in items:
                # Normalize item: support both dict format (with sequences) and old flat tuple format
                if isinstance(item, dict):
                    tag = item.get("tag", "")
                    name = item.get("name", "")
                    val = item.get("value", "")
                    is_seq = item.get("is_seq", False)
                    nested = item.get("nested", [])
                else:
                    tag, name, val = item
                    is_seq = False
                    nested = []

                if filter_text and not matches_filter(item):
                    continue

                row = dpg.add_table_row(parent=parent_table)
                dpg.add_text(tag, color=[150, 255, 150], parent=row)
                dpg.add_text(name, color=cfg_c["text_dim"], parent=row)

                if is_seq and nested:
                    # Create tree node in the value cell
                    with dpg.tree_node(label=val, default_open=False, parent=row):
                        for idx, dataset in enumerate(nested):
                            if len(nested) > 1:
                                dpg.add_text(f"Item #{idx + 1}:", color=[100, 200, 255])

                            sub_table = dpg.add_table(
                                header_row=True,
                                resizable=True,
                                borders_innerH=True,
                                borders_innerV=True,
                                width=-1,
                            )
                            dpg.add_table_column(
                                label="Tag",
                                width_fixed=True,
                                init_width_or_weight=90,
                                parent=sub_table,
                            )
                            dpg.add_table_column(
                                label="Name",
                                width_fixed=True,
                                init_width_or_weight=150,
                                parent=sub_table,
                            )
                            dpg.add_table_column(
                                label="Value", width_stretch=True, parent=sub_table
                            )

                            render_tags_recursive(sub_table, dataset)
                else:
                    dpg.add_text(val, parent=row)

        render_tags_recursive(table_tag, tags)

    def _on_filter_tags(self, sender, app_data, user_data):
        image_id = user_data
        filter_text = dpg.get_value(sender)
        table_tag = self._t(f"table_img_{image_id}")
        if dpg.does_item_exist(table_tag) and image_id in self.open_image_tabs:
            tags = self.open_image_tabs[image_id]["tags"]
            self._populate_tags_table(table_tag, tags, filter_text)

    def _on_tab_bar_callback(self, sender, app_data, user_data):
        closed_image_ids = []
        for image_id in list(self.open_image_tabs.keys()):
            tab_tag = self._t(f"tab_img_{image_id}")
            if dpg.does_item_exist(tab_tag) and not dpg.is_item_visible(tab_tag):
                closed_image_ids.append(image_id)

        for image_id in closed_image_ids:
            self._on_image_tab_closed(image_id)

    def _on_image_tab_closed(self, image_id):
        if image_id in self.open_image_tabs:
            del self.open_image_tabs[image_id]
        tab_tag = self._t(f"tab_img_{image_id}")
        if dpg.does_item_exist(tab_tag):
            dpg.delete_item(tab_tag)

    def update(self, api) -> None:
        pass
