import numpy as np
import dearpygui.dearpygui as dpg
from vvv.ui.ui_components import build_section_title, build_stepped_slider, build_help_button
from .control_threshold import ThresholdController


class ThresholdUI:
    def __init__(self, plugin_id: str, controller: ThresholdController):
        self._plugin_id = plugin_id
        self._c = controller
        self._current_image_id = None

    def _t(self, name: str) -> str:
        return f"{self._plugin_id}_{name}"

    def create_ui(self, parent, api) -> None:
        cfg_c = api.get_ui_config()["colors"]

        with dpg.group(parent=parent or 0, tag=self._plugin_id):
            build_section_title("Interactive Threshold", cfg_c["text_header"])

            dpg.add_text(
                "No Image Selected",
                tag=self._t("active_title"),
                color=cfg_c["text_active"],
            )

            dpg.add_checkbox(
                label="Enable Thresholding",
                tag=self._t("check_ext_enable"),
                callback=self._c.on_enable_toggle,
            )

            dpg.add_text("", tag=self._t("text_ext_preview_context"), color=cfg_c["text_dim"], show=False)
            dpg.add_spacer(height=5)

            build_stepped_slider(
                "Min:",
                self._t("drag_ext_threshold_min"),
                callback=self._c.on_threshold_drag,
                step_callback=self._c.on_step_button_clicked,
                min_val=-100000.0,
                max_val=100000.0,
                has_color=True,
                color_tag=self._t("color_ext_preview_min"),
                color_cb=self._c.on_threshold_drag,
                gui=api,
            )

            build_stepped_slider(
                "Max:",
                self._t("drag_ext_threshold_max"),
                callback=self._c.on_threshold_drag,
                step_callback=self._c.on_step_button_clicked,
                min_val=-100000.0,
                max_val=100000.0,
                has_color=True,
                color_tag=self._t("color_ext_preview_max"),
                color_cb=self._c.on_threshold_drag,
                color_default=(0, 0, 255, 255),
                gui=api,
            )

            dpg.add_spacer(height=5)

            with dpg.group(horizontal=True):
                dpg.add_checkbox(
                    label="Live Preview",
                    tag=self._t("check_ext_preview"),
                    callback=self._c.on_threshold_drag,
                )

                dpg.add_checkbox(
                    label="Sub-Pixel",
                    tag=self._t("check_ext_subpixel"),
                    callback=self._c.on_threshold_drag,
                )
                build_help_button("Live Preview: Renders the threshold dynamically as colored contours.\nSub-Pixel: Uses marching squares interpolation for sub-voxel accuracy instead of blocky pixels.", api)

            # Thickness Slider
            dpg.add_spacer(height=5)
            with dpg.group(horizontal=True):
                dpg.add_text("Thickness:")
                dpg.add_slider_float(
                    tag=self._t("drag_ext_thickness"),
                    width=-1,
                    min_value=0.5,
                    max_value=10.0,
                    default_value=2.0,
                    callback=self._c.on_threshold_drag,
                )

            # Image Generation
            dpg.add_spacer(height=10)
            build_section_title("Image Generation", cfg_c["text_header"])

            with dpg.group(horizontal=True):
                dpg.add_text("BG Range:", color=cfg_c["text_dim"])
                dpg.add_text("---", tag=self._t("text_ext_bg_range"))

            with dpg.group(horizontal=True):
                dpg.add_text("FG Range:", color=cfg_c["text_dim"])
                dpg.add_text("---", tag=self._t("text_ext_fg_range"))

            dpg.add_spacer(height=5)
            with dpg.group(horizontal=True):
                dpg.add_text("BG:")
                dpg.add_combo(
                    ["Constant", "Image"],
                    default_value="Constant",
                    width=95,
                    tag=self._t("combo_ext_bg_mode"),
                    callback=self._c.on_gen_mode_changed,
                )
                dpg.add_input_float(
                    default_value=0.0,
                    width=95,
                    tag=self._t("input_ext_bg_val"),
                    step=0,
                    callback=self._c.on_gen_mode_changed,
                )

            with dpg.group(horizontal=True):
                dpg.add_text("FG:")
                dpg.add_combo(
                    ["Constant", "Image"],
                    default_value="Constant",
                    width=85,
                    tag=self._t("combo_ext_fg_mode"),
                    callback=self._c.on_gen_mode_changed,
                )
                dpg.add_input_float(
                    default_value=1.0,
                    width=75,
                    tag=self._t("input_ext_fg_val"),
                    step=0,
                    callback=self._c.on_gen_mode_changed,
                )
                build_help_button("BG/FG Generation Rules: Voxels inside the threshold range get the FG value. Voxels outside get the BG value. 'Image' keeps the original voxel values.", api)

            dpg.add_spacer(height=5)
            with dpg.group(horizontal=True):
                dpg.add_button(
                    label="Create Image",
                    width=-28,
                    tag=self._t("btn_ext_create"),
                    callback=self._c.on_create_image_clicked,
                )
                build_help_button("Bakes the current threshold range into a brand new standalone image volume in memory.", api)

    def update_ui(self, api) -> None:
        viewer = api.get_active_viewer()
        has_image = bool(viewer and viewer.view_state and viewer.volume)

        # Update active image title
        active_title = self._t("active_title")
        if dpg.does_item_exist(active_title):
            if has_image:
                name_str, is_outdated = api.get_image_display_name(viewer.image_id)
                col = (
                    api.get_ui_config()["colors"]["outdated"]
                    if is_outdated
                    else api.get_ui_config()["colors"]["text_active"]
                )
                dpg.set_value(active_title, name_str)
                dpg.configure_item(active_title, color=col)
            else:
                dpg.set_value(active_title, "No Image Selected")
                dpg.configure_item(
                    active_title,
                    color=api.get_ui_config()["colors"]["text_active"],
                )

        is_rgb = getattr(viewer.volume, "is_rgb", False) if has_image else False

        # If no image or it's an RGB image, disable thresholding controls
        if not has_image or is_rgb:
            tags_to_disable = [
                self._t("check_ext_enable"),
                self._t("drag_ext_threshold_min"),
                self._t("drag_ext_threshold_max"),
                self._t("check_ext_preview"),
                self._t("color_ext_preview_min"),
                self._t("color_ext_preview_max"),
                self._t("check_ext_subpixel"),
                self._t("drag_ext_thickness"),
                self._t("combo_ext_bg_mode"),
                self._t("input_ext_bg_val"),
                self._t("combo_ext_fg_mode"),
                self._t("input_ext_fg_val"),
                self._t("btn_ext_create"),
                f"btn_{self._t('drag_ext_threshold_min')}_minus",
                f"btn_{self._t('drag_ext_threshold_min')}_plus",
                f"btn_{self._t('drag_ext_threshold_max')}_minus",
                f"btn_{self._t('drag_ext_threshold_max')}_plus",
            ]
            for tag in tags_to_disable:
                if dpg.does_item_exist(tag):
                    dpg.configure_item(tag, enabled=False)

            self._current_image_id = None

            bg_range_tag = self._t("text_ext_bg_range")
            fg_range_tag = self._t("text_ext_fg_range")
            if dpg.does_item_exist(bg_range_tag):
                if is_rgb:
                    dpg.set_value(bg_range_tag, "RGB Base")
                    dpg.set_value(fg_range_tag, "Not Supported")
                else:
                    dpg.set_value(bg_range_tag, "---")
                    dpg.set_value(fg_range_tag, "---")
            return

        vol = viewer.volume
        ext_state = self._c.get_image_state(viewer.image_id)
        img_id = viewer.image_id

        # Update cache bounds if needed
        current_data_id = id(vol.data)
        if (
            not hasattr(vol, "_cached_min_val")
            or getattr(vol, "_cached_data_id", None) != current_data_id
        ):
            vol._cached_min_val = float(np.min(vol.data))
            vol._cached_max_val = float(np.max(vol.data))
            vol._cached_data_id = current_data_id

        # Auto-clamp state to physical bounds
        if ext_state.threshold_min < vol._cached_min_val:
            ext_state.threshold_min = vol._cached_min_val
        if ext_state.threshold_max > vol._cached_max_val:
            ext_state.threshold_max = vol._cached_max_val

        # Dynamic Range Texts
        min_v = ext_state.threshold_min
        max_v = ext_state.threshold_max
        bg_range_tag = self._t("text_ext_bg_range")
        fg_range_tag = self._t("text_ext_fg_range")
        if dpg.does_item_exist(bg_range_tag):
            dpg.set_value(bg_range_tag, f"< {min_v:g}   OR   > {max_v:g}")
        if dpg.does_item_exist(fg_range_tag):
            dpg.set_value(fg_range_tag, f"[{min_v:g}  ...  {max_v:g}]")

        # Dynamic Temporal/Vector Context Feedback
        preview_context_tag = self._t("text_ext_preview_context")
        if dpg.does_item_exist(preview_context_tag):
            if vol.num_timepoints > 1 and ext_state.is_enabled:
                if getattr(vol, "is_dvf", False):
                    comps = ["dx", "dy", "dz"]
                    c_name = comps[viewer.view_state.camera.time_idx] if viewer.view_state.camera.time_idx < len(comps) else f"c{viewer.view_state.camera.time_idx}"
                    context_text = f"Previewing Component: {c_name}"
                else:
                    context_text = f"Previewing Frame: {viewer.view_state.camera.time_idx + 1} / {vol.num_timepoints}"
                dpg.set_value(preview_context_tag, context_text)
                dpg.configure_item(preview_context_tag, show=True)
            else:
                dpg.configure_item(preview_context_tag, show=False)

        # Update sliders min/max/speed bounds
        speed = max(0.1, viewer.view_state.display.ww * 0.005)
        for tag in [self._t("drag_ext_threshold_min"), self._t("drag_ext_threshold_max")]:
            if dpg.does_item_exist(tag):
                dpg.configure_item(
                    tag, min_value=vol._cached_min_val, max_value=vol._cached_max_val, speed=speed
                )

        # Context Switch Snap
        if self._current_image_id != img_id:
            self._current_image_id = img_id

            dpg.set_value(self._t("check_ext_enable"), ext_state.is_enabled)
            dpg.set_value(self._t("drag_ext_threshold_min"), ext_state.threshold_min)
            dpg.set_value(self._t("drag_ext_threshold_max"), ext_state.threshold_max)
            dpg.set_value(self._t("check_ext_preview"), ext_state.show_preview)
            dpg.set_value(self._t("check_ext_subpixel"), ext_state.subpixel_accurate)

            color_min_tag = self._t("color_ext_preview_min")
            if dpg.does_item_exist(color_min_tag):
                dpg.set_value(color_min_tag, list(ext_state.preview_color_min))

            color_max_tag = self._t("color_ext_preview_max")
            if dpg.does_item_exist(color_max_tag):
                dpg.set_value(color_max_tag, list(ext_state.preview_color_max))

            dpg.set_value(self._t("drag_ext_thickness"), ext_state.preview_thickness)
            dpg.set_value(self._t("combo_ext_bg_mode"), ext_state.gen_bg_mode)
            dpg.set_value(self._t("input_ext_bg_val"), ext_state.gen_bg_val)
            dpg.set_value(self._t("combo_ext_fg_mode"), ext_state.gen_fg_mode)
            dpg.set_value(self._t("input_ext_fg_val"), ext_state.gen_fg_val)

        # Continuous Sync
        else:
            check_enable = self._t("check_ext_enable")
            if dpg.does_item_exist(check_enable):
                if dpg.get_value(check_enable) != ext_state.is_enabled:
                    dpg.set_value(check_enable, ext_state.is_enabled)

            drag_min = self._t("drag_ext_threshold_min")
            if dpg.does_item_exist(drag_min):
                if not dpg.is_item_active(drag_min):
                    dpg.set_value(drag_min, ext_state.threshold_min)

            drag_max = self._t("drag_ext_threshold_max")
            if dpg.does_item_exist(drag_max):
                if not dpg.is_item_active(drag_max):
                    dpg.set_value(drag_max, ext_state.threshold_max)

            drag_thickness = self._t("drag_ext_thickness")
            if dpg.does_item_exist(drag_thickness):
                if not dpg.is_item_active(drag_thickness):
                    dpg.set_value(drag_thickness, ext_state.preview_thickness)

            input_bg = self._t("input_ext_bg_val")
            if dpg.does_item_exist(input_bg):
                if not dpg.is_item_active(input_bg):
                    dpg.set_value(input_bg, ext_state.gen_bg_val)

            input_fg = self._t("input_ext_fg_val")
            if dpg.does_item_exist(input_fg):
                if not dpg.is_item_active(input_fg):
                    dpg.set_value(input_fg, ext_state.gen_fg_val)

            combo_bg = self._t("combo_ext_bg_mode")
            if dpg.does_item_exist(combo_bg):
                dpg.set_value(combo_bg, ext_state.gen_bg_mode)

            combo_fg = self._t("combo_ext_fg_mode")
            if dpg.does_item_exist(combo_fg):
                dpg.set_value(combo_fg, ext_state.gen_fg_mode)

            check_preview = self._t("check_ext_preview")
            if dpg.does_item_exist(check_preview):
                if dpg.get_value(check_preview) != ext_state.show_preview:
                    dpg.set_value(check_preview, ext_state.show_preview)

            check_subpixel = self._t("check_ext_subpixel")
            if dpg.does_item_exist(check_subpixel):
                if dpg.get_value(check_subpixel) != ext_state.subpixel_accurate:
                    dpg.set_value(check_subpixel, ext_state.subpixel_accurate)

            # Safe Float/Int Color Syncing
            color_min = self._t("color_ext_preview_min")
            if dpg.does_item_exist(color_min):
                raw_ui_col_min = dpg.get_value(color_min)[:4]
                ui_scale_min = 255.0 if all(c <= 1.0 for c in raw_ui_col_min) else 1.0
                ui_col_min = [int(c * ui_scale_min) for c in raw_ui_col_min]
                if ui_col_min != list(ext_state.preview_color_min):
                    dpg.set_value(color_min, list(ext_state.preview_color_min))

            color_max = self._t("color_ext_preview_max")
            if dpg.does_item_exist(color_max):
                raw_ui_col_max = dpg.get_value(color_max)[:4]
                ui_scale_max = 255.0 if all(c <= 1.0 for c in raw_ui_col_max) else 1.0
                ui_col_max = [int(c * ui_scale_max) for c in raw_ui_col_max]
                if ui_col_max != list(ext_state.preview_color_max):
                    dpg.set_value(color_max, list(ext_state.preview_color_max))

        # UI Locking Rules
        dpg.configure_item(self._t("check_ext_enable"), enabled=True)

        dpg.configure_item(
            self._t("input_ext_bg_val"), enabled=(ext_state.gen_bg_mode == "Constant")
        )
        dpg.configure_item(
            self._t("input_ext_fg_val"), enabled=(ext_state.gen_fg_mode == "Constant")
        )

        locked_when_disabled = [
            self._t("drag_ext_threshold_min"),
            f"btn_{self._t('drag_ext_threshold_min')}_minus",
            f"btn_{self._t('drag_ext_threshold_min')}_plus",
            self._t("drag_ext_threshold_max"),
            f"btn_{self._t('drag_ext_threshold_max')}_minus",
            f"btn_{self._t('drag_ext_threshold_max')}_plus",
        ]

        always_enabled = [
            self._t("check_ext_preview"),
            self._t("check_ext_subpixel"),
            self._t("color_ext_preview_min"),
            self._t("color_ext_preview_max"),
            self._t("drag_ext_thickness"),
            self._t("combo_ext_bg_mode"),
            self._t("combo_ext_fg_mode"),
            self._t("btn_ext_create"),
        ]

        for tag in locked_when_disabled:
            if dpg.does_item_exist(tag):
                dpg.configure_item(tag, enabled=ext_state.is_enabled)

        for tag in always_enabled:
            if dpg.does_item_exist(tag):
                dpg.configure_item(tag, enabled=True)
