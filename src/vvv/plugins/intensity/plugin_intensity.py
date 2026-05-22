from vvv.plugins.plugin_api import PluginAPI
from .ui_intensity import IntensityUI
from .control_intensity import IntensityController


class IntensityPlugin:
    plugin_id = "intensity_plugin"
    label = "Intensity"
    description = "Adjust window/level, colormaps, thresholds, and view the image histogram."
    order = 10

    def __init__(self):
        self._controller = IntensityController(self.plugin_id)
        self._ui = IntensityUI(self.plugin_id, self._controller)
        self._controller.bind_ui(self._ui)

    def create_ui(self, parent, api: PluginAPI) -> None:
        self._controller.bind(api)
        self._ui.create_ui(parent, api)

    def update(self, api: PluginAPI) -> None:
        self._controller.update(api)

    def on_image_removed(self, image_id: str) -> None:
        self._controller.on_image_removed(image_id)

    def save_settings(self, api: PluginAPI) -> None:
        self._controller.save_settings(api)

    def load_settings(self, api: PluginAPI) -> None:
        self._controller.load_settings(api)

    def destroy(self) -> None:
        self._controller.destroy()
