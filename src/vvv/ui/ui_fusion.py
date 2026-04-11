import time
import threading
import dearpygui.dearpygui as dpg


class FusionUI:
    """Delegated UI handler for the Fusion tab."""

    def __init__(self, gui, controller):
        self.gui = gui
        self.controller = controller

    @staticmethod
    def build_tab_fusion(gui):
        cfg_c = gui.ui_cfg["colors"]
        with dpg.tab(label="Fusion", tag="tab_fusion"):
            dpg.add_spacer(height=5)
            dpg.add_text("Active Fusion", color=cfg_c["text_header"])
            dpg.add_separator()
            with dpg.group(tag="image_fusion_group"):
                with dpg.group(horizontal=True):
                    dpg.add_text("Base   ")
                    dpg.add_text(
                        "-", tag="text_fusion_base_image", color=cfg_c["text_active"]
                    )
                with dpg.group(horizontal=True):
                    dpg.add_text("Target ")
                    dpg.add_combo(
                        ["None"],
                        tag="combo_fusion_select",
                        width=-1,
                        callback=gui.fusion_ui.on_fusion_target_selected,
                    )
                with dpg.group(horizontal=True):
                    dpg.add_text("Opacity")
                    dpg.add_slider_float(
                        tag="slider_fusion_opacity",
                        min_value=0.0,
                        max_value=1.0,
                        width=-1,
                        callback=gui.fusion_ui.on_fusion_opacity_changed,
                    )

                # W/L & Threshold Layout (Matches Active Viewer)
                dim_color = cfg_c["text_dim"]
                with dpg.group(horizontal=True):
                    with dpg.group(horizontal=True):
                        dpg.add_text("Window", color=dim_color)
                        dpg.add_input_text(
                            tag="fusion_info_window",
                            width=65,
                            on_enter=True,
                            callback=gui.fusion_ui.on_fusion_wl_change,
                        )
                    dpg.add_spacer(width=5)
                    with dpg.group(horizontal=True):
                        dpg.add_text("Level", color=dim_color)
                        dpg.add_input_text(
                            tag="fusion_info_level",
                            width=65,
                            on_enter=True,
                            callback=gui.fusion_ui.on_fusion_wl_change,
                        )

                with dpg.group(horizontal=True):
                    dpg.add_text("Min Threshold", color=dim_color)
                    dpg.add_input_text(
                        tag="fusion_info_threshold",
                        width=65,
                        on_enter=True,
                        callback=gui.fusion_ui.on_fusion_wl_change,
                    )

                with dpg.group(horizontal=True):
                    dpg.add_text("Mode   ")
                    dpg.add_combo(
                        ["Alpha", "Registration", "Checkerboard"],
                        tag="combo_fusion_mode",
                        width=-1,
                        callback=gui.fusion_ui.on_fusion_mode_changed,
                    )
                with dpg.group(
                    horizontal=True, tag="group_fusion_checkerboard", show=False
                ):
                    dpg.add_text("Square ")
                    dpg.add_slider_float(
                        tag="slider_fusion_chk_size",
                        min_value=1.0,
                        max_value=200.0,
                        format="%.1f mm",
                        width=100,
                        callback=gui.fusion_ui.on_fusion_checkerboard_changed,
                    )
                    dpg.add_checkbox(
                        label="Swap",
                        tag="check_fusion_chk_swap",
                        callback=gui.fusion_ui.on_fusion_checkerboard_changed,
                    )

    def refresh_fusion_ui(self):
        viewer = self.gui.context_viewer
        # UI should only consider the viewer "active" if the ViewState actually exists in memory!
        has_image = (
            viewer is not None and getattr(viewer, "view_state", None) is not None
        )

        # 1. Clear UI completely if no base image is selected
        if not has_image:
            if dpg.does_item_exist("text_fusion_base_image"):
                dpg.set_value("text_fusion_base_image", "")
            if dpg.does_item_exist("group_fusion_checkerboard"):
                dpg.configure_item("group_fusion_checkerboard", show=False)

            # Empty out texts and disable
            for t in [
                "fusion_info_window",
                "fusion_info_level",
                "fusion_info_threshold",
            ]:
                if dpg.does_item_exist(t):
                    dpg.set_value(t, "")
                    dpg.configure_item(t, enabled=False)

            if dpg.does_item_exist("slider_fusion_opacity"):
                dpg.set_value("slider_fusion_opacity", 0.0)
                dpg.configure_item("slider_fusion_opacity", enabled=False)

            for t in ["combo_fusion_select", "combo_fusion_mode"]:
                if dpg.does_item_exist(t):
                    dpg.configure_item(t, enabled=False)
            return

        vol = viewer.volume

        if dpg.does_item_exist("text_fusion_base_image"):
            name_str, is_outdated = self.controller.get_image_display_name(
                viewer.image_id
            )
            dpg.set_value("text_fusion_base_image", name_str)

            col = (
                self.gui.ui_cfg["colors"]["outdated"]
                if is_outdated
                else self.gui.ui_cfg["colors"]["text_active"]
            )
            dpg.configure_item("text_fusion_base_image", color=col)

        if dpg.does_item_exist("combo_fusion_select"):
            options = ["None"]
            for vid, ovs in self.controller.view_states.items():
                if vid != viewer.image_id:
                    # Use the new helper for the dropdown options
                    opt_name, _ = self.controller.get_image_display_name(vid)
                    options.append(opt_name)

            dpg.configure_item("combo_fusion_select", items=options)
            dpg.configure_item("combo_fusion_select", enabled=True)

            current_sel = "None"
            has_overlay = False
            if viewer.view_state and viewer.view_state.display.overlay_id:
                has_overlay = True
                # Use the new helper for the currently selected item
                opt_name, _ = self.controller.get_image_display_name(
                    viewer.view_state.display.overlay_id
                )
                current_sel = opt_name

            dpg.set_value("combo_fusion_select", current_sel)

            is_chk = viewer.view_state.display.overlay_mode == "Checkerboard"
            if dpg.does_item_exist("slider_fusion_opacity"):
                dpg.configure_item(
                    "slider_fusion_opacity", enabled=has_overlay and not is_chk
                )
                if not has_overlay:
                    dpg.set_value("slider_fusion_opacity", 0.0)

            # Enable/Disable New W/L Text Boxes
            tags_to_enable = ["fusion_info_threshold", "combo_fusion_mode"]
            if has_overlay:
                ov_vs = self.controller.view_states[
                    viewer.view_state.display.overlay_id
                ]
                is_ov_rgb = getattr(ov_vs.volume, "is_rgb", False)
                if not is_ov_rgb:
                    tags_to_enable.extend(["fusion_info_window", "fusion_info_level"])
                else:
                    dpg.set_value("fusion_info_window", "RGB")
                    dpg.set_value("fusion_info_level", "RGB")
            else:
                # Explicitly wipe the text inputs clean if there is no fusion overlay
                for t in [
                    "fusion_info_window",
                    "fusion_info_level",
                    "fusion_info_threshold",
                ]:
                    if dpg.does_item_exist(t):
                        dpg.set_value(t, "")

            for t in [
                "fusion_info_window",
                "fusion_info_level",
                "fusion_info_threshold",
                "combo_fusion_mode",
            ]:
                if dpg.does_item_exist(t):
                    dpg.configure_item(t, enabled=(t in tags_to_enable and has_overlay))

            if dpg.does_item_exist("group_fusion_checkerboard"):
                dpg.configure_item(
                    "group_fusion_checkerboard", show=has_overlay and is_chk
                )

        # Ensure the text values are immediately correct
        self.sync_fusion_ui()

    def sync_fusion_ui(self):
        """Called every frame to update the text boxes if they changed via hotkeys (e.g., 'X' Auto-Window)."""
        viewer = self.gui.context_viewer

        # If there is no active overlay, ensure the inputs stay empty
        if (
            not viewer
            or not viewer.view_state
            or not viewer.view_state.display.overlay_id
        ):
            for t in [
                "fusion_info_window",
                "fusion_info_level",
                "fusion_info_threshold",
            ]:
                if dpg.does_item_exist(t) and not dpg.is_item_focused(t):
                    if dpg.get_value(t) != "":
                        dpg.set_value(t, "")
            return

        ov_vs = self.controller.view_states.get(viewer.view_state.display.overlay_id)
        if not ov_vs:
            return

        # 1. Overlay W/L (from Overlay's ViewState)
        if not getattr(ov_vs.volume, "is_rgb", False):
            if dpg.does_item_exist("fusion_info_window") and not dpg.is_item_focused(
                "fusion_info_window"
            ):
                current_ww = dpg.get_value("fusion_info_window")
                new_ww = f"{ov_vs.display.ww:g}"
                if current_ww != new_ww:
                    dpg.set_value("fusion_info_window", new_ww)

            if dpg.does_item_exist("fusion_info_level") and not dpg.is_item_focused(
                "fusion_info_level"
            ):
                current_wl = dpg.get_value("fusion_info_level")
                new_wl = f"{ov_vs.display.wl:g}"
                if current_wl != new_wl:
                    dpg.set_value("fusion_info_level", new_wl)

        # 2. Overlay Threshold (Now synced perfectly with Image B's Base Settings)
        if dpg.does_item_exist("fusion_info_threshold") and not dpg.is_item_focused(
            "fusion_info_threshold"
        ):
            current_thr = dpg.get_value("fusion_info_threshold")
            new_thr = f"{ov_vs.display.base_threshold:g}"
            if current_thr != new_thr:
                dpg.set_value("fusion_info_threshold", new_thr)

    # Callbacks
    def on_fusion_wl_change(self, sender, app_data, user_data):
        viewer = self.gui.context_viewer
        if (
            not viewer
            or not viewer.view_state
            or not viewer.view_state.display.overlay_id
        ):
            return

        try:
            new_ww = float(dpg.get_value("fusion_info_window"))
            new_wl = float(dpg.get_value("fusion_info_level"))

            thr_str = dpg.get_value("fusion_info_threshold")
            new_thr = float(thr_str) if thr_str.strip() else -1e9

            ovs = self.controller.view_states[viewer.view_state.display.overlay_id]

            # Update the properties directly on Image B!
            ovs.display.base_threshold = new_thr

            if not getattr(ovs.volume, "is_rgb", False):
                ovs.display.ww = max(1e-20, new_ww)
                ovs.display.wl = new_wl
                self.controller.sync.propagate_window_level(
                    viewer.view_state.display.overlay_id
                )

            viewer.view_state.is_data_dirty = True
            ovs.is_data_dirty = True

            self.controller.update_all_viewers_of_image(viewer.image_id)
        except ValueError:
            pass

    def on_fusion_target_selected(self, sender, app_data, user_data):
        viewer = self.gui.context_viewer
        if not viewer or not viewer.view_state:
            return

        if app_data == "None":
            viewer.view_state.set_overlay(None, None)
            self.refresh_fusion_ui()
        else:
            target_id = None
            for vid in self.controller.view_states.keys():
                opt_name, _ = self.controller.get_image_display_name(vid)
                if opt_name == app_data:
                    target_id = vid
                    break

            if not target_id:
                return

            target_vol = self.controller.volumes[target_id]

            def _resample():
                self.gui.show_status_message(f"Resampling overlay to physical grid...")
                viewer.view_state.set_overlay(target_id, target_vol, self.controller)
                self.controller.update_all_viewers_of_image(viewer.image_id)
                self.gui.show_status_message("Overlay applied")
                self.refresh_fusion_ui()

            threading.Thread(target=_resample, daemon=True).start()

    def on_fusion_mode_changed(self, sender, app_data, user_data):
        viewer = self.gui.context_viewer
        if not viewer or not viewer.view_state:
            return
        viewer.view_state.display.overlay_mode = app_data
        viewer.view_state.is_data_dirty = True

        if app_data == "Registration":
            self.controller.sync.propagate_window_level(viewer.image_id)

        self.controller.sync.propagate_overlay_mode(viewer.image_id)
        self.refresh_fusion_ui()

    def on_fusion_checkerboard_changed(self, sender, app_data, user_data):
        viewer = self.gui.context_viewer
        if not viewer or not viewer.view_state:
            return

        if sender == "slider_fusion_chk_size":
            viewer.view_state.display.overlay_checkerboard_size = app_data
        elif sender == "check_fusion_chk_swap":
            viewer.view_state.display.overlay_checkerboard_swap = app_data

        viewer.view_state.is_data_dirty = True
        self.controller.sync.propagate_overlay_mode(viewer.image_id)

    def on_fusion_opacity_changed(self, sender, app_data, user_data):
        if self.gui.context_viewer and self.gui.context_viewer.view_state:
            self.gui.context_viewer.view_state.display.overlay_opacity = app_data
            self.gui.context_viewer.view_state.is_data_dirty = True
