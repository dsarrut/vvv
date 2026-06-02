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

        self._last_image_id = None
        self._last_roi_ids = set()
        self._scroll_to_active = False

    def bind(self, api: PluginAPI) -> None:
        self.api = api

    def bind_ui(self, ui) -> None:
        self.ui = ui

    def update(self, api: PluginAPI) -> None:
        if not self.ui:
            return
        viewer = api.get_active_viewer()
        image_id = viewer.image_id if (viewer and viewer.image_id) else None
        roi_ids = set(viewer.view_state.rois.keys()) if (viewer and viewer.view_state and viewer.view_state.rois) else set()

        if api._controller.ui_needs_refresh or image_id != self._last_image_id or roi_ids != self._last_roi_ids:
            self._last_image_id = image_id
            self._last_roi_ids = roi_ids
            self.ui.refresh_rois_ui()

    def on_image_loaded(self, image_id: str) -> None:
        if self.ui:
            self.ui.refresh_rois_ui()

    def on_image_removed(self, image_id: str) -> None:
        if self.active_roi_id == image_id:
            self.active_roi_id = None
        self.roi_filters.pop(image_id, None)
        self.roi_sort_orders.pop(image_id, None)
        if self.ui:
            self.ui.close_rtstruct_modal()
            self.ui.close_all_stats_windows()
            self.ui.refresh_rois_ui()

    def serialize_image_state(self, image_id: str, context: str = "history") -> dict:
        return {
            "roi_filter": self.roi_filters.get(image_id, ""),
            "roi_sort_order": self.roi_sort_orders.get(image_id, 0),
        }

    def restore_image_state(self, image_id: str, data: dict, context: str = "history") -> None:
        if "roi_filter" in data:
            self.roi_filters[image_id] = data["roi_filter"]
        if "roi_sort_order" in data:
            self.roi_sort_orders[image_id] = data["roi_sort_order"]

    def save_settings(self, api: PluginAPI) -> None:
        if self.ui:
            self.ui.save_settings(api)

    def load_settings(self, api: PluginAPI) -> None:
        if self.ui:
            self.ui.load_settings(api)

    def destroy(self) -> None:
        if self.ui:
            self.ui.close_rtstruct_modal()
            self.ui.close_all_stats_windows()

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

    def move_roi_selection(self, delta: int) -> None:
        if not self.api:
            return
        viewer = self.api.get_active_viewer()
        if not viewer or not viewer.view_state or not viewer.view_state.rois:
            return

        vs_id = viewer.image_id
        filter_text = self.roi_filters.get(vs_id, "")
        sort_order = self.roi_sort_orders.get(vs_id, 0)

        roi_items = list(viewer.view_state.rois.items())
        if sort_order == 1:
            roi_items.sort(key=lambda x: x[1].name.lower())
        elif sort_order == -1:
            roi_items.sort(key=lambda x: x[1].name.lower(), reverse=True)

        # Filter the items
        filtered_roi_ids = []
        for roi_id, roi in roi_items:
            if filter_text and filter_text not in roi.name.lower():
                continue
            filtered_roi_ids.append(roi_id)

        if not filtered_roi_ids:
            return

        try:
            current_idx = filtered_roi_ids.index(self.active_roi_id)
        except ValueError:
            current_idx = -1

        if current_idx == -1:
            if delta > 0:
                new_idx = 0
            else:
                new_idx = len(filtered_roi_ids) - 1
        else:
            new_idx = current_idx + delta
            new_idx = max(0, min(new_idx, len(filtered_roi_ids) - 1))

        self._scroll_to_active = True
        self.on_roi_selected(filtered_roi_ids[new_idx])
