import os
import json
import dearpygui.dearpygui as dpg
from vvv.ui.ui_sequences import load_batch_rois_sequence
from vvv.ui.file_dialog import open_file_dialog, save_file_dialog


class RoiUI:
    def __init__(self, gui, controller):
        self.gui = gui
        self.controller = controller
        self.active_roi_id = None
        self.roi_selectables = {}

    def refresh_rois_ui(self):
        container = "roi_list_container"
        if not dpg.does_item_exist(container):
            return

        current_scroll = 0.0
        if dpg.does_item_exist("roi_table"):
            current_scroll = dpg.get_y_scroll("roi_table")

        dpg.delete_item(container, children_only=True)
        self.roi_selectables.clear()

        viewer = self.gui.context_viewer

        if not viewer or not viewer.view_state or not viewer.view_state.rois:
            self.refresh_roi_detail_ui()
            return

        with dpg.table(
            tag="roi_table",
            parent=container,
            header_row=False,
            resizable=False,
            borders_innerH=False,
            scrollY=True,
        ):
            # 1. Color Box
            dpg.add_table_column(width_fixed=True, init_width_or_weight=20)
            # 2. ROI Name (This one stretches to fill all empty space!)
            dpg.add_table_column(width_stretch=True)
            # 3. Visible (Eye)
            dpg.add_table_column(width_fixed=True, init_width_or_weight=20)
            # 4. Center Target
            dpg.add_table_column(width_fixed=True, init_width_or_weight=20)
            # 5. Reload
            dpg.add_table_column(width_fixed=True, init_width_or_weight=20)
            # 6. Close/Delete
            dpg.add_table_column(width_fixed=True, init_width_or_weight=20)

            for roi_id, roi in viewer.view_state.rois.items():
                with dpg.table_row():
                    lbl_eye = "\uf06e" if roi.visible else "\uf070"
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
                    is_outdated = (
                        getattr(roi_vol, "_is_outdated", False) if roi_vol else False
                    )
                    label_str = f"{roi.name} *" if is_outdated else roi.name

                    sel_id = dpg.add_selectable(
                        label=label_str,
                        default_value=is_active,
                        user_data=roi_id,
                        callback=self.on_roi_selected,
                    )
                    self.roi_selectables[roi_id] = sel_id

                    if is_outdated and dpg.does_item_exist("outdated_item_theme"):
                        dpg.bind_item_theme(sel_id, "outdated_item_theme")

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
                    btn_reload = dpg.add_button(
                        label="\uf01e",
                        width=20,
                        user_data=roi_id,
                        callback=self.on_roi_reload,
                    )
                    btn_close = dpg.add_button(
                        label="\uf00d",
                        width=20,
                        user_data=roi_id,
                        callback=self.on_roi_close,
                    )

                    if dpg.does_item_exist("icon_font_tag"):
                        for btn in [btn_eye, btn_reload, btn_center, btn_close]:
                            dpg.bind_item_font(btn, "icon_font_tag")

                    if dpg.does_item_exist("delete_button_theme"):
                        dpg.bind_item_theme(btn_close, "delete_button_theme")

        dpg.set_y_scroll("roi_table", current_scroll)
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

        roi = viewer.view_state.rois[self.active_roi_id]

        with dpg.group(parent=container):
            with dpg.group(horizontal=True):
                dpg.add_text("Opacity:")
                dpg.add_slider_float(
                    default_value=roi.opacity,
                    min_value=0.0,
                    max_value=1.0,
                    width=-1,
                    tag="slider_roi_opacity",
                    user_data=self.active_roi_id,
                    callback=self.on_roi_opacity_changed,
                )

            theme_tag = "dynamic_roi_slider_theme"
            if dpg.does_item_exist(theme_tag):
                dpg.delete_item(theme_tag)
            with dpg.theme(tag=theme_tag):
                with dpg.theme_component(dpg.mvSliderFloat):
                    r, g, b = roi.color
                    dpg.add_theme_color(dpg.mvThemeCol_SliderGrab, [r, g, b, 255])
                    dpg.add_theme_color(
                        dpg.mvThemeCol_SliderGrabActive,
                        [min(255, r + 40), min(255, g + 40), min(255, b + 40), 255],
                    )
                    dpg.add_theme_color(dpg.mvThemeCol_FrameBgActive, [r, g, b, 100])
                    dpg.add_theme_color(dpg.mvThemeCol_FrameBgHovered, [r, g, b, 50])
            dpg.bind_item_theme("slider_roi_opacity", theme_tag)
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

            dim_col = self.gui.ui_cfg["colors"]["text_dim"]
            with dpg.table(header_row=False, borders_innerH=True):
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
                with dpg.table_row():
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
    def on_load_roi_clicked(self, sender, app_data, user_data):
        viewer = self.gui.context_viewer
        if not viewer or not viewer.image_id:
            self.gui.show_status_message(
                "Select a base image first!", color=[255, 100, 100]
            )
            return

        roi_type = (
            dpg.get_value("combo_roi_type")
            if dpg.does_item_exist("combo_roi_type")
            else "Binary Mask"
        )
        file_paths = open_file_dialog(f"Load {roi_type}(s)", multiple=True)
        if not file_paths:
            return
        if isinstance(file_paths, str):
            file_paths = [file_paths]

        mode = (
            dpg.get_value("combo_roi_mode")
            if dpg.does_item_exist("combo_roi_mode")
            else "Ignore BG (val)"
        )
        val = (
            dpg.get_value("input_roi_val")
            if dpg.does_item_exist("input_roi_val")
            else 0.0
        )

        self.gui.tasks.append(
            load_batch_rois_sequence(
                self.gui,
                self.controller,
                viewer.image_id,
                file_paths,
                roi_type,
                mode,
                val,
            )
        )

    def on_roi_toggle_visible(self, sender, app_data, user_data):
        vs = self.gui.context_viewer.view_state
        vs.rois[user_data].visible = not vs.rois[user_data].visible
        vs.is_data_dirty = True
        self.refresh_rois_ui()
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

    def on_roi_reload(self, sender, app_data, user_data):
        self.controller.roi.reload_roi(self.gui.context_viewer.image_id, user_data)

    def on_roi_center(self, sender, app_data, user_data):
        self.controller.roi.center_on_roi(self.gui.context_viewer.image_id, user_data)

    def on_roi_selected(self, sender, app_data, user_data):
        self.active_roi_id = user_data
        for r_id, sel_id in getattr(self, "roi_selectables", {}).items():
            if dpg.does_item_exist(sel_id):
                dpg.set_value(sel_id, r_id == self.active_roi_id)
        self.refresh_roi_detail_ui()

    def on_roi_show_all(self, sender, app_data, user_data):
        viewer = self.gui.context_viewer
        if not viewer or not viewer.view_state:
            return
        for roi in viewer.view_state.rois.values():
            roi.visible = True
        viewer.view_state.is_data_dirty = True
        self.refresh_rois_ui()
        self.controller.update_all_viewers_of_image(viewer.image_id)

    def on_roi_hide_all(self, sender, app_data, user_data):
        viewer = self.gui.context_viewer
        if not viewer or not viewer.view_state:
            return
        for roi in viewer.view_state.rois.values():
            roi.visible = False
        viewer.view_state.is_data_dirty = True
        self.refresh_rois_ui()
        self.controller.update_all_viewers_of_image(viewer.image_id)

    def on_roi_type_changed(self, sender, app_data, user_data):
        if dpg.does_item_exist("group_roi_mode"):
            dpg.configure_item("group_roi_mode", show=(app_data == "Binary Mask"))

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

        self.refresh_rois_ui()
        self.gui.update_sidebar_info(viewer)
