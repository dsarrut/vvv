from typing import Optional, TYPE_CHECKING, Tuple, Any
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

    def get_dose_status(self) -> Tuple[bool, Any, bool, Optional[str]]:
        """
        Evaluates the active viewer to determine if dose analysis is active.
        Returns:
            (is_active, target_volume, is_overlay, unit_string)
        Priority:
            1. If fused overlay has a Gy-compatible unit -> targets overlay.
            2. If base image has a Gy-compatible unit -> targets base.
            3. Neither has Gy -> returns (False, fallback_vol, is_overlay, fallback_unit).
        """
        if not self._api:
            return False, None, False, None

        viewer = self._api.get_active_viewer()
        if not viewer or not viewer.volume:
            return False, None, False, None

        base_vol = viewer.volume
        base_unit = getattr(base_vol, "unit", None)
        base_unit_str = str(base_unit).strip() if base_unit else None

        # Check fused overlay first
        if viewer.view_state and viewer.view_state.display.overlay:
            ov_id = viewer.view_state.display.overlay.image_id
            if ov_id:
                ov_vol = self._api.get_volumes().get(ov_id)
                if ov_vol:
                    ov_unit = getattr(ov_vol, "unit", None)
                    ov_unit_str = str(ov_unit).strip() if ov_unit else None
                    if ov_unit_str and ov_unit_str.lower() in DOSE_UNITS:
                        return True, ov_vol, True, ov_unit_str

        # Check base image
        if base_unit_str and base_unit_str.lower() in DOSE_UNITS:
            return True, base_vol, False, base_unit_str

        # If neither is Gy, return default target (overlay if present, else base) for enable action
        if viewer.view_state and viewer.view_state.display.overlay:
            ov_id = viewer.view_state.display.overlay.image_id
            if ov_id:
                ov_vol = self._api.get_volumes().get(ov_id)
                if ov_vol:
                    ov_unit = getattr(ov_vol, "unit", None)
                    return False, ov_vol, True, str(ov_unit) if ov_unit else None

        return False, base_vol, False, base_unit_str

    def on_enable_clicked(self, sender, app_data, user_data) -> None:
        """
        Sets unit to 'Gy' on the target volume (overlay if present, otherwise base).
        Updates GUI legends, geometry flags, and notifies the application.
        """
        if not self._api:
            return

        viewer = self._api.get_active_viewer()
        if not viewer or not viewer.volume:
            return

        # Prioritize overlay if loaded, otherwise base
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

            # Mark all viewers dirty to redraw legends and refresh UI
            for v in self._api.get_viewers().values():
                v.is_geometry_dirty = True
                v.drawer._last_leg_state = None
                if getattr(v, "show_legend", False):
                    v.drawer.draw_legend()

            self._api.request_refresh()

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

