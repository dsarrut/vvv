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



    def go_to_max(self) -> None:
        """Finds the maximum dose voxel in the active target volume and centers crosshair and camera on it."""
        is_active, target_vol, is_overlay, _, target_id, target_vs = self.get_dose_target_info()
        if not is_active or not target_vol or not self._api:
            return

        viewer = self._api.get_active_viewer()
        if not viewer or not viewer.view_state:
            return

        arr = target_vol.data
        if arr is None or arr.size == 0:
            return

        if arr.ndim == 4 and not getattr(target_vol, "is_rgb", False):
            t_idx = min(getattr(viewer.view_state.camera, "time_idx", 0), arr.shape[0] - 1)
            arr_3d = arr[t_idx]
        else:
            arr_3d = arr

        try:
            if np.isnan(arr_3d).any():
                idx_flat = int(np.nanargmax(arr_3d))
            else:
                idx_flat = int(np.argmax(arr_3d))
            z_idx, y_idx, x_idx = np.unravel_index(idx_flat, arr_3d.shape)
        except Exception:
            return

        if getattr(target_vol, "sitk_image", None):
            try:
                phys = target_vol.sitk_image.TransformIndexToPhysicalPoint([int(x_idx), int(y_idx), int(z_idx)])
                phys_coord = np.array(phys[:3], dtype=np.float64)
            except Exception:
                phys_coord = target_vol.voxel_coord_to_physic_coord(np.array([float(x_idx), float(y_idx), float(z_idx)]))
        else:
            phys_coord = target_vol.voxel_coord_to_physic_coord(np.array([float(x_idx), float(y_idx), float(z_idx)]))

        vs = viewer.view_state
        vs.camera.target_center = phys_coord
        vs.update_crosshair_from_phys(phys_coord)

        base_id = getattr(viewer, "image_id", None)
        if base_id and hasattr(self._api, "propagate_sync"):
            self._api.propagate_sync(base_id)

        self._api.request_refresh()
        if hasattr(self._api, "update_sidebar_crosshair"):
            self._api.update_sidebar_crosshair(viewer)

    def on_image_loaded(self, image_id: str) -> None:
        pass

    def on_image_removed(self, image_id: str) -> None:
        pass

    def serialize_image_state(self, image_id: str, context: str = "history") -> dict:
        return {}

    def restore_image_state(self, image_id: str, data: dict, context: str = "history") -> None:
        pass

    def save_settings(self, api: PluginAPI) -> None:
        pass

    def load_settings(self, api: PluginAPI) -> None:
        pass

    def destroy(self) -> None:
        pass
