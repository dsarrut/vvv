import dearpygui.dearpygui as dpg

class MainWindow:

    def __init__(self, controller):
        self.controller = controller
        self.active_viewer = None

    def cleanup(self):
        dpg.stop_dearpygui()

    def get_hovered_viewer(self):
        """Finds which quadrant the mouse is currently over."""
        for tag, viewer in self.controller.viewers.items():
            if dpg.is_item_hovered(f"win_{tag}"):
                return viewer
        return None

    def on_window_resize(self):
        # 1. Get current window dimensions
        window_width = dpg.get_item_width("PrimaryWindow")
        window_height = dpg.get_item_height("PrimaryWindow")
        if not window_width or not window_height:
            return  # Safety

        # 2. Subtract the sidebar and margins
        side_panel_width = 250
        available_width = window_width - side_panel_width - 25
        available_height = window_height - 45  # Adjusted for menu bar

        # Resize the container child window
        if dpg.does_item_exist("viewers_container"):
            dpg.set_item_width("viewers_container", available_width)
            dpg.set_item_height("viewers_container", available_height)

        # 3. Calculate the sizes for each quadrant (2x2)
        quad_w = available_width // 2
        quad_h = available_height // 2

        # Resize all viewers
        for viewer in self.controller.viewers.values():
            viewer.resize(quad_w, quad_h)

    def on_global_scroll(self, delta):
        viewer = self.get_hovered_viewer()
        if viewer:
            viewer.on_scroll(delta)

    def on_key_press(self, key):
        if key == dpg.mvKey_L:
            # Toggle global state
            self.controller.interpolation_linear = not self.controller.interpolation_linear
            # Refresh all viewers
            for v in self.controller.viewers.values():
                v.update_render()
            return

        viewer = self.get_hovered_viewer()
        if not viewer:
            return

        # pass the pressed key to the current viewer
        viewer.on_key_press(key)

    def on_global_click(self, button):
        if button == dpg.mvMouseButton_Left:
            # Lock the viewer that was initially clicked
            self.active_viewer = self.get_hovered_viewer()
            if self.active_viewer and not dpg.is_key_down(dpg.mvKey_LShift) and not dpg.is_key_down(dpg.mvKey_LControl):
                self.active_viewer.sync_other_views()

    def on_global_drag(self, data):
        # Use the locked active_viewer instead of the hovered one
        if self.active_viewer:
            self.active_viewer.on_drag(data)

    def on_global_release(self):
        # Reset the lock and the drag deltas
        for v in self.controller.viewers.values():
            v.last_dx, v.last_dy = 0, 0
        self.active_viewer = None

    def update_overlays(self):
        """Delegates overlay calculation to each individual viewer."""
        for viewer in self.controller.viewers.values():
            viewer.update_overlay()

