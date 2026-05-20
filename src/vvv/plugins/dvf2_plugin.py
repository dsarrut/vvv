import dearpygui.dearpygui as dpg
from vvv.plugins.plugin_api import PluginAPI
from vvv.ui.ui_components import build_section_title, build_stepped_slider


class DvfPlugin:
    plugin_id = "dvf2"
    label = "DVF2"
    description = "Displacement Vector Fields visualization."

    def __init__(self):
        self._api: PluginAPI  # set in create_ui

    def _t(self, name):
        return f"{self.plugin_id}_{name}"

    def _get_target_vs(self):
        viewer = self._api.get_active_viewer()
        if not viewer or not viewer.view_state:
            return None, False
        is_base = getattr(viewer.volume, "is_dvf", False)
        if is_base:
            return viewer.view_state, True
        ov_id = viewer.view_state.display.overlay_id
        if ov_id:
            ov_vs = self._api.get_view_states().get(ov_id)
            if ov_vs and getattr(ov_vs.volume, "is_dvf", False):
                return ov_vs, False
        return None, False

    def create_ui(self, parent, api):
        self._api = api
        cfg_c = api.get_ui_config()["colors"]

        with dpg.group(parent=parent or 0, tag=self.plugin_id):
            build_section_title("DVF Visualization", cfg_c["text_header"])

            dpg.add_text(
                "No Image Selected",
                tag=self._t("active_title"),
                color=cfg_c["text_active"],
            )

            dpg.add_text(
                "Not a Displacement Vector Field.",
                tag=self._t("warning"),
                color=cfg_c.get("text_muted", [150, 150, 150]),
                show=False,
            )

            with dpg.group(tag=self._t("controls"), show=False):
                dpg.add_text("Display Mode:", tag=self._t("display_mode_label"))
                dpg.add_radio_button(
                    items=["Component", "RGB", "Vector Field"],
                    default_value="Component",
                    tag=self._t("radio_mode"),
                    callback=self._on_mode_changed,
                )

                dpg.add_spacer(height=10)

                with dpg.group(tag=self._t("vector_settings"), show=False):
                    build_section_title("Vector Field Settings", cfg_c["text_header"])

                    build_stepped_slider(
                        "Thickness:",
                        self._t("thickness"),
                        callback=self._on_thickness_changed,
                        step_callback=self._on_step_button_clicked,
                        min_val=1.0,
                        max_val=10.0,
                        default_val=1.0,
                        format="%.0f px",
                        label_width=90,
                        help_text="Thickness of the vector lines.",
                        gui=None,
                    )

                    build_stepped_slider(
                        "Arrow >",
                        self._t("min_arrow"),
                        callback=self._on_min_arrow_changed,
                        step_callback=self._on_step_button_clicked,
                        min_val=0.0,
                        max_val=500.0,
                        default_val=3.0,
                        format="%.1f mm",
                        help_text="Minimum vector magnitude required to draw an arrowhead.",
                        gui=None,
                        label_width=90,
                    )

                    build_stepped_slider(
                        "Show >",
                        self._t("min_draw"),
                        callback=self._on_min_draw_changed,
                        step_callback=self._on_step_button_clicked,
                        min_val=0.0,
                        max_val=500.0,
                        default_val=0.0,
                        format="%.1f mm",
                        has_color=True,
                        color_tag=self._t("color_min"),
                        color_cb=self._on_color_min_changed,
                        color_default=(0, 255, 255, 255),
                        help_text="Minimum vector magnitude required to draw the vector at all.",
                        gui=None,
                        label_width=90,
                    )

                    build_stepped_slider(
                        "Max Col >",
                        self._t("color_max_mag"),
                        callback=self._on_color_max_mag_changed,
                        step_callback=self._on_step_button_clicked,
                        min_val=0.1,
                        max_val=500.0,
                        default_val=10.0,
                        format="%.1f mm",
                        has_color=True,
                        color_tag=self._t("color_max"),
                        color_cb=self._on_color_max_changed,
                        color_default=(255, 0, 0, 255),
                        help_text="Magnitude value at which the colormap reaches its maximum intensity (e.g. Red).",
                        gui=None,
                        label_width=90,
                    )

                    dpg.add_spacer(height=5)

                    build_stepped_slider(
                        "Sampling:",
                        self._t("sampling"),
                        callback=self._on_sampling_changed,
                        step_callback=self._on_step_button_clicked,
                        min_val=1.0,
                        max_val=100.0,
                        default_val=5.0,
                        format="%.0f px",
                        help_text="Spacing between rendered vectors (in pixels). Higher sampling improves performance.",
                        gui=None,
                        label_width=90,
                    )

                    build_stepped_slider(
                        "Scale:",
                        self._t("scale"),
                        callback=self._on_scale_changed,
                        step_callback=self._on_step_button_clicked,
                        min_val=0.1,
                        max_val=100.0,
                        default_val=1.0,
                        format="%.1f x",
                        help_text="Visual multiplier for vector lengths.",
                        gui=None,
                        label_width=90,
                    )

                    dpg.add_spacer(height=5)

                    build_stepped_slider(
                        "Precision:",
                        self._t("precision"),
                        callback=self._on_precision_changed,
                        step_callback=self._on_step_button_clicked,
                        min_val=0.0,
                        max_val=6.0,
                        default_val=2.0,
                        format="%.0f",
                        help_text="Number of decimal places displayed in the crosshair and tracker.",
                        gui=None,
                        label_width=90,
                    )

    def update(self, api):
        if not api.is_dirty:
            return

        viewer = api.get_active_viewer()
        target_vs, is_base = self._get_target_vs()
        is_dvf = target_vs is not None

        active_title = self._t("active_title")
        if dpg.does_item_exist(active_title):
            if viewer and viewer.image_id and api.get_volumes().get(viewer.image_id):
                name_str, is_outdated = api.get_image_display_name(viewer.image_id)
                dpg.set_value(active_title, name_str)
                col = (
                    api.get_ui_config()["colors"]["outdated"]
                    if is_outdated
                    else api.get_ui_config()["colors"]["text_active"]
                )
                dpg.configure_item(active_title, color=col)
            else:
                dpg.set_value(active_title, "No Image Selected")
                dpg.configure_item(
                    active_title,
                    color=api.get_ui_config()["colors"]["text_active"],
                )

        warning_tag = self._t("warning")
        if dpg.does_item_exist(warning_tag):
            dpg.configure_item(warning_tag, show=not is_dvf)

        controls_tag = self._t("controls")
        if dpg.does_item_exist(controls_tag):
            dpg.configure_item(controls_tag, show=is_dvf)

        if not is_dvf:
            return

        dvf_state = target_vs.dvf

        display_mode_label = self._t("display_mode_label")
        if dpg.does_item_exist(display_mode_label):
            dpg.configure_item(display_mode_label, show=is_base)

        radio_mode = self._t("radio_mode")
        if dpg.does_item_exist(radio_mode):
            dpg.configure_item(radio_mode, show=is_base)
            if not dpg.is_item_active(radio_mode) and is_base:
                dpg.set_value(radio_mode, dvf_state.display_mode)

        show_vectors = not is_base or dvf_state.display_mode == "Vector Field"
        vector_settings = self._t("vector_settings")
        if dpg.does_item_exist(vector_settings):
            dpg.configure_item(vector_settings, show=show_vectors)

        for tag_name, attr in [
            ("sampling", "vector_sampling"),
            ("scale", "vector_scale"),
            ("thickness", "vector_thickness"),
            ("min_arrow", "vector_min_length_arrow"),
            ("min_draw", "vector_min_length_draw"),
            ("color_max_mag", "vector_color_max_mag"),
            ("precision", "vector_precision"),
        ]:
            tag = self._t(tag_name)
            if dpg.does_item_exist(tag) and not dpg.is_item_active(tag):
                dpg.set_value(tag, float(getattr(dvf_state, attr)))

        for tag_name, prop in [("color_min", "vector_color_min"), ("color_max", "vector_color_max")]:
            tag = self._t(tag_name)
            if dpg.does_item_exist(tag):
                raw_ui_col = dpg.get_value(tag)[:4]
                ui_scale = 255.0 if all(c <= 1.0 for c in raw_ui_col) else 1.0
                ui_col = [int(c * ui_scale) for c in raw_ui_col]
                if ui_col != list(getattr(dvf_state, prop)):
                    dpg.set_value(tag, list(getattr(dvf_state, prop)))

    # --- Callbacks ---

    def _on_mode_changed(self, sender, app_data, user_data):
        target_vs, is_base = self._get_target_vs()
        if target_vs and is_base:
            target_vs.dvf.display_mode = app_data
            self._api.request_refresh()

    def _on_sampling_changed(self, sender, app_data, user_data):
        target_vs, _ = self._get_target_vs()
        if target_vs:
            target_vs.dvf.vector_sampling = int(max(1.0, app_data))

    def _on_scale_changed(self, sender, app_data, user_data):
        target_vs, _ = self._get_target_vs()
        if target_vs:
            target_vs.dvf.vector_scale = max(0.1, app_data)

    def _on_thickness_changed(self, sender, app_data, user_data):
        target_vs, _ = self._get_target_vs()
        if target_vs:
            target_vs.dvf.vector_thickness = int(max(1.0, min(10.0, app_data)))

    def _on_min_arrow_changed(self, sender, app_data, user_data):
        target_vs, _ = self._get_target_vs()
        if target_vs:
            target_vs.dvf.vector_min_length_arrow = max(0.0, app_data)

    def _on_min_draw_changed(self, sender, app_data, user_data):
        target_vs, _ = self._get_target_vs()
        if target_vs:
            target_vs.dvf.vector_min_length_draw = max(0.0, app_data)

    def _on_color_max_mag_changed(self, sender, app_data, user_data):
        target_vs, _ = self._get_target_vs()
        if target_vs:
            target_vs.dvf.vector_color_max_mag = max(0.1, app_data)

    def _on_precision_changed(self, sender, app_data, user_data):
        target_vs, _ = self._get_target_vs()
        if target_vs:
            target_vs.dvf.vector_precision = int(app_data)
            self._api.request_refresh()

    def _on_color_min_changed(self, sender, app_data, user_data):
        target_vs, _ = self._get_target_vs()
        if target_vs:
            scale = 255.0 if all(c <= 1.0 for c in app_data) else 1.0
            target_vs.dvf.vector_color_min = [int(c * scale) for c in app_data[:4]]

    def _on_color_max_changed(self, sender, app_data, user_data):
        target_vs, _ = self._get_target_vs()
        if target_vs:
            scale = 255.0 if all(c <= 1.0 for c in app_data) else 1.0
            target_vs.dvf.vector_color_max = [int(c * scale) for c in app_data[:4]]

    def _on_step_button_clicked(self, sender, app_data, user_data):
        target_vs, _ = self._get_target_vs()
        if not target_vs:
            return

        direction = user_data["dir"]
        tag = user_data["tag"]
        current_val = dpg.get_value(tag)

        step_size = 0.5
        if tag in [self._t("sampling"), self._t("thickness")]:
            step_size = 1.0
        new_val = current_val + (step_size * direction)

        if tag == self._t("sampling"):
            new_val = max(1.0, new_val)
            target_vs.dvf.vector_sampling = int(new_val)
        elif tag == self._t("scale"):
            new_val = max(0.1, new_val)
            target_vs.dvf.vector_scale = new_val
        elif tag == self._t("thickness"):
            new_val = max(1.0, min(10.0, new_val))
            target_vs.dvf.vector_thickness = int(new_val)
        elif tag == self._t("min_arrow"):
            target_vs.dvf.vector_min_length_arrow = max(0.0, new_val)
        elif tag == self._t("min_draw"):
            target_vs.dvf.vector_min_length_draw = max(0.0, new_val)
        elif tag == self._t("color_max_mag"):
            target_vs.dvf.vector_color_max_mag = max(0.1, new_val)
        elif tag == self._t("precision"):
            new_val = max(0.0, min(6.0, new_val))
            target_vs.dvf.vector_precision = int(new_val)
            self._api.request_refresh()
