import dearpygui.dearpygui as dpg
import numpy as np
from vvv.ui.ui_components import build_section_title

class TestDebugPlugin:
    def __init__(self):
        self.plugin_id = "test_debug_plugin"
        self.label = "DEBUG"
        self._last_img_name = None
        self._last_coords = None
        self._last_mouse = None

    def create_ui(self, parent, gui):
        """Creates the static UI skeleton for the test plugin."""
        cfg_c = gui.ui_cfg["colors"]

        header_color = cfg_c["text_header"]

        # If parent is None or 0, DPG adds it to the current container stack
        with dpg.group(parent=parent or 0, tag=self.plugin_id):           
            build_section_title(self.label, color=header_color)

            with dpg.group(tag=f"{self.plugin_id}_fields"):
                gui.create_labeled_field("Active Images", f"{self.plugin_id}_images")
                gui.create_labeled_field("Crosshair (W)", f"{self.plugin_id}_coords")
                gui.create_labeled_field("Mouse Tracker", f"{self.plugin_id}_mouse")
            
            if dpg.does_item_exist("sleek_readonly_theme"):
                dpg.bind_item_theme(f"{self.plugin_id}_fields", "sleek_readonly_theme")

            dpg.add_spacer(height=5)
            dpg.add_separator()

    def update(self, api):
        """Step 4: Update values from the PluginAPI."""
        
        # 1. Check mouse position (high frequency, might not trip is_dirty)
        mouse = np.array(api.get_mouse_position())
        if self._last_mouse is None or not np.array_equal(mouse, self._last_mouse):
            dpg.set_value(f"{self.plugin_id}_mouse", f"Px: {int(mouse[0])}, Py: {int(mouse[1])}")
            self._last_mouse = mouse

        # 2. Early exit if the rest of the viewer state hasn't changed
        if not api.is_dirty:
            return

        # Image Name
        img_name = api.get_active_image_name()
        if img_name != self._last_img_name:
            dpg.set_value(f"{self.plugin_id}_images", img_name)
            self._last_img_name = img_name

        # Crosshair Coordinates (using numpy for robust float comparison)
        coords = np.array(api.get_crosshair_world())
        if self._last_coords is None or not np.allclose(coords, self._last_coords, atol=1e-3):
            dpg.set_value(f"{self.plugin_id}_coords", f"X: {coords[0]:.1f}, Y: {coords[1]:.1f}, Z: {coords[2]:.1f}")
            self._last_coords = coords