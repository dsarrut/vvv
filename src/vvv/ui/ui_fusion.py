import time
import threading
import dearpygui.dearpygui as dpg


class FusionUI:
    """Delegated UI handler for the Fusion tab."""

    def __init__(self, gui, controller):
        self.gui = gui
        self.controller = controller

    def refresh_fusion_ui(self):
        viewer = self.gui.context_viewer
        has_image = viewer is not None and viewer.image_id is not None

        # 1. Clear UI if no image is selected
        if not has_image:
            if dpg.does_item_exist("text_fusion_base_image"):
                dpg.set_value("text_fusion_base_image", "")
            if dpg.does_item_exist("group_fusion_checkerboard"):
                dpg.configure_item("group_fusion_checkerboard", show=False)
            for t in [
                "combo_fusion_select",
                "slider_fusion_opacity",
                "input_fusion_threshold",
                "combo_fusion_mode",
            ]:
                if dpg.does_item_exist(t):
                    dpg.configure_item(t, enabled=False)
            return

        # 2. Populate UI with the Active Image
        vol = viewer.volume
        if dpg.does_item_exist("text_fusion_base_image"):
            dpg.set_value("text_fusion_base_image", vol.name)

        if dpg.does_item_exist("combo_fusion_select"):
            options = ["None"]
            for vid, ovs in self.controller.view_states.items():
                if vid != viewer.image_id:
                    options.append(f"{vid}: {ovs.volume.name}")

            dpg.configure_item("combo_fusion_select", items=options)
            dpg.configure_item("combo_fusion_select", enabled=True)

            # Evaluate if we currently have an overlay (Backend concept)
            current_sel = "None"
            has_overlay = False
            if viewer.view_state.display.overlay_id:
                has_overlay = True
                ovs_name = self.controller.view_states[
                    viewer.view_state.display.overlay_id
                ].volume.name
                current_sel = f"{viewer.view_state.display.overlay_id}: {ovs_name}"

            dpg.set_value("combo_fusion_select", current_sel)

            # Disable/Enable the controls dynamically
            is_chk = viewer.view_state.display.overlay_mode == "Checkerboard"
            dpg.configure_item(
                "slider_fusion_opacity", enabled=has_overlay and not is_chk
            )
            dpg.configure_item("input_fusion_threshold", enabled=has_overlay)
            if dpg.does_item_exist("combo_fusion_mode"):
                dpg.configure_item("combo_fusion_mode", enabled=has_overlay)

            # Show/Hide the extra row
            if dpg.does_item_exist("group_fusion_checkerboard"):
                dpg.configure_item(
                    "group_fusion_checkerboard", show=has_overlay and is_chk
                )

    # --- Callbacks ---
    def on_fusion_target_selected(self, sender, app_data, user_data):
        viewer = self.gui.context_viewer
        if not viewer or not viewer.view_state:
            return

        if app_data == "None":
            viewer.view_state.set_overlay(None, None)
            self.refresh_fusion_ui()
        else:
            target_id = app_data.split(":")[0]
            target_vol = self.controller.volumes[target_id]
            self.gui.show_status_message(f"Resampling overlay to physical grid...")

            def _resample():
                time.sleep(0.05)
                viewer.view_state.set_overlay(target_id, target_vol)
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

        # Pushes the sync to other viewers and forces the UI to show/hide the checkerboard sliders
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

    def on_fusion_threshold_changed(self, sender, app_data, user_data):
        if self.gui.context_viewer and self.gui.context_viewer.view_state:
            self.gui.context_viewer.view_state.display.overlay_threshold = app_data
            self.gui.context_viewer.view_state.is_data_dirty = True
