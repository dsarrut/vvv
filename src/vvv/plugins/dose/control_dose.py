from typing import Optional, TYPE_CHECKING, Tuple, Any
import numpy as np
import dearpygui.dearpygui as dpg
from vvv.plugins.plugin_api import PluginTagMixin, PluginAPI

if TYPE_CHECKING:
    from .ui_dose import DosePluginUI

DOSE_UNITS = {"gy", "mgy", "gy/decay"}


class DosePluginController(PluginTagMixin):
    def __init__(self, plugin_id: str):
        self._plugin_id = plugin_id
        self._api: Optional[PluginAPI] = None
        self._ui: Optional["DosePluginUI"] = None
        self._threshold_5pct: bool = False

    def bind(self, api: PluginAPI) -> None:
        self._api = api

    def bind_ui(self, ui: "DosePluginUI") -> None:
        self._ui = ui

    def update(self, api: PluginAPI) -> None:
        if self._ui:
            self._ui.update_ui(api)

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
        """Backwards compatible status accessor."""
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

    def apply_display_window(self, mode: str) -> None:
        """
        Applies standard radiotherapy dose window/level presets:
            - 'full_range': [D_min, D_max]
            - 'rx_100': [0, D_max]
            - 'rx_107': [0, 1.07 * D_max]
        """
        is_active, target_vol, is_overlay, _, target_id, target_vs = self.get_dose_target_info()
        if not is_active or not target_vol or not target_vs:
            return

        raw_min, raw_max = target_vol.get_data_range()
        d_min = float(raw_min)
        d_max = float(raw_max)

        if mode == "full_range":
            low = min(0.0, d_min)
            high = max(1e-12, d_max)
            ww = high - low
            wl = (high + low) / 2.0
        elif mode == "rx_100":
            ww = max(1e-12, d_max)
            wl = d_max / 2.0
        elif mode == "rx_107":
            ww = max(1e-12, 1.07 * d_max)
            wl = (1.07 * d_max) / 2.0
        else:
            return

        target_vs.display.ww = max(1e-20, ww)
        target_vs.display.wl = wl
        target_vs.is_data_dirty = True

        if self._api:
            self._api.request_refresh()

    def set_background_threshold(self, enabled: bool, pct: float = 0.05) -> None:
        """Thresholds low dose (< pct * D_max) so exterior anatomy is visible."""
        is_active, target_vol, _, _, _, target_vs = self.get_dose_target_info()
        if not is_active or not target_vol or not target_vs:
            return

        self._threshold_5pct = enabled
        if enabled:
            _, raw_max = target_vol.get_data_range()
            target_vs.display.min_threshold = float(pct * raw_max)
        else:
            target_vs.display.min_threshold = None

        target_vs.is_data_dirty = True
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
        """Returns (dose_value, percentage_of_max) at the current crosshair position."""
        is_active, target_vol, _, _, _, target_vs = self.get_dose_target_info()
        if not is_active or not target_vol or not target_vs or not self._api:
            return None, None

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
                val = float(raw_val)
                _, raw_max = target_vol.get_data_range()
                pct = (val / raw_max) * 100.0 if raw_max > 0 else 0.0
                return val, pct

        return None, None

    def on_image_loaded(self, image_id: str) -> None:
        pass

    def on_image_removed(self, image_id: str) -> None:
        pass

    def serialize_image_state(self, image_id: str, context: str = "history") -> dict:
        return {"threshold_5pct": self._threshold_5pct}

    def restore_image_state(self, image_id: str, data: dict, context: str = "history") -> None:
        if data:
            self._threshold_5pct = bool(data.get("threshold_5pct", False))

    def save_settings(self, api: PluginAPI) -> None:
        pass

    def load_settings(self, api: PluginAPI) -> None:
        pass

    def destroy(self) -> None:
        pass
