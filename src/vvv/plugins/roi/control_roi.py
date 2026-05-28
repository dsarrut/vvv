from typing import Optional, Any
from vvv.plugins.plugin_api import PluginAPI, PluginTagMixin


class RoiPluginController(PluginTagMixin):
    def __init__(self, plugin_id: str):
        self._plugin_id = plugin_id
        self.api: Optional[PluginAPI] = None
        self.ui = None

        # State Persistence (similar to native RoiUI)
        self.active_roi_id = None
        self.roi_filters = {}
        self.roi_sort_orders = {}

    def bind(self, api: PluginAPI) -> None:
        self.api = api

    def bind_ui(self, ui) -> None:
        self.ui = ui

    def update(self, api: PluginAPI) -> None:
        # Reactive Update: Rebuild lists when model changes/is dirty
        if api.is_dirty and self.ui:
            self.ui.refresh_rois_ui()

    def on_image_loaded(self, image_id: str) -> None:
        if self.ui:
            self.ui.refresh_rois_ui()

    def on_image_removed(self, image_id: str) -> None:
        if self.active_roi_id == image_id:
            self.active_roi_id = None
        if self.ui:
            self.ui.refresh_rois_ui()

    def serialize_image_state(self, image_id: str) -> dict:
        return {}

    def restore_image_state(self, image_id: str, data: dict) -> None:
        pass

    def save_settings(self, api: PluginAPI) -> None:
        pass

    def load_settings(self, api: PluginAPI) -> None:
        pass

    def destroy(self) -> None:
        pass

    # --- Actions called from UI ---

    def on_roi_filter_changed(self, filter_text: str) -> None:
        assert self.api is not None
        viewer = self.api.get_active_viewer()
        if viewer and viewer.image_id:
            self.roi_filters[viewer.image_id] = filter_text.lower() if filter_text else ""
            if self.ui:
                self.ui.refresh_rois_ui()

    def on_clear_roi_filter(self) -> None:
        assert self.api is not None
        viewer = self.api.get_active_viewer()
        if viewer and viewer.image_id:
            self.roi_filters[viewer.image_id] = ""
            if self.ui:
                self.ui.refresh_rois_ui()

    def on_sort_rois(self) -> None:
        assert self.api is not None
        viewer = self.api.get_active_viewer()
        if not viewer or not viewer.image_id:
            return
        vs_id = viewer.image_id
        current = self.roi_sort_orders.get(vs_id, 0)
        if current == 0:
            self.roi_sort_orders[vs_id] = 1
        elif current == 1:
            self.roi_sort_orders[vs_id] = -1
        else:
            self.roi_sort_orders[vs_id] = 0
        if self.ui:
            self.ui.refresh_rois_ui()

    def on_roi_selected(self, roi_id: str) -> None:
        self.active_roi_id = roi_id
        if self.ui:
            self.ui.refresh_rois_ui()
