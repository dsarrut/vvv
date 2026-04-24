import numpy as np
import dearpygui.dearpygui as dpg
from vvv.ui.ui_components import build_section_title, build_stepped_slider


class ExtractionUI:
    """Handles the Interactive Thresholding UI elements and user input."""

    def __init__(self, gui, controller):
        self.gui = gui
        self.controller = controller
        # --- Context Switch Tracker ---
        self._current_image_id = None

    def build_tab_extraction(self, gui):
        cfg_c = gui.ui_cfg["colors"]

        with dpg.tab(label="Extract", tag="tab_extraction"):
            dpg.add_spacer(height=5)
            build_section_title("Interactive Threshold", cfg_c["text_header"])

            dpg.add_checkbox(
                label="Enable Thresholding",
                tag="check_ext_enable",
                callback=self.on_enable_toggle,
            )
            dpg.add_spacer(height=5)

            build_stepped_slider(
                "Threshold:",
                "drag_ext_threshold",
                callback=self.on_threshold_drag,
                step_callback=self.on_step_button_clicked,
                min_val=-100000.0,
                max_val=100000.0,
            )

            dpg.add_spacer(height=5)

            with dpg.group(horizontal=True):
                dpg.add_checkbox(
                    label="Live Preview",
                    tag="check_ext_preview",
                    callback=self.on_threshold_drag,
                )
                dpg.add_color_edit(
                    (255, 255, 0, 255),
                    tag="color_ext_preview",
                    no_inputs=True,
                    no_label=True,
                    no_alpha=True,
                    width=20,
                    height=20,
                    callback=self.on_threshold_drag,
                )

            dpg.add_spacer(height=15)
            dpg.add_separator()
            dpg.add_spacer(height=5)

            dpg.add_button(
                label="Extract to ROI",
                tag="btn_ext_extract",
                width=-1,
                height=30,
                callback=self.on_extract_clicked,
            )

            dpg.add_spacer(height=5)
            dpg.add_progress_bar(
                tag="prog_ext", default_value=0.0, width=-1, show=False
            )
            dpg.add_text("", tag="text_prog_ext", color=cfg_c["text_dim"], show=False)

    def refresh_extraction_ui(self):
        viewer = self.gui.context_viewer
        if not viewer or not viewer.view_state:
            self._current_image_id = None
            return

        ext_state = viewer.view_state.extraction
        img_id = viewer.image_id

        # CONTEXT SWITCH: Snap UI widgets to this image's unique state
        if self._current_image_id != img_id:
            self._current_image_id = img_id
            dpg.set_value("check_ext_enable", ext_state.is_enabled)
            dpg.set_value("drag_ext_threshold", ext_state.threshold)
            dpg.set_value("check_ext_preview", ext_state.show_preview)
            dpg.set_value("color_ext_preview", list(ext_state.preview_color))

        # CONTINUOUS SYNC: Lock UI elements based on Enable flag
        dpg.configure_item("check_ext_enable", enabled=True)
        tags_to_toggle = [
            "drag_ext_threshold",
            "btn_ext_extract",
            "check_ext_preview",
            "color_ext_preview",
        ]
        for tag in tags_to_toggle:
            if dpg.does_item_exist(tag):
                dpg.configure_item(tag, enabled=ext_state.is_enabled)
            self._current_image_id = None
            return

        vol = viewer.volume
        ext_state = viewer.view_state.extraction
        img_id = viewer.image_id

        # 2. Update dynamic constraints (Min/Max and Speed)
        current_data_id = id(vol.data)
        if (
            not hasattr(vol, "_cached_min_val")
            or getattr(vol, "_cached_data_id", None) != current_data_id
        ):
            vol._cached_min_val = float(np.min(vol.data))
            vol._cached_max_val = float(np.max(vol.data))
            vol._cached_data_id = current_data_id

        # Ensure the minimum allows 0.0 to prevent clipping of default values
        safe_min = min(0.0, vol._cached_min_val)
        dpg.configure_item(
            "drag_ext_threshold", min_value=safe_min, max_value=vol._cached_max_val
        )
        dpg.configure_item(
            "drag_ext_threshold", speed=max(0.1, viewer.view_state.display.ww * 0.005)
        )

        # 3. CONTEXT SWITCH: If active image changed, snap UI to the new image's state
        if self._current_image_id != img_id:
            self._current_image_id = img_id
            dpg.set_value("check_ext_enable", ext_state.is_enabled)
            dpg.set_value("drag_ext_threshold", ext_state.threshold)
            dpg.set_value("check_ext_preview", ext_state.show_preview)
            dpg.set_value("color_ext_preview", list(ext_state.preview_color))

        # 4. CONTINUOUS SYNC: Ensure UI reflects state if not being actively interacted with
        else:
            if dpg.get_value("check_ext_enable") != ext_state.is_enabled:
                dpg.set_value("check_ext_enable", ext_state.is_enabled)

            if not dpg.is_item_active("drag_ext_threshold"):
                dpg.set_value("drag_ext_threshold", ext_state.threshold)

            if dpg.get_value("check_ext_preview") != ext_state.show_preview:
                dpg.set_value("check_ext_preview", ext_state.show_preview)

            ui_col = [int(c) for c in dpg.get_value("color_ext_preview")[:4]]
            if ui_col != list(ext_state.preview_color):
                dpg.set_value("color_ext_preview", list(ext_state.preview_color))

        # 5. UI LOCKING: Enable components only if master thresholding is enabled
        dpg.configure_item("check_ext_enable", enabled=True)
        tags_to_toggle = [
            "drag_ext_threshold",
            "btn_ext_extract",
            "btn_drag_ext_threshold_minus",
            "btn_drag_ext_threshold_plus",
            "check_ext_preview",
            "color_ext_preview",
        ]
        for tag in tags_to_toggle:
            if dpg.does_item_exist(tag):
                dpg.configure_item(tag, enabled=ext_state.is_enabled)

    # --- Callbacks: View -> Model ---

    def on_enable_toggle(self, sender, app_data, user_data):
        viewer = self.gui.context_viewer
        if not viewer or not viewer.view_state:
            return

        viewer.view_state.extraction.is_enabled = app_data

        # Cleanup the Live Preview from the ContourManager if disabled
        if not app_data:
            self.controller.extraction.clear_preview(viewer.image_id, viewer.view_state)

        self.controller.ui_needs_refresh = True

    def on_threshold_drag(self, sender, app_data, user_data):
        viewer = self.gui.context_viewer
        if not viewer or not viewer.view_state:
            return

        if sender == "color_ext_preview":
            # Check if DPG is sending normalized floats (0.0-1.0) or ints (0-255)
            scale = 255.0 if all(c <= 1.0 for c in app_data) else 1.0
            viewer.view_state.extraction.preview_color = [
                int(c * scale) for c in app_data[:4]
            ]

        elif sender == "check_ext_preview":
            viewer.view_state.extraction.show_preview = app_data
            if not app_data:
                self.controller.extraction.clear_preview(
                    viewer.image_id, viewer.view_state
                )
        else:
            viewer.view_state.extraction.threshold = dpg.get_value("drag_ext_threshold")

        self.controller.ui_needs_refresh = True

    def on_step_button_clicked(self, sender, app_data, user_data):
        viewer = self.gui.context_viewer
        if not viewer or not viewer.view_state:
            return

        direction = user_data["dir"]
        current_val = viewer.view_state.extraction.threshold
        step_size = (
            max(0.1, viewer.view_state.display.ww * 0.02) if viewer.view_state else 1.0
        )
        new_val = current_val + (step_size * direction)

        if hasattr(viewer.volume, "_cached_min_val"):
            new_val = np.clip(
                new_val, viewer.volume._cached_min_val, viewer.volume._cached_max_val
            )

        viewer.view_state.extraction.threshold = new_val
        self.controller.ui_needs_refresh = True

    def on_extract_clicked(self, sender, app_data, user_data):
        viewer = self.gui.context_viewer
        if not viewer or not viewer.view_state or not viewer.volume:
            return

        img_id = viewer.image_id
        ext_state = viewer.view_state.extraction

        self.controller.status_message = "Extracting Full 3D Volume..."
        self.controller.ui_needs_refresh = True

        dpg.configure_item("prog_ext", show=True, default_value=0.0)
        dpg.configure_item(
            "text_prog_ext", show=True, default_value="Binarizing Volume..."
        )

        def _on_progress(processed, total):
            dpg.set_value("prog_ext", processed / total)
            dpg.set_value("text_prog_ext", f"Extracting: {processed} / {total}")
            self.controller.update_all_viewers_of_image(img_id, data_dirty=False)

        def _on_complete(roi_name):
            dpg.configure_item("prog_ext", show=False)
            dpg.configure_item("text_prog_ext", show=False)
            self.controller.status_message = f"Finished! Added: {roi_name}"
            self.controller.ui_needs_refresh = True

        def _on_error(msg):
            dpg.configure_item("prog_ext", show=False)
            dpg.configure_item("text_prog_ext", show=False)
            self.controller.status_message = msg
            self.controller.ui_needs_refresh = True

        self.controller.extraction.extract_full_volume(
            img_id,
            viewer.volume,
            viewer.view_state,
            ext_state.threshold,
            ext_state.preview_color,
            _on_progress,
            _on_complete,
            _on_error,
        )
