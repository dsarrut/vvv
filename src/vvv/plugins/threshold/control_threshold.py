import numpy as np
import dearpygui.dearpygui as dpg
from vvv.plugins.plugin_api import PluginAPI


class ThresholdState:
    """Per-image state for interactive thresholding in the plugin."""

    def __init__(self):
        self.is_enabled = False
        self.threshold_min = 0.0
        self.threshold_max = 1.0
        self.show_preview = False
        self.subpixel_accurate = False
        self.preview_color_min = [255, 0, 0, 255]
        self.preview_color_max = [0, 0, 255, 255]
        self.preview_thickness = 2.0
        self.gen_bg_mode = "Constant"
        self.gen_bg_val = 0.0
        self.gen_fg_mode = "Constant"
        self.gen_fg_val = 1.0
        self.is_initialized = False

    def to_dict(self) -> dict:
        return {
            "is_enabled": self.is_enabled,
            "threshold_min": self.threshold_min,
            "threshold_max": self.threshold_max,
            "show_preview": self.show_preview,
            "subpixel_accurate": self.subpixel_accurate,
            "preview_color_min": list(self.preview_color_min),
            "preview_color_max": list(self.preview_color_max),
            "preview_thickness": self.preview_thickness,
            "gen_bg_mode": self.gen_bg_mode,
            "gen_bg_val": self.gen_bg_val,
            "gen_fg_mode": self.gen_fg_mode,
            "gen_fg_val": self.gen_fg_val,
        }

    def from_dict(self, d: dict) -> None:
        if not d:
            return
        self.is_enabled = d.get("is_enabled", self.is_enabled)
        self.threshold_min = d.get("threshold_min", self.threshold_min)
        self.threshold_max = d.get("threshold_max", self.threshold_max)
        self.show_preview = d.get("show_preview", self.show_preview)
        self.subpixel_accurate = d.get("subpixel_accurate", self.subpixel_accurate)
        self.preview_color_min = d.get("preview_color_min", self.preview_color_min)
        self.preview_color_max = d.get("preview_color_max", self.preview_color_max)
        self.preview_thickness = d.get("preview_thickness", self.preview_thickness)
        self.gen_bg_mode = d.get("gen_bg_mode", self.gen_bg_mode)
        self.gen_bg_val = d.get("gen_bg_val", self.gen_bg_val)
        self.gen_fg_mode = d.get("gen_fg_mode", self.gen_fg_mode)
        self.gen_fg_val = d.get("gen_fg_val", self.gen_fg_val)
        self.is_initialized = True


class ThresholdController:
    """Manages thresholding state and UI callbacks for the plugin without active image wiring."""

    def __init__(self, plugin_id: str):
        self._plugin_id = plugin_id
        self._api = None
        self._ui = None
        self._states: dict[str, ThresholdState] = {}
        self._last_sidebar_image_id = None

    def _t(self, name: str) -> str:
        return f"{self._plugin_id}_{name}"

    def bind(self, api: PluginAPI) -> None:
        self._api = api

    def bind_ui(self, ui) -> None:
        self._ui = ui

    def get_image_state(self, image_id: str) -> ThresholdState:
        if image_id not in self._states:
            self._states[image_id] = ThresholdState()
            if self._api:
                vol = self._api.get_volumes().get(image_id)
                if vol is not None:
                    self._init_state_from_volume(self._states[image_id], vol)
        return self._states[image_id]

    def _init_state_from_volume(self, state: ThresholdState, vol) -> None:
        if vol is not None:
            current_data_id = id(vol.data)
            if not hasattr(vol, "_cached_min_val") or getattr(vol, "_cached_data_id", None) != current_data_id:
                vol._cached_min_val = float(np.min(vol.data))
                vol._cached_max_val = float(np.max(vol.data))
                vol._cached_data_id = current_data_id

            if not state.is_initialized:
                state.threshold_min = vol._cached_min_val
                state.threshold_max = vol._cached_max_val
                state.is_initialized = True

    def update(self, api: PluginAPI) -> None:
        if self._ui:
            self._ui.update_ui(api)

    def on_image_loaded(self, image_id: str) -> None:
        self.get_image_state(image_id)

    def on_image_removed(self, image_id: str) -> None:
        self._states.pop(image_id, None)
        if self._last_sidebar_image_id == image_id:
            self._last_sidebar_image_id = None

    def serialize_image_state(self, image_id: str) -> dict:
        state = self._states.get(image_id)
        if state is None:
            return {}
        return state.to_dict()

    def restore_image_state(self, image_id: str, data: dict) -> None:
        state = self.get_image_state(image_id)
        state.from_dict(data)

    def save_settings(self, api: PluginAPI) -> None:
        pass

    def load_settings(self, api: PluginAPI) -> None:
        pass

    def destroy(self) -> None:
        pass

    # --- Callbacks ---

    def on_enable_toggle(self, sender, app_data, user_data):
        viewer = self._api.get_active_viewer()
        if not viewer or not viewer.view_state:
            return
        state = self.get_image_state(viewer.image_id)
        state.is_enabled = app_data
        self._api.request_refresh()

    def on_threshold_drag(self, sender, app_data, user_data):
        viewer = self._api.get_active_viewer()
        if not viewer or not viewer.view_state:
            return
        state = self.get_image_state(viewer.image_id)

        if sender == self._t("color_ext_preview_min"):
            scale = 255.0 if all(c <= 1.0 for c in app_data) else 1.0
            state.preview_color_min = [int(c * scale) for c in app_data[:4]]

        elif sender == self._t("color_ext_preview_max"):
            scale = 255.0 if all(c <= 1.0 for c in app_data) else 1.0
            state.preview_color_max = [int(c * scale) for c in app_data[:4]]

        elif sender == self._t("check_ext_preview"):
            state.show_preview = app_data

        elif sender == self._t("check_ext_subpixel"):
            state.subpixel_accurate = app_data

        elif sender == self._t("drag_ext_thickness"):
            state.preview_thickness = app_data

        elif sender in (self._t("drag_ext_threshold_min"), self._t("drag_ext_threshold_max")):
            val = dpg.get_value(sender)
            if hasattr(viewer.volume, "_cached_min_val"):
                val = float(np.clip(val, viewer.volume._cached_min_val, viewer.volume._cached_max_val))

            if sender == self._t("drag_ext_threshold_min"):
                if val > state.threshold_max:
                    state.threshold_max = val
                state.threshold_min = val
            else:
                if val < state.threshold_min:
                    state.threshold_min = val
                state.threshold_max = val

        self._api.request_refresh()

    def on_step_button_clicked(self, sender, app_data, user_data):
        viewer = self._api.get_active_viewer()
        if not viewer or not viewer.view_state:
            return

        direction = user_data["dir"]
        tag = user_data["tag"]
        is_min = tag == self._t("drag_ext_threshold_min")

        state = self.get_image_state(viewer.image_id)
        current_val = state.threshold_min if is_min else state.threshold_max
        step_size = max(0.1, viewer.view_state.display.ww * 0.02) if viewer.view_state else 1.0
        new_val = current_val + (step_size * direction)

        if hasattr(viewer.volume, "_cached_min_val"):
            new_val = np.clip(new_val, viewer.volume._cached_min_val, viewer.volume._cached_max_val)

        if is_min:
            if new_val > state.threshold_max:
                state.threshold_max = new_val
            state.threshold_min = new_val
        else:
            if new_val < state.threshold_min:
                state.threshold_min = new_val
            state.threshold_max = new_val

        self._api.request_refresh()

    def on_gen_mode_changed(self, sender, app_data, user_data):
        viewer = self._api.get_active_viewer()
        if not viewer or not viewer.view_state:
            return
        state = self.get_image_state(viewer.image_id)

        if sender == self._t("combo_ext_bg_mode"):
            state.gen_bg_mode = app_data
        elif sender == self._t("combo_ext_fg_mode"):
            state.gen_fg_mode = app_data
        elif sender == self._t("input_ext_bg_val"):
            state.gen_bg_val = app_data
        elif sender == self._t("input_ext_fg_val"):
            state.gen_fg_val = app_data

        self._api.request_refresh()

    def on_create_image_clicked(self, sender, app_data, user_data):
        if self._api:
            self._api.notify("Threshold Plugin: Create Image is not wired yet")
