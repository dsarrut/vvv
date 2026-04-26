import dearpygui.dearpygui as dpg
from vvv.ui.ui_components import build_section_title
from vvv.utils import ViewMode


class ContoursUI:
    """Delegated UI handler for the Contours tab."""

    def __init__(self, gui, controller):
        self.gui = gui
        self.controller = controller

    @staticmethod
    def build_tab_contours(gui):
        cfg_c = gui.ui_cfg["colors"]
        with dpg.group(tag="tab_contours", show=False):
            build_section_title("Vector Engine", cfg_c["text_header"])

            dpg.add_checkbox(
                label="Show Contours",
                tag="check_show_contour",
                callback=gui.contours_ui.on_toggle_contour,
                default_value=True,
            )

    def refresh_contours_ui(self):
        pass

    def on_toggle_contour(self, sender, app_data, user_data):
        viewer = self.gui.context_viewer
        if viewer and viewer.view_state:
            viewer.view_state.camera.show_contour = app_data
            self.controller.ui_needs_refresh = True
