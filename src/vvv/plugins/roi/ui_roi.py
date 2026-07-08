import os
import dearpygui.dearpygui as dpg
from vvv.plugins.plugin_api import PluginAPI, PluginTagMixin
from vvv.ui.ui_components import (
    build_section_title,
    build_help_button,
    build_beginner_tooltip,
    build_stepped_slider,
)


class RoiPluginUI(PluginTagMixin):
    def __init__(self, plugin_id: str, controller):
        self._plugin_id = plugin_id
        self._c = controller
        self.api: PluginAPI = None  # type: ignore
        self.roi_selectables = {}
        self.open_stats_wins = set()
        self.stats_win_positions = {}

    def create_ui(self, parent, api: PluginAPI) -> None:
        self.api = api
        cfg_c = api.get_ui_config()["colors"]
        cfg_l = api.get_ui_config()["layout"]

        # Ensure item clicked handler registry exists
        if not dpg.does_item_exist(self._t("item_clicked_handler")):
            with dpg.item_handler_registry(tag=self._t("item_clicked_handler")):
                dpg.add_item_clicked_handler(callback=self.on_roi_input_clicked)

        # Create active and inactive text themes
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

        if not dpg.does_item_exist(self._t("outdated_active_roi_input_theme")):
            with dpg.theme(tag=self._t("outdated_active_roi_input_theme")):
                with dpg.theme_component(dpg.mvInputText):
                    dpg.add_theme_color(dpg.mvThemeCol_Text, cfg_c["outdated"])
                    dpg.add_theme_color(dpg.mvThemeCol_FrameBg, [0, 0, 0, 0])
                    dpg.add_theme_style(dpg.mvStyleVar_FrameBorderSize, 0)

        if not dpg.does_item_exist(self._t("outdated_inactive_roi_input_theme")):
            with dpg.theme(tag=self._t("outdated_inactive_roi_input_theme")):
                with dpg.theme_component(dpg.mvInputText):
                    dpg.add_theme_color(dpg.mvThemeCol_Text, cfg_c["outdated"])
                    dpg.add_theme_color(dpg.mvThemeCol_FrameBg, [0, 0, 0, 0])
                    dpg.add_theme_style(dpg.mvStyleVar_FrameBorderSize, 0)

        # Main panel group
        with dpg.group(parent=parent, tag=self._plugin_id):
            build_section_title("ROIs", cfg_c["text_header"])

            dpg.add_text(
                "No Image Selected",
                tag=self._t("text_roi_active_title"),
                color=cfg_c["text_active"],
            )

            # --- TOP: Load & Import ---
            with dpg.group(horizontal=True):
                btn_rt = dpg.add_button(
                    label="Open RT-Struct...",
                    width=150,
                    callback=self.on_load_rtstruct_clicked,
                    tag=self._t("btn_roi_load_rtstruct"),
                )
                build_beginner_tooltip(
                    btn_rt,
                    "Click to load DICOM RT-Struct files.",
                    self.api,
                )

                btn_labels = dpg.add_button(
                    label="Open labels...",
                    width=150,
                    callback=self.on_load_labels_clicked,
                    tag=self._t("btn_roi_load_labels"),
                )
                build_beginner_tooltip(
                    btn_labels,
                    "Click to load a label map image (each unique integer value becomes a separate ROI).",
                    self.api,
                )

            with dpg.group(horizontal=True, tag=self._t("group_roi_binary_row")):
                btn_binary = dpg.add_button(
                    label="Open mask...",
                    width=90,
                    callback=self.on_load_binary_roi_clicked,
                    tag=self._t("btn_roi_load_binary"),
                )
                build_beginner_tooltip(
                    btn_binary,
                    "Click to binarize and load image mask files (e.g. NIfTI, TIFF, JPEG).",
                    self.api,
                )

                dpg.add_combo(
                    ["Ignore BG (val)", "Target FG (val)"],
                    default_value="Ignore BG (val)",
                    tag=self._t("combo_roi_mode"),
                    width=90,
                    callback=self.on_roi_mode_changed,
                )
                build_beginner_tooltip(
                    self._t("combo_roi_mode"),
                    "Choose how voxels are selected from the loaded image to form the ROI.",
                    self.api,
                )
                build_help_button(
                    "Ignore BG: Makes the specified value transparent and keeps everything else.\nTarget FG: Keeps only the exact value specified.",
                    self.api,
                )

                dpg.add_input_float(
                    default_value=0.0, step=1.0, width=90, tag=self._t("input_roi_val")
                )

            with dpg.group(horizontal=True):

                dpg.add_text(
                    "Add a simple ROI : ",
                    color=cfg_c["text_header"],
                )

                btn_sph_icon = dpg.add_button(
                    label="\uf111",
                    width=20,
                    callback=self.on_add_spheroid_clicked,
                    tag=self._t("btn_roi_add_spheroid_icon"),
                )

                dpg.add_spacer(width=5)

                btn_rec_icon = dpg.add_button(
                    label="\uf0c8",
                    width=20,
                    callback=self.on_add_rect_clicked,
                    tag=self._t("btn_roi_add_rect_icon"),
                )

                if dpg.does_item_exist("icon_font_tag"):
                    dpg.bind_item_font(btn_sph_icon, "icon_font_tag")
                    dpg.bind_item_font(btn_rec_icon, "icon_font_tag")

                build_beginner_tooltip(
                    btn_sph_icon,
                    "Create a new spheroid ROI centered at the crosshair.",
                    self.api,
                )
                build_beginner_tooltip(
                    btn_rec_icon,
                    "Create a new rectangular ROI centered at the crosshair (not implemented yet).",
                    self.api,
                )
                build_help_button(
                    "Spheroid/Box ROI creation:\n"
                    "- Click Sphere (circle) to create a spheroid ROI centered at the crosshair.\n"
                    "- Click Box (square) to create a rectangular box ROI centered at the crosshair.\n"
                    "- You can translate/resize these ROIs directly in the slice viewers or edit them in their statistics windows.",
                    self.api,
                )

            dpg.add_separator()
            dpg.add_spacer(height=10)

            # --- MIDDLE: Master List Controls ---
            with dpg.group(horizontal=True):
                btn_color_picker = dpg.add_color_edit(
                    default_value=[255, 255, 255, 255],
                    no_inputs=True,
                    no_label=True,
                    no_alpha=True,
                    width=20,
                    height=20,
                    tag=self._t("btn_roi_color_picker"),
                    callback=self.on_global_roi_color_picker_changed,
                )
                btn_show = dpg.add_button(
                    label="\uf06e",
                    width=20,
                    callback=self.on_roi_show_all,
                    tag=self._t("btn_roi_show_all"),
                )
                btn_contour = dpg.add_button(
                    label="\uf040",
                    width=20,
                    callback=self.on_roi_contour_all,
                    tag=self._t("btn_roi_contour_all"),
                )
                btn_hide = dpg.add_button(
                    label="\uf070",
                    width=20,
                    callback=self.on_roi_hide_all,
                    tag=self._t("btn_roi_hide_all"),
                )
                btn_roi_above_overlay = dpg.add_button(
                    label="\uf5fd",
                    width=20,
                    callback=self.on_roi_above_overlay_clicked,
                    tag=self._t("btn_roi_above_overlay"),
                )
                btn_close_all = dpg.add_button(
                    label="\uf00d",
                    width=20,
                    callback=self.on_roi_close_all,
                    tag=self._t("btn_roi_close_all"),
                )
                btn_toggle_all_stats = dpg.add_button(
                    label="\uf08e",
                    width=20,
                    callback=self.on_roi_toggle_all_stats,
                    tag=self._t("btn_roi_toggle_all_stats"),
                )
                btn_reload_all = dpg.add_button(
                    label="\uf01e",
                    width=20,
                    callback=self.on_roi_reload_all,
                    tag=self._t("btn_roi_reload_all"),
                    show=False,
                )
                build_help_button(
                    "Global ROI Actions:\n"
                    "- Show All (Raster) [Eye Icon]: Display all ROIs as solid filled regions.\n"
                    "- Show All (Contour) [Pencil Icon]: Display all ROIs as thin outlines.\n"
                    "- Hide All [Slashed Eye Icon]: Hide all ROIs from the slice views.\n"
                    "- Toggle ROI on top of Fusion [Layers Icon]: Render ROIs above or below overlay.\n"
                    "- Toggle All Stats [External Link Icon]: Open or close all statistics windows simultaneously.\n"
                    "- Close All [X Icon]: Permanently remove all ROIs from the current view state.",
                    self.api,
                )

                if dpg.does_item_exist("icon_font_tag"):
                    for btn in [
                        btn_show,
                        btn_contour,
                        btn_hide,
                        btn_toggle_all_stats,
                        btn_reload_all,
                        btn_roi_above_overlay,
                        btn_close_all,
                    ]:
                        dpg.bind_item_font(btn, "icon_font_tag")

                if dpg.does_item_exist("delete_button_theme"):
                    dpg.bind_item_theme(btn_close_all, "delete_button_theme")

                with dpg.tooltip(btn_color_picker):
                    dpg.add_text("Change color of all listed ROIs", tag=self._t("tooltip_roi_color_picker"))

                with dpg.tooltip(btn_show):
                    dpg.add_text("Show All (Raster)")

                with dpg.tooltip(btn_contour):
                    dpg.add_text("Show All (Contour)")

                with dpg.tooltip(btn_hide):
                    dpg.add_text("Hide All")

                with dpg.tooltip(btn_roi_above_overlay):
                    dpg.add_text("Toggle ROI on top of Fusion")

                with dpg.tooltip(btn_close_all):
                    dpg.add_text("Close All")

                with dpg.tooltip(btn_toggle_all_stats):
                    dpg.add_text("Toggle all statistics windows")

                with dpg.tooltip(btn_reload_all):
                    dpg.add_text("Reload all modified ROIs")

            dpg.add_spacer(height=2)

            with dpg.group(horizontal=True):
                dpg.add_text("Op:")
                dpg.add_slider_float(
                    tag=self._t("slider_roi_global_opacity"),
                    width=110,
                    min_value=0.0,
                    max_value=1.0,
                    default_value=0.5,
                    callback=self.on_roi_global_opacity_changed,
                )
                build_beginner_tooltip(
                    self._t("slider_roi_global_opacity"),
                    "Adjust raster transparency for all loaded ROIs simultaneously.",
                    self.api,
                )

                dpg.add_spacer(width=10)

                dpg.add_text("Thk:")
                dpg.add_slider_float(
                    tag=self._t("slider_roi_global_thickness"),
                    width=110,
                    min_value=0.5,
                    max_value=10.0,
                    default_value=1.0,
                    callback=self.on_roi_global_thickness_changed,
                )
                build_beginner_tooltip(
                    self._t("slider_roi_global_thickness"),
                    "Adjust contour line thickness for all loaded ROIs simultaneously.",
                    self.api,
                )

            dpg.add_separator()

            # Filter Group
            with dpg.group(
                tag=self._t("group_roi_filter"), show=False, horizontal=True
            ):
                btn_sort = dpg.add_button(
                    label="\uf0dc",
                    width=20,
                    tag=self._t("btn_roi_sort"),
                    callback=self.on_sort_rois_clicked,
                )
                if dpg.does_item_exist("icon_font_tag"):
                    dpg.bind_item_font(btn_sort, "icon_font_tag")

                dpg.add_text("Filter:", color=cfg_c["text_dim"])
                dpg.add_input_text(
                    tag=self._t("input_roi_filter"),
                    width=-30,
                    callback=self.on_roi_filter_changed,
                )
                build_beginner_tooltip(
                    self._t("input_roi_filter"),
                    "Type to search and filter the list of ROIs by name.",
                    self.api,
                )
                btn_clear_filter = dpg.add_button(
                    label="\uf00d",
                    width=20,
                    callback=self.on_clear_roi_filter_clicked,
                    tag=self._t("btn_clear_filter"),
                )
                if dpg.does_item_exist("icon_font_tag"):
                    dpg.bind_item_font(btn_clear_filter, "icon_font_tag")

            # Table child window
            with dpg.child_window(
                tag=self._t("roi_list_window"),
                height=300,
                border=False,
                no_scrollbar=True,
                no_scroll_with_mouse=True,
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
                    dpg.add_table_column(width_fixed=True, init_width_or_weight=20)

            dpg.add_spacer(height=5)

            # Export button
            dpg.add_button(
                label="Export All Stats to JSON",
                width=-1,
                callback=self.on_export_roi_stats_clicked,
                tag=self._t("btn_roi_export_stats"),
            )
            dpg.add_spacer(height=10)

            # --- BOTTOM: The Detail Panel ---
            with dpg.group(tag=self._t("roi_detail_header_group"), show=False):
                with dpg.group(horizontal=True):
                    dpg.add_text("Selected ROI Properties", color=cfg_c["text_header"])
                    btn_close_detail = dpg.add_button(
                        label="\uf057",
                        width=20,
                        callback=self.on_close_roi_properties,
                        tag=self._t("btn_close_detail"),
                    )
                    if dpg.does_item_exist("icon_font_tag"):
                        dpg.bind_item_font(btn_close_detail, "icon_font_tag")
                dpg.add_separator()

            with dpg.child_window(
                tag=self._t("roi_detail_window"),
                border=False,
                no_scrollbar=True,
                no_scroll_with_mouse=True,
                show=False,
            ):
                with dpg.group(tag=self._t("roi_detail_container")):
                    pass

        self.refresh_rois_ui()

    def refresh_rois_ui(self):
        table_id = self._t("roi_list_table")
        if not dpg.does_item_exist(table_id):
            return

        current_scroll = dpg.get_y_scroll(table_id)

        # Explicitly delete children with custom tags to release their aliases in DPG registry
        for viewer in self.api.get_viewers().values():
            if viewer.view_state:
                for roi_id in list(viewer.view_state.rois.keys()):
                    for tag in (
                        self._t(f"list_color_picker_{roi_id}"),
                        self._t(f"input_roi_name_{roi_id}"),
                    ):
                        if dpg.does_item_exist(tag):
                            dpg.delete_item(tag)

        # Delete row children inside table slot 1
        dpg.delete_item(table_id, children_only=True, slot=1)
        self.roi_selectables.clear()

        assert self.api is not None
        viewer = self.api.get_active_viewer()
        is_mip = bool(
            viewer
            and viewer.image_id
            and self.api.is_mip_active(viewer.image_id, viewer.tag)
        )
        has_image = bool(
            viewer and viewer.image_id and self.api.get_volumes().get(viewer.image_id)
        )
        has_rois = bool(has_image and viewer.view_state and viewer.view_state.rois)

        load_controls = [
            "btn_roi_load_rtstruct",
            "btn_roi_load_labels",
            "btn_roi_load_binary",
            "combo_roi_mode",
            "input_roi_val",
        ]
        for name in load_controls:
            tag = self._t(name)
            if dpg.does_item_exist(tag):
                dpg.configure_item(tag, enabled=has_image and not is_mip)

        roi_controls = [
            "btn_roi_color_picker",
            "btn_roi_show_all",
            "btn_roi_contour_all",
            "btn_roi_hide_all",
            "btn_roi_close_all",
            "btn_roi_toggle_all_stats",
            "btn_roi_reload_all",
            "btn_roi_sort",
            "btn_clear_filter",
            "btn_roi_export_stats",
            "slider_roi_global_opacity",
            "slider_roi_global_thickness",
            "input_roi_filter",
            "btn_roi_above_overlay",
        ]
        for name in roi_controls:
            tag = self._t(name)
            if dpg.does_item_exist(tag):
                enabled = has_rois and not is_mip
                if name == "btn_roi_above_overlay":
                    has_overlay = bool(viewer and viewer.view_state and viewer.view_state.display.overlay.image_id)
                    enabled = enabled and has_overlay
                dpg.configure_item(tag, enabled=enabled)

        if dpg.does_item_exist(self._t("btn_roi_above_overlay")) and viewer and viewer.view_state:
            val = getattr(viewer.view_state.display, "roi_above_overlay", False)
            if hasattr(val, "mock_calls"):
                val = False
            else:
                val = bool(val)
            if val:
                if dpg.does_item_exist("active_nav_button_theme"):
                    dpg.bind_item_theme(self._t("btn_roi_above_overlay"), "active_nav_button_theme")
            else:
                dpg.bind_item_theme(self._t("btn_roi_above_overlay"), 0)

        if dpg.does_item_exist(self._t("text_roi_active_title")):
            if (
                viewer
                and viewer.image_id
                and self.api.get_volumes().get(viewer.image_id)
            ):
                name_str, is_outdated = self.api.get_image_display_name(viewer.image_id)
                dpg.set_value(self._t("text_roi_active_title"), name_str)
                col = (
                    self.api.ui_cfg["colors"]["outdated"]
                    if is_outdated
                    else self.api.ui_cfg["colors"]["text_active"]
                )
                dpg.configure_item(self._t("text_roi_active_title"), color=col)
            else:
                dpg.set_value(self._t("text_roi_active_title"), "No Image Selected")
                dpg.configure_item(
                    self._t("text_roi_active_title"),
                    color=self.api.ui_cfg["colors"]["text_active"],
                )

        if not viewer or not viewer.view_state or not viewer.view_state.rois:
            if dpg.does_item_exist(self._t("group_roi_filter")):
                dpg.configure_item(self._t("group_roi_filter"), show=False)
            if dpg.does_item_exist(self._t("btn_roi_reload_all")):
                dpg.configure_item(self._t("btn_roi_reload_all"), show=False)
            self.refresh_roi_detail_ui()
            return

        vs_id = viewer.image_id
        color_picker_tag = self._t("btn_roi_color_picker")
        if dpg.does_item_exist(color_picker_tag):
            filter_text = self._c.roi_filters.get(vs_id, "").lower()
            matching_colors = []
            for roi in viewer.view_state.rois.values():
                if filter_text and filter_text not in roi.name.lower():
                    continue
                matching_colors.append(tuple(roi.color[:3]))

            unique_colors = set(matching_colors)
            tooltip_tag = self._t("tooltip_roi_color_picker")

            if not matching_colors:
                dpg.set_value(color_picker_tag, [255, 255, 255, 255])
                if dpg.does_item_exist(tooltip_tag):
                    dpg.set_value(tooltip_tag, "No ROIs listed")
            elif len(unique_colors) == 1:
                # All listed ROIs share the same color
                single_color = list(matching_colors[0])
                dpg.set_value(color_picker_tag, single_color + [255])
                if dpg.does_item_exist(tooltip_tag):
                    dpg.set_value(tooltip_tag, "Change color of all listed ROIs (currently sharing this color)")
            else:
                # Mixed colors: set alpha to 0 for checkerboard, fallback to neutral gray
                dpg.set_value(color_picker_tag, [127, 127, 127, 0])
                if dpg.does_item_exist(tooltip_tag):
                    dpg.set_value(tooltip_tag, "Change color of all listed ROIs (currently mixed colors)")

        filter_text = self._c.roi_filters.get(vs_id, "")
        sort_order = self._c.roi_sort_orders.get(vs_id, 0)

        if dpg.does_item_exist(self._t("input_roi_filter")) and not dpg.is_item_focused(
            self._t("input_roi_filter")
        ):
            dpg.set_value(self._t("input_roi_filter"), filter_text)

        if dpg.does_item_exist(self._t("btn_roi_sort")):
            if sort_order == 1:
                dpg.configure_item(self._t("btn_roi_sort"), label="\uf15d")
            elif sort_order == -1:
                dpg.configure_item(self._t("btn_roi_sort"), label="\uf15e")
            else:
                dpg.configure_item(self._t("btn_roi_sort"), label="\uf0dc")

        total_rois = len(viewer.view_state.rois)
        if dpg.does_item_exist(self._t("group_roi_filter")):
            dpg.configure_item(self._t("group_roi_filter"), show=total_rois > 10)

        any_outdated = False
        for roi_id in viewer.view_state.rois:
            rvol = self.api.get_volumes().get(roi_id)
            if rvol and getattr(rvol, "_is_outdated", False):
                any_outdated = True
                break
        if dpg.does_item_exist(self._t("btn_roi_reload_all")):
            dpg.configure_item(self._t("btn_roi_reload_all"), show=any_outdated)

        roi_items = list(viewer.view_state.rois.items())
        if sort_order == 1:
            roi_items.sort(key=lambda x: x[1].name.lower())
        elif sort_order == -1:
            roi_items.sort(key=lambda x: x[1].name.lower(), reverse=True)

        for roi_id, roi in roi_items:
            if filter_text and filter_text not in roi.name.lower():
                continue

            with dpg.table_row(parent=table_id):
                if roi.visible:
                    lbl_eye = "\uf040" if roi.is_contour else "\uf06e"
                else:
                    lbl_eye = "\uf070"

                dpg.add_color_edit(
                    default_value=roi.color + [255],
                    no_inputs=True,
                    no_label=True,
                    no_alpha=True,
                    width=20,
                    height=20,
                    tag=self._t(f"list_color_picker_{roi_id}"),
                    user_data=roi_id,
                    callback=self.on_roi_color_changed,
                )

                is_active = roi_id == self._c.active_roi_id
                roi_vol = self.api.get_volumes().get(roi_id)
                is_outdated = roi_vol._is_outdated if roi_vol else False

                with dpg.group(horizontal=True):
                    input_id = dpg.add_input_text(
                        tag=self._t(f"input_roi_name_{roi_id}"),
                        default_value=roi.name,
                        width=-15 if is_outdated else -1,
                        user_data=roi_id,
                        callback=self.on_roi_name_changed,
                    )
                    if is_outdated:
                        dpg.add_text("*", color=self.api.ui_cfg["colors"]["outdated"])

                self.roi_selectables[roi_id] = input_id
                dpg.bind_item_handler_registry(
                    input_id, self._t("item_clicked_handler")
                )

                if is_active:
                    dpg.bind_item_theme(
                        input_id,
                        (
                            self._t("outdated_active_roi_input_theme")
                            if is_outdated
                            else self._t("active_input_theme")
                        ),
                    )
                else:
                    dpg.bind_item_theme(
                        input_id,
                        (
                            self._t("outdated_inactive_roi_input_theme")
                            if is_outdated
                            else self._t("inactive_input_theme")
                        ),
                    )

                btn_eye = dpg.add_button(
                    label=lbl_eye,
                    width=20,
                    user_data=roi_id,
                    callback=self.on_roi_toggle_visible,
                )
                btn_center = dpg.add_button(
                    label="\uf05b",
                    width=20,
                    user_data=roi_id,
                    callback=self.on_roi_center,
                )
                btn_stats = dpg.add_button(
                    label="\uf08e",
                    width=20,
                    user_data=roi_id,
                    callback=self.on_roi_stats_toggle,
                )
                with dpg.tooltip(btn_stats):
                    dpg.add_text("Toggle ROI statistics window")

                source_type = getattr(roi, "source_type", "Binary")

                if is_outdated:
                    btn_action = dpg.add_button(
                        label="\uf01e",
                        width=20,
                        user_data=roi_id,
                        callback=self.on_roi_reload,
                    )
                    with dpg.tooltip(btn_action):
                        dpg.add_text("Reload modified file")
                else:
                    btn_action = dpg.add_button(
                        label="\uf0c7",
                        width=20,
                        user_data=roi_id,
                        callback=self.on_roi_save,
                    )
                    with dpg.tooltip(btn_action):
                        if source_type == "Binary":
                            dpg.add_text("Save ROI As...")
                        else:
                            dpg.add_text("Extract & Save ROI")

                btn_close = dpg.add_button(
                    label="\uf00d",
                    width=20,
                    user_data=roi_id,
                    callback=self.on_roi_close,
                )

                if dpg.does_item_exist("icon_font_tag"):
                    for btn in [btn_eye, btn_action, btn_center, btn_stats, btn_close]:
                        dpg.bind_item_font(btn, "icon_font_tag")

                if dpg.does_item_exist("delete_button_theme"):
                    dpg.bind_item_theme(btn_close, "delete_button_theme")

                if is_mip:
                    for btn in [btn_eye, btn_action, btn_center, btn_stats, btn_close]:
                        dpg.configure_item(btn, enabled=False)

        if getattr(self._c, "_scroll_to_active", False):
            self._c._scroll_to_active = False
            if self._c.active_roi_id and self._c.active_roi_id in self.roi_selectables:
                try:
                    active_idx = list(self.roi_selectables.keys()).index(
                        self._c.active_roi_id
                    )
                    row_height = 28.0  # Estimated height with padding
                    item_top = active_idx * row_height
                    item_bottom = item_top + row_height
                    view_height = (
                        dpg.get_item_height(self._t("roi_list_window")) or 300.0
                    )
                    scroll_max = dpg.get_y_scroll_max(table_id)

                    if item_top < current_scroll:
                        current_scroll = max(0.0, item_top)
                    elif item_bottom > current_scroll + view_height:
                        current_scroll = min(
                            scroll_max, item_bottom - view_height + 4.0
                        )
                except Exception:
                    pass

        dpg.set_y_scroll(table_id, current_scroll)
        self.refresh_all_open_stats_windows()
        self.refresh_roi_detail_ui()

    def refresh_roi_detail_ui(self):
        container = self._t("roi_detail_container")
        header = self._t("roi_detail_header_group")
        window = self._t("roi_detail_window")
        if not dpg.does_item_exist(container):
            return

        assert self.api is not None
        viewer = self.api.get_active_viewer()

        has_selection = (
            viewer
            and viewer.view_state
            and self._c.active_roi_id
            and self._c.active_roi_id in viewer.view_state.rois
        )

        if not has_selection:
            if dpg.does_item_exist(header):
                dpg.configure_item(header, show=False)
            if dpg.does_item_exist(window):
                dpg.configure_item(window, show=False)
            dpg.delete_item(container, children_only=True)
            dpg.add_text(
                "Select a ROI from the list above.",
                color=self.api.ui_cfg["colors"]["text_dim"],
                parent=container,
            )
            self.api.on_window_resize()
            return

        if dpg.does_item_exist(header):
            dpg.configure_item(header, show=True)
        if dpg.does_item_exist(window):
            dpg.configure_item(window, show=True)

        dpg.delete_item(container, children_only=True)

        roi_state = viewer.view_state.rois[self._c.active_roi_id]
        roi_vol = self.api.get_volumes().get(self._c.active_roi_id)
        dim_col = self.api.ui_cfg["colors"]["text_dim"]

        with dpg.group(parent=container):
            # Opacity/Thickness
            with dpg.group(horizontal=True):
                if getattr(roi_state, "is_contour", False):
                    dpg.add_text("Thickness:")
                    active_slider_tag = self._t("slider_roi_thickness")
                    dpg.add_slider_float(
                        default_value=getattr(roi_state, "thickness", 1.0),
                        min_value=0.5,
                        max_value=10.0,
                        width=-1,
                        tag=active_slider_tag,
                        user_data=self._c.active_roi_id,
                        callback=self.on_roi_thickness_changed,
                    )
                else:
                    dpg.add_text("Opacity:")
                    active_slider_tag = self._t("slider_roi_opacity")
                    dpg.add_slider_float(
                        default_value=getattr(roi_state, "opacity", 0.5),
                        min_value=0.0,
                        max_value=1.0,
                        width=-1,
                        tag=active_slider_tag,
                        user_data=self._c.active_roi_id,
                        callback=self.on_roi_opacity_changed,
                    )

            # Custom grab theme color matching active ROI color
            theme_tag = self._t("dynamic_roi_slider_theme")
            if dpg.does_item_exist(theme_tag):
                dpg.delete_item(theme_tag)
            with dpg.theme(tag=theme_tag):
                with dpg.theme_component(dpg.mvSliderFloat):
                    r, g, b = getattr(roi_state, "color", [255, 0, 0])
                    dpg.add_theme_color(dpg.mvThemeCol_SliderGrab, [r, g, b, 255])
                    dpg.add_theme_color(
                        dpg.mvThemeCol_SliderGrabActive,
                        [min(255, r + 40), min(255, g + 40), min(255, b + 40), 255],
                    )
                    dpg.add_theme_color(dpg.mvThemeCol_FrameBgActive, [r, g, b, 100])
                    dpg.add_theme_color(dpg.mvThemeCol_FrameBgHovered, [r, g, b, 50])
            dpg.bind_item_theme(active_slider_tag, theme_tag)

            dpg.add_spacer(height=5)

            # 6. Stats Summary
            with dpg.table(header_row=False, borders_innerH=False):
                dpg.add_table_column(width_stretch=True)
                dpg.add_table_column(width_stretch=True)
                with dpg.table_row():
                    with dpg.group(horizontal=True):
                        dpg.add_text("Vol:", color=dim_col)
                        dpg.add_text("---", tag=self._t("roi_stat_vol"))
                    with dpg.group(horizontal=True):
                        dpg.add_text("Mean:", color=dim_col)
                        dpg.add_text("---", tag=self._t("roi_stat_mean"))
                with dpg.table_row():
                    with dpg.group(horizontal=True):
                        dpg.add_text("Max:", color=dim_col)
                        dpg.add_text("---", tag=self._t("roi_stat_max"))
                    with dpg.group(horizontal=True):
                        dpg.add_text("Min:", color=dim_col)
                        dpg.add_text("---", tag=self._t("roi_stat_min"))
                with dpg.table_row():
                    with dpg.group(horizontal=True):
                        dpg.add_text("Std:", color=dim_col)
                        dpg.add_text("---", tag=self._t("roi_stat_std"))
                    with dpg.group(horizontal=True):
                        peak_lbl = dpg.add_text("Peak:", color=dim_col)
                        with dpg.tooltip(peak_lbl):
                            dpg.add_text(
                                "95th percentile of intensity values inside the ROI"
                            )
                        dpg.add_text("---", tag=self._t("roi_stat_peak"))
                with dpg.table_row():
                    with dpg.group(horizontal=True):
                        dpg.add_text("Mass:", color=dim_col)
                        dpg.add_text("---", tag=self._t("roi_stat_mass"))


        self.update_roi_stats_ui()
        self.api.on_window_resize()

    def show_rtstruct_selection_modal(self, filepath, rois_info):
        modal_tag = self._t("rtstruct_selection_modal")
        if dpg.does_item_exist(modal_tag):
            dpg.delete_item(modal_tag)

        self._rtstruct_cb_ids = []

        viewer = self.api.get_active_viewer()
        image_id = viewer.image_id if (viewer and viewer.image_id) else ""
        name_str = ""
        if image_id:
            name_str, _ = self.api.get_image_display_name(image_id)
        label_title = (
            f"Select ROIs to Load - {name_str}" if name_str else "Select ROIs to Load"
        )

        with dpg.window(
            tag=modal_tag,
            modal=True,
            show=True,
            label=label_title,
            no_collapse=True,
            width=450,
            height=500,
        ):
            dpg.add_text(
                f"File: {os.path.basename(filepath)}",
                color=self.api.ui_cfg["colors"]["text_dim"],
            )
            dpg.add_spacer(height=5)

            with dpg.group(horizontal=True):
                dpg.add_button(
                    label="Select All",
                    callback=lambda: [
                        dpg.set_value(cb_id, True) for cb_id in self._rtstruct_cb_ids
                    ],
                )
                dpg.add_button(
                    label="Select None",
                    callback=lambda: [
                        dpg.set_value(cb_id, False) for cb_id in self._rtstruct_cb_ids
                    ],
                )

            dpg.add_separator()

            with dpg.child_window(height=-40, border=False):
                for i, r_info in enumerate(rois_info):
                    cb_id = dpg.generate_uuid()
                    self._rtstruct_cb_ids.append(cb_id)
                    with dpg.group(horizontal=True):
                        dpg.add_checkbox(default_value=True, tag=cb_id)

                        color = r_info.get("color", [255, 0, 0])
                        if not isinstance(color, (list, tuple)) or len(color) < 3:
                            color = [255, 0, 0]
                        try:
                            r, g, b = [max(0, min(255, int(c))) for c in color[:3]]
                        except Exception:
                            r, g, b = 255, 0, 0

                        dpg.add_color_edit(
                            default_value=[r, g, b, 255],
                            no_inputs=True,
                            no_label=True,
                            no_alpha=True,
                            width=20,
                            height=20,
                        )

                        name = r_info.get("name")
                        dpg.add_text(str(name) if name else f"ROI {i}")

            dpg.add_separator()
            with dpg.group(horizontal=True):
                dpg.add_spacer(width=250)
                dpg.add_button(
                    label="Cancel",
                    width=80,
                    callback=lambda: dpg.delete_item(modal_tag),
                )

                def _on_load():
                    selected_indices = [
                        i
                        for i, cb_id in enumerate(self._rtstruct_cb_ids)
                        if dpg.get_value(cb_id)
                    ]
                    dpg.delete_item(modal_tag)
                    if not selected_indices:
                        return

                    selected_rois = [rois_info[i] for i in selected_indices]
                    viewer = self.api.get_active_viewer()
                    if viewer and viewer.image_id:
                        self.api.load_rtstruct(viewer.image_id, filepath, selected_rois)

                dpg.add_button(label="Load", width=80, callback=_on_load)

        vp_width = max(dpg.get_viewport_client_width(), 800)
        vp_height = max(dpg.get_viewport_client_height(), 600)
        dpg.set_item_pos(modal_tag, [vp_width // 2 - 225, vp_height // 2 - 250])

    def on_roi_input_clicked(self, sender, app_data, user_data):
        if not app_data or len(app_data) < 2:
            return
        item_id = app_data[1]
        roi_id = dpg.get_item_user_data(item_id)
        if roi_id and self._c.active_roi_id != roi_id:
            self._c.on_roi_selected(roi_id)

    def on_load_rtstruct_clicked(self, sender, app_data, user_data):
        viewer = self.api.get_active_viewer()
        if not viewer or not viewer.image_id:
            self.api.notify("Select a base image first!", color=[255, 100, 100])
            return

        from vvv.ui.file_dialog import open_file_dialog

        file_paths = open_file_dialog(
            "Load RT-Struct", multiple=False, extensions=["dcm"]
        )
        if not file_paths:
            return

        first_file = file_paths[0] if isinstance(file_paths, list) else file_paths

        try:
            rois_info = self.api.parse_rtstruct(first_file)
        except Exception as e:
            self.api.show_message("Error", f"Failed to parse RT-Struct:\n{e}")
            return

        if not rois_info:
            self.api.show_message(
                "No ROIs", "No valid ROIs found in this RT-Struct file."
            )
            return

        self.show_rtstruct_selection_modal(first_file, rois_info)

    def on_load_labels_clicked(self, sender, app_data, user_data):
        viewer = self.api.get_active_viewer()
        if not viewer or not viewer.image_id:
            self.api.notify("Select a base image first!", color=[255, 100, 100])
            return

        from vvv.ui.file_dialog import open_file_dialog

        file_paths = open_file_dialog("Load Labels Image", multiple=False)
        if not file_paths:
            return

        self.api.load_label_map(viewer.image_id, file_paths)

    def on_load_binary_roi_clicked(self, sender, app_data, user_data):
        viewer = self.api.get_active_viewer()
        if not viewer or not viewer.image_id:
            self.api.notify("Select a base image first!", color=[255, 100, 100])
            return

        mode = (
            dpg.get_value(self._t("combo_roi_mode"))
            if dpg.does_item_exist(self._t("combo_roi_mode"))
            else "Ignore BG (val)"
        )
        val = (
            dpg.get_value(self._t("input_roi_val"))
            if dpg.does_item_exist(self._t("input_roi_val"))
            else 0.0
        )

        from vvv.ui.file_dialog import open_file_dialog

        file_paths = open_file_dialog("Load Binary Image(s)", multiple=True)
        if not file_paths:
            return

        if isinstance(file_paths, str):
            file_paths = [file_paths]

        self.api.load_batch_rois(viewer.image_id, file_paths, "Binary Mask", mode, val)

    def on_roi_mode_changed(self, sender, app_data, user_data):
        pass

    def on_roi_toggle_visible(self, sender, app_data, user_data):
        roi_id = user_data
        viewer = self.api.get_active_viewer()
        if not viewer or not viewer.view_state:
            return
        vs = viewer.view_state
        roi = vs.rois[roi_id]

        if roi.visible and not roi.is_contour:
            roi.visible = True
            roi.is_contour = True
            for ori in roi.polygons:
                roi.polygons[ori].clear()
        elif roi.visible and roi.is_contour:
            roi.visible = False
            roi.is_contour = False
        else:
            roi.visible = True
            roi.is_contour = False

        vs.is_data_dirty = True
        vs.is_geometry_dirty = True
        self.api.request_refresh()
        self.api.update_all_viewers_of_image(viewer.image_id)

    def on_roi_color_changed(self, sender, app_data, user_data):
        roi_id = user_data
        viewer = self.api.get_active_viewer()
        if not viewer or not viewer.view_state:
            return
        vs = viewer.view_state
        scale = 255.0 if all(c <= 1.0 for c in app_data) else 1.0
        vs.rois[roi_id].color = [int(c * scale) for c in app_data[:3]]
        vs.is_data_dirty = True
        self._sync_roi_color_ui(roi_id, sender)
        self.api.update_all_viewers_of_image(viewer.image_id)

    def on_global_roi_color_picker_changed(self, sender, app_data, user_data):
        viewer = self.api.get_active_viewer()
        if not viewer or not viewer.view_state or not viewer.view_state.rois:
            return
        vs = viewer.view_state
        vs_id = viewer.image_id
        filter_text = self._c.roi_filters.get(vs_id, "").lower()
        scale = 255.0 if all(c <= 1.0 for c in app_data) else 1.0
        new_color = [int(c * scale) for c in app_data[:3]]

        changed = False
        for roi_id, roi in list(vs.rois.items()):
            if filter_text and filter_text not in roi.name.lower():
                continue
            roi.color = list(new_color)
            self._sync_roi_color_ui(roi_id, sender)
            changed = True

        if changed:
            vs.is_data_dirty = True
            self.api.update_all_viewers_of_image(viewer.image_id)

    def _sync_roi_color_ui(self, roi_id, sender=None):
        """Sync all color-related UI elements for a given ROI after its color changed.

        Updates: the stats window color picker, the stats window title theme,
        and the detail panel slider grab theme.  *sender* is the widget that
        triggered the change — it is skipped to avoid feedback loops.
        """
        viewer = self.api.get_active_viewer()
        if not viewer or not viewer.view_state or roi_id not in viewer.view_state.rois:
            return
        roi = viewer.view_state.rois[roi_id]
        rgb = roi.color[:3]

        # 1. Sync color pickers (skip the one that triggered the change)
        for picker_tag in (
            self._t(f"list_color_picker_{roi_id}"),
            self._t(f"stats_color_picker_{roi_id}"),
            self._t("btn_roi_color_picker"),
        ):
            if dpg.does_item_exist(picker_tag) and picker_tag != sender:
                dpg.set_value(picker_tag, rgb + [255])

        # 2. Update stats window title theme
        win_tag = self._t(f"stats_win_{roi_id}")
        if dpg.does_item_exist(win_tag):
            theme_tag = self._t(f"stats_theme_{roi_id}")
            if dpg.does_item_exist(theme_tag):
                dpg.delete_item(theme_tag, children_only=True)
            else:
                dpg.add_theme(tag=theme_tag)

            r, g, b = rgb
            luminance = 0.299 * r + 0.587 * g + 0.114 * b
            text_color = [0, 0, 0, 255] if luminance > 128 else [255, 255, 255, 255]
            with dpg.theme_component(dpg.mvWindowAppItem, parent=theme_tag):
                dpg.add_theme_color(dpg.mvThemeCol_TitleBg, rgb + [255])
                dpg.add_theme_color(dpg.mvThemeCol_TitleBgActive, rgb + [255])
                dpg.add_theme_color(dpg.mvThemeCol_Text, text_color)
            dpg.bind_item_theme(win_tag, theme_tag)

            # Also sync the slider theme inside the stats window
            slider_theme_tag = self._t(f"stats_slider_theme_{roi_id}")
            if dpg.does_item_exist(slider_theme_tag):
                dpg.delete_item(slider_theme_tag, children_only=True)
                with dpg.theme_component(dpg.mvSliderFloat, parent=slider_theme_tag):
                    dpg.add_theme_color(dpg.mvThemeCol_SliderGrab, [r, g, b, 255])
                    dpg.add_theme_color(
                        dpg.mvThemeCol_SliderGrabActive,
                        [min(255, r + 40), min(255, g + 40), min(255, b + 40), 255],
                    )
                    dpg.add_theme_color(dpg.mvThemeCol_FrameBgActive, [r, g, b, 100])
                    dpg.add_theme_color(dpg.mvThemeCol_FrameBgHovered, [r, g, b, 50])

        # 3. Update detail panel slider theme if this ROI is selected
        if self._c.active_roi_id == roi_id:
            detail_theme = self._t("dynamic_roi_slider_theme")
            if dpg.does_item_exist(detail_theme):
                dpg.delete_item(detail_theme, children_only=True)
                r, g, b = rgb
                with dpg.theme_component(dpg.mvSliderFloat, parent=detail_theme):
                    dpg.add_theme_color(dpg.mvThemeCol_SliderGrab, [r, g, b, 255])
                    dpg.add_theme_color(
                        dpg.mvThemeCol_SliderGrabActive,
                        [min(255, r + 40), min(255, g + 40), min(255, b + 40), 255],
                    )
                    dpg.add_theme_color(dpg.mvThemeCol_FrameBgActive, [r, g, b, 100])
                    dpg.add_theme_color(dpg.mvThemeCol_FrameBgHovered, [r, g, b, 50])

    def on_roi_name_changed(self, sender, app_data, user_data):
        roi_id = user_data
        new_name = app_data
        viewer = self.api.get_active_viewer()
        if not viewer or not viewer.view_state:
            return
        vs = viewer.view_state
        if roi_id in vs.rois:
            vs.rois[roi_id].name = new_name

        roi_vol = self.api.get_volumes().get(roi_id)
        if roi_vol:
            roi_vol.name = new_name

    def on_roi_center(self, sender, app_data, user_data):
        viewer = self.api.get_active_viewer()
        if viewer and viewer.image_id:
            self.api.center_on_roi(viewer.image_id, user_data)

    def on_roi_reload(self, sender, app_data, user_data):
        viewer = self.api.get_active_viewer()
        if viewer and viewer.image_id:
            self.api.reload_roi(viewer.image_id, user_data)

    def on_roi_reload_all(self, sender, app_data, user_data):
        viewer = self.api.get_active_viewer()
        if not viewer or not viewer.image_id or not viewer.view_state:
            return
        outdated_ids = []
        for roi_id in list(viewer.view_state.rois.keys()):
            roi_vol = self.api.get_volumes().get(roi_id)
            if roi_vol and getattr(roi_vol, "_is_outdated", False):
                outdated_ids.append(roi_id)
        for roi_id in outdated_ids:
            if roi_id in viewer.view_state.rois:
                self.api.reload_roi(viewer.image_id, roi_id)

    def on_roi_save(self, sender, app_data, user_data):
        roi_id = user_data
        roi_vol = self.api.get_volumes().get(roi_id)
        if not roi_vol:
            return

        default_name = roi_vol.name
        if not default_name.lower().endswith(".nii.gz"):
            default_name += ".nii.gz"

        from vvv.ui.file_dialog import save_file_dialog

        file_path = save_file_dialog("Save ROI As", default_name=default_name)
        if file_path:
            self.api.notify(f"Saving {roi_vol.name}...")
            stop = self._c._stop_event

            def _save():
                self.api.save_image(roi_id, file_path)

                if stop.is_set():
                    return

                def _on_done():
                    for vs in self.api.get_view_states().values():
                        if roi_id in vs.rois:
                            r = vs.rois[roi_id]
                            r.source_type = "Binary"
                            r.source_mode = "Target FG (val)"
                            r.source_val = 1.0
                            r.rtstruct_info = None
                    self.api.notify(f"Saved: {os.path.basename(file_path)}")
                    self.api.request_refresh()

                self.api.run_on_main_thread(_on_done)

            import threading
            threading.Thread(target=_save, daemon=True).start()

    def on_roi_stats_radius_x_slider_changed(self, sender, app_data, user_data):
        roi_id = user_data
        viewer = self.api.get_active_viewer()
        if not viewer or not viewer.image_id or not viewer.view_state:
            return
        base_vol = self.api.get_volumes().get(viewer.image_id)
        roi_vol = self.api.get_volumes().get(roi_id)
        roi_state = viewer.view_state.rois.get(roi_id)
        if not base_vol or not roi_vol or not roi_state:
            return
        new_r_mm = float(app_data)
        new_r_mm = max(new_r_mm, 0.5)

        roi_state.spheroid_radius_x = new_r_mm
        roi_state.spheroid_radius_xy = new_r_mm
        roi_state.spheroid_radius = new_r_mm
        self._c.update_spheroid_mask(
            base_vol,
            roi_vol,
            roi_state,
            new_r_x_mm=new_r_mm,
        )

        for ori in roi_state.polygons:
            roi_state.polygons[ori].clear()

        viewer.view_state.is_geometry_dirty = True
        viewer.view_state.is_data_dirty = True
        self.api.update_all_viewers_of_image(viewer.image_id, data_dirty=True)
        if sender is None:
            self.api.request_refresh()
            self.refresh_all_open_stats_windows()

    def on_roi_stats_radius_slider_changed(self, sender, app_data, user_data):
        self.on_roi_stats_radius_x_slider_changed(sender, app_data, user_data)

    def on_roi_stats_radius_x_step_callback(self, sender, app_data, user_data):
        tag = user_data["tag"]
        prefix = self._t("slider_roi_radius_x_")
        if not tag.startswith(prefix):
            return
        roi_id = tag[len(prefix) :]

        viewer = self.api.get_active_viewer()
        if not viewer or not viewer.image_id or not viewer.view_state:
            return
        roi_state = viewer.view_state.rois.get(roi_id)
        if not roi_state:
            return

        direction = user_data["dir"]
        current_r = (
            getattr(roi_state, "spheroid_radius_x", None)
            or getattr(roi_state, "spheroid_radius_xy", None)
            or getattr(roi_state, "spheroid_radius", 10.0)
        )

        step_size = 1.0
        new_r = max(0.5, current_r + (step_size * direction))

        if dpg.does_item_exist(tag):
            dpg.set_value(tag, new_r)

        self.on_roi_stats_radius_x_slider_changed(None, new_r, roi_id)

    def on_roi_stats_radius_step_callback(self, sender, app_data, user_data):
        self.on_roi_stats_radius_x_step_callback(sender, app_data, user_data)

    def on_roi_stats_radius_y_slider_changed(self, sender, app_data, user_data):
        roi_id = user_data
        viewer = self.api.get_active_viewer()
        if not viewer or not viewer.image_id or not viewer.view_state:
            return
        base_vol = self.api.get_volumes().get(viewer.image_id)
        roi_vol = self.api.get_volumes().get(roi_id)
        roi_state = viewer.view_state.rois.get(roi_id)
        if not base_vol or not roi_vol or not roi_state:
            return
        new_r_mm = float(app_data)
        new_r_mm = max(new_r_mm, 0.5)

        roi_state.spheroid_radius_y = new_r_mm
        self._c.update_spheroid_mask(
            base_vol,
            roi_vol,
            roi_state,
            new_r_y_mm=new_r_mm,
        )

        for ori in roi_state.polygons:
            roi_state.polygons[ori].clear()

        viewer.view_state.is_geometry_dirty = True
        viewer.view_state.is_data_dirty = True
        self.api.update_all_viewers_of_image(viewer.image_id, data_dirty=True)
        if sender is None:
            self.api.request_refresh()
            self.refresh_all_open_stats_windows()

    def on_roi_stats_radius_y_step_callback(self, sender, app_data, user_data):
        tag = user_data["tag"]
        prefix = self._t("slider_roi_radius_y_")
        if not tag.startswith(prefix):
            return
        roi_id = tag[len(prefix) :]

        viewer = self.api.get_active_viewer()
        if not viewer or not viewer.image_id or not viewer.view_state:
            return
        roi_state = viewer.view_state.rois.get(roi_id)
        if not roi_state:
            return

        direction = user_data["dir"]
        current_r = (
            getattr(roi_state, "spheroid_radius_y", None)
            or getattr(roi_state, "spheroid_radius_xy", None)
            or getattr(roi_state, "spheroid_radius", 10.0)
        )

        step_size = 1.0
        new_r = max(0.5, current_r + (step_size * direction))

        if dpg.does_item_exist(tag):
            dpg.set_value(tag, new_r)

        self.on_roi_stats_radius_y_slider_changed(None, new_r, roi_id)

    def on_roi_stats_radius_z_slider_changed(self, sender, app_data, user_data):
        roi_id = user_data
        viewer = self.api.get_active_viewer()
        if not viewer or not viewer.image_id or not viewer.view_state:
            return
        base_vol = self.api.get_volumes().get(viewer.image_id)
        roi_vol = self.api.get_volumes().get(roi_id)
        roi_state = viewer.view_state.rois.get(roi_id)
        if not base_vol or not roi_vol or not roi_state:
            return

        new_r_z_mm = float(app_data)
        new_r_z_mm = max(new_r_z_mm, 0.5)

        roi_state.spheroid_radius_z = new_r_z_mm
        self._c.update_spheroid_mask(
            base_vol,
            roi_vol,
            roi_state,
            new_r_x_mm=getattr(roi_state, "spheroid_radius_x", None)
            or getattr(roi_state, "spheroid_radius_xy", None)
            or getattr(roi_state, "spheroid_radius", 10.0),
            new_r_y_mm=getattr(roi_state, "spheroid_radius_y", None)
            or getattr(roi_state, "spheroid_radius_xy", None)
            or getattr(roi_state, "spheroid_radius", 10.0),
            new_r_z_mm=new_r_z_mm,
        )

        for ori in roi_state.polygons:
            roi_state.polygons[ori].clear()

        viewer.view_state.is_geometry_dirty = True
        viewer.view_state.is_data_dirty = True
        self.api.update_all_viewers_of_image(viewer.image_id, data_dirty=True)
        if sender is None:
            self.api.request_refresh()
            self.refresh_all_open_stats_windows()

    def on_roi_stats_radius_z_step_callback(self, sender, app_data, user_data):
        tag = user_data["tag"]
        prefix = self._t("slider_roi_radius_z_")
        if not tag.startswith(prefix):
            return
        roi_id = tag[len(prefix) :]

        viewer = self.api.get_active_viewer()
        if not viewer or not viewer.image_id or not viewer.view_state:
            return
        roi_state = viewer.view_state.rois.get(roi_id)
        if not roi_state:
            return

        direction = user_data["dir"]
        current_r = getattr(roi_state, "spheroid_radius_z", None) or getattr(
            roi_state, "spheroid_radius", 10.0
        )

        # Step size is 1.0 mm by default
        step_size = 1.0
        new_r = max(0.5, current_r + (step_size * direction))

        if dpg.does_item_exist(tag):
            dpg.set_value(tag, new_r)

        self.on_roi_stats_radius_z_slider_changed(None, new_r, roi_id)

    def on_roi_stats_slider_deactivated(self, sender, app_data, user_data):
        self.api.request_refresh()
        self.refresh_all_open_stats_windows()

    def on_roi_stats_center_changed(self, sender, app_data, user_data):
        roi_id = user_data["roi_id"]
        coord_idx = user_data["coord_idx"]
        viewer = self.api.get_active_viewer()
        if not viewer or not viewer.image_id or not viewer.view_state:
            return
        base_vol = self.api.get_volumes().get(viewer.image_id)
        roi_vol = self.api.get_volumes().get(roi_id)
        roi_state = viewer.view_state.rois.get(roi_id)
        if not base_vol or not roi_vol or not roi_state:
            return

        new_val = float(app_data)
        if roi_state.spheroid_center is None:
            roi_state.spheroid_center = [0.0, 0.0, 0.0]
        roi_state.spheroid_center[coord_idx] = new_val

        self._c.update_spheroid_mask(
            base_vol,
            roi_vol,
            roi_state,
            new_r_x_mm=getattr(roi_state, "spheroid_radius_x", None)
            or getattr(roi_state, "spheroid_radius_xy", None)
            or getattr(roi_state, "spheroid_radius", 10.0),
            new_r_y_mm=getattr(roi_state, "spheroid_radius_y", None)
            or getattr(roi_state, "spheroid_radius_xy", None)
            or getattr(roi_state, "spheroid_radius", 10.0),
            new_r_z_mm=getattr(roi_state, "spheroid_radius_z", None)
            or getattr(roi_state, "spheroid_radius", 10.0),
        )

        for ori in roi_state.polygons:
            roi_state.polygons[ori].clear()

        viewer.view_state.is_geometry_dirty = True
        viewer.view_state.is_data_dirty = True

        # Sync crosshair and slice
        if hasattr(viewer.view_state, "update_crosshair_from_phys"):
            import numpy as np
            viewer.view_state.update_crosshair_from_phys(np.array(roi_state.spheroid_center))
            self.api.propagate_sync(viewer.image_id)

        self.api.request_refresh()
        self.api.update_all_viewers_of_image(viewer.image_id, data_dirty=True)
        self.refresh_all_open_stats_windows()

    def on_roi_close(self, sender, app_data, user_data):
        viewer = self.api.get_active_viewer()
        if not viewer or not viewer.image_id:
            return

        self.api.close_roi(viewer.image_id, user_data)
        if self._c.active_roi_id == user_data:
            self._c.active_roi_id = None

        win_tag = self._t(f"stats_win_{user_data}")
        if win_tag in self.open_stats_wins:
            self.open_stats_wins.remove(win_tag)
        if dpg.does_item_exist(win_tag):
            dpg.delete_item(win_tag)

        self.api.request_refresh()

    def on_close_roi_properties(self, sender, app_data, user_data):
        self._c.active_roi_id = None
        self.refresh_rois_ui()
        self.api.request_refresh()

    def on_roi_close_all(self, sender, app_data, user_data):
        viewer = self.api.get_active_viewer()
        if not viewer or not viewer.image_id or not viewer.view_state:
            return

        filter_text = self._c.roi_filters.get(viewer.image_id, "")
        for roi_id, roi in list(viewer.view_state.rois.items()):
            if filter_text and filter_text not in roi.name.lower():
                continue
            self.api.close_roi(viewer.image_id, roi_id)
            win_tag = self._t(f"stats_win_{roi_id}")
            if win_tag in self.open_stats_wins:
                self.open_stats_wins.remove(win_tag)
            if dpg.does_item_exist(win_tag):
                dpg.delete_item(win_tag)

        if (
            self._c.active_roi_id
            and self._c.active_roi_id not in viewer.view_state.rois
        ):
            self._c.active_roi_id = None

        self.api.request_refresh()

    def on_roi_stats_toggle(self, sender, app_data, user_data):
        roi_id = user_data
        win_tag = self._t(f"stats_win_{roi_id}")
        if dpg.does_item_exist(win_tag):
            self.on_roi_stats_window_closed(win_tag, None, roi_id)
            return

        assert self.api is not None
        viewer = self.api.get_active_viewer()
        if not viewer or not viewer.view_state or roi_id not in viewer.view_state.rois:
            return

        roi = viewer.view_state.rois[roi_id]
        image_name, _ = self.api.get_image_display_name(viewer.image_id)

        theme_tag = self._t(f"stats_theme_{roi_id}")
        if dpg.does_item_exist(theme_tag):
            dpg.delete_item(theme_tag, children_only=True)
        else:
            dpg.add_theme(tag=theme_tag)

        r, g, b = roi.color[:3]
        luminance = 0.299 * r + 0.587 * g + 0.114 * b
        text_color = [0, 0, 0, 255] if luminance > 128 else [255, 255, 255, 255]

        with dpg.theme_component(dpg.mvWindowAppItem, parent=theme_tag):
            dpg.add_theme_color(dpg.mvThemeCol_TitleBg, roi.color + [255])
            dpg.add_theme_color(dpg.mvThemeCol_TitleBgActive, roi.color + [255])
            dpg.add_theme_color(dpg.mvThemeCol_Text, text_color)

        content_theme_tag = self._t(f"stats_content_theme_{roi_id}")
        if dpg.does_item_exist(content_theme_tag):
            dpg.delete_item(content_theme_tag, children_only=True)
        else:
            dpg.add_theme(tag=content_theme_tag)

        with dpg.theme_component(dpg.mvGroup, parent=content_theme_tag):
            dpg.add_theme_color(dpg.mvThemeCol_Text, [255, 255, 255, 255])

        stats = self._c.compute_detailed_roi_stats(viewer.image_id, roi_id)
        has_overlay = bool(stats and stats.get("overlay_stats"))
        is_created = getattr(roi, "source_type", None) == "Created"
        is_spheroid = getattr(roi, "is_spheroid", False)
        is_box = getattr(roi, "is_box", False)
        if is_spheroid or is_box:
            win_h = 820 if has_overlay else 710
        elif is_created:
            win_h = 750 if has_overlay else 640
        else:
            win_h = 650 if has_overlay else 530

        # Determine initial position
        if roi_id in self.stats_win_positions:
            win_pos = self.stats_win_positions[roi_id]
        else:
            vp_w = dpg.get_viewport_client_width()
            vp_h = dpg.get_viewport_client_height()
            win_w, win_h = 320, win_h

            base_x = max(10, vp_w - win_w - 50)
            base_y = max(10, (vp_h - win_h) // 2)

            num_open = len(self.open_stats_wins)
            offset = 25 * num_open
            pos_x = base_x - offset
            pos_y = base_y + offset

            if pos_x < 10:
                pos_x = base_x
            if pos_y + win_h > vp_h - 10:
                pos_y = base_y

            win_pos = [pos_x, pos_y]

        with dpg.window(
            tag=win_tag,
            label=f"{roi.name} - {image_name}",
            width=320,
            height=win_h,
            pos=win_pos,
            on_close=self.on_roi_stats_window_closed,
            user_data=roi_id,
        ):
            content_tag = self._t(f"stats_content_{roi_id}")
            with dpg.group(tag=content_tag):
                self.build_stats_window_contents(content_tag, viewer.image_id, roi_id)

        dpg.bind_item_theme(win_tag, theme_tag)
        dpg.bind_item_theme(content_tag, content_theme_tag)

        self.open_stats_wins.add(win_tag)

    def build_stats_window_contents(self, parent_tag, base_vs_id, roi_id):
        stats = self._c.compute_detailed_roi_stats(base_vs_id, roi_id)
        if not stats:
            dpg.add_text("Failed to calculate statistics.", parent=parent_tag)
            return

        viewer = self.api.get_active_viewer()
        if not viewer or not viewer.view_state or roi_id not in viewer.view_state.rois:
            dpg.add_text("Failed to calculate statistics.", parent=parent_tag)
            return
        roi = viewer.view_state.rois[roi_id]

        dim_col = self.api.ui_cfg["colors"]["text_dim"]
        header_col = self.api.ui_cfg["colors"]["text_header"]

        # Create slider theme matching active ROI color
        slider_theme_tag = self._t(f"stats_slider_theme_{roi_id}")
        if dpg.does_item_exist(slider_theme_tag):
            dpg.delete_item(slider_theme_tag, children_only=True)
        else:
            dpg.add_theme(tag=slider_theme_tag)

        with dpg.theme_component(dpg.mvSliderFloat, parent=slider_theme_tag):
            r, g, b = roi.color[:3]
            dpg.add_theme_color(dpg.mvThemeCol_SliderGrab, [r, g, b, 255])
            dpg.add_theme_color(
                dpg.mvThemeCol_SliderGrabActive,
                [min(255, r + 40), min(255, g + 40), min(255, b + 40), 255],
            )
            dpg.add_theme_color(dpg.mvThemeCol_FrameBgActive, [r, g, b, 100])
            dpg.add_theme_color(dpg.mvThemeCol_FrameBgHovered, [r, g, b, 50])

        # Control Toolbar Row
        with dpg.group(horizontal=True, parent=parent_tag):
            # Color Picker
            color_picker = dpg.add_color_edit(
                default_value=roi.color + [255],
                no_inputs=True,
                no_label=True,
                no_alpha=True,
                width=20,
                height=20,
                tag=self._t(f"stats_color_picker_{roi_id}"),
                user_data=roi_id,
                callback=self.on_roi_color_changed,
            )
            with dpg.tooltip(color_picker):
                dpg.add_text("Change ROI color")

            # Copy to Clipboard Button (Icon)
            btn_copy = dpg.add_button(
                label="\uf0c5",
                width=20,
                callback=self.on_copy_stats_to_clipboard,
                user_data={"base_vs_id": base_vs_id, "roi_id": roi_id},
            )
            with dpg.tooltip(btn_copy):
                dpg.add_text("Copy statistics to clipboard")

            # Contour/Visibility Toggle
            if roi.visible:
                lbl_eye = "\uf040" if roi.is_contour else "\uf06e"
            else:
                lbl_eye = "\uf070"
            btn_eye = dpg.add_button(
                label=lbl_eye,
                width=20,
                tag=self._t(f"stats_btn_eye_{roi_id}"),
                user_data=roi_id,
                callback=self.on_roi_toggle_visible,
            )
            with dpg.tooltip(btn_eye):
                dpg.add_text("Toggle visibility (show / contour / hide)")

            # Center Camera
            btn_center = dpg.add_button(
                label="\uf05b",
                width=20,
                user_data=roi_id,
                callback=self.on_roi_center,
            )
            with dpg.tooltip(btn_center):
                dpg.add_text("Center camera on ROI")

            # Save / Reload
            roi_vol = self.api.get_volumes().get(roi_id)
            is_outdated = roi_vol._is_outdated if roi_vol else False
            source_type = getattr(roi, "source_type", "Binary")
            btn_action_tag = self._t(f"stats_btn_action_{roi_id}")
            if is_outdated:
                btn_action = dpg.add_button(
                    label="\uf01e",
                    width=20,
                    tag=btn_action_tag,
                    user_data=roi_id,
                    callback=self.on_roi_reload,
                )
                with dpg.tooltip(btn_action):
                    dpg.add_text(
                        "Reload modified file",
                        tag=self._t(f"stats_tooltip_action_{roi_id}"),
                    )
            else:
                btn_action = dpg.add_button(
                    label="\uf0c7",
                    width=20,
                    tag=btn_action_tag,
                    user_data=roi_id,
                    callback=self.on_roi_save,
                )
                with dpg.tooltip(btn_action):
                    dpg.add_text(
                        (
                            "Save ROI As..."
                            if source_type == "Binary"
                            else "Extract & Save ROI"
                        ),
                        tag=self._t(f"stats_tooltip_action_{roi_id}"),
                    )

            # Slider Opacity/Thickness
            dpg.add_spacer(width=5)
            slider_tag = self._t(f"stats_slider_opacity_thickness_{roi_id}")
            if roi.is_contour:
                slider = dpg.add_slider_float(
                    default_value=getattr(roi, "thickness", 1.0),
                    min_value=0.5,
                    max_value=10.0,
                    width=90,
                    tag=slider_tag,
                    format="Thick: %.1f",
                    user_data=roi_id,
                    callback=self.on_roi_thickness_changed,
                )
                with dpg.tooltip(slider):
                    dpg.add_text("Adjust contour thickness")
            else:
                slider = dpg.add_slider_float(
                    default_value=getattr(roi, "opacity", 0.5),
                    min_value=0.0,
                    max_value=1.0,
                    width=90,
                    tag=slider_tag,
                    format="Opac: %.2f",
                    user_data=roi_id,
                    callback=self.on_roi_opacity_changed,
                )
                with dpg.tooltip(slider):
                    dpg.add_text("Adjust ROI opacity")

            dpg.bind_item_theme(slider, slider_theme_tag)
            build_help_button(
                "ROI Actions Toolbar:\n"
                "- Color Block: Click to change the display color of the ROI.\n"
                "- Copy [Clipboard Icon]: Copy detailed statistics to your clipboard.\n"
                "- Eye/Pencil Icon: Toggle display mode (solid raster fill, contour lines, or hidden).\n"
                "- Target Icon: Recenter and focus all slice view cameras on the ROI's center of mass.\n"
                "- Floppy/Sync Icon: Save ROI to disk, or reload if outdated.\n"
                "- Opac/Thick Slider: Drag to change opacity (for solid fill) or line width (for contour outlines).",
                self.api,
            )

            if dpg.does_item_exist("icon_font_tag"):
                for btn in [btn_copy, btn_eye, btn_center, btn_action]:
                    dpg.bind_item_font(btn, "icon_font_tag")

        # Spheroid Parameters group
        spheroid_group_tag = self._t(f"stats_group_spheroid_{roi_id}")
        with dpg.group(
            tag=spheroid_group_tag,
            parent=parent_tag,
            show=getattr(roi, "is_spheroid", False),
        ):
            dpg.add_spacer(height=5)
            dpg.add_text("Spheroid Parameters", color=header_col)
            dpg.add_separator()

            # Radius X Slider
            slider_x_tag = self._t(f"slider_roi_radius_x_{roi_id}")
            with dpg.group():
                build_stepped_slider(
                    label="Radius X (mm):",
                    tag=slider_x_tag,
                    callback=self.on_roi_stats_radius_x_slider_changed,
                    step_callback=self.on_roi_stats_radius_x_step_callback,
                    min_val=0.5,
                    max_val=150.0,
                    default_val=getattr(roi, "spheroid_radius_x", None)
                    or getattr(roi, "spheroid_radius_xy", None)
                    or getattr(roi, "spheroid_radius", None)
                    or 10.0,
                    format="%.1f",
                    gui=self.api,
                    user_data=roi_id,
                    use_slider=True,
                )

            # Radius Y Slider
            slider_y_tag = self._t(f"slider_roi_radius_y_{roi_id}")
            with dpg.group():
                build_stepped_slider(
                    label="Radius Y (mm):",
                    tag=slider_y_tag,
                    callback=self.on_roi_stats_radius_y_slider_changed,
                    step_callback=self.on_roi_stats_radius_y_step_callback,
                    min_val=0.5,
                    max_val=150.0,
                    default_val=getattr(roi, "spheroid_radius_y", None)
                    or getattr(roi, "spheroid_radius_xy", None)
                    or getattr(roi, "spheroid_radius", None)
                    or 10.0,
                    format="%.1f",
                    gui=self.api,
                    user_data=roi_id,
                    use_slider=True,
                )

            # Radius Z Slider
            slider_z_tag = self._t(f"slider_roi_radius_z_{roi_id}")
            with dpg.group():
                build_stepped_slider(
                    label="Radius Z (mm):",
                    tag=slider_z_tag,
                    callback=self.on_roi_stats_radius_z_slider_changed,
                    step_callback=self.on_roi_stats_radius_z_step_callback,
                    min_val=0.5,
                    max_val=150.0,
                    default_val=getattr(roi, "spheroid_radius_z", None)
                    or getattr(roi, "spheroid_radius", None)
                    or 10.0,
                    format="%.1f",
                    gui=self.api,
                    user_data=roi_id,
                    use_slider=True,
                )

            # Create deactivated handler registry if it doesn't exist
            handler_reg = self._t("slider_deactivated_handler_reg")
            if not dpg.does_item_exist(handler_reg):
                with dpg.item_handler_registry(tag=handler_reg):
                    dpg.add_item_deactivated_after_edit_handler(
                        callback=self.on_roi_stats_slider_deactivated
                    )
            # Bind to all three sliders
            dpg.bind_item_handler_registry(slider_x_tag, handler_reg)
            dpg.bind_item_handler_registry(slider_y_tag, handler_reg)
            dpg.bind_item_handler_registry(slider_z_tag, handler_reg)

            # Center Inputs
            center = getattr(roi, "spheroid_center", None) or [0.0, 0.0, 0.0]
            with dpg.group(horizontal=True):
                dpg.add_text("Center X:", color=dim_col)
                dpg.add_input_float(
                    tag=self._t(f"input_roi_center_x_{roi_id}"),
                    default_value=center[0],
                    step=0,
                    width=55,
                    format="%.1f",
                    user_data={"roi_id": roi_id, "coord_idx": 0},
                    callback=self.on_roi_stats_center_changed,
                    on_enter=True,
                )
                dpg.add_text("Y:", color=dim_col)
                dpg.add_input_float(
                    tag=self._t(f"input_roi_center_y_{roi_id}"),
                    default_value=center[1],
                    step=0,
                    width=55,
                    format="%.1f",
                    user_data={"roi_id": roi_id, "coord_idx": 1},
                    callback=self.on_roi_stats_center_changed,
                    on_enter=True,
                )
                dpg.add_text("Z:", color=dim_col)
                dpg.add_input_float(
                    tag=self._t(f"input_roi_center_z_{roi_id}"),
                    default_value=center[2],
                    step=0,
                    width=55,
                    format="%.1f",
                    user_data={"roi_id": roi_id, "coord_idx": 2},
                    callback=self.on_roi_stats_center_changed,
                    on_enter=True,
                )

        # Box Parameters group
        box_group_tag = self._t(f"stats_group_box_{roi_id}")
        with dpg.group(
            tag=box_group_tag, parent=parent_tag, show=getattr(roi, "is_box", False)
        ):
            dpg.add_spacer(height=5)
            dpg.add_text("Box Parameters", color=header_col)
            dpg.add_separator()

            # Size X Slider
            slider_box_x_tag = self._t(f"slider_roi_box_size_x_{roi_id}")
            with dpg.group():
                build_stepped_slider(
                    label="Length X (mm):",
                    tag=slider_box_x_tag,
                    callback=self.on_roi_stats_box_size_x_slider_changed,
                    step_callback=self.on_roi_stats_box_size_x_step_callback,
                    min_val=1.0,
                    max_val=300.0,
                    default_val=getattr(roi, "box_size_x", None) or 20.0,
                    format="%.1f",
                    gui=self.api,
                    user_data=roi_id,
                    use_slider=True,
                )

            # Size Y Slider
            slider_box_y_tag = self._t(f"slider_roi_box_size_y_{roi_id}")
            with dpg.group():
                build_stepped_slider(
                    label="Length Y (mm):",
                    tag=slider_box_y_tag,
                    callback=self.on_roi_stats_box_size_y_slider_changed,
                    step_callback=self.on_roi_stats_box_size_y_step_callback,
                    min_val=1.0,
                    max_val=300.0,
                    default_val=getattr(roi, "box_size_y", None) or 20.0,
                    format="%.1f",
                    gui=self.api,
                    user_data=roi_id,
                    use_slider=True,
                )

            # Size Z Slider
            slider_box_z_tag = self._t(f"slider_roi_box_size_z_{roi_id}")
            with dpg.group():
                build_stepped_slider(
                    label="Length Z (mm):",
                    tag=slider_box_z_tag,
                    callback=self.on_roi_stats_box_size_z_slider_changed,
                    step_callback=self.on_roi_stats_box_size_z_step_callback,
                    min_val=1.0,
                    max_val=300.0,
                    default_val=getattr(roi, "box_size_z", None) or 20.0,
                    format="%.1f",
                    gui=self.api,
                    user_data=roi_id,
                    use_slider=True,
                )

            # Bind to deactivated handler registry
            handler_reg = self._t("slider_deactivated_handler_reg")
            if dpg.does_item_exist(handler_reg):
                dpg.bind_item_handler_registry(slider_box_x_tag, handler_reg)
                dpg.bind_item_handler_registry(slider_box_y_tag, handler_reg)
                dpg.bind_item_handler_registry(slider_box_z_tag, handler_reg)

            # Center Inputs
            center = getattr(roi, "box_center", None) or [0.0, 0.0, 0.0]
            with dpg.group(horizontal=True):
                dpg.add_text("Center X:", color=dim_col)
                dpg.add_input_float(
                    tag=self._t(f"input_roi_box_center_x_{roi_id}"),
                    default_value=center[0],
                    step=0,
                    width=55,
                    format="%.1f",
                    user_data={"roi_id": roi_id, "coord_idx": 0},
                    callback=self.on_roi_stats_box_center_changed,
                    on_enter=True,
                )
                dpg.add_text("Y:", color=dim_col)
                dpg.add_input_float(
                    tag=self._t(f"input_roi_box_center_y_{roi_id}"),
                    default_value=center[1],
                    step=0,
                    width=55,
                    format="%.1f",
                    user_data={"roi_id": roi_id, "coord_idx": 1},
                    callback=self.on_roi_stats_box_center_changed,
                    on_enter=True,
                )
                dpg.add_text("Z:", color=dim_col)
                dpg.add_input_float(
                    tag=self._t(f"input_roi_box_center_z_{roi_id}"),
                    default_value=center[2],
                    step=0,
                    width=55,
                    format="%.1f",
                    user_data={"roi_id": roi_id, "coord_idx": 2},
                    callback=self.on_roi_stats_box_center_changed,
                    on_enter=True,
                )

        dpg.add_spacer(height=5, parent=parent_tag)

        dpg.add_text("Source", color=header_col, parent=parent_tag)
        dpg.add_separator(parent=parent_tag)

        file_row_tag = self._t(f"stats_row_file_{roi_id}")
        is_created = getattr(roi, "source_type", None) == "Created"
        with dpg.group(
            horizontal=True, parent=parent_tag, tag=file_row_tag, show=not is_created
        ):
            dpg.add_text("File:", color=dim_col)
            file_txt = dpg.add_text(
                stats.get("source_filename", "Unknown"),
                tag=self._t(f"stats_txt_file_{roi_id}"),
            )
            if stats.get("source_filepath"):
                with dpg.tooltip(file_txt):
                    dpg.add_text(stats["source_filepath"])

        with dpg.group(horizontal=True, parent=parent_tag):
            dpg.add_text("Type:", color=dim_col)
            if is_created:
                if getattr(roi, "is_spheroid", False):
                    t_str = "Sphere"
                elif getattr(roi, "is_box", False):
                    t_str = "Box"
                else:
                    t_str = "Created"
            else:
                t_str = stats.get("source_type", "Unknown")
            dpg.add_text(t_str, tag=self._t(f"stats_txt_type_{roi_id}"))

        dpg.add_spacer(height=5, parent=parent_tag)

        with dpg.group(horizontal=True, parent=parent_tag):
            dpg.add_text("Geometry", color=header_col)
            build_help_button(
                "Geometry parameters:\n"
                "- Volume (cc): Physical volume in cubic centimeters.\n"
                "- Mass (g): Estimated mass calculated using mean voxel intensity as density (only for CT images).\n"
                "- Number of voxels: Count of non-zero pixels.\n"
                "- Size: Voxel dimensions of the base image (and cropped mask bounding box size).\n"
                "- Spacing: Spacing between voxel centers in mm (X x Y x Z).\n"
                "- Center of Mass: Average voxel location (Pixel coordinates and physical coordinates).",
                self.api,
            )
        dpg.add_separator(parent=parent_tag)

        # Volumes, Voxels and Mass on the same row!
        with dpg.group(horizontal=True, parent=parent_tag):
            dpg.add_text("Volume (cc):", color=dim_col)
            dpg.add_text(
                f"{stats['vol_cc']:.3f}", tag=self._t(f"stats_txt_vol_cc_{roi_id}")
            )
            dpg.add_spacer(width=10)
            mass_label = dpg.add_text("Mass (g):", color=dim_col)
            with dpg.tooltip(mass_label):
                dpg.add_text("Estimated mass, only if the image is a CT (HU)")

            dpg.add_text(
                f"{stats.get('mass', 0.0):.2f}", tag=self._t(f"stats_txt_mass_{roi_id}")
            )

        with dpg.group(horizontal=True, parent=parent_tag):
            dpg.add_text("Number of voxels:", color=dim_col)
            dpg.add_text(
                f"{stats['voxel_count']}", tag=self._t(f"stats_txt_voxels_{roi_id}")
            )

        with dpg.group(horizontal=True, parent=parent_tag):
            dpg.add_text("Size:", color=dim_col)
            size_str = (
                f"{stats['size']} ({stats['cropped_size']})"
                if stats.get("cropped_size")
                else stats["size"]
            )
            dpg.add_text(size_str, tag=self._t(f"stats_txt_size_{roi_id}"))
        with dpg.group(horizontal=True, parent=parent_tag):
            dpg.add_text("Spacing (mm):", color=dim_col)
            dpg.add_text(stats["spacing"], tag=self._t(f"stats_txt_spacing_{roi_id}"))

        dpg.add_text("Center of Mass:", parent=parent_tag, color=dim_col)
        with dpg.group(horizontal=True, parent=parent_tag):
            dpg.add_text("  Pixel:", color=dim_col)
            px, py, pz = stats["com_pixel"]
            dpg.add_text(
                f"({px:.1f}, {py:.1f}, {pz:.1f})",
                tag=self._t(f"stats_txt_com_pixel_{roi_id}"),
            )
        with dpg.group(horizontal=True, parent=parent_tag):
            dpg.add_text("  Physical (mm):", color=dim_col)
            mx, my, mz = stats["com_mm"]
            dpg.add_text(
                f"({mx:.1f}, {my:.1f}, {mz:.1f})",
                tag=self._t(f"stats_txt_com_mm_{roi_id}"),
            )

        dpg.add_spacer(height=5, parent=parent_tag)

        with dpg.group(horizontal=True, parent=parent_tag):
            dpg.add_text("Intensity", color=header_col)
            build_help_button(
                "Base image intensity statistics inside the ROI:\n"
                "- Mean / Std Dev: Average voxel value and standard deviation.\n"
                "- Median: Voxel value at the 50th percentile.\n"
                "- Peak (95%): Voxel value at the 95th percentile, representing peak intake.\n"
                "- Min / Max: Lowest and highest voxel values.",
                self.api,
            )
        dpg.add_separator(parent=parent_tag)

        with dpg.group(horizontal=True, parent=parent_tag):
            dpg.add_text("Mean:", color=dim_col)
            dpg.add_text(
                f"{stats['mean']:.2f}", tag=self._t(f"stats_txt_mean_{roi_id}")
            )
            dpg.add_spacer(width=10)
            dpg.add_text("Std Dev:", color=dim_col)
            dpg.add_text(f"{stats['std']:.2f}", tag=self._t(f"stats_txt_std_{roi_id}"))
        with dpg.group(horizontal=True, parent=parent_tag):
            dpg.add_text("Median:", color=dim_col)
            dpg.add_text(
                f"{stats['median']:.2f}", tag=self._t(f"stats_txt_median_{roi_id}")
            )
            dpg.add_spacer(width=10)
            peak_label = dpg.add_text("Peak (95%):", color=dim_col)
            with dpg.tooltip(peak_label):
                dpg.add_text("95th percentile of intensity values inside the ROI")
            dpg.add_text(
                f"{stats['peak']:.2f}", tag=self._t(f"stats_txt_peak_{roi_id}")
            )
        with dpg.group(horizontal=True, parent=parent_tag):
            dpg.add_text("Min / Max:", color=dim_col)
            dpg.add_text(
                f"{stats['min']:.2f} / {stats['max']:.2f}",
                tag=self._t(f"stats_txt_min_max_{roi_id}"),
            )

        # Overlay stats group
        overlay_group_tag = self._t(f"stats_group_overlay_{roi_id}")
        ov_stats = stats.get("overlay_stats")
        with dpg.group(tag=overlay_group_tag, parent=parent_tag, show=bool(ov_stats)):
            name_str = ov_stats["name"] if ov_stats else "Overlay"
            dpg.add_spacer(height=5)
            with dpg.group(horizontal=True):
                dpg.add_text(
                    f"Fusion Intensity ({name_str})",
                    color=header_col,
                    tag=self._t(f"stats_txt_overlay_header_{roi_id}"),
                )
                build_help_button(
                    "Fused overlay image intensity statistics inside the ROI:\n"
                    "- Mean / Std Dev: Average overlay value and standard deviation.\n"
                    "- Median: Voxel value at the 50th percentile of the overlay.\n"
                    "- Peak (95%): 95th percentile value of the overlay.\n"
                    "- Min / Max: Lowest and highest overlay values inside the ROI.",
                    self.api,
                )
            dpg.add_separator()

            with dpg.group(horizontal=True):
                dpg.add_text("Mean:", color=dim_col)
                dpg.add_text(
                    f"{ov_stats['mean']:.2f}" if ov_stats else "0.00",
                    tag=self._t(f"stats_txt_overlay_mean_{roi_id}"),
                )
                dpg.add_spacer(width=10)
                dpg.add_text("Std Dev:", color=dim_col)
                dpg.add_text(
                    f"{ov_stats['std']:.2f}" if ov_stats else "0.00",
                    tag=self._t(f"stats_txt_overlay_std_{roi_id}"),
                )
            with dpg.group(horizontal=True):
                dpg.add_text("Median:", color=dim_col)
                dpg.add_text(
                    f"{ov_stats['median']:.2f}" if ov_stats else "0.00",
                    tag=self._t(f"stats_txt_overlay_median_{roi_id}"),
                )
                dpg.add_spacer(width=10)
                ov_peak_label = dpg.add_text("Peak (95%):", color=dim_col)
                with dpg.tooltip(ov_peak_label):
                    dpg.add_text("95th percentile of intensity values inside the ROI")
                dpg.add_text(
                    f"{ov_stats['peak']:.2f}" if ov_stats else "0.00",
                    tag=self._t(f"stats_txt_overlay_peak_{roi_id}"),
                )
            with dpg.group(horizontal=True):
                dpg.add_text("Min / Max:", color=dim_col)
                min_max_str = (
                    f"{ov_stats['min']:.2f} / {ov_stats['max']:.2f}"
                    if ov_stats
                    else "0.00 / 0.00"
                )
                dpg.add_text(
                    min_max_str, tag=self._t(f"stats_txt_overlay_min_max_{roi_id}")
                )

        dpg.add_spacer(height=10, parent=parent_tag)
        dpg.add_button(
            label="Export Stats to JSON",
            parent=parent_tag,
            width=-1,
            user_data={"base_vs_id": base_vs_id, "roi_id": roi_id},
            callback=self.on_export_stats_to_json,
        )
        dpg.add_spacer(height=5, parent=parent_tag)
        btn_delete = dpg.add_button(
            label="Delete ROI",
            parent=parent_tag,
            width=-1,
            user_data=roi_id,
            callback=self.on_roi_close,
        )
        if dpg.does_item_exist("delete_button_theme"):
            dpg.bind_item_theme(btn_delete, "delete_button_theme")

    def update_stats_window_contents(self, base_vs_id, roi_id):
        viewer = self.api.get_active_viewer()
        if not viewer or not viewer.view_state or roi_id not in viewer.view_state.rois:
            return
        roi = viewer.view_state.rois[roi_id]
        roi_vol = self.api.get_volumes().get(roi_id)

        stats = self._c.compute_detailed_roi_stats(base_vs_id, roi_id)
        if stats:
            # Update text labels
            dpg.set_value(self._t(f"stats_txt_vol_cc_{roi_id}"), f"{stats['vol_cc']:.3f}")
            dpg.set_value(
                self._t(f"stats_txt_mass_{roi_id}"), f"{stats.get('mass', 0.0):.2f}"
            )
            dpg.set_value(self._t(f"stats_txt_voxels_{roi_id}"), f"{stats['voxel_count']}")

            size_str = (
                f"{stats['size']} ({stats['cropped_size']})"
                if stats.get("cropped_size")
                else stats["size"]
            )
            dpg.set_value(self._t(f"stats_txt_size_{roi_id}"), size_str)
            dpg.set_value(self._t(f"stats_txt_spacing_{roi_id}"), stats["spacing"])

            px, py, pz = stats["com_pixel"]
            dpg.set_value(
                self._t(f"stats_txt_com_pixel_{roi_id}"), f"({px:.1f}, {py:.1f}, {pz:.1f})"
            )
            mx, my, mz = stats["com_mm"]
            dpg.set_value(
                self._t(f"stats_txt_com_mm_{roi_id}"), f"({mx:.1f}, {my:.1f}, {mz:.1f})"
            )

            dpg.set_value(self._t(f"stats_txt_mean_{roi_id}"), f"{stats['mean']:.2f}")
            dpg.set_value(self._t(f"stats_txt_std_{roi_id}"), f"{stats['std']:.2f}")
            dpg.set_value(self._t(f"stats_txt_median_{roi_id}"), f"{stats['median']:.2f}")
            dpg.set_value(self._t(f"stats_txt_peak_{roi_id}"), f"{stats['peak']:.2f}")
            dpg.set_value(
                self._t(f"stats_txt_min_max_{roi_id}"),
                f"{stats['min']:.2f} / {stats['max']:.2f}",
            )

        # Update overlay stats
        ov_stats = stats.get("overlay_stats") if stats else None
        overlay_group = self._t(f"stats_group_overlay_{roi_id}")
        if dpg.does_item_exist(overlay_group):
            dpg.configure_item(overlay_group, show=bool(ov_stats))
            if ov_stats:
                dpg.set_value(
                    self._t(f"stats_txt_overlay_header_{roi_id}"),
                    f"Fusion Intensity ({ov_stats['name']})",
                )
                dpg.set_value(
                    self._t(f"stats_txt_overlay_mean_{roi_id}"),
                    f"{ov_stats['mean']:.2f}",
                )
                dpg.set_value(
                    self._t(f"stats_txt_overlay_std_{roi_id}"), f"{ov_stats['std']:.2f}"
                )
                dpg.set_value(
                    self._t(f"stats_txt_overlay_median_{roi_id}"),
                    f"{ov_stats['median']:.2f}",
                )
                dpg.set_value(
                    self._t(f"stats_txt_overlay_peak_{roi_id}"),
                    f"{ov_stats['peak']:.2f}",
                )
                dpg.set_value(
                    self._t(f"stats_txt_overlay_min_max_{roi_id}"),
                    f"{ov_stats['min']:.2f} / {ov_stats['max']:.2f}",
                )

        # Update file / type row
        is_created = getattr(roi, "source_type", None) == "Created"
        file_row = self._t(f"stats_row_file_{roi_id}")
        if dpg.does_item_exist(file_row):
            dpg.configure_item(file_row, show=not is_created)
            if not is_created:
                dpg.set_value(
                    self._t(f"stats_txt_file_{roi_id}"),
                    stats.get("source_filename", "Unknown") if stats else "Unknown",
                )

            if is_created:
                if getattr(roi, "is_spheroid", False):
                    t_str = "Sphere"
                elif getattr(roi, "is_box", False):
                    t_str = "Box"
                else:
                    t_str = "Created"
            else:
                t_str = stats.get("source_type", "Unknown") if stats else getattr(roi, "source_type", "Unknown")
            dpg.set_value(self._t(f"stats_txt_type_{roi_id}"), t_str)

        # Update spheroid inputs
        spheroid_group = self._t(f"stats_group_spheroid_{roi_id}")
        if dpg.does_item_exist(spheroid_group):
            dpg.configure_item(spheroid_group, show=getattr(roi, "is_spheroid", False))
            if getattr(roi, "is_spheroid", False):
                r_x = (
                    getattr(roi, "spheroid_radius_x", None)
                    or getattr(roi, "spheroid_radius_xy", None)
                    or getattr(roi, "spheroid_radius", 10.0)
                )
                r_y = (
                    getattr(roi, "spheroid_radius_y", None)
                    or getattr(roi, "spheroid_radius_xy", None)
                    or getattr(roi, "spheroid_radius", 10.0)
                )
                r_z = getattr(roi, "spheroid_radius_z", None) or getattr(
                    roi, "spheroid_radius", 10.0
                )
                dpg.set_value(self._t(f"slider_roi_radius_x_{roi_id}"), r_x)
                dpg.set_value(self._t(f"slider_roi_radius_y_{roi_id}"), r_y)
                dpg.set_value(self._t(f"slider_roi_radius_z_{roi_id}"), r_z)

                center = getattr(roi, "spheroid_center", [0.0, 0.0, 0.0])
                dpg.set_value(self._t(f"input_roi_center_x_{roi_id}"), center[0])
                dpg.set_value(self._t(f"input_roi_center_y_{roi_id}"), center[1])
                dpg.set_value(self._t(f"input_roi_center_z_{roi_id}"), center[2])

        # Update box inputs
        box_group = self._t(f"stats_group_box_{roi_id}")
        if dpg.does_item_exist(box_group):
            dpg.configure_item(box_group, show=getattr(roi, "is_box", False))
            if getattr(roi, "is_box", False):
                b_x = getattr(roi, "box_size_x", 20.0)
                b_y = getattr(roi, "box_size_y", 20.0)
                b_z = getattr(roi, "box_size_z", 20.0)
                dpg.set_value(self._t(f"slider_roi_box_size_x_{roi_id}"), b_x)
                dpg.set_value(self._t(f"slider_roi_box_size_y_{roi_id}"), b_y)
                dpg.set_value(self._t(f"slider_roi_box_size_z_{roi_id}"), b_z)

                center = getattr(roi, "box_center", [0.0, 0.0, 0.0])
                dpg.set_value(self._t(f"input_roi_box_center_x_{roi_id}"), center[0])
                dpg.set_value(self._t(f"input_roi_box_center_y_{roi_id}"), center[1])
                dpg.set_value(self._t(f"input_roi_box_center_z_{roi_id}"), center[2])

        # Opacity / thickness slider
        slider_tag = self._t(f"stats_slider_opacity_thickness_{roi_id}")
        if dpg.does_item_exist(slider_tag):
            if roi.is_contour:
                dpg.configure_item(
                    slider_tag,
                    default_value=getattr(roi, "thickness", 1.0),
                    min_value=0.5,
                    max_value=10.0,
                    format="Thick: %.1f",
                    callback=self.on_roi_thickness_changed,
                )
                dpg.set_value(slider_tag, getattr(roi, "thickness", 1.0))
            else:
                dpg.configure_item(
                    slider_tag,
                    default_value=getattr(roi, "opacity", 0.5),
                    min_value=0.0,
                    max_value=1.0,
                    format="Opac: %.2f",
                    callback=self.on_roi_opacity_changed,
                )
                dpg.set_value(slider_tag, getattr(roi, "opacity", 0.5))

        # Save/Reload action button
        btn_action_tag = self._t(f"stats_btn_action_{roi_id}")
        if dpg.does_item_exist(btn_action_tag):
            is_outdated = roi_vol._is_outdated if roi_vol else False
            source_type = getattr(roi, "source_type", "Binary")
            tooltip_tag = self._t(f"stats_tooltip_action_{roi_id}")
            if is_outdated:
                dpg.configure_item(
                    btn_action_tag, label="\uf01e", callback=self.on_roi_reload
                )
                if dpg.does_item_exist(tooltip_tag):
                    dpg.set_value(tooltip_tag, "Reload modified file")
            else:
                dpg.configure_item(
                    btn_action_tag, label="\uf0c7", callback=self.on_roi_save
                )
                if dpg.does_item_exist(tooltip_tag):
                    dpg.set_value(
                        tooltip_tag,
                        (
                            "Save ROI As..."
                            if source_type == "Binary"
                            else "Extract & Save ROI"
                        ),
                    )

        # Color picker
        color_picker_tag = self._t(f"stats_color_picker_{roi_id}")
        if dpg.does_item_exist(color_picker_tag):
            dpg.set_value(color_picker_tag, roi.color + [255])

        # Update slider theme matching active ROI color
        slider_theme_tag = self._t(f"stats_slider_theme_{roi_id}")
        if dpg.does_item_exist(slider_theme_tag):
            dpg.delete_item(slider_theme_tag, children_only=True)
            with dpg.theme_component(dpg.mvSliderFloat, parent=slider_theme_tag):
                r, g, b = roi.color[:3]
                dpg.add_theme_color(dpg.mvThemeCol_SliderGrab, [r, g, b, 255])
                dpg.add_theme_color(
                    dpg.mvThemeCol_SliderGrabActive,
                    [min(255, r + 40), min(255, g + 40), min(255, b + 40), 255],
                )
                dpg.add_theme_color(dpg.mvThemeCol_FrameBgActive, [r, g, b, 100])
                dpg.add_theme_color(dpg.mvThemeCol_FrameBgHovered, [r, g, b, 50])

        # Enable / disable based on MIP mode
        is_mip = bool(
            viewer
            and viewer.image_id
            and self.api.is_mip_active(viewer.image_id, viewer.tag)
        )
        slider_x_tag = self._t(f"slider_roi_radius_x_{roi_id}")
        slider_y_tag = self._t(f"slider_roi_radius_y_{roi_id}")
        slider_z_tag = self._t(f"slider_roi_radius_z_{roi_id}")
        slider_box_x_tag = self._t(f"slider_roi_box_size_x_{roi_id}")
        slider_box_y_tag = self._t(f"slider_roi_box_size_y_{roi_id}")
        slider_box_z_tag = self._t(f"slider_roi_box_size_z_{roi_id}")
        for item in [
            color_picker_tag,
            slider_tag,
            btn_action_tag,
            slider_x_tag,
            f"btn_{slider_x_tag}_minus",
            f"btn_{slider_x_tag}_plus",
            slider_y_tag,
            f"btn_{slider_y_tag}_minus",
            f"btn_{slider_y_tag}_plus",
            slider_z_tag,
            f"btn_{slider_z_tag}_minus",
            f"btn_{slider_z_tag}_plus",
            slider_box_x_tag,
            f"btn_{slider_box_x_tag}_minus",
            f"btn_{slider_box_x_tag}_plus",
            slider_box_y_tag,
            f"btn_{slider_box_y_tag}_minus",
            f"btn_{slider_box_y_tag}_plus",
            slider_box_z_tag,
            f"btn_{slider_box_z_tag}_minus",
            f"btn_{slider_box_z_tag}_plus",
            self._t(f"input_roi_center_x_{roi_id}"),
            self._t(f"input_roi_center_y_{roi_id}"),
            self._t(f"input_roi_center_z_{roi_id}"),
            self._t(f"input_roi_box_center_x_{roi_id}"),
            self._t(f"input_roi_box_center_y_{roi_id}"),
            self._t(f"input_roi_box_center_z_{roi_id}"),
        ]:
            if dpg.does_item_exist(item):
                dpg.configure_item(item, enabled=not is_mip)

        # Update visibility eye button icon
        btn_eye_tag = self._t(f"stats_btn_eye_{roi_id}")
        if dpg.does_item_exist(btn_eye_tag):
            if roi.visible:
                lbl_eye = "\uf040" if roi.is_contour else "\uf06e"
            else:
                lbl_eye = "\uf070"
            dpg.configure_item(btn_eye_tag, label=lbl_eye, enabled=not is_mip)

        # Dynamic window height adjustment
        win_tag = self._t(f"stats_win_{roi_id}")
        if dpg.does_item_exist(win_tag):
            is_spheroid = getattr(roi, "is_spheroid", False)
            is_box = getattr(roi, "is_box", False)
            if is_spheroid or is_box:
                win_h = 820 if ov_stats else 710
            elif is_created:
                win_h = 750 if ov_stats else 640
            else:
                win_h = 650 if ov_stats else 530
            dpg.configure_item(win_tag, height=win_h)

    def on_copy_stats_to_clipboard(self, sender, app_data, user_data):
        base_vs_id = user_data["base_vs_id"]
        roi_id = user_data["roi_id"]
        stats = self._c.compute_detailed_roi_stats(base_vs_id, roi_id)
        if not stats:
            return

        viewer = self.api.get_active_viewer()
        if not viewer or not viewer.view_state or roi_id not in viewer.view_state.rois:
            return
        roi = viewer.view_state.rois[roi_id]
        image_name, _ = self.api.get_image_display_name(viewer.image_id)

        size_val = stats["size"]
        if stats.get("cropped_size"):
            size_val += f" (cropped: {stats['cropped_size']})"

        text_lines = [
            f"ROI: {roi.name}",
            f"Image: {image_name}",
            "Geometry:",
            f"  Volume (cc): {stats['vol_cc']:.3f}",
            f"  Mass (g): {stats.get('mass', 0.0):.2f}",
            f"  Voxels: {stats['voxel_count']}",
            f"  Size: {size_val}",
            f"  Spacing (mm): {stats['spacing']}",
            f"  Center of Mass (pixel): ({stats['com_pixel'][0]:.1f}, {stats['com_pixel'][1]:.1f}, {stats['com_pixel'][2]:.1f})",
            f"  Center of Mass (mm): ({stats['com_mm'][0]:.1f}, {stats['com_mm'][1]:.1f}, {stats['com_mm'][2]:.1f})",
            "Intensity:",
            f"  Mean: {stats['mean']:.2f}",
            f"  Std Dev: {stats['std']:.2f}",
            f"  Median: {stats['median']:.2f}",
            f"  Peak (95%): {stats['peak']:.2f}",
            f"  Min: {stats['min']:.2f}",
            f"  Max: {stats['max']:.2f}",
        ]
        ov_stats = stats.get("overlay_stats")
        if ov_stats:
            text_lines.extend(
                [
                    f"Fusion Intensity ({ov_stats['name']}):",
                    f"  Mean: {ov_stats['mean']:.2f}",
                    f"  Std Dev: {ov_stats['std']:.2f}",
                    f"  Median: {ov_stats['median']:.2f}",
                    f"  Peak (95%): {ov_stats['peak']:.2f}",
                    f"  Min: {ov_stats['min']:.2f}",
                    f"  Max: {ov_stats['max']:.2f}",
                ]
            )
        clipboard_text = "\n".join(text_lines)
        dpg.set_clipboard_text(clipboard_text)
        self.api.set_async_status("Stats copied to clipboard!")

    def on_export_stats_to_json(self, sender, app_data, user_data):
        base_vs_id = user_data["base_vs_id"]
        roi_id = user_data["roi_id"]
        stats = self._c.compute_detailed_roi_stats(base_vs_id, roi_id)
        if not stats:
            return

        viewer = self.api.get_active_viewer()
        if not viewer or not viewer.view_state or roi_id not in viewer.view_state.rois:
            return
        roi = viewer.view_state.rois[roi_id]
        image_name, _ = self.api.get_image_display_name(viewer.image_id)

        default_name = f"{roi.name}_stats.json"

        from vvv.ui.file_dialog import save_file_dialog

        file_path = save_file_dialog("Export Stats to JSON", default_name=default_name)
        if not file_path:
            return

        export_data = {"roi_name": roi.name, "base_image": image_name, "stats": stats}

        try:
            import json
            import os

            with open(file_path, "w") as f:
                json.dump(export_data, f, indent=4)
            self.api.set_async_status(
                f"Stats exported to {os.path.basename(file_path)}!"
            )
        except Exception as e:
            self.api.notify(f"Error exporting stats: {e}")

    def refresh_all_open_stats_windows(self):
        viewer = self.api.get_active_viewer()
        if not viewer or not viewer.image_id or not viewer.view_state:
            self.close_all_stats_windows()
            return

        image_name, _ = self.api.get_image_display_name(viewer.image_id)

        for win_tag in list(self.open_stats_wins):
            roi_id = None
            for r_id in viewer.view_state.rois:
                if self._t(f"stats_win_{r_id}") == win_tag:
                    roi_id = r_id
                    break

            if not roi_id:
                if dpg.does_item_exist(win_tag):
                    dpg.delete_item(win_tag)
                self.open_stats_wins.discard(win_tag)
                continue

            roi = viewer.view_state.rois[roi_id]
            if dpg.does_item_exist(win_tag):
                dpg.configure_item(win_tag, label=f"{roi.name} - {image_name}")

                # Recreate and update the theme in case the ROI color was modified
                theme_tag = self._t(f"stats_theme_{roi_id}")
                if dpg.does_item_exist(theme_tag):
                    dpg.delete_item(theme_tag, children_only=True)
                else:
                    dpg.add_theme(tag=theme_tag)

                r, g, b = roi.color[:3]
                luminance = 0.299 * r + 0.587 * g + 0.114 * b
                text_color = [0, 0, 0, 255] if luminance > 128 else [255, 255, 255, 255]

                with dpg.theme_component(dpg.mvWindowAppItem, parent=theme_tag):
                    dpg.add_theme_color(dpg.mvThemeCol_TitleBg, roi.color + [255])
                    dpg.add_theme_color(dpg.mvThemeCol_TitleBgActive, roi.color + [255])
                    dpg.add_theme_color(dpg.mvThemeCol_Text, text_color)

                dpg.bind_item_theme(win_tag, theme_tag)

            content_tag = self._t(f"stats_content_{roi_id}")
            if dpg.does_item_exist(content_tag):
                vol_tag = self._t(f"stats_txt_vol_cc_{roi_id}")
                if dpg.does_item_exist(vol_tag):
                    self.update_stats_window_contents(viewer.image_id, roi_id)
                else:
                    dpg.delete_item(content_tag, children_only=True)
                    self.build_stats_window_contents(
                        content_tag, viewer.image_id, roi_id
                    )

    def on_roi_toggle_all_stats(self, sender, app_data, user_data):
        viewer = self.api.get_active_viewer()
        if not viewer or not viewer.image_id or not viewer.view_state:
            return

        filter_text = self._c.roi_filters.get(viewer.image_id, "")
        rois_to_toggle = []
        for roi_id, roi in list(viewer.view_state.rois.items()):
            if filter_text and filter_text not in roi.name.lower():
                continue
            rois_to_toggle.append(roi_id)

        if not rois_to_toggle:
            return

        any_open = any(
            self._t(f"stats_win_{roi_id}") in self.open_stats_wins
            for roi_id in rois_to_toggle
        )

        if any_open:
            for roi_id in rois_to_toggle:
                win_tag = self._t(f"stats_win_{roi_id}")
                if win_tag in self.open_stats_wins:
                    self.open_stats_wins.remove(win_tag)
                if dpg.does_item_exist(win_tag):
                    # Save position before deleting the window!
                    self.stats_win_positions[roi_id] = dpg.get_item_pos(win_tag)
                    dpg.delete_item(win_tag)
        else:
            for roi_id in rois_to_toggle:
                win_tag = self._t(f"stats_win_{roi_id}")
                if not dpg.does_item_exist(win_tag):
                    self.on_roi_stats_toggle(None, None, roi_id)

    def on_roi_stats_window_closed(self, sender, app_data, user_data):
        roi_id = user_data
        win_tag = self._t(f"stats_win_{roi_id}")
        if win_tag in self.open_stats_wins:
            self.open_stats_wins.remove(win_tag)
        if dpg.does_item_exist(win_tag):
            self.stats_win_positions[roi_id] = dpg.get_item_pos(win_tag)
            dpg.delete_item(win_tag)

        theme_tag = self._t(f"stats_theme_{roi_id}")
        if dpg.does_item_exist(theme_tag):
            dpg.delete_item(theme_tag)
        content_theme_tag = self._t(f"stats_content_theme_{roi_id}")
        if dpg.does_item_exist(content_theme_tag):
            dpg.delete_item(content_theme_tag)

    def close_all_stats_windows(self):
        for win_tag in list(self.open_stats_wins):
            prefix = self._t("stats_win_")
            if win_tag.startswith(prefix):
                roi_id = win_tag[len(prefix) :]
                self.on_roi_stats_window_closed(None, None, roi_id)
        self.open_stats_wins.clear()

    def on_roi_show_all(self, sender, app_data, user_data):
        viewer = self.api.get_active_viewer()
        if not viewer or not viewer.view_state:
            return
        filter_text = self._c.roi_filters.get(viewer.image_id, "")
        for roi in viewer.view_state.rois.values():
            if filter_text and filter_text not in roi.name.lower():
                continue
            roi.visible = True
            roi.is_contour = False
        viewer.view_state.is_data_dirty = True
        viewer.view_state.is_geometry_dirty = True
        self.api.request_refresh()
        self.api.update_all_viewers_of_image(viewer.image_id)

    def on_roi_contour_all(self, sender, app_data, user_data):
        viewer = self.api.get_active_viewer()
        if not viewer or not viewer.view_state:
            return
        filter_text = self._c.roi_filters.get(viewer.image_id, "")
        for roi in viewer.view_state.rois.values():
            if filter_text and filter_text not in roi.name.lower():
                continue
            roi.visible = True
            roi.is_contour = True
            for ori in roi.polygons:
                roi.polygons[ori].clear()
        viewer.view_state.is_data_dirty = True
        viewer.view_state.is_geometry_dirty = True
        self.api.request_refresh()
        self.api.update_all_viewers_of_image(viewer.image_id)

    def on_roi_hide_all(self, sender, app_data, user_data):
        viewer = self.api.get_active_viewer()
        if not viewer or not viewer.view_state:
            return
        filter_text = self._c.roi_filters.get(viewer.image_id, "")
        for roi in viewer.view_state.rois.values():
            if filter_text and filter_text not in roi.name.lower():
                continue
            roi.visible = False
        viewer.view_state.is_data_dirty = True
        viewer.view_state.is_geometry_dirty = True
        self.api.request_refresh()
        self.api.update_all_viewers_of_image(viewer.image_id)

    def on_roi_above_overlay_clicked(self, sender, app_data):
        viewer = self.api.get_active_viewer()
        if not viewer or not viewer.view_state:
            return
        val = getattr(viewer.view_state.display, "roi_above_overlay", False)
        if hasattr(val, "mock_calls"):
            val = False
        new_val = not bool(val)
        viewer.view_state.display.roi_above_overlay = new_val
        if new_val:
            if dpg.does_item_exist("active_nav_button_theme"):
                dpg.bind_item_theme(self._t("btn_roi_above_overlay"), "active_nav_button_theme")
        else:
            dpg.bind_item_theme(self._t("btn_roi_above_overlay"), 0)
        self.api.request_refresh()
        self.api.update_all_viewers_of_image(viewer.image_id)

    def on_roi_global_opacity_changed(self, sender, app_data, user_data):
        viewer = self.api.get_active_viewer()
        if not viewer or not viewer.view_state:
            return
        filter_text = self._c.roi_filters.get(viewer.image_id, "")
        for roi in viewer.view_state.rois.values():
            if filter_text and filter_text not in roi.name.lower():
                continue
            roi.opacity = app_data
        viewer.view_state.is_data_dirty = True
        self.api.request_refresh()
        self.api.update_all_viewers_of_image(viewer.image_id)

    def on_roi_global_thickness_changed(self, sender, app_data, user_data):
        viewer = self.api.get_active_viewer()
        if not viewer or not viewer.view_state:
            return
        filter_text = self._c.roi_filters.get(viewer.image_id, "")
        for roi in viewer.view_state.rois.values():
            if filter_text and filter_text not in roi.name.lower():
                continue
            roi.thickness = app_data
        viewer.view_state.is_geometry_dirty = True
        self.api.request_refresh()
        self.api.update_all_viewers_of_image(viewer.image_id, data_dirty=False)

    def on_roi_filter_changed(self, sender, app_data, user_data):
        self._c.on_roi_filter_changed(app_data)

    def on_clear_roi_filter_clicked(self, sender, app_data, user_data):
        if dpg.does_item_exist(self._t("input_roi_filter")):
            dpg.set_value(self._t("input_roi_filter"), "")
        self._c.on_clear_roi_filter()

    def on_sort_rois_clicked(self, sender, app_data, user_data):
        self._c.on_sort_rois()

    def on_export_roi_stats_clicked(self, sender, app_data, user_data):
        # Excluded from wiring in Step 2: remains mock popup
        if self.api:
            self.api.notify("ROI: Export stats clicked")

    def on_mock_action(self, sender, app_data, user_data):
        if self.api:
            self.api.notify(f"ROI: Slider or combo callback (sender: {sender})")

    def on_roi_opacity_changed(self, sender, app_data, user_data):
        viewer = self.api.get_active_viewer()
        if not viewer or not viewer.view_state:
            return
        vs = viewer.view_state
        vs.rois[user_data].opacity = app_data
        vs.is_data_dirty = True
        self.api.update_all_viewers_of_image(viewer.image_id)

    def on_roi_thickness_changed(self, sender, app_data, user_data):
        viewer = self.api.get_active_viewer()
        if not viewer or not viewer.view_state:
            return
        vs = viewer.view_state
        vs.rois[user_data].thickness = app_data
        vs.is_geometry_dirty = True
        self.api.update_all_viewers_of_image(viewer.image_id, data_dirty=False)

    def clear_roi_stats(self):
        tags = [
            "roi_stat_vol",
            "roi_stat_mean",
            "roi_stat_max",
            "roi_stat_min",
            "roi_stat_std",
            "roi_stat_peak",
            "roi_stat_mass",
        ]
        for tag in tags:
            full_tag = self._t(tag)
            if dpg.does_item_exist(full_tag):
                dpg.set_value(full_tag, "---")

    def update_roi_stats_ui(self):
        viewer = self.api.get_active_viewer()
        if (
            not viewer
            or not viewer.view_state
            or not self._c.active_roi_id
            or self._c.active_roi_id not in viewer.view_state.rois
        ):
            self.clear_roi_stats()
            return

        combo_tag = self._t("combo_roi_image")
        is_overlay = (
            dpg.get_value(combo_tag) == "Active Overlay"
            if dpg.does_item_exist(combo_tag)
            else False
        )

        stats = self.api.get_roi_stats(
            base_vs_id=viewer.image_id,
            roi_id=self._c.active_roi_id,
            is_overlay=is_overlay,
        )

        if not stats:
            self.clear_roi_stats()
            return

        dpg.set_value(self._t("roi_stat_vol"), f"{stats['vol']:.2f} cc")
        dpg.set_value(self._t("roi_stat_mean"), f"{stats['mean']:.2f}")
        dpg.set_value(self._t("roi_stat_max"), f"{stats['max']:.2f}")
        dpg.set_value(self._t("roi_stat_min"), f"{stats['min']:.2f}")
        dpg.set_value(self._t("roi_stat_std"), f"{stats['std']:.2f}")
        dpg.set_value(self._t("roi_stat_peak"), f"{stats['peak']:.2f}")
        dpg.set_value(self._t("roi_stat_mass"), f"{stats['mass']:.2f} g")

    def close_rtstruct_modal(self):
        modal_tag = self._t("rtstruct_selection_modal")
        if dpg.does_item_exist(modal_tag):
            dpg.delete_item(modal_tag)

    def save_settings(self, api: PluginAPI) -> None:
        pass

    def load_settings(self, api: PluginAPI) -> None:
        pass

    def on_add_spheroid_clicked(self, sender, app_data, user_data):
        viewer = self.api.get_active_viewer()
        if not viewer or not viewer.image_id:
            self.api.notify("Please select an active image first.")
            return
        self._c.on_add_spheroid(viewer.image_id)

    def on_add_rect_clicked(self, sender, app_data, user_data):
        viewer = self.api.get_active_viewer()
        if not viewer or not viewer.image_id:
            self.api.notify("Please select an active image first.")
            return
        self._c.on_add_box(viewer.image_id)

    def on_roi_stats_box_size_x_slider_changed(self, sender, app_data, user_data):
        roi_id = user_data
        viewer = self.api.get_active_viewer()
        if not viewer or not viewer.image_id or not viewer.view_state:
            return
        base_vol = self.api.get_volumes().get(viewer.image_id)
        roi_vol = self.api.get_volumes().get(roi_id)
        roi_state = viewer.view_state.rois.get(roi_id)
        if not base_vol or not roi_vol or not roi_state:
            return
        new_size = float(app_data)
        new_size = max(new_size, 1.0)

        roi_state.box_size_x = new_size
        self._c.update_box_mask(
            base_vol,
            roi_vol,
            roi_state,
            new_size_x=new_size,
        )

        for ori in roi_state.polygons:
            roi_state.polygons[ori].clear()

        viewer.view_state.is_geometry_dirty = True
        viewer.view_state.is_data_dirty = True
        self.api.update_all_viewers_of_image(viewer.image_id, data_dirty=True)
        if sender is None:
            self.api.request_refresh()
            self.refresh_all_open_stats_windows()

    def on_roi_stats_box_size_x_step_callback(self, sender, app_data, user_data):
        tag = user_data["tag"]
        prefix = self._t("slider_roi_box_size_x_")
        if not tag.startswith(prefix):
            return
        roi_id = tag[len(prefix) :]

        viewer = self.api.get_active_viewer()
        if not viewer or not viewer.image_id or not viewer.view_state:
            return
        roi_state = viewer.view_state.rois.get(roi_id)
        if not roi_state:
            return

        direction = user_data["dir"]
        current_size = getattr(roi_state, "box_size_x", 20.0)

        step_size = 1.0
        new_size = max(1.0, current_size + (step_size * direction))

        if dpg.does_item_exist(tag):
            dpg.set_value(tag, new_size)

        self.on_roi_stats_box_size_x_slider_changed(None, new_size, roi_id)

    def on_roi_stats_box_size_y_slider_changed(self, sender, app_data, user_data):
        roi_id = user_data
        viewer = self.api.get_active_viewer()
        if not viewer or not viewer.image_id or not viewer.view_state:
            return
        base_vol = self.api.get_volumes().get(viewer.image_id)
        roi_vol = self.api.get_volumes().get(roi_id)
        roi_state = viewer.view_state.rois.get(roi_id)
        if not base_vol or not roi_vol or not roi_state:
            return
        new_size = float(app_data)
        new_size = max(new_size, 1.0)

        roi_state.box_size_y = new_size
        self._c.update_box_mask(
            base_vol,
            roi_vol,
            roi_state,
            new_size_y=new_size,
        )

        for ori in roi_state.polygons:
            roi_state.polygons[ori].clear()

        viewer.view_state.is_geometry_dirty = True
        viewer.view_state.is_data_dirty = True
        self.api.update_all_viewers_of_image(viewer.image_id, data_dirty=True)
        if sender is None:
            self.api.request_refresh()
            self.refresh_all_open_stats_windows()

    def on_roi_stats_box_size_y_step_callback(self, sender, app_data, user_data):
        tag = user_data["tag"]
        prefix = self._t("slider_roi_box_size_y_")
        if not tag.startswith(prefix):
            return
        roi_id = tag[len(prefix) :]

        viewer = self.api.get_active_viewer()
        if not viewer or not viewer.image_id or not viewer.view_state:
            return
        roi_state = viewer.view_state.rois.get(roi_id)
        if not roi_state:
            return

        direction = user_data["dir"]
        current_size = getattr(roi_state, "box_size_y", 20.0)

        step_size = 1.0
        new_size = max(1.0, current_size + (step_size * direction))

        if dpg.does_item_exist(tag):
            dpg.set_value(tag, new_size)

        self.on_roi_stats_box_size_y_slider_changed(None, new_size, roi_id)

    def on_roi_stats_box_size_z_slider_changed(self, sender, app_data, user_data):
        roi_id = user_data
        viewer = self.api.get_active_viewer()
        if not viewer or not viewer.image_id or not viewer.view_state:
            return
        base_vol = self.api.get_volumes().get(viewer.image_id)
        roi_vol = self.api.get_volumes().get(roi_id)
        roi_state = viewer.view_state.rois.get(roi_id)
        if not base_vol or not roi_vol or not roi_state:
            return
        new_size = float(app_data)
        new_size = max(new_size, 1.0)

        roi_state.box_size_z = new_size
        self._c.update_box_mask(
            base_vol,
            roi_vol,
            roi_state,
            new_size_z=new_size,
        )

        for ori in roi_state.polygons:
            roi_state.polygons[ori].clear()

        viewer.view_state.is_geometry_dirty = True
        viewer.view_state.is_data_dirty = True
        self.api.update_all_viewers_of_image(viewer.image_id, data_dirty=True)
        if sender is None:
            self.api.request_refresh()
            self.refresh_all_open_stats_windows()

    def on_roi_stats_box_size_z_step_callback(self, sender, app_data, user_data):
        tag = user_data["tag"]
        prefix = self._t("slider_roi_box_size_z_")
        if not tag.startswith(prefix):
            return
        roi_id = tag[len(prefix) :]

        viewer = self.api.get_active_viewer()
        if not viewer or not viewer.image_id or not viewer.view_state:
            return
        roi_state = viewer.view_state.rois.get(roi_id)
        if not roi_state:
            return

        direction = user_data["dir"]
        current_size = getattr(roi_state, "box_size_z", 20.0)

        step_size = 1.0
        new_size = max(1.0, current_size + (step_size * direction))

        if dpg.does_item_exist(tag):
            dpg.set_value(tag, new_size)

        self.on_roi_stats_box_size_z_slider_changed(None, new_size, roi_id)

    def on_roi_stats_box_center_changed(self, sender, app_data, user_data):
        roi_id = user_data["roi_id"]
        coord_idx = user_data["coord_idx"]
        viewer = self.api.get_active_viewer()
        if not viewer or not viewer.image_id or not viewer.view_state:
            return
        base_vol = self.api.get_volumes().get(viewer.image_id)
        roi_vol = self.api.get_volumes().get(roi_id)
        roi_state = viewer.view_state.rois.get(roi_id)
        if not base_vol or not roi_vol or not roi_state:
            return

        val = float(app_data)
        if roi_state.box_center is None:
            roi_state.box_center = [0.0, 0.0, 0.0]
        roi_state.box_center[coord_idx] = val

        self._c.update_box_mask(
            base_vol,
            roi_vol,
            roi_state,
        )

        for ori in roi_state.polygons:
            roi_state.polygons[ori].clear()

        viewer.view_state.is_geometry_dirty = True
        viewer.view_state.is_data_dirty = True

        # Sync crosshair and slice
        if hasattr(viewer.view_state, "update_crosshair_from_phys"):
            import numpy as np
            viewer.view_state.update_crosshair_from_phys(np.array(roi_state.box_center))
            self.api.propagate_sync(viewer.image_id)

        self.api.update_all_viewers_of_image(viewer.image_id, data_dirty=True)
        self.api.request_refresh()
        self.refresh_all_open_stats_windows()
