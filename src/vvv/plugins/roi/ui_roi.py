import os
import dearpygui.dearpygui as dpg
from typing import Optional
from vvv.plugins.plugin_api import PluginAPI, PluginTagMixin
from vvv.ui.ui_components import (
    build_section_title,
    build_help_button,
    build_beginner_tooltip,
)


class RoiPluginUI(PluginTagMixin):
    def __init__(self, plugin_id: str, controller):
        self._plugin_id = plugin_id
        self._c = controller
        self.api: PluginAPI = None  # type: ignore
        self.roi_selectables = {}

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
                    label="RT-Struct...",
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
                    label="Labels...",
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
                    label="Binary...",
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
                    self.api._gui,
                )

                dpg.add_input_float(
                    default_value=0.0, step=1.0, width=90, tag=self._t("input_roi_val")
                )

            dpg.add_spacer(height=10)

            # --- MIDDLE: Master List Controls ---
            with dpg.group(horizontal=True):
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
                btn_close_all = dpg.add_button(
                    label="\uf00d",
                    width=20,
                    callback=self.on_roi_close_all,
                    tag=self._t("btn_roi_close_all"),
                )

                if dpg.does_item_exist("icon_font_tag"):
                    for btn in [btn_show, btn_contour, btn_hide, btn_close_all]:
                        dpg.bind_item_font(btn, "icon_font_tag")

                if dpg.does_item_exist("delete_button_theme"):
                    dpg.bind_item_theme(btn_close_all, "delete_button_theme")

                with dpg.tooltip(btn_show):
                    dpg.add_text("Show All (Raster)")

                with dpg.tooltip(btn_contour):
                    dpg.add_text("Show All (Contour)")

                with dpg.tooltip(btn_hide):
                    dpg.add_text("Hide All")

                with dpg.tooltip(btn_close_all):
                    dpg.add_text("Close All")

                dpg.add_text("Op:")
                dpg.add_slider_float(
                    tag=self._t("slider_roi_global_opacity"),
                    width=50,
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
                dpg.add_text("Thk:")
                dpg.add_slider_float(
                    tag=self._t("slider_roi_global_thickness"),
                    width=50,
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
                height=150,
                border=False,
                no_scrollbar=True,
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
                        label="\uf00d",
                        width=20,
                        callback=self.on_close_roi_properties,
                        tag=self._t("btn_close_detail"),
                    )
                    if dpg.does_item_exist("icon_font_tag"):
                        dpg.bind_item_font(btn_close_detail, "icon_font_tag")
                    if dpg.does_item_exist("delete_button_theme"):
                        dpg.bind_item_theme(btn_close_detail, "delete_button_theme")
                dpg.add_separator()

            with dpg.child_window(
                tag=self._t("roi_detail_window"),
                border=False,
                no_scrollbar=True,
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

        toolbar_btns = [
            "btn_roi_load_rtstruct",
            "btn_roi_load_labels",
            "btn_roi_load_binary",
            "btn_roi_show_all",
            "btn_roi_contour_all",
            "btn_roi_hide_all",
            "btn_roi_close_all",
            "btn_roi_sort",
            "btn_clear_filter",
            "btn_roi_export_stats",
        ]
        for name in toolbar_btns:
            tag = self._t(name)
            if dpg.does_item_exist(tag):
                dpg.configure_item(tag, enabled=not is_mip)

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
            self.refresh_roi_detail_ui()
            return

        vs_id = viewer.image_id
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
                    user_data=roi_id,
                    callback=self.on_roi_color_changed,
                )

                is_active = roi_id == self._c.active_roi_id
                roi_vol = self.api.get_volumes().get(roi_id)
                is_outdated = roi_vol._is_outdated if roi_vol else False

                with dpg.group(horizontal=True):
                    input_id = dpg.add_input_text(
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
                    for btn in [btn_eye, btn_action, btn_center, btn_close]:
                        dpg.bind_item_font(btn, "icon_font_tag")

                if dpg.does_item_exist("delete_button_theme"):
                    dpg.bind_item_theme(btn_close, "delete_button_theme")

                if is_mip:
                    for btn in [btn_eye, btn_action, btn_center, btn_close]:
                        dpg.configure_item(btn, enabled=False)

        dpg.set_y_scroll(table_id, current_scroll)
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
            self.api._gui.on_window_resize()
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
            if roi_vol:
                # 0. Source file and type
                source_type = getattr(roi_state, "source_type", "Binary")
                if roi_vol.file_paths:
                    fname = os.path.basename(roi_vol.file_paths[0])
                    with dpg.group(horizontal=True):
                        dpg.add_text("File:", color=dim_col)
                        file_tag = dpg.add_text(fname)
                        with dpg.tooltip(file_tag):
                            dpg.add_text(roi_vol.file_paths[0])
                        dpg.add_text(f"[{source_type}]", color=dim_col)

                dpg.add_spacer(height=3)

                # 1. Loading Rule
                mode_str = getattr(roi_state, "source_mode", "Binary")
                val_str = f"{getattr(roi_state, 'source_val', 1.0):g}"
                with dpg.group(horizontal=True):
                    dpg.add_text("Rule:", color=dim_col)
                    dpg.add_text(f"{mode_str} ({val_str})")

                # 2. Dimensions
                z, y, x = roi_vol.shape3d
                with dpg.group(horizontal=True):
                    dpg.add_text("Size:", color=dim_col)
                    dpg.add_text(f"{x} x {y} x {z}")

                # 3. Spacing
                sx, sy, sz = roi_vol.spacing
                with dpg.group(horizontal=True):
                    dpg.add_text("Spacing:", color=dim_col)
                    dpg.add_text(f"{sx:.3f} x {sy:.3f} x {sz:.3f}")

                dpg.add_spacer(height=5)

            # 4. Opacity/Thickness
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

            # 5. Analysis
            with dpg.group(horizontal=True):
                dpg.add_text("Analyze:")
                dpg.add_combo(
                    ["Base Image", "Active Overlay"],
                    default_value="Base Image",
                    tag=self._t("combo_roi_image"),
                    width=-1,
                    callback=self.on_roi_stat_dropdown_changed,
                )

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
                        dpg.add_text("Peak:", color=dim_col)
                        dpg.add_text("---", tag=self._t("roi_stat_peak"))
                    with dpg.group(horizontal=True):
                        dpg.add_text("Mass:", color=dim_col)
                        dpg.add_text("---", tag=self._t("roi_stat_mass"))

        self.update_roi_stats_ui()
        self.api._gui.on_window_resize()

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
            self.api._gui.show_message("Error", f"Failed to parse RT-Struct:\n{e}")
            return

        if not rois_info:
            self.api._gui.show_message(
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
        self.api.update_all_viewers_of_image(viewer.image_id)

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
            import threading

            def _save():
                self.api.save_image(roi_id, file_path)

                for vs in self.api.get_view_states().values():
                    if roi_id in vs.rois:
                        r = vs.rois[roi_id]
                        r.source_type = "Binary"
                        r.source_mode = "Target FG (val)"
                        r.source_val = 1.0
                        r.rtstruct_info = None

                self.api.set_async_status(f"Saved: {os.path.basename(file_path)}")
                self.api.request_refresh()

            threading.Thread(target=_save, daemon=True).start()

    def on_roi_close(self, sender, app_data, user_data):
        viewer = self.api.get_active_viewer()
        if not viewer or not viewer.image_id:
            return

        self.api.close_roi(viewer.image_id, user_data)
        if self._c.active_roi_id == user_data:
            self._c.active_roi_id = None

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

        if (
            self._c.active_roi_id
            and self._c.active_roi_id not in viewer.view_state.rois
        ):
            self._c.active_roi_id = None

        self.api.request_refresh()

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

    def on_roi_stat_dropdown_changed(self, sender, app_data, user_data):
        self.update_roi_stats_ui()

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
        if dpg.does_item_exist(self._t("combo_roi_mode")):
            api._controller.update_setting(
                ["behavior", f"{self._plugin_id}_default_mode"],
                dpg.get_value(self._t("combo_roi_mode")),
            )
        if dpg.does_item_exist(self._t("input_roi_val")):
            api._controller.update_setting(
                ["behavior", f"{self._plugin_id}_default_val"],
                dpg.get_value(self._t("input_roi_val")),
            )

    def load_settings(self, api: PluginAPI) -> None:
        ctrl = api._controller
        mode = ctrl.settings.data.get("behavior", {}).get(
            f"{self._plugin_id}_default_mode", "Ignore BG (val)"
        )
        val = ctrl.settings.data.get("behavior", {}).get(
            f"{self._plugin_id}_default_val", 0.0
        )
        if dpg.does_item_exist(self._t("combo_roi_mode")):
            dpg.set_value(self._t("combo_roi_mode"), mode)
        if dpg.does_item_exist(self._t("input_roi_val")):
            dpg.set_value(self._t("input_roi_val"), float(val))
