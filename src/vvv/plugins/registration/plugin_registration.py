from vvv.plugins.plugin_api import PluginAPI, PluginProtocol
from .ui_registration import RegistrationPluginUI
from .control_registration import RegistrationPluginController


class RegistrationPlugin(PluginProtocol):
    plugin_id = "registration_plugin"
    label = "Transform"
    description = "Transform tools for image alignment"
    order = 40

    def __init__(self):
        self._controller = RegistrationPluginController(self.plugin_id)
        self._ui = RegistrationPluginUI(self.plugin_id, self._controller)
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

    def serialize_image_state(self, image_id: str) -> dict:
        return self._controller.serialize_image_state(image_id)

    def restore_image_state(self, image_id: str, data: dict) -> None:
        self._controller.restore_image_state(image_id, data)

    def save_settings(self, api: PluginAPI) -> None:
        self._controller.save_settings(api)

    def load_settings(self, api: PluginAPI) -> None:
        self._controller.load_settings(api)

    def destroy(self) -> None:
        self._controller.destroy()
