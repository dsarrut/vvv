from vvv.plugins.plugin_api import PluginTagMixin


class DicomPluginController(PluginTagMixin):
    def __init__(self, plugin_id: str):
        self._plugin_id = plugin_id
        self._ui = None
        self.api = None

    def bind_ui(self, ui) -> None:
        self._ui = ui

    def bind(self, api) -> None:
        self.api = api

    def update(self, api) -> None:
        pass

    def on_image_loaded(self, image_id: str) -> None:
        pass

    def on_image_removed(self, image_id: str) -> None:
        pass

    def serialize_image_state(self, image_id: str) -> dict:
        return {}

    def restore_image_state(self, image_id: str, data: dict) -> None:
        pass

    def save_settings(self, api) -> None:
        pass

    def load_settings(self, api) -> None:
        pass

    def destroy(self) -> None:
        pass
