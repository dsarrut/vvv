import dearpygui.dearpygui as dpg


class MainWindow:

    def __init__(self, controller):
        self.controller = controller
        # Locked during click/drag
        self.drag_viewer = None
        # The one showing in the sidebar
        self.context_viewer = None
        self.side_panel_width = 300

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
        #side_panel_width = 250
        available_width = window_width - self.side_panel_width - 25
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
        viewer = self.get_hovered_viewer()
        if not viewer:
            return

        # pass the pressed key to the current viewer
        viewer.on_key_press(key)

    def on_global_click(self, button):
        if button == dpg.mvMouseButton_Left:
            # Set the drag viewer to lock interaction to this quadrant
            self.drag_viewer = self.get_hovered_viewer()
            if self.drag_viewer and not dpg.is_key_down(dpg.mvKey_LShift) and not dpg.is_key_down(dpg.mvKey_LControl):
                # self.drag_viewer.sync_other_views()
                # 2. Force an immediate coordinate calculation for the click position
                self.drag_viewer.update_overlay()

                # 3. Update the sidebar immediately on click
                self.drag_viewer.update_sidebar_crosshair()
                self.drag_viewer.update_sidebar_info()
                self.context_viewer = self.drag_viewer

                # 4. Sync other views if no modifiers are held
                if not dpg.is_key_down(dpg.mvKey_LShift) and not dpg.is_key_down(dpg.mvKey_LControl):
                    self.drag_viewer.sync_other_views()

    def on_global_drag(self, data):
        # Use the locked active_viewer instead of the hovered one
        if self.drag_viewer:
            self.drag_viewer.on_drag(data)

    def on_global_release(self):
        if self.drag_viewer:
            # update the crosshair coord for other viewers of the same image
            for v in self.controller.viewers.values():
                if v.current_image_id == self.drag_viewer.current_image_id:
                    v.update_crosshair_position(self.drag_viewer)
            # Finalize sidebar data when the user lets go
            self.drag_viewer.update_sidebar_crosshair()
            self.drag_viewer.update_sidebar_info()

        # Reset the drag lock
        for v in self.controller.viewers.values():
            v.last_dx, v.last_dy = 0, 0
        self.drag_viewer = None

    def update_overlays(self):
        """Updates sidebar context on hover and refreshes on-image overlays."""
        hover_viewer = self.get_hovered_viewer()

        # Context Switch: Mouse moved to a different quadrant while not dragging
        if hover_viewer and hover_viewer != self.context_viewer and not self.drag_viewer:
            # Restore the specific metadata for this image
            hover_viewer.update_sidebar_info()

            # Restore the LAST KNOWN crosshair position/value for this specific viewer
            hover_viewer.update_sidebar_crosshair()

            self.context_viewer = hover_viewer

        # Always refresh the on-image text/crosshairs for all viewers
        for viewer in self.controller.viewers.values():
            viewer.update_overlay()
