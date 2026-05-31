import dearpygui.dearpygui as dpg
from vvv.ui.ui_components import build_section_title, build_stepped_slider, build_help_button
from .control_dvf import DvfController
from vvv.plugins.plugin_api import PluginTagMixin


class DvfUI(PluginTagMixin):
    def __init__(self, plugin_id: str, controller: DvfController):
        self._plugin_id = plugin_id
        self._c = controller

    def create_ui(self, parent, api) -> None:
        cfg_c = api.get_ui_config()["colors"]

        with dpg.group(parent=parent or 0, tag=self._plugin_id):
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

            with dpg.group(tag=self._t("controls")):
                with dpg.group(tag=self._t("display_mode_group"), horizontal=True):
                    dpg.add_text("Display Mode:", tag=self._t("display_mode_label"))
                    build_help_button(
                        "Display Mode — how the displacement vector field is visualized:\n\n"
                        "Component: View each spatial component (X, Y, or Z) as a scalar image.\n"
                        "RGB: Remap vector components to color channels (X->R, Y->G, Z->B).\n"
                        "Vector Field: Overlay 2D/3D arrow glyphs directly on the slice grid.",
                        api,
                    )
                dpg.add_radio_button(
                    items=["Component", "RGB", "Vector Field"],
                    default_value="Component",
                    tag=self._t("radio_mode"),
                    callback=self._c.on_mode_changed,
                )

                dpg.add_spacer(height=10)

                with dpg.group(tag=self._t("vector_settings"), show=False):
                    build_section_title("Vector Field Settings", cfg_c["text_header"])

                    build_stepped_slider(
                        "Thickness:",
                        self._t("thickness"),
                        callback=self._c.on_thickness_changed,
                        step_callback=self._c.on_step_button_clicked,
                        min_val=1.0,
                        max_val=10.0,
                        default_val=1.0,
                        format="%.0f px",
                        label_width=90,
                        help_text="Thickness of the vector lines.",
                        gui=api,
                    )

                    build_stepped_slider(
                        "Arrow >",
                        self._t("min_arrow"),
                        callback=self._c.on_min_arrow_changed,
                        step_callback=self._c.on_step_button_clicked,
                        min_val=0.0,
                        max_val=500.0,
                        default_val=3.0,
                        format="%.1f mm",
                        help_text="Minimum vector magnitude required to draw an arrowhead.",
                        gui=api,
                        label_width=90,
                    )

                    build_stepped_slider(
                        "Show >",
                        self._t("min_draw"),
                        callback=self._c.on_min_draw_changed,
                        step_callback=self._c.on_step_button_clicked,
                        min_val=0.0,
                        max_val=500.0,
                        default_val=0.0,
                        format="%.1f mm",
                        has_color=True,
                        color_tag=self._t("color_min"),
                        color_cb=self._c.on_color_min_changed,
                        color_default=(0, 255, 255, 255),
                        help_text="Minimum vector magnitude required to draw the vector at all.",
                        gui=api,
                        label_width=90,
                    )

                    build_stepped_slider(
                        "Max Col >",
                        self._t("color_max_mag"),
                        callback=self._c.on_color_max_mag_changed,
                        step_callback=self._c.on_step_button_clicked,
                        min_val=0.1,
                        max_val=500.0,
                        default_val=10.0,
                        format="%.1f mm",
                        has_color=True,
                        color_tag=self._t("color_max"),
                        color_cb=self._c.on_color_max_changed,
                        color_default=(255, 0, 0, 255),
                        help_text="Magnitude value at which the colormap reaches its maximum intensity (e.g. Red).",
                        gui=api,
                        label_width=90,
                    )

                    dpg.add_spacer(height=5)

                    build_stepped_slider(
                        "Sampling:",
                        self._t("sampling"),
                        callback=self._c.on_sampling_changed,
                        step_callback=self._c.on_step_button_clicked,
                        min_val=1.0,
                        max_val=100.0,
                        default_val=5.0,
                        format="%.0f px",
                        help_text="Spacing between rendered vectors (in pixels). Higher sampling improves performance.",
                        gui=api,
                        label_width=90,
                    )

                    build_stepped_slider(
                        "Scale:",
                        self._t("scale"),
                        callback=self._c.on_scale_changed,
                        step_callback=self._c.on_step_button_clicked,
                        min_val=0.1,
                        max_val=100.0,
                        default_val=1.0,
                        format="%.1f x",
                        help_text="Visual multiplier for vector lengths.",
                        gui=api,
                        label_width=90,
                    )

                    dpg.add_spacer(height=5)

                    build_stepped_slider(
                        "Precision:",
                        self._t("precision"),
                        callback=self._c.on_precision_changed,
                        step_callback=self._c.on_step_button_clicked,
                        min_val=0.0,
                        max_val=6.0,
                        default_val=2.0,
                        format="%.0f",
                        help_text="Number of decimal places displayed in the crosshair and tracker.",
                        gui=api,
                        label_width=90,
                    )
