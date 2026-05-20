import dearpygui.dearpygui as dpg
from vvv.ui.ui_components import build_section_title

class TestDebugPlugin:
    def __init__(self):
        self.plugin_id = "test_debug_plugin"
        self.label = "DEBUG"

    def create_ui(self, parent, gui):
        """Creates the static UI skeleton for the test plugin."""
        cfg_c = gui.ui_cfg["colors"]

        header_color = cfg_c["text_header"]
        dim_color = cfg_c["text_dim"]
        active_color = cfg_c["text_active"]

        # If parent is None or 0, DPG adds it to the current container stack
        with dpg.group(parent=parent or 0, tag=self.plugin_id):
            dim_color = gui.ui_cfg["colors"].get("text_dim", [150, 150, 150])
            
            build_section_title(self.label, color=header_color)

            with dpg.group(horizontal=True):
                dpg.add_text("Active Images:", color=dim_color)
                dpg.add_text("---", tag=f"{self.plugin_id}_images", color=active_color)

            with dpg.group(horizontal=True):
                dpg.add_text("Crosshair (W):", color=dim_color)
                dpg.add_text("X: 0.0, Y: 0.0, Z: 0.0", tag=f"{self.plugin_id}_coords")

            with dpg.group(horizontal=True):
                dpg.add_text("Mouse Tracker:", color=dim_color)
                dpg.add_text("Px: 0, Py: 0", tag=f"{self.plugin_id}_mouse")

            dpg.add_spacer(height=5)
            dpg.add_separator()

    def update(self, api):
        """Step 4: Update values from the PluginAPI."""
        img_name = api.get_active_image_name()
        coords = api.get_crosshair_world()
        mouse = api.get_mouse_position()

        dpg.set_value(f"{self.plugin_id}_images", img_name)
        dpg.set_value(f"{self.plugin_id}_coords", f"X: {coords[0]:.1f}, Y: {coords[1]:.1f}, Z: {coords[2]:.1f}")
        dpg.set_value(f"{self.plugin_id}_mouse", f"Px: {int(mouse[0])}, Py: {int(mouse[1])}")