import dearpygui.dearpygui as dpg
from vvv.ui.ui_components import build_section_title, build_stepped_slider


class DvfUI:
    """Delegated UI handler for the Displacement Vector Fields (DVF) tab."""

    def __init__(self, gui, controller):
        self.gui = gui
        self.controller = controller

    @staticmethod
    def build_tab_dvf(gui):
        cfg_c = gui.ui_cfg["colors"]

        with dpg.group(tag="tab_dvf", show=False):
            build_section_title("DVF Visualization", cfg_c["text_header"])

            dpg.add_text(
                "Active image is not a Displacement Vector Field.",
                tag="text_dvf_warning",
                color=cfg_c.get("text_muted", [150, 150, 150]),
                show=False,
            )

            with dpg.group(tag="group_dvf_controls", show=False):
                dpg.add_text("Display Mode:")
                dpg.add_radio_button(
                    items=["Component", "RGB", "Vector Field"],
                    default_value="Component",
                    tag="radio_dvf_mode",
                    callback=gui.dvf_ui.on_mode_changed,
                )

                dpg.add_spacer(height=10)

                with dpg.group(tag="group_dvf_vector_settings", show=False):
                    build_section_title("Vector Field Settings", cfg_c["text_header"])

                    build_stepped_slider(
                        "Sampling:",
                        "drag_dvf_sampling",
                        callback=gui.dvf_ui.on_sampling_changed,
                        step_callback=gui.dvf_ui.on_step_button_clicked,
                        min_val=1.0,
                        max_val=100.0,
                        default_val=10.0,
                        format="%.0f px",
                    )
                    
                    build_stepped_slider(
                        "Scale:   ",
                        "drag_dvf_scale",
                        callback=gui.dvf_ui.on_scale_changed,
                        step_callback=gui.dvf_ui.on_step_button_clicked,
                        min_val=0.1,
                        max_val=100.0,
                        default_val=1.0,
                        format="%.1f x",
                    )

    def refresh_dvf_ui(self):
        viewer = self.gui.context_viewer
        has_image = bool(viewer and viewer.view_state and viewer.volume)
        is_dvf = getattr(viewer.volume, "is_dvf", False) if has_image else False

        if dpg.does_item_exist("text_dvf_warning"):
            dpg.configure_item("text_dvf_warning", show=has_image and not is_dvf)
        if dpg.does_item_exist("group_dvf_controls"):
            dpg.configure_item("group_dvf_controls", show=is_dvf)

        if not is_dvf:
            return

        dvf_state = viewer.view_state.dvf

        if dpg.does_item_exist("radio_dvf_mode") and not dpg.is_item_active("radio_dvf_mode"):
            dpg.set_value("radio_dvf_mode", dvf_state.display_mode)

        show_vectors = dvf_state.display_mode == "Vector Field"
        if dpg.does_item_exist("group_dvf_vector_settings"):
            dpg.configure_item("group_dvf_vector_settings", show=show_vectors)

        if dpg.does_item_exist("drag_dvf_sampling") and not dpg.is_item_active("drag_dvf_sampling"):
            dpg.set_value("drag_dvf_sampling", float(dvf_state.vector_sampling))
        if dpg.does_item_exist("drag_dvf_scale") and not dpg.is_item_active("drag_dvf_scale"):
            dpg.set_value("drag_dvf_scale", float(dvf_state.vector_scale))

    # --- Callbacks ---

    def on_mode_changed(self, sender, app_data, user_data):
        viewer = self.gui.context_viewer
        if not viewer or not viewer.view_state:
            return
        viewer.view_state.dvf.display_mode = app_data
        self.controller.ui_needs_refresh = True

    def on_sampling_changed(self, sender, app_data, user_data):
        viewer = self.gui.context_viewer
        if not viewer or not viewer.view_state:
            return
        viewer.view_state.dvf.vector_sampling = int(max(1.0, app_data))

    def on_scale_changed(self, sender, app_data, user_data):
        viewer = self.gui.context_viewer
        if not viewer or not viewer.view_state:
            return
        viewer.view_state.dvf.vector_scale = max(0.1, app_data)

    def on_step_button_clicked(self, sender, app_data, user_data):
        viewer = self.gui.context_viewer
        if not viewer or not viewer.view_state:
            return

        direction = user_data["dir"]
        tag = user_data["tag"]
        current_val = dpg.get_value(tag)

        step_size = 1.0
        new_val = current_val + (step_size * direction)

        if tag == "drag_dvf_sampling":
            new_val = max(1.0, new_val)
            viewer.view_state.dvf.vector_sampling = int(new_val)
        dpg.set_value(tag, new_val)