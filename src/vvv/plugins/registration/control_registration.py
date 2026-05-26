from typing import Optional
from vvv.plugins.plugin_api import PluginAPI, PluginTagMixin


class RegistrationPluginController(PluginTagMixin):
    """Controller for the registration plugin (UI Shell Phase)."""

    def __init__(self, plugin_id: str):
        self._plugin_id = plugin_id
        self._api: Optional[PluginAPI] = None
        self._ui = None

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

    # --- UI Callbacks (No-op for UI Shell Phase) ---

    def on_reg_load_clicked(self, sender, app_data, user_data):
        pass

    def on_reg_save_clicked(self, sender, app_data, user_data):
        pass

    def on_reg_save_as_clicked(self, sender, app_data, user_data):
        pass

    def on_reg_reload_clicked(self, sender, app_data, user_data):
        pass

    def on_reg_center_cor_clicked(self, sender, app_data, user_data):
        pass

    def on_reg_cor_to_crosshair_clicked(self, sender, app_data, user_data):
        pass

    def on_reg_step_changed(self, sender, app_data, user_data):
        pass

    def on_reg_step_button_clicked(self, sender, app_data, user_data):
        pass

    def on_reg_reset_clicked(self, sender, app_data, user_data):
        pass

    def on_reg_invert_clicked(self, sender, app_data, user_data):
        pass

    def on_reg_auto_resample_toggled(self, sender, app_data, user_data):
        pass

    def on_reg_resample_clicked(self, sender, app_data, user_data):
        pass

    def on_reg_manual_changed(self, sender, app_data, user_data):
        pass

    def on_reg_bake_clicked(self, sender, app_data, user_data):
        pass
