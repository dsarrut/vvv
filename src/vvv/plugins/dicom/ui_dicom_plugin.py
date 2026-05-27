import os
import dearpygui.dearpygui as dpg
from vvv.plugins.plugin_api import PluginTagMixin


class DicomPluginUI(PluginTagMixin):
    def __init__(self, plugin_id: str, controller):
        self._plugin_id = plugin_id
        self._c = controller
        self.window_tag = self._t("window")
        self.api = None

        # State persistence (placeholders)
        self.last_folder = os.getcwd()
        self.scanned_series = []
        self.active_series = None
        self.active_idx = -1

    def create_ui(self, parent, api) -> None:
        self.api = api
        cfg_c = api.get_ui_config()["colors"]

        with dpg.group(parent=parent or 0, tag=self._plugin_id):
            from vvv.ui.gui import build_section_title
            build_section_title("DICOM Browser", cfg_c["text_header"])
            
            dpg.add_text("This plugin allows you to scan folders for DICOM series, view metadata, and load them as 3D volumes.")
            dpg.add_spacer(height=5)
            
            btn_open_win = dpg.add_button(
                label="Open DICOM Browser Window",
                width=-1,
                height=30,
                callback=self.show_window,
                tag=self._t("btn_open_sidebar")
            )
            if dpg.does_item_exist("icon_button_theme"):
                dpg.bind_item_theme(btn_open_win, "icon_button_theme")

            dpg.add_spacer(height=5)
            dpg.add_text("Note: You can also open the browser directly from the File menu.", color=cfg_c["text_dim"])

    def show_window(self) -> None:
        if dpg.does_item_exist(self.window_tag):
            dpg.focus_item(self.window_tag)
            return

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

                    dpg.add_spacer(height=10)
                    dpg.add_separator()
                    dpg.add_text(
                        "DICOM Metadata", color=cfg_c["text_header"]
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

    def tick(self) -> None:
        pass

    def on_select_folder(self) -> None:
        pass

    def on_scan_clicked(self) -> None:
        pass

    def on_open_clicked(self) -> None:
        pass

    def on_series_selected(self, sender, app_data, user_data) -> None:
        pass
