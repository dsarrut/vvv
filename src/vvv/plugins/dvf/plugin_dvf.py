from vvv.plugins.plugin_api import PluginAPI
from .ui_dvf import DvfUI
from .control_dvf import DvfController


class DvfPlugin:
    plugin_id = "dvf"
    label = "DVF"
    description = "Displacement Vector Fields visualization."
    order = 1000

    def __init__(self):
        self._controller = DvfController(self.plugin_id)
        self._ui = DvfUI(self.plugin_id, self._controller)

    def create_ui(self, parent, api: PluginAPI) -> None:
        self._controller.bind(api)
        self._ui.create_ui(parent, api)

    def update(self, api: PluginAPI) -> None:
        self._controller.update(api)

    def on_image_loaded(self, image_id: str) -> None:
        pass

    def on_image_removed(self, image_id: str) -> None:
        self._controller.on_image_removed(image_id)

    def save_settings(self, api: PluginAPI) -> None:
        self._controller.save_settings(api)

    def load_settings(self, api: PluginAPI) -> None:
        self._controller.load_settings(api)

    def destroy(self) -> None:
        pass
