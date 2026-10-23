from vvv.plugins.plugin_api import PluginAPI, PluginProtocol
from .ui_dose import DosePluginUI
from .control_dose import DosePluginController


class DosePlugin(PluginProtocol):
    plugin_id = "dose_plugin"
    label = "Dose"
    description = "Radiation dose inspection, scaling, isodose, and DVH tools."
    order = 80

    def __init__(self):
        self._controller = DosePluginController(self.plugin_id)
        self._ui = DosePluginUI(self.plugin_id, self._controller)
        self._controller.bind_ui(self._ui)

    def create_ui(self, parent, api: PluginAPI) -> None:
        self._controller.bind(api)
        self._ui.create_ui(parent, api)

    def is_applicable(self, api: PluginAPI) -> bool:
        """A dose image (Gy unit) is the base or fused image of the active viewer."""
        return bool(self._controller.get_dose_target_info()[0])

    def update(self, api: PluginAPI) -> None:
        self._controller.update(api)

    def on_image_loaded(self, image_id: str) -> None:
        self._controller.on_image_loaded(image_id)

    def on_image_removed(self, image_id: str) -> None:
        self._controller.on_image_removed(image_id)

    def serialize_image_state(self, image_id: str, context: str = "history") -> dict:
        return self._controller.serialize_image_state(image_id, context=context)

    def restore_image_state(
        self, image_id: str, data: dict, context: str = "history"
    ) -> None:
        self._controller.restore_image_state(image_id, data, context=context)

    def save_settings(self, api: PluginAPI) -> None:
        self._controller.save_settings(api)

    def load_settings(self, api: PluginAPI) -> None:
        self._controller.load_settings(api)

    def destroy(self) -> None:
        self._controller.destroy()

