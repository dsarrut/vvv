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
                "No Image Selected",
                tag="text_dvf_active_title",
                color=cfg_c["text_active"],
            )

            dpg.add_text(
                "Not a Displacement Vector Field.",
                tag="text_dvf_warning",
                color=cfg_c.get("text_muted", [150, 150, 150]),
                show=False,
            )

            with dpg.group(tag="group_dvf_controls", show=False):
                dpg.add_text("Display Mode:", tag="text_dvf_display_mode")
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
                        "Thickness:",
                        "drag_dvf_thickness",
                        callback=gui.dvf_ui.on_thickness_changed,
                        step_callback=gui.dvf_ui.on_step_button_clicked,
                        min_val=1.0,
                        max_val=10.0,
                        default_val=1.0,
                        format="%.0f px",
                        label_width=90,
                        help_text="Thickness of the vector lines.",
                        gui=gui,
                    )

                    build_stepped_slider(
                        "Arrow >",
                        "drag_dvf_min_arrow",
                        callback=gui.dvf_ui.on_min_arrow_changed,
                        step_callback=gui.dvf_ui.on_step_button_clicked,
                        min_val=0.0,
                        max_val=500.0,
                        default_val=3.0,
                        format="%.1f mm",
                        help_text="Minimum vector magnitude required to draw an arrowhead.",
                        gui=gui,
                        label_width=90,
                    )

                    build_stepped_slider(
                        "Show >",
                        "drag_dvf_min_draw",
                        callback=gui.dvf_ui.on_min_draw_changed,
                        step_callback=gui.dvf_ui.on_step_button_clicked,
                        min_val=0.0,
                        max_val=500.0,
                        default_val=0.0,
                        format="%.1f mm",
                        has_color=True,
                        color_tag="color_dvf_min",
                        color_cb=gui.dvf_ui.on_color_min_changed,
                        color_default=(0, 255, 255, 255),
                        help_text="Minimum vector magnitude required to draw the vector at all.",
                        gui=gui,
                        label_width=90,
                    )

                    build_stepped_slider(
                        "Max Col >",
                        "drag_dvf_color_max_mag",
                        callback=gui.dvf_ui.on_color_max_mag_changed,
                        step_callback=gui.dvf_ui.on_step_button_clicked,
                        min_val=0.1,
                        max_val=500.0,
                        default_val=10.0,
                        format="%.1f mm",
                        has_color=True,
                        color_tag="color_dvf_max",
                        color_cb=gui.dvf_ui.on_color_max_changed,
                        color_default=(255, 0, 0, 255),
                        help_text="Magnitude value at which the colormap reaches its maximum intensity (e.g. Red).",
                        gui=gui,
                        label_width=90,
                    )
                    dpg.add_spacer(height=5)

                    build_stepped_slider(
                        "Sampling:",
                        "drag_dvf_sampling",
                        callback=gui.dvf_ui.on_sampling_changed,
                        step_callback=gui.dvf_ui.on_step_button_clicked,
                        min_val=1.0,
                        max_val=100.0,
                        default_val=5.0,
                        format="%.0f px",
                        help_text="Spacing between rendered vectors (in pixels). Higher sampling improves performance.",
                        gui=gui,
                        label_width=90,
                    )

                    build_stepped_slider(
                        "Scale:",
                        "drag_dvf_scale",
                        callback=gui.dvf_ui.on_scale_changed,
                        step_callback=gui.dvf_ui.on_step_button_clicked,
                        min_val=0.1,
                        max_val=100.0,
                        default_val=1.0,
                        format="%.1f x",
                        help_text="Visual multiplier for vector lengths.",
                        gui=gui,
                        label_width=90,
                    )

    def _get_target_vs(self, viewer):
        if not viewer or not viewer.view_state:
            return None, False
        is_base = getattr(viewer.volume, "is_dvf", False)
        if is_base:
            return viewer.view_state, True
        ov_id = viewer.view_state.display.overlay_id
        if ov_id:
            ov_vs = self.controller.view_states.get(ov_id)
            if ov_vs and getattr(ov_vs.volume, "is_dvf", False):
                return ov_vs, False
        return None, False

    def refresh_dvf_ui(self):
        viewer = self.gui.context_viewer
        target_vs, is_base = self._get_target_vs(viewer)
        is_dvf = target_vs is not None

        if dpg.does_item_exist("text_dvf_active_title"):
            if viewer and viewer.image_id and self.controller.volumes.get(viewer.image_id):
                name_str, is_outdated = self.controller.get_image_display_name(
                    viewer.image_id
                )
                dpg.set_value("text_dvf_active_title", name_str)
                col = (
                    self.gui.ui_cfg["colors"]["outdated"]
                    if is_outdated
                    else self.gui.ui_cfg["colors"]["text_active"]
                )
                dpg.configure_item("text_dvf_active_title", color=col)
            else:
                dpg.set_value("text_dvf_active_title", "No Image Selected")
                dpg.configure_item(
                    "text_dvf_active_title",
                    color=self.gui.ui_cfg["colors"]["text_active"],
                )

        if dpg.does_item_exist("text_dvf_warning"):
            dpg.configure_item("text_dvf_warning", show=not is_dvf)
        if dpg.does_item_exist("group_dvf_controls"):
            dpg.configure_item("group_dvf_controls", show=is_dvf)

        if not is_dvf:
            return

        dvf_state = target_vs.dvf

        if dpg.does_item_exist("text_dvf_display_mode"):
            dpg.configure_item("text_dvf_display_mode", show=is_base)

        if dpg.does_item_exist("radio_dvf_mode"):
            dpg.configure_item("radio_dvf_mode", show=is_base)
            if not dpg.is_item_active("radio_dvf_mode") and is_base:
                dpg.set_value("radio_dvf_mode", dvf_state.display_mode)

        show_vectors = not is_base or dvf_state.display_mode == "Vector Field"
        if dpg.does_item_exist("group_dvf_vector_settings"):
            dpg.configure_item("group_dvf_vector_settings", show=show_vectors)

        if dpg.does_item_exist("drag_dvf_sampling") and not dpg.is_item_active("drag_dvf_sampling"):
            dpg.set_value("drag_dvf_sampling", float(dvf_state.vector_sampling))
        if dpg.does_item_exist("drag_dvf_scale") and not dpg.is_item_active("drag_dvf_scale"):
            dpg.set_value("drag_dvf_scale", float(dvf_state.vector_scale))
        if dpg.does_item_exist("drag_dvf_thickness") and not dpg.is_item_active("drag_dvf_thickness"):
            dpg.set_value("drag_dvf_thickness", float(dvf_state.vector_thickness))
        if dpg.does_item_exist("drag_dvf_min_arrow") and not dpg.is_item_active("drag_dvf_min_arrow"):
            dpg.set_value("drag_dvf_min_arrow", float(dvf_state.vector_min_length_arrow))
        if dpg.does_item_exist("drag_dvf_min_draw") and not dpg.is_item_active("drag_dvf_min_draw"):
            dpg.set_value("drag_dvf_min_draw", float(dvf_state.vector_min_length_draw))
        if dpg.does_item_exist("drag_dvf_color_max_mag") and not dpg.is_item_active("drag_dvf_color_max_mag"):
            dpg.set_value("drag_dvf_color_max_mag", float(dvf_state.vector_color_max_mag))

        for tag, prop in [("color_dvf_min", "vector_color_min"), ("color_dvf_max", "vector_color_max")]:
            if dpg.does_item_exist(tag):
                raw_ui_col = dpg.get_value(tag)[:4]
                ui_scale = 255.0 if all(c <= 1.0 for c in raw_ui_col) else 1.0
                ui_col = [int(c * ui_scale) for c in raw_ui_col]
                if ui_col != list(getattr(dvf_state, prop)):
                    dpg.set_value(tag, list(getattr(dvf_state, prop)))

    # --- Callbacks ---

    def on_mode_changed(self, sender, app_data, user_data):
        target_vs, is_base = self._get_target_vs(self.gui.context_viewer)
        if target_vs and is_base:
            target_vs.dvf.display_mode = app_data
            self.controller.ui_needs_refresh = True

    def on_sampling_changed(self, sender, app_data, user_data):
        target_vs, _ = self._get_target_vs(self.gui.context_viewer)
        if not target_vs:
            return
        target_vs.dvf.vector_sampling = int(max(1.0, app_data))

    def on_scale_changed(self, sender, app_data, user_data):
        target_vs, _ = self._get_target_vs(self.gui.context_viewer)
        if not target_vs:
            return
        target_vs.dvf.vector_scale = max(0.1, app_data)

    def on_thickness_changed(self, sender, app_data, user_data):
        target_vs, _ = self._get_target_vs(self.gui.context_viewer)
        if not target_vs:
            return
        target_vs.dvf.vector_thickness = int(max(1.0, min(10.0, app_data)))

    def on_min_arrow_changed(self, sender, app_data, user_data):
        target_vs, _ = self._get_target_vs(self.gui.context_viewer)
        if not target_vs:
            return
        target_vs.dvf.vector_min_length_arrow = max(0.0, app_data)

    def on_min_draw_changed(self, sender, app_data, user_data):
        target_vs, _ = self._get_target_vs(self.gui.context_viewer)
        if not target_vs:
            return
        target_vs.dvf.vector_min_length_draw = max(0.0, app_data)

    def on_color_max_mag_changed(self, sender, app_data, user_data):
        target_vs, _ = self._get_target_vs(self.gui.context_viewer)
        if not target_vs:
            return
        target_vs.dvf.vector_color_max_mag = max(0.1, app_data)

    def on_color_min_changed(self, sender, app_data, user_data):
        target_vs, _ = self._get_target_vs(self.gui.context_viewer)
        if not target_vs:
            return
        scale = 255.0 if all(c <= 1.0 for c in app_data) else 1.0
        target_vs.dvf.vector_color_min = [int(c * scale) for c in app_data[:4]]

    def on_color_max_changed(self, sender, app_data, user_data):
        target_vs, _ = self._get_target_vs(self.gui.context_viewer)
        if not target_vs:
            return
        scale = 255.0 if all(c <= 1.0 for c in app_data) else 1.0
        target_vs.dvf.vector_color_max = [int(c * scale) for c in app_data[:4]]

    def on_step_button_clicked(self, sender, app_data, user_data):
        target_vs, _ = self._get_target_vs(self.gui.context_viewer)
        if not target_vs:
            return

        direction = user_data["dir"]
        tag = user_data["tag"]
        current_val = dpg.get_value(tag)

        step_size = 0.5
        if tag in ["drag_dvf_sampling", "drag_dvf_thickness"]:
            step_size = 1.0
        new_val = current_val + (step_size * direction)

        if tag == "drag_dvf_sampling":
            new_val = max(1.0, new_val)
            target_vs.dvf.vector_sampling = int(new_val)
        elif tag == "drag_dvf_scale":
            new_val = max(0.1, new_val)
            target_vs.dvf.vector_scale = new_val
        elif tag == "drag_dvf_thickness":
            new_val = max(1.0, min(10.0, new_val))
            target_vs.dvf.vector_thickness = int(new_val)
        elif tag == "drag_dvf_min_arrow":
            target_vs.dvf.vector_min_length_arrow = max(0.0, new_val)
        elif tag == "drag_dvf_min_draw":
            target_vs.dvf.vector_min_length_draw = max(0.0, new_val)
        elif tag == "drag_dvf_color_max_mag":
            target_vs.dvf.vector_color_max_mag = max(0.1, new_val)

        dpg.set_value(tag, new_val)