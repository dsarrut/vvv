from typing import Optional
from vvv.plugins.plugin_api import PluginAPI, PluginTagMixin


class LandmarkPluginController(PluginTagMixin):
    """Controller for 3D landmarks plugin."""

    def __init__(self, plugin_id: str):
        self._plugin_id = plugin_id
        self._api: Optional[PluginAPI] = None
        self._ui = None
        self.landmark_filters: dict[str, str] = {}

    def bind(self, api: PluginAPI) -> None:
        self._api = api

    def bind_ui(self, ui) -> None:
        self._ui = ui

    def update(self, api: PluginAPI) -> None:
        if self._ui:
            self._ui.update_ui(api)

    def on_image_loaded(self, image_id: str) -> None:
        pass

    def on_image_removed(self, image_id: str) -> None:
        self.landmark_filters.pop(image_id, None)

    def serialize_image_state(self, image_id: str, context: str = "history") -> dict:
        return {}

    def restore_image_state(
        self, image_id: str, data: dict, context: str = "history"
    ) -> None:
        pass

    def save_settings(self, api: PluginAPI) -> None:
        pass

    def load_settings(self, api: PluginAPI) -> None:
        pass

    def destroy(self) -> None:
        pass

    # --- Callback Stubs (Unwired for Step 1 UI Shell) ---

    def on_btn_add_clicked(self, sender, app_data, user_data) -> None:
        pass

    def on_btn_load_clicked(self, sender, app_data, user_data) -> None:
        pass

    def on_btn_save_clicked(self, sender, app_data, user_data) -> None:
        pass

    def on_btn_snap_all_clicked(self, sender, app_data, user_data) -> None:
        pass

    def on_btn_clear_all_clicked(self, sender, app_data, user_data) -> None:
        pass

    def on_filter_changed(self, filter_text: str) -> None:
        pass

    def on_clear_filter_clicked(self) -> None:
        pass

    def on_batch_color_clicked(self, sender, app_data, user_data) -> None:
        pass

    def on_batch_show_clicked(self, sender, app_data, user_data) -> None:
        pass

    def on_batch_hide_clicked(self, sender, app_data, user_data) -> None:
        pass

    def on_batch_delete_clicked(self, sender, app_data, user_data) -> None:
        pass
