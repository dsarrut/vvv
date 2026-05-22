import dearpygui.dearpygui as dpg
from vvv.plugins.plugin_api import PluginAPI


class IntensityController:
    def __init__(self, plugin_id: str):
        self._plugin_id = plugin_id
        self._api: PluginAPI
        self._ui = None

    def _t(self, name: str) -> str:
        return f"{self._plugin_id}_{name}"

    def bind(self, api: PluginAPI) -> None:
        self._api = api

    def bind_ui(self, ui) -> None:
        self._ui = ui

    def update(self, api: PluginAPI) -> None:
        # Update the active image title
        active_title = self._t("active_title")
        if dpg.does_item_exist(active_title):
            img_name = api.get_active_image_name()
            dpg.set_value(active_title, img_name)

    # --- Callbacks (Stubs) ---
    def on_preset_changed(self, sender, app_data, user_data):
        pass

    def on_ww_changed(self, sender, app_data, user_data):
        pass

    def on_wl_changed(self, sender, app_data, user_data):
        pass

    def on_colormap_changed(self, sender, app_data, user_data):
        pass

    def on_threshold_changed(self, sender, app_data, user_data):
        pass

    def on_threshold_toggle(self, sender, app_data, user_data):
        pass

    def on_hist_drag_lower(self, sender, app_data, user_data):
        pass

    def on_hist_drag_upper(self, sender, app_data, user_data):
        pass

    def on_hist_drag_level(self, sender, app_data, user_data):
        pass

    def on_hist_center(self, sender, app_data, user_data):
        pass

    def on_hist_bar_toggle(self, sender, app_data, user_data):
        pass

    def on_hist_log_toggle(self, sender, app_data, user_data):
        pass

    def on_hist_popup(self, sender, app_data, user_data):
        if self._ui and self._api:
            self._ui.create_popup_ui(self._api)

    def on_hist_xcenter_drag(self, sender, app_data, user_data):
        pass

    def on_hist_xwidth_drag(self, sender, app_data, user_data):
        pass

    def on_hist_ymax_drag(self, sender, app_data, user_data):
        pass

    def on_step_button_clicked(self, sender, app_data, user_data):
        pass

    def on_hist_popup_drag_lower(self, sender, app_data, user_data):
        pass

    def on_hist_popup_drag_upper(self, sender, app_data, user_data):
        pass

    def on_hist_popup_drag_level(self, sender, app_data, user_data):
        pass

    def on_hist_bins_drag(self, sender, app_data, user_data):
        pass
