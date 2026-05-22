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

    def destroy(self) -> None:
        pass
