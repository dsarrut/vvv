import threading
import numpy as np
import dearpygui.dearpygui as dpg
from typing import Optional
from vvv.plugins.plugin_api import PluginAPI, PluginTagMixin
from vvv.maths.contours import ContourROI


class ThresholdState:
    """Per-image state for interactive thresholding in the plugin."""

    def __init__(self):
        self.is_enabled = False
        self.threshold_min = 0.0
        self.threshold_max = 1.0
        self.show_preview = True
        self.subpixel_accurate = True
        self.preview_color_min = [255, 0, 0, 255]
        self.preview_color_max = [0, 0, 255, 255]
        self.preview_thickness = 0.5
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
        def get_val(key, default):
            v = d.get(key, default)
            return default if v is None else v

        self.is_enabled = get_val("is_enabled", self.is_enabled)
        self.threshold_min = get_val("threshold_min", self.threshold_min)
        self.threshold_max = get_val("threshold_max", self.threshold_max)
        self.show_preview = get_val("show_preview", self.show_preview)
        self.subpixel_accurate = get_val("subpixel_accurate", self.subpixel_accurate)
        self.preview_color_min = get_val("preview_color_min", self.preview_color_min)
        self.preview_color_max = get_val("preview_color_max", self.preview_color_max)
        self.preview_thickness = get_val("preview_thickness", self.preview_thickness)
        self.gen_bg_mode = get_val("gen_bg_mode", self.gen_bg_mode)
        self.gen_bg_val = get_val("gen_bg_val", self.gen_bg_val)
        self.gen_fg_mode = get_val("gen_fg_mode", self.gen_fg_mode)
        self.gen_fg_val = get_val("gen_fg_val", self.gen_fg_val)
        self.is_initialized = True


class ThresholdController(PluginTagMixin):
    """Manages thresholding state and UI callbacks for the plugin without active image wiring."""

    def __init__(self, plugin_id: str):
        self._plugin_id = plugin_id
        self._api: Optional[PluginAPI] = None
        self._ui = None
        self._states: dict[str, ThresholdState] = {}
        self._last_sidebar_image_id = None
        self._generation_stop: Optional[threading.Event] = None

    def bind(self, api: PluginAPI) -> None:
        self._api = api

    def bind_ui(self, ui) -> None:
        self._ui = ui

    def get_image_state(self, image_id: str) -> ThresholdState:
        if image_id not in self._states:
            self._states[image_id] = ThresholdState()
        state = self._states[image_id]
        if not state.is_initialized and self._api:
            vol = self._api.get_volumes().get(image_id)
            if vol is not None:
                self._init_state_from_volume(state, vol)
        return state

    def _init_state_from_volume(self, state: ThresholdState, vol) -> None:
        if vol is not None:
            current_data_id = id(vol.data)
            if not hasattr(vol, "_cached_min_val") or getattr(vol, "_cached_data_id", None) != current_data_id:
                if vol.data is not None and vol.data.size > 0:
                    min_val = np.min(vol.data)
                    max_val = np.max(vol.data)
                    vol._cached_min_val = float(min_val) if min_val is not None else 0.0
                    vol._cached_max_val = float(max_val) if max_val is not None else 1.0
                else:
                    vol._cached_min_val = 0.0
                    vol._cached_max_val = 1.0
                vol._cached_data_id = current_data_id

            if not state.is_initialized:
                state.threshold_min = float(np.clip(0.0, vol._cached_min_val, vol._cached_max_val))
                state.threshold_max = vol._cached_max_val + 1.0
                state.is_initialized = True

    def update(self, api: PluginAPI) -> None:
        if self._ui:
            self._ui.update_ui(api)

    def on_image_loaded(self, image_id: str) -> None:
        self.get_image_state(image_id)

    def on_image_removed(self, image_id: str) -> None:
        if self._generation_stop:
            self._generation_stop.set()
        if self._api:
            vs = self._api.get_view_states().get(image_id)
            if vs:
                self.clear_preview(image_id, vs)
        self._states.pop(image_id, None)
        if self._last_sidebar_image_id == image_id:
            self._last_sidebar_image_id = None

    def serialize_image_state(self, image_id: str, context: str = "history") -> dict:
        state = self._states.get(image_id)
        if state is None:
            return {}
        return state.to_dict()

    def restore_image_state(self, image_id: str, data: dict, context: str = "history") -> None:
        state = self.get_image_state(image_id)
        state.from_dict(data)
        if self._api:
            vs = self._api.get_view_states().get(image_id)
            if vs:
                vs.is_geometry_dirty = True

    def save_settings(self, api: PluginAPI) -> None:
        pass

    def load_settings(self, api: PluginAPI) -> None:
        pass

    def destroy(self) -> None:
        if self._generation_stop:
            self._generation_stop.set()
        if self._api:
            for img_id, vs in self._api.get_view_states().items():
                self.clear_preview(img_id, vs)

    def _get_or_create_preview_rois(self, img_id, vs, state):
        """Retrieves or initializes the transient Plugin Draft ROIs inside the ViewState."""
        assert self._api is not None
        roi_min = next(
            (c for c in vs.contours.values() if getattr(c, "is_plugin_draft_min", False)), None
        )
        if not roi_min:
            roi_min = ContourROI(
                name="Plugin Draft Min",
                color=state.preview_color_min,
                thickness=state.preview_thickness,
            )
            roi_min.is_plugin_draft_min = True
            roi_min.last_computed_threshold_min = None
            roi_min.last_computed_threshold_max = None
            roi_min.last_computed_subpixel = None
            roi_min.last_computed_time_idx = None
            roi_min.last_computed_transform = None
            self._api.add_contour(img_id, roi_min)
        else:
            roi_min.color = state.preview_color_min
            roi_min.thickness = state.preview_thickness

        roi_max = next(
            (c for c in vs.contours.values() if getattr(c, "is_plugin_draft_max", False)), None
        )
        if not roi_max:
            roi_max = ContourROI(
                name="Plugin Draft Max",
                color=state.preview_color_max,
                thickness=state.preview_thickness,
            )
            roi_max.is_plugin_draft_max = True
            roi_max.last_computed_threshold_min = None
            roi_max.last_computed_threshold_max = None
            roi_max.last_computed_subpixel = None
            roi_max.last_computed_time_idx = None
            roi_max.last_computed_transform = None
            self._api.add_contour(img_id, roi_max)
        else:
            roi_max.color = state.preview_color_max
            roi_max.thickness = state.preview_thickness

        return roi_min, roi_max

    def clear_preview(self, img_id, vs):
        """Removes the plugin draft ROIs from the image's state."""
        if not self._api:
            return False
        roi_min = next(
            (c for c in vs.contours.values() if getattr(c, "is_plugin_draft_min", False)), None
        )
        roi_max = next(
            (c for c in vs.contours.values() if getattr(c, "is_plugin_draft_max", False)), None
        )
        cleared = False
        if roi_min:
            self._api.remove_contour(img_id, roi_min.id)
            cleared = True
        if roi_max:
            self._api.remove_contour(img_id, roi_max.id)
            cleared = True
        return cleared

    def update_preview(
        self, img_id, vol, vs, state, ori, s_idx, slice_data
    ):
        """Computes missing slices on the fly for the plugin's preview contours."""
        from vvv.maths.contours import extract_2d_contours_from_slice
        
        roi_min, roi_max = self._get_or_create_preview_rois(img_id, vs, state)

        current_transform = vs.space.get_parameters() if vs.space.is_active else None

        cache_mismatch = (
            getattr(roi_min, "last_computed_threshold_min", None) != state.threshold_min
            or getattr(roi_min, "last_computed_threshold_max", None) != state.threshold_max
            or getattr(roi_min, "last_computed_subpixel", None) != state.subpixel_accurate
            or getattr(roi_min, "last_computed_time_idx", None) != vs.camera.time_idx
            or getattr(roi_min, "last_computed_transform", None) != current_transform
        )

        # Clear draft if the slider OR the subpixel flag moved OR transform changed
        if cache_mismatch:
            roi_min.invalidate()
            roi_max.invalidate()

            roi_min.last_computed_threshold_min = state.threshold_min
            roi_min.last_computed_threshold_max = state.threshold_max
            roi_min.last_computed_subpixel = state.subpixel_accurate
            roi_min.last_computed_time_idx = vs.camera.time_idx
            roi_min.last_computed_transform = current_transform
            roi_max.last_computed_threshold_min = state.threshold_min
            roi_max.last_computed_threshold_max = state.threshold_max
            roi_max.last_computed_subpixel = state.subpixel_accurate
            roi_max.last_computed_time_idx = vs.camera.time_idx
            roi_max.last_computed_transform = current_transform

        extracted_any = False
        if s_idx not in roi_min.polygons[ori]:
            sw, sh = vol.get_physical_aspect_ratio(ori)

            if slice_data is None or slice_data.size == 0:
                roi_min.polygons[ori][s_idx] = []
                roi_max.polygons[ori][s_idx] = []
            elif state.subpixel_accurate:
                c_max = np.max(slice_data)

                if c_max >= state.threshold_min:
                    roi_min.polygons[ori][s_idx] = extract_2d_contours_from_slice(
                        slice_data, state.threshold_min, sw, sh
                    )
                else:
                    roi_min.polygons[ori][s_idx] = []

                if c_max >= state.threshold_max:
                    roi_max.polygons[ori][s_idx] = extract_2d_contours_from_slice(
                        slice_data, state.threshold_max, sw, sh
                    )
                else:
                    roi_max.polygons[ori][s_idx] = []

            else:
                mask_min = (slice_data >= state.threshold_min).astype(np.uint8)
                mask_max = (slice_data >= state.threshold_max).astype(np.uint8)

                if np.any(mask_min):
                    roi_min.polygons[ori][s_idx] = extract_2d_contours_from_slice(
                        mask_min, 0.5, sw, sh
                    )
                else:
                    roi_min.polygons[ori][s_idx] = []

                if np.any(mask_max):
                    roi_max.polygons[ori][s_idx] = extract_2d_contours_from_slice(
                        mask_max, 0.5, sw, sh
                    )
                else:
                    roi_max.polygons[ori][s_idx] = []

            extracted_any = True

    # --- Callbacks ---

    def on_enable_toggle(self, sender, app_data, user_data):
        api = self._api
        if not api:
            return
        viewer = api.get_active_viewer()
        if not viewer or not viewer.view_state:
            return
        state = self.get_image_state(viewer.image_id)
        state.is_enabled = app_data
        if not app_data:
            self.clear_preview(viewer.image_id, viewer.view_state)
        else:
            state.show_preview = True
        viewer.view_state.is_geometry_dirty = True
        api.request_refresh()

    def on_threshold_drag(self, sender, app_data, user_data):
        api = self._api
        if not api:
            return
        viewer = api.get_active_viewer()
        if not viewer or not viewer.view_state:
            return
        state = self.get_image_state(viewer.image_id)

        if sender == self._t("color_ext_preview_min"):
            from vvv.ui.ui_components import normalize_rgba_to_int
            state.preview_color_min = normalize_rgba_to_int(app_data)

        elif sender == self._t("color_ext_preview_max"):
            from vvv.ui.ui_components import normalize_rgba_to_int
            state.preview_color_max = normalize_rgba_to_int(app_data)

        elif sender == self._t("check_ext_preview"):
            state.show_preview = app_data
            if not app_data:
                self.clear_preview(viewer.image_id, viewer.view_state)

        elif sender == self._t("check_ext_subpixel"):
            state.subpixel_accurate = app_data

        elif sender == self._t("drag_ext_thickness"):
            state.preview_thickness = app_data

        elif sender in (self._t("drag_ext_threshold_min"), self._t("drag_ext_threshold_max")):
            val = dpg.get_value(sender)
            if hasattr(viewer.volume, "_cached_min_val"):
                val = float(np.clip(val, viewer.volume._cached_min_val, viewer.volume._cached_max_val + 1.0))

            if sender == self._t("drag_ext_threshold_min"):
                if val > state.threshold_max:
                    state.threshold_max = val
                state.threshold_min = val
            else:
                if val < state.threshold_min:
                    state.threshold_min = val
                state.threshold_max = val

        viewer.view_state.is_geometry_dirty = True
        api.request_refresh()

    def on_step_button_clicked(self, sender, app_data, user_data):
        api = self._api
        if not api:
            return
        viewer = api.get_active_viewer()
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
            new_val = np.clip(new_val, viewer.volume._cached_min_val, viewer.volume._cached_max_val + 1.0)

        if is_min:
            if new_val > state.threshold_max:
                state.threshold_max = new_val
            state.threshold_min = new_val
        else:
            if new_val < state.threshold_min:
                state.threshold_min = new_val
            state.threshold_max = new_val

        viewer.view_state.is_geometry_dirty = True
        api.request_refresh()

    def on_gen_mode_changed(self, sender, app_data, user_data):
        api = self._api
        if not api:
            return
        viewer = api.get_active_viewer()
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

        api.request_refresh()

    def on_create_image_clicked(self, sender, app_data, user_data):
        api = self._api
        if not api:
            return
        viewer = api.get_active_viewer()
        if not viewer or not viewer.view_state or not viewer.volume:
            return

        vol = viewer.volume
        state = self.get_image_state(viewer.image_id)
        vs = viewer.view_state

        stop_event = threading.Event()
        self._generation_stop = stop_event

        api.set_async_status("Generating thresholded image...")
        api.request_refresh()

        def _extract():
            import SimpleITK as sitk
            from vvv.maths.image import VolumeData
            from vvv.core.view_state import ViewState

            if stop_event.is_set():
                return

            try:
                # 1. Generate Masks
                new_data = np.zeros_like(vol.data)

                # Frame-by-frame processing to prevent massive RAM spikes on 4D volumes
                if vol.data.ndim == 4:
                    for t in range(vol.data.shape[0]):
                        mask_fg = (vol.data[t] >= state.threshold_min) & (vol.data[t] <= state.threshold_max)
                        mask_bg = ~mask_fg

                        if state.gen_fg_mode == "Constant":
                            new_data[t, mask_fg] = state.gen_fg_val
                        else:
                            new_data[t, mask_fg] = vol.data[t, mask_fg]

                        if state.gen_bg_mode == "Constant":
                            new_data[t, mask_bg] = state.gen_bg_val
                        else:
                            new_data[t, mask_bg] = vol.data[t, mask_bg]
                else:
                    mask_fg = (vol.data >= state.threshold_min) & (vol.data <= state.threshold_max)
                    mask_bg = ~mask_fg

                    if state.gen_fg_mode == "Constant":
                        new_data[mask_fg] = state.gen_fg_val
                    else:
                        new_data[mask_fg] = vol.data[mask_fg]

                    if state.gen_bg_mode == "Constant":
                        new_data[mask_bg] = state.gen_bg_val
                    else:
                        new_data[mask_bg] = vol.data[mask_bg]

                # 2. Build the ITK Image
                if getattr(vol, "is_dvf", False):
                    data_to_build = np.moveaxis(new_data, 0, -1)
                    new_img = sitk.GetImageFromArray(data_to_build, isVector=True)
                elif vol.data.ndim == 4:
                    vols = [sitk.GetImageFromArray(new_data[t]) for t in range(new_data.shape[0])]
                    new_img = sitk.JoinSeries(vols)
                else:
                    new_img = sitk.GetImageFromArray(new_data)
                new_img.SetSpacing(vol.sitk_image.GetSpacing())
                new_img.SetOrigin(vol.sitk_image.GetOrigin())
                new_img.SetDirection(vol.sitk_image.GetDirection())

                if stop_event.is_set():
                    return

                def _mount_on_main():
                    if stop_event.is_set():
                        return
                    try:
                        # 3. Bypass Disk I/O to Create VolumeData
                        new_vol = VolumeData.__new__(VolumeData)
                        new_vol.path = vol.path
                        new_vol.file_paths = list(vol.file_paths)
                        new_vol.name = f"Thr: {vol.name}"
                        new_vol.sitk_image = new_img
                        new_vol.data = new_data
                        new_vol.matrix_display_str = vol.matrix_display_str
                        new_vol.matrix_tooltip_str = vol.matrix_tooltip_str
                        new_vol.read_image_metadata()
                        new_vol.last_mtime = 0
                        new_vol._last_check_time = 0
                        new_vol._is_outdated = False

                        # 4. Build ViewState and Mount it!
                        new_vs = ViewState(new_vol)
                        new_vs.camera.from_dict(vs.camera.to_dict())

                        api.mount_generated_image(new_vol, new_vs)
                        api.set_async_status("Threshold image generated successfully")
                        api.request_refresh()
                    except Exception as inner_e:
                        api.set_async_status(f"Failed to mount generated image: {inner_e}")
                        api.request_refresh()

                api.run_on_main_thread(_mount_on_main)

            except Exception as e:
                def _handle_error():
                    api.set_async_status(f"Failed to generate image: {e}")
                    api.request_refresh()
                api.run_on_main_thread(_handle_error)
                raise e

        threading.Thread(target=_extract, daemon=True).start()
