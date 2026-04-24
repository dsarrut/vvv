import time
import numpy as np
import threading
import dearpygui.dearpygui as dpg
from vvv.ui.ui_components import build_section_title, build_stepped_slider


class ExtractionUI:
    """Handles the Interactive Thresholding UI elements and user input."""

    def __init__(self, gui, controller):
        self.gui = gui
        self.controller = controller

        self._debounce_timer = None
        self._last_visible_targets = frozenset()

        # Format: { image_id: {"enabled": False, "threshold": 0.0} }
        self._image_states = {}
        self._current_image_id = None

        threading.Thread(target=self._scroll_monitor_daemon, daemon=True).start()

    def _scroll_monitor_daemon(self):
        while True:
            time.sleep(0.05)
            try:
                if not dpg.is_dearpygui_running():
                    break
                if dpg.does_item_exist("check_ext_enable") and dpg.get_value(
                    "check_ext_enable"
                ):
                    if dpg.does_item_exist("check_ext_preview") and dpg.get_value(
                        "check_ext_preview"
                    ):
                        targets = self._get_visible_targets()
                        if targets and targets != self._last_visible_targets:
                            self._run_preview_extraction(clear_cache=False)
            except Exception:
                pass

    def _get_visible_targets(self):
        viewer = self.gui.context_viewer
        if not viewer:
            return frozenset()

        targets = set()
        img_id = viewer.image_id
        for v in self.controller.viewers.values():
            if v.image_id == img_id and v.is_image_orientation():
                targets.add((v.orientation, v.slice_idx))
        return frozenset(targets)

    def _trigger_redraw(self, img_id):
        for v in self.controller.viewers.values():
            if v.image_id == img_id:
                v.is_geometry_dirty = True

    def build_tab_extraction(self, gui):
        cfg_c = gui.ui_cfg["colors"]

        with dpg.tab(label="Extract", tag="tab_extraction"):
            dpg.add_spacer(height=5)
            build_section_title("Interactive Threshold", cfg_c["text_header"])

            dpg.add_checkbox(
                label="Enable Thresholding",
                tag="check_ext_enable",
                default_value=False,
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
                    default_value=True,
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
        has_image = (
            viewer is not None
            and getattr(viewer, "view_state", None) is not None
            and viewer.volume is not None
        )

        if not has_image:
            tags_to_disable = [
                "check_ext_enable",
                "drag_ext_threshold",
                "btn_ext_extract",
                "btn_drag_ext_threshold_minus",
                "btn_drag_ext_threshold_plus",
                "check_ext_preview",
            ]
            for tag in tags_to_disable:
                if dpg.does_item_exist(tag):
                    dpg.configure_item(tag, enabled=False)
            self._current_image_id = None
            return

        vol = viewer.volume
        img_id = viewer.image_id
        current_data_id = id(vol.data)

        if (
            not hasattr(vol, "_cached_min_val")
            or getattr(vol, "_cached_data_id", None) != current_data_id
        ):
            vol._cached_min_val = float(np.min(vol.data))
            vol._cached_max_val = float(np.max(vol.data))
            vol._cached_data_id = current_data_id

        min_v = vol._cached_min_val
        max_v = vol._cached_max_val

        # --- TWO-WAY STATE SYNCHRONIZATION ---

        # 1. Initialize memory if this image has never been seen (Default 0.0, Disabled)
        if img_id not in self._image_states:
            self._image_states[img_id] = {"enabled": False, "threshold": 0.0}

        # 2. Context Switch: Apply memory to the UI
        if self._current_image_id != img_id:
            self._current_image_id = img_id

            # Apply constraints before setting value to prevent clamping errors
            dpg.configure_item("drag_ext_threshold", min_value=min_v, max_value=max_v)

            dpg.set_value("check_ext_enable", self._image_states[img_id]["enabled"])
            dpg.set_value("drag_ext_threshold", self._image_states[img_id]["threshold"])

        # 3. Same Image: Constantly save UI changes back to memory
        else:
            self._image_states[img_id]["enabled"] = dpg.get_value("check_ext_enable")
            self._image_states[img_id]["threshold"] = dpg.get_value(
                "drag_ext_threshold"
            )

        # Set physical speed
        dpg.configure_item("check_ext_enable", enabled=True)
        dpg.configure_item(
            "drag_ext_threshold", speed=max(0.1, viewer.view_state.display.ww * 0.005)
        )

        # Lock elements if master toggle is off
        is_active = self._image_states[img_id]["enabled"]
        tags_to_toggle = [
            "drag_ext_threshold",
            "btn_ext_extract",
            "btn_drag_ext_threshold_minus",
            "btn_drag_ext_threshold_plus",
            "check_ext_preview",
        ]

        for tag in tags_to_toggle:
            if dpg.does_item_exist(tag):
                dpg.configure_item(tag, enabled=is_active)

    def on_enable_toggle(self, sender, app_data, user_data):
        self.refresh_extraction_ui()
        self._run_preview_extraction(clear_cache=True)

    def on_step_button_clicked(self, sender, app_data, user_data):
        target_tag = user_data["tag"]
        direction = user_data["dir"]
        current_val = dpg.get_value(target_tag)

        viewer = self.gui.context_viewer
        step_size = (
            max(0.1, viewer.view_state.display.ww * 0.02)
            if (viewer and viewer.view_state)
            else 1.0
        )
        new_val = current_val + (step_size * direction)

        if viewer and hasattr(viewer.volume, "_cached_min_val"):
            new_val = np.clip(
                new_val, viewer.volume._cached_min_val, viewer.volume._cached_max_val
            )

        dpg.set_value(target_tag, new_val)
        self._run_preview_extraction(clear_cache=True)

    def on_threshold_drag(self, sender, app_data, user_data):
        if self._debounce_timer is not None:
            self._debounce_timer.cancel()

        self._debounce_timer = threading.Timer(
            0.1, lambda: self._run_preview_extraction(clear_cache=True)
        )
        self._debounce_timer.start()

    def _run_preview_extraction(self, clear_cache=False):
        viewer = self.gui.context_viewer
        if not viewer or not viewer.view_state or not viewer.volume:
            return

        img_id = viewer.image_id
        is_enabled = dpg.get_value("check_ext_enable")
        show_preview = dpg.get_value("check_ext_preview")

        # If toggle is OFF, wipe the preview instantly
        if not is_enabled or not show_preview:
            if self.controller.extraction.clear_preview(img_id, viewer.view_state):
                self._trigger_redraw(img_id)
            return

        visible_targets = self._get_visible_targets()
        threshold_val = dpg.get_value("drag_ext_threshold")
        color = [int(c) for c in dpg.get_value("color_ext_preview")[:3]]

        self.controller.status_message = "Updating Preview Slice..."
        self.controller.ui_needs_refresh = True

        extracted_any = self.controller.extraction.update_preview(
            img_id,
            viewer.volume,
            viewer.view_state,
            threshold_val,
            visible_targets,
            color,
            clear_cache,
        )

        self._last_visible_targets = visible_targets

        if extracted_any or clear_cache:
            self._trigger_redraw(img_id)
            self.controller.status_message = "Live Preview Active"
            self.controller.ui_needs_refresh = True

    def on_extract_clicked(self, sender, app_data, user_data):
        viewer = self.gui.context_viewer
        if not viewer or not viewer.view_state or not viewer.volume:
            return

        img_id = viewer.image_id

        self.controller.status_message = "Extracting Full 3D Volume..."
        self.controller.ui_needs_refresh = True

        dpg.configure_item("prog_ext", show=True, default_value=0.0)
        dpg.configure_item(
            "text_prog_ext", show=True, default_value="Binarizing Volume..."
        )

        threshold_val = dpg.get_value("drag_ext_threshold")
        color = [int(c) for c in dpg.get_value("color_ext_preview")[:3]]

        def _on_progress(processed, total):
            dpg.set_value("prog_ext", processed / total)
            dpg.set_value("text_prog_ext", f"Extracting: {processed} / {total}")
            self._trigger_redraw(img_id)

        def _on_complete(roi_name):
            dpg.configure_item("prog_ext", show=False)
            dpg.configure_item("text_prog_ext", show=False)

            if self.controller.extraction.clear_preview(img_id, viewer.view_state):
                self._trigger_redraw(img_id)

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
            threshold_val,
            color,
            _on_progress,
            _on_complete,
            _on_error,
        )
