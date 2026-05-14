import time
import threading
import dearpygui.dearpygui as dpg
from vvv.ui.ui_components import build_section_title, build_stepped_slider, build_help_button, build_beginner_tooltip


class FusionUI:
    """Delegated UI handler for the Fusion tab."""

    def __init__(self, gui, controller):
        self.gui = gui
        self.controller = controller

    @staticmethod
    def build_tab_fusion(gui):
        cfg_c = gui.ui_cfg["colors"]
        with dpg.group(tag="tab_fusion", show=False):
            build_section_title("Active Fusion", cfg_c["text_header"])
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
                build_beginner_tooltip("combo_fusion_select", "Select the image to fuse as an overlay on top of the base image.", gui)
                with dpg.group(horizontal=True):
                    dpg.add_text("Opacity")
                    dpg.add_slider_float(
                        tag="slider_fusion_opacity",
                        min_value=0.0,
                        max_value=1.0,
                        width=-1,
                        callback=gui.fusion_ui.on_fusion_opacity_changed,
                    )

                build_stepped_slider(
                    "Window:",
                    "drag_fusion_ww",
                    callback=gui.fusion_ui.on_fusion_ww_changed,
                    step_callback=gui.fusion_ui.on_step_button_clicked,
                    min_val=1e-5,
                )
                build_stepped_slider(
                    "Level: ",
                    "drag_fusion_wl",
                    callback=gui.fusion_ui.on_fusion_wl_changed,
                    step_callback=gui.fusion_ui.on_step_button_clicked,
                )

                build_stepped_slider(
                    "Min Thr:",
                    "drag_fusion_threshold",
                    callback=gui.fusion_ui.on_fusion_threshold_changed,
                    step_callback=gui.fusion_ui.on_step_button_clicked,
                    has_checkbox=True,
                    check_tag="check_fusion_threshold",
                    check_cb=gui.fusion_ui.on_fusion_threshold_toggle,
                )
                build_beginner_tooltip("drag_fusion_threshold", "Pixels below this value will be completely transparent.", gui)

                with dpg.group(horizontal=True):
                    dpg.add_text("Mode   ")
                    combo = dpg.add_combo(
                        ["Alpha", "Registration", "Checkerboard", "DVF"],
                        tag="combo_fusion_mode",
                        width=-30,
                        callback=gui.fusion_ui.on_fusion_mode_changed,
                    )
                    build_help_button("Alpha: Standard transparency blending.\nRegistration: Red/Green difference map.\nCheckerboard: Alternating squares of base and overlay.\nDVF: Renders vectors as arrows.", gui)
                    with dpg.tooltip(combo, tag="tooltip_fusion_mode", show=False):
                        dpg.add_text("Base image format restricts blending to Alpha mode only.")
                dpg.add_text(
                    "RGB/DVF base: Alpha only",
                    tag="text_fusion_mode_restricted",
                    show=False,
                    color=cfg_c.get("outdated", [255, 200, 50, 200]),
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
        has_image = bool(viewer and viewer.view_state and viewer.volume)

        # 1. Clear UI completely if no base image is selected
        if not has_image:
            if dpg.does_item_exist("text_fusion_base_image"):
                dpg.set_value("text_fusion_base_image", "")
            if dpg.does_item_exist("group_fusion_checkerboard"):
                dpg.configure_item("group_fusion_checkerboard", show=False)

            # Empty out texts and disable
            for t in [
                "drag_fusion_ww",
                "drag_fusion_wl",
            ]:
                if dpg.does_item_exist(t):
                    dpg.set_value(t, 0.0)
                    dpg.configure_item(t, enabled=False)
                    if dpg.does_item_exist(f"btn_{t}_minus"):
                        dpg.configure_item(f"btn_{t}_minus", enabled=False)
                    if dpg.does_item_exist(f"btn_{t}_plus"):
                        dpg.configure_item(f"btn_{t}_plus", enabled=False)

            if dpg.does_item_exist("check_fusion_threshold"):
                dpg.set_value("check_fusion_threshold", False)
                dpg.configure_item("check_fusion_threshold", enabled=False)

            if dpg.does_item_exist("drag_fusion_threshold"):
                dpg.set_value("drag_fusion_threshold", 0.0)
                dpg.configure_item("drag_fusion_threshold", enabled=False)
                if dpg.does_item_exist("btn_drag_fusion_threshold_minus"):
                    dpg.configure_item("btn_drag_fusion_threshold_minus", enabled=False)
                if dpg.does_item_exist("btn_drag_fusion_threshold_plus"):
                    dpg.configure_item("btn_drag_fusion_threshold_plus", enabled=False)

            if dpg.does_item_exist("slider_fusion_opacity"):
                dpg.set_value("slider_fusion_opacity", 0.0)
                dpg.configure_item("slider_fusion_opacity", enabled=False)

            for t in ["combo_fusion_select", "combo_fusion_mode"]:
                if dpg.does_item_exist(t):
                    dpg.configure_item(t, enabled=False)
            return

        vol = viewer.volume
        is_base_restricted = getattr(vol, "is_rgb", False) or getattr(vol, "is_dvf", False)

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
            for vid, ovs in list(self.controller.view_states.items()):
                if vid != viewer.image_id:
                    # Filter out RGB as they cannot be used as overlays
                    if getattr(ovs.volume, "is_rgb", False):
                        continue
                    # Use the new helper for the dropdown options
                    opt_name, _ = self.controller.get_image_display_name(vid)
                    options.append(opt_name)

            dpg.configure_item("combo_fusion_select", items=options)
            dpg.configure_item("combo_fusion_select", enabled=True)

            current_sel = "None"
            has_overlay = False
            # Check if overlay is set AND actively exists in memory (guard against stale history references)
            if (
                viewer.view_state
                and viewer.view_state.display.overlay_id in self.controller.view_states
            ):
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
            tags_to_enable = ["combo_fusion_mode"]
            has_thr = False
            thr = None
            ov_vs = None
            if has_overlay:
                ov_vs = self.controller.view_states.get(viewer.view_state.display.overlay_id)
                if ov_vs and ov_vs.volume:
                    is_ov_rgb = ov_vs.volume.is_rgb
                    is_ov_dvf = getattr(ov_vs.volume, "is_dvf", False)
                    if not is_ov_rgb and not is_ov_dvf:
                        tags_to_enable.extend(
                            ["drag_fusion_ww", "drag_fusion_wl"]
                        )
                        if not dpg.is_item_active("drag_fusion_ww"):
                            dpg.set_value("drag_fusion_ww", ov_vs.display.ww)
                        if not dpg.is_item_active("drag_fusion_wl"):
                            dpg.set_value("drag_fusion_wl", ov_vs.display.wl)
                        
                        dynamic_speed = max(0.1, ov_vs.display.ww * 0.005)
                        dpg.configure_item("drag_fusion_ww", speed=dynamic_speed)
                        dpg.configure_item("drag_fusion_wl", speed=dynamic_speed)

                    thr = ov_vs.display.base_threshold
                    has_thr = thr is not None
            else:
                # Explicitly wipe the text inputs clean if there is no fusion overlay
                for t in [
                    "drag_fusion_ww",
                    "drag_fusion_wl",
                ]:
                    if dpg.does_item_exist(t):
                        dpg.set_value(t, 0.0)

            for t in [
                "drag_fusion_ww",
                "drag_fusion_wl",
                "combo_fusion_mode",
            ]:
                if dpg.does_item_exist(t):
                    is_enabled = (t in tags_to_enable and has_overlay)
                    dpg.configure_item(t, enabled=is_enabled)
                    if dpg.does_item_exist(f"btn_{t}_minus"):
                        dpg.configure_item(f"btn_{t}_minus", enabled=is_enabled)
                    if dpg.does_item_exist(f"btn_{t}_plus"):
                        dpg.configure_item(f"btn_{t}_plus", enabled=is_enabled)

            if dpg.does_item_exist("check_fusion_threshold"):
                dpg.set_value("check_fusion_threshold", has_thr)
                dpg.configure_item("check_fusion_threshold", enabled=has_overlay)

            if dpg.does_item_exist("drag_fusion_threshold"):
                if has_thr and not dpg.is_item_active("drag_fusion_threshold"):
                    dpg.set_value("drag_fusion_threshold", thr)
                thr_enabled = has_overlay and has_thr
                dpg.configure_item("drag_fusion_threshold", enabled=thr_enabled)
                if dpg.does_item_exist("btn_drag_fusion_threshold_minus"):
                    dpg.configure_item("btn_drag_fusion_threshold_minus", enabled=thr_enabled)
                if dpg.does_item_exist("btn_drag_fusion_threshold_plus"):
                    dpg.configure_item("btn_drag_fusion_threshold_plus", enabled=thr_enabled)
                
                if has_overlay and ov_vs:
                    dynamic_speed = max(0.1, ov_vs.display.ww * 0.005)
                    dpg.configure_item("drag_fusion_threshold", speed=dynamic_speed)

            if dpg.does_item_exist("combo_fusion_mode"):
                is_ov_dvf = False
                if has_overlay:
                    ov_vs = self.controller.view_states.get(viewer.view_state.display.overlay_id)
                    if ov_vs and getattr(ov_vs.volume, "is_dvf", False):
                        is_ov_dvf = True
                        
                if is_ov_dvf:
                    dpg.configure_item("combo_fusion_mode", items=["DVF"], enabled=False)
                    if viewer.view_state.display.overlay_mode != "DVF":
                        viewer.view_state.display.overlay_mode = "DVF"
                        viewer.view_state.is_data_dirty = True
                    if dpg.does_item_exist("tooltip_fusion_mode"):
                        dpg.configure_item("tooltip_fusion_mode", show=False)
                    if dpg.does_item_exist("text_fusion_mode_restricted"):
                        dpg.configure_item("text_fusion_mode_restricted", show=False)
                elif is_base_restricted:
                    dpg.configure_item("combo_fusion_mode", items=["Alpha"], enabled=False)
                    if dpg.does_item_exist("tooltip_fusion_mode"):
                        dpg.configure_item("tooltip_fusion_mode", show=True)
                    if dpg.does_item_exist("text_fusion_mode_restricted"):
                        dpg.configure_item("text_fusion_mode_restricted", show=True)
                    if viewer.view_state.display.overlay_mode != "Alpha":
                        viewer.view_state.display.overlay_mode = "Alpha"
                        viewer.view_state.is_data_dirty = True
                else:
                    dpg.configure_item("combo_fusion_mode", items=["Alpha", "Registration", "Checkerboard"], enabled=True)
                    if dpg.does_item_exist("tooltip_fusion_mode"):
                        dpg.configure_item("tooltip_fusion_mode", show=False)
                    if dpg.does_item_exist("text_fusion_mode_restricted"):
                        dpg.configure_item("text_fusion_mode_restricted", show=False)
                
                # Force the UI to reflect the actual mode in state!
                dpg.set_value("combo_fusion_mode", viewer.view_state.display.overlay_mode)

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
                "drag_fusion_ww",
                "drag_fusion_wl",
            ]:
                if dpg.does_item_exist(t) and not dpg.is_item_active(t):
                    if dpg.get_value(t) != 0.0:
                        dpg.set_value(t, 0.0)
            return

        ov_vs = self.controller.view_states.get(viewer.view_state.display.overlay_id)
        if not ov_vs:
            return

        # 1. Overlay W/L (from Overlay's ViewState)
        if not ov_vs.volume.is_rgb and not getattr(ov_vs.volume, "is_dvf", False):
            if dpg.does_item_exist("drag_fusion_ww") and not dpg.is_item_active("drag_fusion_ww"):
                current_ww = dpg.get_value("drag_fusion_ww")
                new_ww = ov_vs.display.ww
                if current_ww != new_ww:
                    dpg.set_value("drag_fusion_ww", new_ww)

            if dpg.does_item_exist("drag_fusion_wl") and not dpg.is_item_active("drag_fusion_wl"):
                current_wl = dpg.get_value("drag_fusion_wl")
                new_wl = ov_vs.display.wl
                if current_wl != new_wl:
                    dpg.set_value("drag_fusion_wl", new_wl)

        # 2. Overlay Threshold (Now synced perfectly with Image B's Base Settings)
        if dpg.does_item_exist("drag_fusion_threshold") and not dpg.is_item_active("drag_fusion_threshold"):
            current_thr = dpg.get_value("drag_fusion_threshold")
            new_thr = ov_vs.display.base_threshold
            if new_thr is not None and current_thr != new_thr:
                dpg.set_value("drag_fusion_threshold", new_thr)

    # Callbacks
    def on_fusion_ww_changed(self, sender, app_data, user_data):
        viewer = self.gui.context_viewer
        if not viewer or not viewer.view_state or not viewer.view_state.display.overlay_id:
            return

        ovs = self.controller.view_states.get(viewer.view_state.display.overlay_id)
        if not ovs or getattr(ovs.volume, "is_rgb", False):
            return

        ovs.display.ww = max(1e-20, app_data)
        viewer.view_state.is_data_dirty = True
        ovs.is_data_dirty = True
        self.controller.sync.propagate_window_level(viewer.view_state.display.overlay_id)
        self.controller.update_all_viewers_of_image(viewer.image_id)

    def on_fusion_wl_changed(self, sender, app_data, user_data):
        viewer = self.gui.context_viewer
        if not viewer or not viewer.view_state or not viewer.view_state.display.overlay_id:
            return

        ovs = self.controller.view_states.get(viewer.view_state.display.overlay_id)
        if not ovs or getattr(ovs.volume, "is_rgb", False):
            return

        ovs.display.wl = app_data
        viewer.view_state.is_data_dirty = True
        ovs.is_data_dirty = True
        self.controller.sync.propagate_window_level(viewer.view_state.display.overlay_id)
        self.controller.update_all_viewers_of_image(viewer.image_id)

    def on_fusion_threshold_toggle(self, sender, app_data, user_data):
        viewer = self.gui.context_viewer
        if not viewer or not viewer.view_state or not viewer.view_state.display.overlay_id:
            return
        ovs = self.controller.view_states.get(viewer.view_state.display.overlay_id)
        if not ovs:
            return

        is_enabled = app_data
        if is_enabled:
            val = dpg.get_value("drag_fusion_threshold")
            ovs.display.base_threshold = val
        else:
            ovs.display.base_threshold = None

        viewer.view_state.is_data_dirty = True
        ovs.is_data_dirty = True
        self.controller.sync.propagate_window_level(viewer.view_state.display.overlay_id)
        self.controller.update_all_viewers_of_image(viewer.image_id)
        self.controller.ui_needs_refresh = True

    def on_fusion_threshold_changed(self, sender, app_data, user_data):
        viewer = self.gui.context_viewer
        if not viewer or not viewer.view_state or not viewer.view_state.display.overlay_id:
            return
        ovs = self.controller.view_states.get(viewer.view_state.display.overlay_id)
        if not ovs:
            return

        ovs.display.base_threshold = app_data
        if dpg.does_item_exist("check_fusion_threshold"):
            dpg.set_value("check_fusion_threshold", True)
            
        viewer.view_state.is_data_dirty = True
        ovs.is_data_dirty = True
        self.controller.sync.propagate_window_level(viewer.view_state.display.overlay_id)
        self.controller.update_all_viewers_of_image(viewer.image_id)

    def on_step_button_clicked(self, sender, app_data, user_data):
        target_tag = user_data["tag"]
        direction = user_data["dir"]
        
        viewer = self.gui.context_viewer
        step_size = 1.0
        if viewer and viewer.view_state and viewer.view_state.display.overlay_id:
            ovs = self.controller.view_states.get(viewer.view_state.display.overlay_id)
            if ovs:
                step_size = max(0.1, ovs.display.ww * 0.02)
                
        current_val = dpg.get_value(target_tag)
        new_val = current_val + (step_size * direction)
        
        if target_tag == "drag_fusion_ww":
            new_val = max(1e-5, new_val)
            dpg.set_value(target_tag, new_val)
            self.on_fusion_ww_changed(sender, new_val, user_data)
        elif target_tag == "drag_fusion_wl":
            dpg.set_value(target_tag, new_val)
            self.on_fusion_wl_changed(sender, new_val, user_data)
        elif target_tag == "drag_fusion_threshold":
            dpg.set_value(target_tag, new_val)
            self.on_fusion_threshold_changed(sender, new_val, user_data)

    def on_fusion_target_selected(self, sender, app_data, user_data):
        viewer = self.gui.context_viewer
        if not viewer or not viewer.view_state:
            return

        if app_data == "None":
            viewer.view_state.set_overlay(None, None)
            self.controller.ui_needs_refresh = True
        else:
            target_id = None
            for vid in list(self.controller.view_states.keys()):
                opt_name, _ = self.controller.get_image_display_name(vid)
                if opt_name == app_data:
                    target_id = vid
                    break

            if not target_id:
                return

            target_vol = self.controller.volumes[target_id]

            self.gui.show_status_message("Resampling overlay to physical grid...")

            def _resample():
                # Guard against user rapidly closing the image while the thread boots
                if not viewer.view_state or viewer.image_id is None:
                    return
                viewer.view_state.set_overlay(target_id, target_vol, self.controller)
                self.controller.update_all_viewers_of_image(viewer.image_id)
                self.controller.status_message = "Overlay applied"
                self.controller.ui_needs_refresh = True

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
        self.controller.ui_needs_refresh = True

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
