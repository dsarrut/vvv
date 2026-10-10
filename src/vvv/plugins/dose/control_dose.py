from dataclasses import dataclass, asdict
from typing import Optional, TYPE_CHECKING, Tuple, Any, Dict
import numpy as np
import dearpygui.dearpygui as dpg
from vvv.plugins.plugin_api import PluginTagMixin, PluginAPI

if TYPE_CHECKING:
    from .ui_dose import DosePluginUI

DOSE_UNITS = {"gy", "mgy", "gy/decay"}
NORM_MODES = ["Absolute Dose", "% to Max", "% to Prescription", "% to ROI Mean"]


@dataclass
class DoseSettings:
    scaling_factor: float = 1.0
    norm_mode: str = "Absolute Dose"  # "Absolute Dose", "% to Max", "% to Prescription", "% to ROI Mean"
    rx_dose: float = 50.0             # Prescription dose in Gy
    norm_roi_id: Optional[str] = None # Selected ROI ID for "% to ROI Mean"
    threshold_5pct: bool = False      # Whether low dose (<5% ref) is thresholded


class DosePluginController(PluginTagMixin):
    def __init__(self, plugin_id: str):
        self._plugin_id = plugin_id
        self._api: Optional[PluginAPI] = None
        self._ui: Optional["DosePluginUI"] = None
        self._image_settings: Dict[str, DoseSettings] = {}

    def bind(self, api: PluginAPI) -> None:
        self._api = api

    def bind_ui(self, ui: "DosePluginUI") -> None:
        self._ui = ui

    def update(self, api: PluginAPI) -> None:
        if self._ui:
            self._ui.update_ui(api)

    def get_settings(self, image_id: Optional[str]) -> DoseSettings:
        if not image_id:
            return DoseSettings()
        if image_id not in self._image_settings:
            self._image_settings[image_id] = DoseSettings()
        return self._image_settings[image_id]

    def get_dose_target_info(
        self,
    ) -> Tuple[bool, Any, bool, Optional[str], Optional[str], Optional[Any]]:
        """
        Evaluates the active viewer to identify the dose target image and its ViewState.
        Returns:
            (is_active, target_volume, is_overlay, unit_string, target_id, target_vs)
        Priority:
            1. Fused overlay image if unit in {'gy', 'mgy', 'gy/decay'}.
            2. Base image if unit in {'gy', 'mgy', 'gy/decay'}.
            3. Fallback (inactive): overlay if present, else base.
        """
        if not self._api:
            return False, None, False, None, None, None

        viewer = self._api.get_active_viewer()
        if not viewer or not viewer.volume:
            return False, None, False, None, None, None

        base_vol = viewer.volume
        base_id = getattr(viewer, "image_id", None)
        base_vs = viewer.view_state
        base_unit = getattr(base_vol, "unit", None)
        base_unit_str = str(base_unit).strip() if base_unit else None

        # 1. Check fused overlay first
        if base_vs and base_vs.display.overlay:
            ov_id = base_vs.display.overlay.image_id
            if ov_id:
                ov_vol = self._api.get_volumes().get(ov_id)
                ov_vs = self._api.get_view_states().get(ov_id)
                if ov_vol:
                    ov_unit = getattr(ov_vol, "unit", None)
                    ov_unit_str = str(ov_unit).strip() if ov_unit else None
                    if ov_unit_str and ov_unit_str.lower() in DOSE_UNITS:
                        return True, ov_vol, True, ov_unit_str, ov_id, ov_vs

        # 2. Check base image
        if base_unit_str and base_unit_str.lower() in DOSE_UNITS:
            return True, base_vol, False, base_unit_str, base_id, base_vs

        # 3. Fallback inactive target (overlay if present, else base)
        if base_vs and base_vs.display.overlay:
            ov_id = base_vs.display.overlay.image_id
            if ov_id:
                ov_vol = self._api.get_volumes().get(ov_id)
                ov_vs = self._api.get_view_states().get(ov_id)
                if ov_vol:
                    ov_unit = getattr(ov_vol, "unit", None)
                    return False, ov_vol, True, str(ov_unit) if ov_unit else None, ov_id, ov_vs

        return False, base_vol, False, base_unit_str, base_id, base_vs

    def get_dose_status(self) -> Tuple[bool, Any, bool, Optional[str]]:
        """Backwards compatible status accessor (Step 1)."""
        is_active, target_vol, is_ov, unit_str, _, _ = self.get_dose_target_info()
        return is_active, target_vol, is_ov, unit_str

    def on_enable_clicked(self, sender=None, app_data=None, user_data=None) -> None:
        """Sets unit to 'Gy' on the target volume and updates UI."""
        if not self._api:
            return

        viewer = self._api.get_active_viewer()
        if not viewer or not viewer.volume:
            return

        target_vol = None
        if viewer.view_state and viewer.view_state.display.overlay:
            ov_id = viewer.view_state.display.overlay.image_id
            if ov_id:
                target_vol = self._api.get_volumes().get(ov_id)

        if target_vol is None:
            target_vol = viewer.volume

        if target_vol:
            target_vol.unit = "Gy"
            target_vol.unit_source = "modified, unsaved"
            target_vol._is_outdated = True

            for v in self._api.get_viewers().values():
                v.is_geometry_dirty = True
                v.drawer._last_leg_state = None
                if getattr(v, "show_legend", False):
                    v.drawer.draw_legend()

            self._api.request_refresh()

    def get_scaled_dose_range(self, target_vol, scaling_factor: float) -> Tuple[float, float]:
        """Returns (min_dose, max_dose) taking into account the scaling factor."""
        if not target_vol:
            return 0.0, 0.0
        raw_min, raw_max = target_vol.get_data_range()
        s = scaling_factor if scaling_factor != 0 else 1.0
        return float(raw_min * s), float(raw_max * s)

    def compute_roi_mean_dose(self, target_vol, is_overlay: bool, roi_id: str) -> float:
        """Computes mean dose inside roi_id for the given target volume."""
        if not self._api or not target_vol or not roi_id:
            return 0.0

        viewer = self._api.get_active_viewer()
        if not viewer or not viewer.view_state:
            return 0.0

        volumes = self._api.get_volumes()
        roi_vol = volumes.get(roi_id)
        if not roi_vol or roi_vol.data is None:
            return 0.0

        mask = roi_vol.data > 0
        if not np.any(mask):
            return 0.0

        target_data = None
        if is_overlay:
            target_data = viewer.view_state.display.overlay_data
            if target_data is None:
                target_data = target_vol.data
        else:
            target_data = target_vol.data

        if target_data is None:
            return 0.0

        num_tp = getattr(target_vol, "num_timepoints", 1)
        if isinstance(num_tp, int) and num_tp > 1:
            t = min(viewer.view_state.camera.time_idx, target_data.shape[0] - 1)
            target_data = target_data[t]
        elif target_data.ndim == 4 and not getattr(target_vol, "is_rgb", False):
            target_data = target_data[0]

        roi_bbox = getattr(roi_vol, "roi_bbox", None)
        if roi_bbox is not None and isinstance(roi_bbox, (list, tuple, np.ndarray)) and len(roi_bbox) == 6:
            z0, z1, y0, y1, x0, x1 = roi_bbox
            if z0 != z1:
                target_data = target_data[z0:z1, y0:y1, x0:x1]

        if voxel_count := np.count_nonzero(mask):
            if target_data.shape == mask.shape:
                pixels = target_data[mask]
                if pixels.size > 0:
                    return float(np.mean(pixels))
        return 0.0

    def get_reference_dose(
        self, target_vol, is_overlay: bool, settings: DoseSettings
    ) -> float:
        """Returns the 100% reference dose level (in scaled Gy units)."""
        _, d_max = self.get_scaled_dose_range(target_vol, settings.scaling_factor)
        s = settings.scaling_factor if settings.scaling_factor != 0 else 1.0

        if settings.norm_mode == "% to Max":
            return d_max if d_max > 0 else 1.0
        elif settings.norm_mode == "% to Prescription":
            return settings.rx_dose if settings.rx_dose > 0 else 1.0
        elif settings.norm_mode == "% to ROI Mean":
            if settings.norm_roi_id:
                raw_mean = self.compute_roi_mean_dose(target_vol, is_overlay, settings.norm_roi_id)
                scaled_mean = raw_mean * s
                return scaled_mean if scaled_mean > 0 else 1.0
            return d_max if d_max > 0 else 1.0
        else:
            # Absolute Dose: reference level corresponds to maximum dose
            return d_max if d_max > 0 else 1.0

    def apply_display_window(self, mode: str) -> None:
        """
        Applies standard radiotherapy dose window/level presets:
            - 'full_range': [0, D_max]
            - 'rx_100': [0, D_ref]
            - 'rx_107': [0, 1.07 * D_ref]
        """
        is_active, target_vol, is_overlay, _, target_id, target_vs = self.get_dose_target_info()
        if not is_active or not target_vol or not target_vs:
            return

        settings = self.get_settings(target_id)
        s = settings.scaling_factor if settings.scaling_factor != 0 else 1.0
        d_min, d_max = self.get_scaled_dose_range(target_vol, s)
        d_ref = self.get_reference_dose(target_vol, is_overlay, settings)

        if mode == "full_range":
            low = min(0.0, d_min)
            high = max(1e-12, d_max)
            ww_scaled = high - low
            wl_scaled = (high + low) / 2.0
        elif mode == "rx_100":
            ww_scaled = max(1e-12, d_ref)
            wl_scaled = d_ref / 2.0
        elif mode == "rx_107":
            ww_scaled = max(1e-12, 1.07 * d_ref)
            wl_scaled = (1.07 * d_ref) / 2.0
        else:
            return

        # Convert back to raw voxel array units for SliceRenderer
        target_vs.display.ww = max(1e-20, ww_scaled / s)
        target_vs.display.wl = wl_scaled / s
        target_vs.is_data_dirty = True

        if self._api:
            self._api.request_refresh()

    def set_background_threshold(self, enabled: bool, pct: float = 0.05) -> None:
        """Thresholds low dose (< pct * D_ref) so exterior anatomy is visible."""
        is_active, target_vol, is_overlay, _, target_id, target_vs = self.get_dose_target_info()
        if not is_active or not target_vol or not target_vs:
            return

        settings = self.get_settings(target_id)
        settings.threshold_5pct = enabled
        s = settings.scaling_factor if settings.scaling_factor != 0 else 1.0

        if enabled:
            d_ref = self.get_reference_dose(target_vol, is_overlay, settings)
            thr_scaled = pct * d_ref
            target_vs.display.min_threshold = thr_scaled / s
        else:
            target_vs.display.min_threshold = None

        target_vs.is_data_dirty = True
        if self._api:
            self._api.request_refresh()

    def bake_scaling_factor(self) -> None:
        """Permanently multiplies voxel values by scaling factor S and resets S to 1.0."""
        is_active, target_vol, is_overlay, _, target_id, target_vs = self.get_dose_target_info()
        if not is_active or not target_vol or target_vol.data is None:
            return

        settings = self.get_settings(target_id)
        s = settings.scaling_factor
        if s == 1.0 or s == 0.0:
            return

        target_vol.data = (target_vol.data * s).astype(np.float32)
        if hasattr(target_vol, "_data_range_cache"):
            delattr(target_vol, "_data_range_cache")
        target_vol._is_outdated = True

        if target_vs:
            target_vs.display.ww *= s
            target_vs.display.wl *= s
            if target_vs.display.min_threshold is not None:
                target_vs.display.min_threshold *= s
            target_vs.is_data_dirty = True

        settings.scaling_factor = 1.0

        if self._ui:
            self._ui.update_ui(self._api)
        if self._api:
            self._api.request_refresh()

    def set_colormap(self, cmap_name: str) -> None:
        is_active, _, _, _, _, target_vs = self.get_dose_target_info()
        if not is_active or not target_vs:
            return
        target_vs.display.colormap = cmap_name
        target_vs.is_data_dirty = True
        if self._api:
            self._api.request_refresh()

    def get_crosshair_dose_sample(self) -> Tuple[Optional[float], Optional[float]]:
        """Returns (scaled_dose_gy, relative_pct) at the current crosshair position."""
        is_active, target_vol, is_overlay, _, target_id, target_vs = self.get_dose_target_info()
        if not is_active or not target_vol or not target_vs:
            return None, None

        settings = self.get_settings(target_id)
        s = settings.scaling_factor

        viewer = self._api.get_active_viewer()
        if not viewer or not viewer.view_state:
            return None, None

        phys = viewer.view_state.camera.crosshair_phys_coord
        if phys is None:
            return None, None

        target_v = target_vs.world_to_display(phys, is_buffered=False)
        if target_v is None:
            return None, None

        limit_x = target_vol.shape3d[2]
        limit_y = target_vol.shape3d[1]
        limit_z = target_vol.shape3d[0]
        ix, iy, iz = int(np.round(target_v[0])), int(np.round(target_v[1])), int(np.round(target_v[2]))

        if 0 <= ix < limit_x and 0 <= iy < limit_y and 0 <= iz < limit_z:
            raw_val = target_vs._read_voxel_value(ix, iy, iz, use_buffer=False)
            if raw_val is not None:
                scaled_dose = float(raw_val) * s
                d_ref = self.get_reference_dose(target_vol, is_overlay, settings)
                rel_pct = (scaled_dose / d_ref) * 100.0 if d_ref > 0 else 0.0
                return scaled_dose, rel_pct

        return None, None

    def on_image_loaded(self, image_id: str) -> None:
        pass

    def on_image_removed(self, image_id: str) -> None:
        self._image_settings.pop(image_id, None)

    def serialize_image_state(self, image_id: str, context: str = "history") -> dict:
        settings = self._image_settings.get(image_id)
        if settings:
            return asdict(settings)
        return {}

    def restore_image_state(self, image_id: str, data: dict, context: str = "history") -> None:
        if not data:
            return
        self._image_settings[image_id] = DoseSettings(
            scaling_factor=float(data.get("scaling_factor", 1.0)),
            norm_mode=str(data.get("norm_mode", "Absolute Dose")),
            rx_dose=float(data.get("rx_dose", 50.0)),
            norm_roi_id=data.get("norm_roi_id", None),
            threshold_5pct=bool(data.get("threshold_5pct", False)),
        )

    def save_settings(self, api: PluginAPI) -> None:
        pass

    def load_settings(self, api: PluginAPI) -> None:
        pass

    def destroy(self) -> None:
        self._image_settings.clear()
