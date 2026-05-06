import os
import json
import dearpygui.dearpygui as dpg
from vvv.ui.ui_components import build_section_title
from vvv.ui.ui_sequences import load_batch_rois_sequence
from vvv.ui.file_dialog import open_file_dialog, save_file_dialog


class RoiUI:
    """
    ARCHITECTURE MANDATES (UI Components):
    1. REACTIVE REFRESH ONLY: This class must only rebuild its ROI list when
       'refresh_rois_ui' is called by the MainGUI. Trigger refreshes via
       'self.controller.ui_needs_refresh = True'.

    2. STATE-DRIVEN BUILDING: The ROI table must be a direct reflection of
       the 'ViewState.rois' dictionary.

    3. ONE-WAY DATA FLOW: Callbacks (visibility toggle, color change) must
       update the 'ViewState' directly. The UI will reflect these changes
       automatically on the next reactive frame.

    4. DECOUPLED LOGIC: Keep ROI math (statistics, binarization) in the
       'ROIManager' or 'math' modules. This class is purely for layout.
    """

    def __init__(self, gui, controller):
        self.gui = gui
        self.controller = controller
        self.active_roi_id = None
        self.roi_selectables = {}
        self.roi_filters = {}
        self.roi_sort_orders = {}

    @staticmethod
    def build_tab_rois(gui):
        cfg_c = gui.ui_cfg["colors"]
        cfg_l = gui.ui_cfg["layout"]

        if not dpg.does_item_exist("roi_item_clicked_handler"):
            with dpg.item_handler_registry(tag="roi_item_clicked_handler"):
                dpg.add_item_clicked_handler(callback=gui.roi_ui.on_roi_input_clicked)

        if not dpg.does_item_exist("active_roi_input_theme"):
            with dpg.theme(tag="active_roi_input_theme"):
                with dpg.theme_component(dpg.mvInputText):
                    dpg.add_theme_color(dpg.mvThemeCol_Text, cfg_c["text_active"])
                    dpg.add_theme_color(dpg.mvThemeCol_FrameBg, [0, 0, 0, 0])
                    dpg.add_theme_style(dpg.mvStyleVar_FrameBorderSize, 0)

        if not dpg.does_item_exist("inactive_roi_input_theme"):
            with dpg.theme(tag="inactive_roi_input_theme"):
                with dpg.theme_component(dpg.mvInputText):
                    dpg.add_theme_color(dpg.mvThemeCol_FrameBg, [0, 0, 0, 0])
                    dpg.add_theme_style(dpg.mvStyleVar_FrameBorderSize, 0)

        if not dpg.does_item_exist("outdated_active_roi_input_theme"):
            with dpg.theme(tag="outdated_active_roi_input_theme"):
                with dpg.theme_component(dpg.mvInputText):
                    dpg.add_theme_color(dpg.mvThemeCol_Text, cfg_c["outdated"])
                    dpg.add_theme_color(dpg.mvThemeCol_FrameBg, [0, 0, 0, 0])
                    dpg.add_theme_style(dpg.mvStyleVar_FrameBorderSize, 0)

        if not dpg.does_item_exist("outdated_inactive_roi_input_theme"):
            with dpg.theme(tag="outdated_inactive_roi_input_theme"):
                with dpg.theme_component(dpg.mvInputText):
                    dpg.add_theme_color(dpg.mvThemeCol_Text, cfg_c["outdated"])
                    dpg.add_theme_color(dpg.mvThemeCol_FrameBg, [0, 0, 0, 0])
                    dpg.add_theme_style(dpg.mvStyleVar_FrameBorderSize, 0)

        with dpg.group(tag="tab_rois", show=False):
            build_section_title("ROI", cfg_c["text_header"])

            dpg.add_text(
                "No Image Selected",
                tag="text_roi_active_title",
                color=cfg_c["text_active"],
            )

            # --- TOP: Load & Import ---
            with dpg.group(horizontal=True):
                dpg.add_button(
                    label="Load ROI / RT-Struct / Label Map...",
                    width=-1,
                    callback=gui.roi_ui.on_load_roi_clicked,
                    tag="btn_roi_load",
                )

            with dpg.group(horizontal=True, tag="group_roi_mode"):
                dpg.add_text("Rule:")
                dpg.add_combo(
                    ["Ignore BG (val)", "Target FG (val)", "Label Map"],
                    default_value="Ignore BG (val)",
                    tag="combo_roi_mode",
                    width=130,
                    callback=gui.roi_ui.on_roi_mode_changed,
                )

            with dpg.group(horizontal=True, tag="group_roi_mode2"):
                dpg.add_text("Val:")
                dpg.add_input_float(
                    default_value=0.0, step=1.0, width=140, tag="input_roi_val"
                )

            dpg.add_spacer(height=10)

            # --- MIDDLE: The Master List ---
            with dpg.group(horizontal=True):
                # Show/Hide All Buttons
                btn_show = dpg.add_button(
                    label="\uf06e",
                    width=20,
                    callback=gui.roi_ui.on_roi_show_all,
                    tag="btn_roi_show_all",
                )
                btn_contour = dpg.add_button(
                    label="\uf040",
                    width=20,
                    callback=gui.roi_ui.on_roi_contour_all,
                    tag="btn_roi_contour_all",
                )
                btn_hide = dpg.add_button(
                    label="\uf070",
                    width=20,
                    callback=gui.roi_ui.on_roi_hide_all,
                    tag="btn_roi_hide_all",
                )
                btn_close_all = dpg.add_button(
                    label="\uf00d",
                    width=20,
                    callback=gui.roi_ui.on_roi_close_all,
                    tag="btn_roi_close_all",
                )
                if dpg.does_item_exist("icon_font_tag"):
                    dpg.bind_item_font(btn_show, "icon_font_tag")
                    dpg.bind_item_font(btn_contour, "icon_font_tag")
                    dpg.bind_item_font(btn_hide, "icon_font_tag")
                    dpg.bind_item_font(btn_close_all, "icon_font_tag")

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
                    tag="slider_roi_global_opacity",
                    width=50,
                    min_value=0.0,
                    max_value=1.0,
                    default_value=0.5,
                    callback=gui.roi_ui.on_roi_global_opacity_changed,
                )
                dpg.add_text("Thk:")
                dpg.add_slider_float(
                    tag="slider_roi_global_thickness",
                    width=50,
                    min_value=0.5,
                    max_value=10.0,
                    default_value=1.0,
                    callback=gui.roi_ui.on_roi_global_thickness_changed,
                )

            dpg.add_separator()

            with dpg.group(tag="group_roi_filter", show=False, horizontal=True):
                btn_sort = dpg.add_button(
                    label="\uf0dc",
                    width=20,
                    tag="btn_roi_sort",
                    callback=gui.roi_ui.on_sort_rois_clicked,
                )
                if dpg.does_item_exist("icon_font_tag"):
                    dpg.bind_item_font(btn_sort, "icon_font_tag")

                dpg.add_text("Filter:", color=cfg_c["text_dim"])
                dpg.add_input_text(
                    tag="input_roi_filter",
                    width=-30,
                    callback=gui.roi_ui.on_roi_filter_changed,
                )
                btn_clear_filter = dpg.add_button(
                    label="\uf00d",
                    width=20,
                    callback=gui.roi_ui.on_clear_roi_filter_clicked,
                )
                if dpg.does_item_exist("icon_font_tag"):
                    dpg.bind_item_font(btn_clear_filter, "icon_font_tag")

            with dpg.child_window(
                tag="roi_list_window", height=150, border=False, no_scrollbar=True
            ):
                with dpg.table(
                    tag="roi_list_table",
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

            # Export Button
            dpg.add_button(
                label="Export All Stats to JSON",
                width=-1,
                callback=gui.roi_ui.on_export_roi_stats_clicked,
                tag="btn_roi_export_stats",
            )
            dpg.add_spacer(height=10)

            # --- BOTTOM: The Detail Panel ---
            build_section_title("Selected ROI Properties", cfg_c["text_header"])

            with dpg.child_window(border=False, no_scrollbar=True):
                dpg.add_group(tag="roi_detail_container")

    def refresh_rois_ui(self):
        table_id = "roi_list_table"
        if not dpg.does_item_exist(table_id):
            return

        current_scroll = dpg.get_y_scroll(table_id)

        # Delete ONLY the rows (slot=1), leaving the table and scrollbar perfectly intact!
        dpg.delete_item(table_id, children_only=True, slot=1)
        self.roi_selectables.clear()

        viewer = self.gui.context_viewer

        if dpg.does_item_exist("text_roi_active_title"):
            if viewer and viewer.image_id and self.controller.volumes.get(viewer.image_id):
                name_str, is_outdated = self.controller.get_image_display_name(
                    viewer.image_id
                )
                dpg.set_value("text_roi_active_title", name_str)
                col = (
                    self.gui.ui_cfg["colors"]["outdated"]
                    if is_outdated
                    else self.gui.ui_cfg["colors"]["text_active"]
                )
                dpg.configure_item("text_roi_active_title", color=col)
            else:
                dpg.set_value("text_roi_active_title", "No Image Selected")
                dpg.configure_item(
                    "text_roi_active_title",
                    color=self.gui.ui_cfg["colors"]["text_active"],
                )

        if not viewer or not viewer.view_state or not viewer.view_state.rois:
            if dpg.does_item_exist("group_roi_filter"):
                dpg.configure_item("group_roi_filter", show=False)
            self.refresh_roi_detail_ui()
            return

        vs_id = viewer.image_id
        filter_text = self.roi_filters.get(vs_id, "")
        sort_order = self.roi_sort_orders.get(vs_id, 0)

        if dpg.does_item_exist("input_roi_filter") and not dpg.is_item_focused("input_roi_filter"):
            dpg.set_value("input_roi_filter", filter_text)

        if dpg.does_item_exist("btn_roi_sort"):
            if sort_order == 1:
                dpg.configure_item("btn_roi_sort", label="\uf15d")
            elif sort_order == -1:
                dpg.configure_item("btn_roi_sort", label="\uf15e")
            else:
                dpg.configure_item("btn_roi_sort", label="\uf0dc")

        total_rois = len(viewer.view_state.rois)
        if dpg.does_item_exist("group_roi_filter"):
            dpg.configure_item("group_roi_filter", show=total_rois > 10)

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

                is_active = roi_id == self.active_roi_id

                roi_vol = self.controller.volumes.get(roi_id)
                is_outdated = roi_vol._is_outdated if roi_vol else False

                with dpg.group(horizontal=True):
                    input_id = dpg.add_input_text(
                        default_value=roi.name,
                        width=-15 if is_outdated else -1,
                        user_data=roi_id,
                        callback=self.on_roi_name_changed,
                    )
                    if is_outdated:
                        dpg.add_text("*", color=self.gui.ui_cfg["colors"]["outdated"])

                self.roi_selectables[roi_id] = input_id
                dpg.bind_item_handler_registry(input_id, "roi_item_clicked_handler")

                if is_active:
                    dpg.bind_item_theme(input_id, "outdated_active_roi_input_theme" if is_outdated else "active_roi_input_theme")
                else:
                    dpg.bind_item_theme(input_id, "outdated_inactive_roi_input_theme" if is_outdated else "inactive_roi_input_theme")

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
                        label="\uf01e",  # Reload Icon
                        width=20,
                        user_data=roi_id,
                        callback=self.on_roi_reload,
                    )
                    with dpg.tooltip(btn_action):
                        dpg.add_text("Reload modified file")
                else:
                    btn_action = dpg.add_button(
                        label="\uf0c7",  # Save Icon
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

        # Safely re-apply the scroll position
        dpg.set_y_scroll(table_id, current_scroll)
        self.refresh_roi_detail_ui()

    def refresh_roi_detail_ui(self):
        container = "roi_detail_container"
        if not dpg.does_item_exist(container):
            return

        dpg.delete_item(container, children_only=True)
        viewer = self.gui.context_viewer

        if (
            not viewer
            or not viewer.view_state
            or not self.active_roi_id
            or self.active_roi_id not in viewer.view_state.rois
        ):
            dpg.add_text(
                "Select a ROI from the list above.",
                color=self.gui.ui_cfg["colors"]["text_dim"],
                parent=container,
            )
            self.clear_roi_stats()
            return

        roi_state = viewer.view_state.rois[self.active_roi_id]
        roi_vol = self.controller.volumes.get(self.active_roi_id)
        dim_col = self.gui.ui_cfg["colors"]["text_dim"]

        with dpg.group(parent=container):
            if roi_vol:
                # 1. Loading Rule (FG vs BG)
                mode_str = roi_state.source_mode
                val_str = f"{roi_state.source_val:g}"

                with dpg.group(horizontal=True):
                    dpg.add_text("Rule:", color=dim_col)
                    dpg.add_text(f"{mode_str} ({val_str})")

                # 2. Dimensions (Cropped Size)
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

            # --- EXISTING SECTION: Opacity & Analysis ---
            with dpg.group(horizontal=True):
                if roi_state.is_contour:
                    dpg.add_text("Thickness:")
                    active_slider_tag = "slider_roi_thickness"
                    dpg.add_slider_float(
                        default_value=getattr(roi_state, "thickness", 1.0),
                        min_value=0.5,
                        max_value=10.0,
                        width=-1,
                        tag=active_slider_tag,
                        user_data=self.active_roi_id,
                        callback=self.on_roi_thickness_changed,
                    )
                else:
                    dpg.add_text("Opacity:")
                    active_slider_tag = "slider_roi_opacity"
                    dpg.add_slider_float(
                        default_value=roi_state.opacity,
                        min_value=0.0,
                        max_value=1.0,
                        width=-1,
                        tag=active_slider_tag,
                        user_data=self.active_roi_id,
                        callback=self.on_roi_opacity_changed,
                    )

            # Theme code remains the same...
            theme_tag = "dynamic_roi_slider_theme"
            if dpg.does_item_exist(theme_tag):
                dpg.delete_item(theme_tag)
            with dpg.theme(tag=theme_tag):
                with dpg.theme_component(dpg.mvSliderFloat):
                    r, g, b = roi_state.color
                    dpg.add_theme_color(dpg.mvThemeCol_SliderGrab, [r, g, b, 255])
                    dpg.add_theme_color(
                        dpg.mvThemeCol_SliderGrabActive,
                        [min(255, r + 40), min(255, g + 40), min(255, b + 40), 255],
                    )
                    dpg.add_theme_color(dpg.mvThemeCol_FrameBgActive, [r, g, b, 100])
                    dpg.add_theme_color(dpg.mvThemeCol_FrameBgHovered, [r, g, b, 50])
            dpg.bind_item_theme(active_slider_tag, theme_tag)

            dpg.add_spacer(height=5)

            with dpg.group(horizontal=True):
                dpg.add_text("Analyze:")
                dpg.add_combo(
                    ["Base Image", "Active Overlay"],
                    default_value="Base Image",
                    tag="combo_roi_image",
                    width=-1,
                    callback=self.on_roi_stat_dropdown_changed,
                )

            # Stats Table remains the same...
            with dpg.table(header_row=False, borders_innerH=False):
                dpg.add_table_column(width_stretch=True)
                dpg.add_table_column(width_stretch=True)
                with dpg.table_row():
                    with dpg.group(horizontal=True):
                        dpg.add_text("Vol:", color=dim_col)
                        dpg.add_text("---", tag="roi_stat_vol")
                    with dpg.group(horizontal=True):
                        dpg.add_text("Mean:", color=dim_col)
                        dpg.add_text("---", tag="roi_stat_mean")
                with dpg.table_row():
                    with dpg.group(horizontal=True):
                        dpg.add_text("Max:", color=dim_col)
                        dpg.add_text("---", tag="roi_stat_max")
                    with dpg.group(horizontal=True):
                        dpg.add_text("Min:", color=dim_col)
                        dpg.add_text("---", tag="roi_stat_min")
                with dpg.table_row():
                    with dpg.group(horizontal=True):
                        dpg.add_text("Std:", color=dim_col)
                        dpg.add_text("---", tag="roi_stat_std")
                    with dpg.group(horizontal=True):
                        dpg.add_text("Peak:", color=dim_col)
                        dpg.add_text("---", tag="roi_stat_peak")
                    with dpg.group(horizontal=True):
                        dpg.add_text("Mass:", color=dim_col)
                        dpg.add_text("---", tag="roi_stat_mass")

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
            if dpg.does_item_exist(tag):
                dpg.set_value(tag, "---")

    def update_roi_stats_ui(self):
        viewer = self.gui.context_viewer
        if (
            not viewer
            or not viewer.view_state
            or not self.active_roi_id
            or self.active_roi_id not in viewer.view_state.rois
        ):
            self.clear_roi_stats()
            return

        is_overlay = (
            dpg.get_value("combo_roi_image") == "Active Overlay"
            if dpg.does_item_exist("combo_roi_image")
            else False
        )
        stats = self.controller.roi.get_roi_stats(
            base_vs_id=viewer.image_id, roi_id=self.active_roi_id, is_overlay=is_overlay
        )

        if not stats:
            self.clear_roi_stats()
            return

        dpg.set_value("roi_stat_vol", f"{stats['vol']:.2f} cc")
        dpg.set_value("roi_stat_mean", f"{stats['mean']:.2f}")
        dpg.set_value("roi_stat_max", f"{stats['max']:.2f}")
        dpg.set_value("roi_stat_min", f"{stats['min']:.2f}")
        dpg.set_value("roi_stat_std", f"{stats['std']:.2f}")
        dpg.set_value("roi_stat_peak", f"{stats['peak']:.2f}")
        dpg.set_value("roi_stat_mass", f"{stats['mass']:.2f} g")

    # --- Callbacks ---
    def on_roi_filter_changed(self, sender, app_data, user_data):
        viewer = self.gui.context_viewer
        if viewer and viewer.image_id:
            self.roi_filters[viewer.image_id] = app_data.lower() if app_data else ""
            self.refresh_rois_ui()

    def on_clear_roi_filter_clicked(self, sender, app_data, user_data):
        viewer = self.gui.context_viewer
        if viewer and viewer.image_id:
            self.roi_filters[viewer.image_id] = ""
            if dpg.does_item_exist("input_roi_filter"):
                dpg.set_value("input_roi_filter", "")
            self.refresh_rois_ui()

    def on_sort_rois_clicked(self, sender, app_data, user_data):
        viewer = self.gui.context_viewer
        if not viewer or not viewer.image_id:
            return
            
        vs_id = viewer.image_id
        current = self.roi_sort_orders.get(vs_id, 0)
        if current == 0:
            self.roi_sort_orders[vs_id] = 1
        elif current == 1:
            self.roi_sort_orders[vs_id] = -1
        else:
            self.roi_sort_orders[vs_id] = 0
        self.refresh_rois_ui()

    def on_roi_name_changed(self, sender, app_data, user_data):
        roi_id = user_data
        new_name = app_data
        viewer = self.gui.context_viewer
        if not viewer or not viewer.view_state:
            return

        vs = viewer.view_state
        if roi_id in vs.rois:
            vs.rois[roi_id].name = new_name

        roi_vol = self.controller.volumes.get(roi_id)
        if roi_vol:
            roi_vol.name = new_name

    def on_roi_input_clicked(self, sender, app_data, user_data):
        if not app_data or len(app_data) < 2:
            return
        item_id = app_data[1]
        roi_id = dpg.get_item_user_data(item_id)
        if roi_id and self.active_roi_id != roi_id:
            self.on_roi_selected(sender, None, roi_id)

    def on_load_roi_clicked(self, sender, app_data, user_data):
        viewer = self.gui.context_viewer
        if not viewer or not viewer.image_id:
            self.gui.show_status_message(
                "Select a base image first!", color=[255, 100, 100]
            )
            return

        mode = dpg.get_value("combo_roi_mode")
        is_label_map = mode == "Label Map"

        file_paths = open_file_dialog(
            "Load ROI(s) / RT-Struct", multiple=not is_label_map
        )
        if not file_paths:
            return

        if is_label_map:
            from vvv.ui.ui_sequences import load_label_map_sequence

            self.gui.tasks.append(
                load_label_map_sequence(
                    self.gui, self.controller, viewer.image_id, file_paths
                )
            )
            return

        # --- Logic for Binary Mask modes ---
        if isinstance(file_paths, str):
            file_paths = [file_paths]

        val = (
            dpg.get_value("input_roi_val")
            if dpg.does_item_exist("input_roi_val")
            else 0.0
        )

        first_file = file_paths[0]
        is_rtstruct = False

        # Smart Detection: Only parse with pydicom if it's not an obvious standard image format
        image_exts = [
            ".nii",
            ".nii.gz",
            ".mhd",
            ".mha",
            ".nrrd",
            ".png",
            ".jpg",
            ".tif",
        ]
        if not any(first_file.lower().endswith(ext) for ext in image_exts):
            try:
                import pydicom

                # Stop before pixels to read header instantly (<1ms)
                ds = pydicom.dcmread(first_file, stop_before_pixels=True, force=True)
                if getattr(ds, "Modality", None) == "RTSTRUCT":
                    is_rtstruct = True
            except Exception:
                pass

        if is_rtstruct:
            try:
                rois_info = self.controller.roi.parse_rtstruct(first_file)
            except Exception as e:
                self.gui.show_message("Error", f"Failed to parse RT-Struct:\n{e}")
                return

            if not rois_info:
                self.gui.show_message(
                    "No ROIs", "No valid ROIs found in this RT-Struct file."
                )
                return

            self.show_rtstruct_selection_modal(first_file, rois_info)
        else:
            from vvv.ui.ui_sequences import load_batch_rois_sequence

            self.gui.tasks.append(
                load_batch_rois_sequence(
                    self.gui,
                    self.controller,
                    viewer.image_id,
                    file_paths,
                    "Binary Mask",
                    mode,
                    val,
                )
            )

    def on_roi_mode_changed(self, sender, app_data, user_data):
        is_label_map = app_data == "Label Map"
        if dpg.does_item_exist("group_roi_mode2"):
            dpg.configure_item("group_roi_mode2", show=not is_label_map)

    def show_rtstruct_selection_modal(self, filepath, rois_info):
        modal_tag = "rtstruct_selection_modal"
        if dpg.does_item_exist(modal_tag):
            dpg.delete_item(modal_tag)

        self._rtstruct_cb_ids = []

        with dpg.window(
            tag=modal_tag,
            modal=True,
            show=True,
            label="Select ROIs to Load",
            no_collapse=True,
            width=450,
            height=500,
        ):
            dpg.add_text(
                f"File: {os.path.basename(filepath)}",
                color=self.gui.ui_cfg["colors"]["text_dim"],
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
                    viewer = self.gui.context_viewer
                    if viewer and viewer.image_id:
                        from vvv.ui.ui_sequences import load_rtstruct_sequence

                        self.gui.tasks.append(
                            load_rtstruct_sequence(
                                self.gui,
                                self.controller,
                                viewer.image_id,
                                filepath,
                                selected_rois,
                            )
                        )

                dpg.add_button(label="Load", width=80, callback=_on_load)

        vp_width = max(dpg.get_viewport_client_width(), 800)
        vp_height = max(dpg.get_viewport_client_height(), 600)
        dpg.set_item_pos(modal_tag, [vp_width // 2 - 225, vp_height // 2 - 250])

    def on_roi_toggle_visible(self, sender, app_data, user_data):
        vs = self.gui.context_viewer.view_state
        roi = vs.rois[user_data]

        # Tri-state toggle: Raster -> Contour -> Hidden -> Raster
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
        self.controller.ui_needs_refresh = True
        self.controller.update_all_viewers_of_image(self.gui.context_viewer.image_id)

    def on_roi_color_changed(self, sender, app_data, user_data):
        vs = self.gui.context_viewer.view_state
        scale = 255.0 if all(c <= 1.0 for c in app_data) else 1.0
        vs.rois[user_data].color = [int(c * scale) for c in app_data[:3]]
        vs.is_data_dirty = True
        self.controller.update_all_viewers_of_image(self.gui.context_viewer.image_id)

    def on_roi_opacity_changed(self, sender, app_data, user_data):
        vs = self.gui.context_viewer.view_state
        vs.rois[user_data].opacity = app_data
        vs.is_data_dirty = True
        self.controller.update_all_viewers_of_image(self.gui.context_viewer.image_id)

    def on_roi_thickness_changed(self, sender, app_data, user_data):
        vs = self.gui.context_viewer.view_state
        vs.rois[user_data].thickness = app_data
        vs.is_geometry_dirty = True
        self.controller.update_all_viewers_of_image(
            self.gui.context_viewer.image_id, data_dirty=False
        )

    def on_roi_save(self, sender, app_data, user_data):
        roi_id = user_data
        roi_vol = self.controller.volumes.get(roi_id)
        if not roi_vol:
            return

        default_name = roi_vol.name
        if not default_name.lower().endswith(".nii.gz"):
            default_name += ".nii.gz"

        file_path = save_file_dialog("Save ROI As", default_name=default_name)
        if file_path:
            self.gui.show_status_message(f"Saving {roi_vol.name}...")
            import threading

            def _save():
                self.controller.save_image(roi_id, file_path)

                # Convert the ROI to a standalone Binary Mask
                for vs in self.controller.view_states.values():
                    if roi_id in vs.rois:
                        r = vs.rois[roi_id]
                        r.source_type = "Binary"
                        r.source_mode = "Target FG (val)"
                        r.source_val = 1.0
                        r.rtstruct_info = None

                self.controller.status_message = f"Saved: {os.path.basename(file_path)}"
                self.controller.ui_needs_refresh = True

            threading.Thread(target=_save, daemon=True).start()

    def on_roi_reload(self, sender, app_data, user_data):
        self.controller.roi.reload_roi(self.gui.context_viewer.image_id, user_data)

    def on_roi_center(self, sender, app_data, user_data):
        self.controller.roi.center_on_roi(self.gui.context_viewer.image_id, user_data)

    def on_roi_selected(self, sender, app_data, user_data):
        self.active_roi_id = user_data
        for r_id, input_id in getattr(self, "roi_selectables", {}).items():
            if dpg.does_item_exist(input_id):
                roi_vol = self.controller.volumes.get(r_id)
                is_outdated = roi_vol._is_outdated if roi_vol else False
                if r_id == self.active_roi_id:
                    dpg.bind_item_theme(input_id, "outdated_active_roi_input_theme" if is_outdated else "active_roi_input_theme")
                else:
                    dpg.bind_item_theme(input_id, "outdated_inactive_roi_input_theme" if is_outdated else "inactive_roi_input_theme")
        self.refresh_roi_detail_ui()

    def on_roi_show_all(self, sender, app_data, user_data):
        viewer = self.gui.context_viewer
        if not viewer or not viewer.view_state:
            return
        filter_text = self.roi_filters.get(viewer.image_id, "")
        for roi in viewer.view_state.rois.values():
            if filter_text and filter_text not in roi.name.lower():
                continue
            roi.visible = True
            roi.is_contour = False
        viewer.view_state.is_data_dirty = True
        viewer.view_state.is_geometry_dirty = True
        self.controller.ui_needs_refresh = True
        self.controller.update_all_viewers_of_image(viewer.image_id)

    def on_roi_hide_all(self, sender, app_data, user_data):
        viewer = self.gui.context_viewer
        if not viewer or not viewer.view_state:
            return
        filter_text = self.roi_filters.get(viewer.image_id, "")
        for roi in viewer.view_state.rois.values():
            if filter_text and filter_text not in roi.name.lower():
                continue
            roi.visible = False
        viewer.view_state.is_data_dirty = True
        viewer.view_state.is_geometry_dirty = True
        self.controller.ui_needs_refresh = True
        self.controller.update_all_viewers_of_image(viewer.image_id)

    def on_roi_contour_all(self, sender, app_data, user_data):
        viewer = self.gui.context_viewer
        if not viewer or not viewer.view_state:
            return
        filter_text = self.roi_filters.get(viewer.image_id, "")
        for roi in viewer.view_state.rois.values():
            if filter_text and filter_text not in roi.name.lower():
                continue
            roi.visible = True
            roi.is_contour = True

            for ori in roi.polygons:
                roi.polygons[ori].clear()
        viewer.view_state.is_data_dirty = True
        viewer.view_state.is_geometry_dirty = True
        self.controller.ui_needs_refresh = True
        self.controller.update_all_viewers_of_image(viewer.image_id)

    def on_roi_global_opacity_changed(self, sender, app_data, user_data):
        viewer = self.gui.context_viewer
        if not viewer or not viewer.view_state:
            return
        filter_text = self.roi_filters.get(viewer.image_id, "")
        for roi in viewer.view_state.rois.values():
            if filter_text and filter_text not in roi.name.lower():
                continue
            roi.opacity = app_data
        viewer.view_state.is_data_dirty = True
        self.controller.ui_needs_refresh = True
        self.controller.update_all_viewers_of_image(viewer.image_id)

    def on_roi_global_thickness_changed(self, sender, app_data, user_data):
        viewer = self.gui.context_viewer
        if not viewer or not viewer.view_state:
            return
        filter_text = self.roi_filters.get(viewer.image_id, "")
        for roi in viewer.view_state.rois.values():
            if filter_text and filter_text not in roi.name.lower():
                continue
            roi.thickness = app_data
        viewer.view_state.is_geometry_dirty = True
        self.controller.ui_needs_refresh = True
        self.controller.update_all_viewers_of_image(viewer.image_id, data_dirty=False)

    def on_export_roi_stats_clicked(self, sender, app_data, user_data):
        viewer = self.gui.context_viewer
        if not viewer or not viewer.view_state or not viewer.view_state.rois:
            self.gui.show_status_message("No ROIs to export.", color=[255, 100, 100])
            return

        file_path = save_file_dialog("Export ROI Stats", default_name="roi_stats.json")
        if not file_path:
            return
        if not file_path.endswith(".json"):
            file_path += ".json"

        is_overlay = (
            dpg.get_value("combo_roi_image") == "Active Overlay"
            if dpg.does_item_exist("combo_roi_image")
            else False
        )
        results = {}
        for r_id, r_state in viewer.view_state.rois.items():
            stats = self.controller.roi.get_roi_stats(
                viewer.image_id, r_id, is_overlay=is_overlay
            )
            if stats:
                results[r_state.name] = stats

        try:
            with open(file_path, "w") as f:
                json.dump(results, f, indent=4)
            self.gui.show_status_message(
                f"Exported stats to {os.path.basename(file_path)}"
            )
        except Exception as e:
            self.gui.show_message("Export Failed", str(e))

    def on_roi_stat_dropdown_changed(self, sender, app_data, user_data):
        self.update_roi_stats_ui()

    def on_roi_close(self, sender, app_data, user_data):
        viewer = self.gui.context_viewer
        if not viewer or not viewer.image_id:
            return

        self.controller.roi.close_roi(viewer.image_id, user_data)
        if getattr(self, "active_roi_id", None) == user_data:
            self.active_roi_id = None

        self.controller.ui_needs_refresh = True

    def on_roi_close_all(self, sender, app_data, user_data):
        viewer = self.gui.context_viewer
        if not viewer or not viewer.image_id or not viewer.view_state:
            return

        filter_text = self.roi_filters.get(viewer.image_id, "")
        for roi_id, roi in list(viewer.view_state.rois.items()):
            if filter_text and filter_text not in roi.name.lower():
                continue
            self.controller.roi.close_roi(viewer.image_id, roi_id)

        if self.active_roi_id and self.active_roi_id not in viewer.view_state.rois:
            self.active_roi_id = None

        self.controller.ui_needs_refresh = True
