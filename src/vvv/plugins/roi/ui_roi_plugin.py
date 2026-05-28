import os
import dearpygui.dearpygui as dpg
from typing import Optional
from vvv.plugins.plugin_api import PluginAPI, PluginTagMixin
from vvv.ui.ui_components import build_section_title, build_help_button


class RoiPluginUI(PluginTagMixin):
    def __init__(self, plugin_id: str, controller):
        self._plugin_id = plugin_id
        self._c = controller
        self.api: Optional[PluginAPI] = None

    def create_ui(self, parent, api: PluginAPI) -> None:
        self.api = api
        cfg_c = api.get_ui_config()["colors"]
        cfg_l = api.get_ui_config()["layout"]

        # Ensure registered item handlers or themes exist if needed
        if not dpg.does_item_exist(self._t("item_clicked_handler")):
            with dpg.item_handler_registry(tag=self._t("item_clicked_handler")):
                dpg.add_item_clicked_handler(callback=self.on_mock_row_clicked)

        # Create theme for active mock text
        if not dpg.does_item_exist(self._t("active_input_theme")):
            with dpg.theme(tag=self._t("active_input_theme")):
                with dpg.theme_component(dpg.mvInputText):
                    dpg.add_theme_color(dpg.mvThemeCol_Text, cfg_c["text_active"])
                    dpg.add_theme_color(dpg.mvThemeCol_FrameBg, [0, 0, 0, 0])
                    dpg.add_theme_style(dpg.mvStyleVar_FrameBorderSize, 0)

        if not dpg.does_item_exist(self._t("inactive_input_theme")):
            with dpg.theme(tag=self._t("inactive_input_theme")):
                with dpg.theme_component(dpg.mvInputText):
                    dpg.add_theme_color(dpg.mvThemeCol_FrameBg, [0, 0, 0, 0])
                    dpg.add_theme_style(dpg.mvStyleVar_FrameBorderSize, 0)

        # Main vertical panel group
        with dpg.group(parent=parent, tag=self._t("panel_group")):
            build_section_title("ROIs (Plugin)", cfg_c["text_header"])

            dpg.add_text(
                "No Image Selected",
                tag=self._t("text_roi_active_title"),
                color=cfg_c["text_active"],
            )

            # --- TOP: Load & Import ---
            with dpg.group(horizontal=True):
                btn_load = dpg.add_button(
                    label="Load ROI / RT-Struct / Label Map...",
                    width=-1,
                    callback=self.on_mock_load_clicked,
                    tag=self._t("btn_roi_load"),
                )

            with dpg.group(horizontal=True, tag=self._t("group_roi_mode")):
                dpg.add_text("Rule:")
                dpg.add_combo(
                    ["Ignore BG (val)", "Target FG (val)", "Label Map"],
                    default_value="Ignore BG (val)",
                    tag=self._t("combo_roi_mode"),
                    width=130,
                    callback=self.on_mock_mode_changed,
                )
                build_help_button(
                    "Ignore BG: Makes '0' transparent and keeps everything else.\nTarget FG: Keeps only the exact 'Val' specified.\nLabel Map: Extracts all unique integer values as separate ROIs.",
                    self.api._gui
                )

            with dpg.group(horizontal=True, tag=self._t("group_roi_mode2")):
                dpg.add_text("Val:")
                dpg.add_input_float(
                    default_value=0.0, step=1.0, width=140, tag=self._t("input_roi_val")
                )

            dpg.add_spacer(height=10)

            # --- MIDDLE: The Master List Controls ---
            with dpg.group(horizontal=True):
                btn_show = dpg.add_button(
                    label="\uf06e",
                    width=20,
                    callback=self.on_mock_action,
                    tag=self._t("btn_roi_show_all"),
                )
                btn_contour = dpg.add_button(
                    label="\uf040",
                    width=20,
                    callback=self.on_mock_action,
                    tag=self._t("btn_roi_contour_all"),
                )
                btn_hide = dpg.add_button(
                    label="\uf070",
                    width=20,
                    callback=self.on_mock_action,
                    tag=self._t("btn_roi_hide_all"),
                )
                btn_close_all = dpg.add_button(
                    label="\uf00d",
                    width=20,
                    callback=self.on_mock_action,
                    tag=self._t("btn_roi_close_all"),
                )

                if dpg.does_item_exist("icon_font_tag"):
                    for btn in [btn_show, btn_contour, btn_hide, btn_close_all]:
                        dpg.bind_item_font(btn, "icon_font_tag")

                if dpg.does_item_exist("delete_button_theme"):
                    dpg.bind_item_theme(btn_close_all, "delete_button_theme")

                with dpg.tooltip(btn_show):
                    dpg.add_text("Show All (Raster) [Mock]")

                with dpg.tooltip(btn_contour):
                    dpg.add_text("Show All (Contour) [Mock]")

                with dpg.tooltip(btn_hide):
                    dpg.add_text("Hide All [Mock]")

                with dpg.tooltip(btn_close_all):
                    dpg.add_text("Close All [Mock]")

                dpg.add_text("Op:")
                dpg.add_slider_float(
                    tag=self._t("slider_roi_global_opacity"),
                    width=50,
                    min_value=0.0,
                    max_value=1.0,
                    default_value=0.5,
                    callback=self.on_mock_action,
                )
                dpg.add_text("Thk:")
                dpg.add_slider_float(
                    tag=self._t("slider_roi_global_thickness"),
                    width=50,
                    min_value=0.5,
                    max_value=10.0,
                    default_value=1.0,
                    callback=self.on_mock_action,
                )

            dpg.add_separator()

            # Filter row
            with dpg.group(tag=self._t("group_roi_filter"), horizontal=True):
                btn_sort = dpg.add_button(
                    label="\uf0dc",
                    width=20,
                    tag=self._t("btn_roi_sort"),
                    callback=self.on_mock_action,
                )
                if dpg.does_item_exist("icon_font_tag"):
                    dpg.bind_item_font(btn_sort, "icon_font_tag")

                dpg.add_text("Filter:", color=cfg_c["text_dim"])
                dpg.add_input_text(
                    tag=self._t("input_roi_filter"),
                    width=-30,
                    callback=self.on_mock_action,
                )
                btn_clear_filter = dpg.add_button(
                    label="\uf00d",
                    width=20,
                    callback=self.on_mock_action,
                    tag=self._t("btn_clear_filter"),
                )
                if dpg.does_item_exist("icon_font_tag"):
                    dpg.bind_item_font(btn_clear_filter, "icon_font_tag")

            # Table Container
            with dpg.child_window(
                tag=self._t("roi_list_window"), height=150, border=False, no_scrollbar=True
            ):
                with dpg.table(
                    tag=self._t("roi_list_table"),
                    header_row=False,
                    resizable=False,
                    borders_innerH=False,
                    scrollY=True,
                ):
                    dpg.add_table_column(width_fixed=True, init_width_or_weight=20)
                    dpg.add_table_column(width_stretch=True)
                    dpg.add_table_column(width_fixed=True, init_width_or_weight=20)
                    dpg.add_table_column(width_fixed=True, init_width_or_weight=20)
                    dpg.add_table_column(width_fixed=True, init_width_or_weight=20)
                    dpg.add_table_column(width_fixed=True, init_width_or_weight=20)

                    # Populating with two mock rows for Step 1 UI Demonstration
                    self._create_mock_table_row([255, 50, 50], "Mock_ROI_Red", True, False, 1)
                    self._create_mock_table_row([50, 255, 50], "Mock_ROI_Green", True, True, 2)

            dpg.add_spacer(height=5)

            # Export Button
            dpg.add_button(
                label="Export All Stats to JSON (Plugin)",
                width=-1,
                callback=self.on_mock_action,
                tag=self._t("btn_roi_export_stats"),
            )
            dpg.add_spacer(height=10)

            # --- BOTTOM: The Detail Panel ---
            with dpg.group(tag=self._t("roi_detail_header_group"), show=True):
                with dpg.group(horizontal=True):
                    dpg.add_text("Selected ROI Properties (Plugin)", color=cfg_c["text_header"])
                    btn_close_detail = dpg.add_button(
                        label="\uf00d", width=20, callback=self.on_mock_action, tag=self._t("btn_close_detail")
                    )
                    if dpg.does_item_exist("icon_font_tag"):
                        dpg.bind_item_font(btn_close_detail, "icon_font_tag")
                    if dpg.does_item_exist("delete_button_theme"):
                        dpg.bind_item_theme(btn_close_detail, "delete_button_theme")
                dpg.add_separator()

            with dpg.child_window(tag=self._t("roi_detail_window"), border=False, no_scrollbar=True, show=True):
                with dpg.group(tag=self._t("roi_detail_container")):
                    dim_col = cfg_c["text_dim"]

                    # 1. Loading Rule
                    with dpg.group(horizontal=True):
                        dpg.add_text("Rule:", color=dim_col)
                        dpg.add_text("Ignore BG (val) [Mock]")

                    # 2. Dimensions
                    with dpg.group(horizontal=True):
                        dpg.add_text("Size:", color=dim_col)
                        dpg.add_text("256 x 256 x 128 [Mock]")

                    # 3. Spacing
                    with dpg.group(horizontal=True):
                        dpg.add_text("Spacing:", color=dim_col)
                        dpg.add_text("1.000 x 1.000 x 1.500 [Mock]")

                    dpg.add_spacer(height=5)

                    # 4. Opacity/Thickness
                    with dpg.group(horizontal=True):
                        dpg.add_text("Opacity:")
                        dpg.add_slider_float(
                            default_value=0.5,
                            min_value=0.0,
                            max_value=1.0,
                            width=-1,
                            tag=self._t("slider_roi_opacity"),
                            callback=self.on_mock_action,
                        )

                    dpg.add_spacer(height=5)

                    # 5. Analysis target selection
                    with dpg.group(horizontal=True):
                        dpg.add_text("Analyze:")
                        dpg.add_combo(
                            ["Base Image", "Active Overlay"],
                            default_value="Base Image",
                            tag=self._t("combo_roi_image"),
                            width=-1,
                            callback=self.on_mock_action,
                        )

                    # 6. Stats table structure
                    with dpg.table(header_row=False, borders_innerH=False):
                        dpg.add_table_column(width_stretch=True)
                        dpg.add_table_column(width_stretch=True)
                        with dpg.table_row():
                            with dpg.group(horizontal=True):
                                dpg.add_text("Vol:", color=dim_col)
                                dpg.add_text("12.45 cc [Mock]", tag=self._t("roi_stat_vol"))
                            with dpg.group(horizontal=True):
                                dpg.add_text("Mean:", color=dim_col)
                                dpg.add_text("250.31 [Mock]", tag=self._t("roi_stat_mean"))
                        with dpg.table_row():
                            with dpg.group(horizontal=True):
                                dpg.add_text("Max:", color=dim_col)
                                dpg.add_text("950.00 [Mock]", tag=self._t("roi_stat_max"))
                            with dpg.group(horizontal=True):
                                dpg.add_text("Min:", color=dim_col)
                                dpg.add_text("-100.00 [Mock]", tag=self._t("roi_stat_min"))
                        with dpg.table_row():
                            with dpg.group(horizontal=True):
                                dpg.add_text("Std:", color=dim_col)
                                dpg.add_text("45.12 [Mock]", tag=self._t("roi_stat_std"))
                            with dpg.group(horizontal=True):
                                dpg.add_text("Peak:", color=dim_col)
                                dpg.add_text("940.50 [Mock]", tag=self._t("roi_stat_peak"))
                            with dpg.group(horizontal=True):
                                dpg.add_text("Mass:", color=dim_col)
                                dpg.add_text("15.22 g [Mock]", tag=self._t("roi_stat_mass"))

    def _create_mock_table_row(self, color, name, visible, is_contour, idx):
        row_id = self._t(f"mock_row_{idx}")
        with dpg.table_row(parent=self._t("roi_list_table"), tag=row_id):
            dpg.add_color_edit(
                default_value=color + [255],
                no_inputs=True,
                no_label=True,
                no_alpha=True,
                width=20,
                height=20,
                callback=self.on_mock_action,
            )

            # Name input text field
            input_tag = self._t(f"mock_input_text_{idx}")
            dpg.add_input_text(
                default_value=name,
                width=-1,
                tag=input_tag,
                user_data=idx,
                callback=self.on_mock_action,
            )
            dpg.bind_item_handler_registry(input_tag, self._t("item_clicked_handler"))
            dpg.bind_item_theme(input_tag, self._t("inactive_input_theme"))

            # Eye button for visibility
            lbl_eye = "\uf040" if is_contour else "\uf06e" if visible else "\uf070"
            btn_eye = dpg.add_button(
                label=lbl_eye,
                width=20,
                callback=self.on_mock_action,
            )

            # Center on ROI button
            btn_center = dpg.add_button(
                label="\uf05b",
                width=20,
                callback=self.on_mock_action,
            )

            # Save ROI button
            btn_save = dpg.add_button(
                label="\uf0c7",
                width=20,
                callback=self.on_mock_action,
            )

            # Close ROI button
            btn_close = dpg.add_button(
                label="\uf00d",
                width=20,
                callback=self.on_mock_action,
            )

            # Font bindings
            if dpg.does_item_exist("icon_font_tag"):
                for btn in [btn_eye, btn_center, btn_save, btn_close]:
                    dpg.bind_item_font(btn, "icon_font_tag")

            if dpg.does_item_exist("delete_button_theme"):
                dpg.bind_item_theme(btn_close, "delete_button_theme")

    # Mock/Placeholder Callbacks
    def on_mock_row_clicked(self, sender, app_data, user_data):
        if not app_data or len(app_data) < 2:
            return
        item_id = app_data[1]
        idx = dpg.get_item_user_data(item_id)
        if idx:
            # Rebind active themes for demonstration
            for i in [1, 2]:
                inp = self._t(f"mock_input_text_{i}")
                if dpg.does_item_exist(inp):
                    if i == idx:
                        dpg.bind_item_theme(inp, self._t("active_input_theme"))
                    else:
                        dpg.bind_item_theme(inp, self._t("inactive_input_theme"))

    def on_mock_load_clicked(self, sender, app_data, user_data):
        if self.api:
            self.api._gui.show_status_message("ROI Plugin [Mock]: Load button clicked")

    def on_mock_mode_changed(self, sender, app_data, user_data):
        show_val = app_data != "Label Map"
        if dpg.does_item_exist(self._t("group_roi_mode2")):
            dpg.configure_item(self._t("group_roi_mode2"), show=show_val)

    def on_mock_action(self, sender, app_data, user_data):
        if self.api:
            self.api._gui.show_status_message(f"ROI Plugin [Mock]: Callback triggered (sender: {sender})")
