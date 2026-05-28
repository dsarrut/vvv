from typing import Optional
from vvv.plugins.plugin_api import PluginAPI, PluginTagMixin


class RoiPluginController(PluginTagMixin):
    def __init__(self, plugin_id: str):
        self._plugin_id = plugin_id
        self.api: Optional[PluginAPI] = None
        self.ui = None

    def bind(self, api: PluginAPI) -> None:
        self.api = api

    def bind_ui(self, ui) -> None:
        self.ui = ui

    def update(self, api: PluginAPI) -> None:
        pass

    def on_image_loaded(self, image_id: str) -> None:
        pass

    def on_image_removed(self, image_id: str) -> None:
        pass

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
