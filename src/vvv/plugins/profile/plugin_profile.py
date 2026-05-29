from vvv.plugins.plugin_api import PluginAPI, PluginProtocol
from .ui_profile import ProfilePluginUI
from .control_profile import ProfilePluginController


class ProfilePlugin(PluginProtocol):
    plugin_id = "profile_plugin"
    label = "Profiles"
    description = "Interactive Intensity Profiles"
    order = 20

    def __init__(self):
        self._controller = ProfilePluginController(self.plugin_id)
        self._ui = ProfilePluginUI(self.plugin_id, self._controller)
        self._controller.bind_ui(self._ui)

    def create_ui(self, parent, api: PluginAPI) -> None:
        self._controller.bind(api)
        self._ui.create_ui(parent, api)

    def update(self, api: PluginAPI) -> None:
        self._controller.update(api)

    def on_image_loaded(self, image_id: str) -> None:
        self._controller.on_image_loaded(image_id)

    def on_image_removed(self, image_id: str) -> None:
        self._controller.on_image_removed(image_id)

    def serialize_image_state(self, image_id: str, context: str = "history") -> dict:
        return self._controller.serialize_image_state(image_id, context=context)

    def restore_image_state(self, image_id: str, data: dict, context: str = "history") -> None:
        self._controller.restore_image_state(image_id, data, context=context)

    def save_settings(self, api: PluginAPI) -> None:
        self._controller.save_settings(api)

    def load_settings(self, api: PluginAPI) -> None:
        self._controller.load_settings(api)

    def tick(self) -> None:
        self._controller.tick()

    def destroy(self) -> None:
        self._controller.destroy()
