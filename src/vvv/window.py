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
        # Get current window dimensions
        window_width = dpg.get_item_width("PrimaryWindow")
        window_height = dpg.get_item_height("PrimaryWindow")
        if not window_width or not window_height:
            return  # Safety

        # Constants
        margin_height = 30
        margin_width = 30
        side_panel_width = self.side_panel_width
        available_width = window_width - side_panel_width - margin_width
        available_height = window_height - margin_height

        # Calculate the sizes for each quadrant (2x2)
        quad_w = available_width // 2
        quad_h = available_height // 2

        # Calculate the total height used by the 2 rows of viewers
        total_viewers_height = quad_h * 2

        if dpg.does_item_exist("viewers_container"):
            dpg.set_item_width("viewers_container", available_width)
            dpg.set_item_height("viewers_container", total_viewers_height)
            # 10 and 22 are "magic" values such that the panel does not have scrollbars
            # and the bottom viewers are aligned with the bottom left panel
            dpg.set_item_pos("viewers_container", [side_panel_width + 10, 22])

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
            self.drag_viewer = self.get_hovered_viewer()
            if self.drag_viewer and self.drag_viewer.orientation != "Histogram":
                self.context_viewer = self.drag_viewer

                # If no modifiers, update crosshair position
                if not dpg.is_key_down(dpg.mvKey_LShift) and not dpg.is_key_down(dpg.mvKey_LControl):
                    # This updates the ImageModel data
                    #self.drag_viewer.sync_other_views()
                    # This propagates that data to other ImageModels in the group
                    self.controller.propagate_sync(self.drag_viewer.image_id)

    def on_global_click_initial(self, button):
        if button == dpg.mvMouseButton_Left:
            # Set the drag viewer to lock interaction to this quadrant
            self.drag_viewer = self.get_hovered_viewer()
            if self.drag_viewer:
                if self.drag_viewer.orientation == "Histogram":
                    return
                self.drag_viewer.update_overlay()
                self.drag_viewer.update_sidebar_info()
                self.drag_viewer.update_sidebar_crosshair()
                self.context_viewer = self.drag_viewer

                # Sync other views if no modifiers are held
                if not dpg.is_key_down(dpg.mvKey_LShift) and not dpg.is_key_down(dpg.mvKey_LControl):
                    #self.drag_viewer.sync_other_views()
                    self.controller.propagate_sync(self.drag_viewer.image_id)

    def on_global_drag(self, data):
        # Use the locked active_viewer instead of the hovered one
        if self.drag_viewer:
            self.drag_viewer.on_drag(data)

    def on_global_release(self):
        if self.drag_viewer:
            self.drag_viewer.update_sidebar_crosshair()
            self.drag_viewer.update_sidebar_info()

        # Reset the drag lock
        for v in self.controller.viewers.values():
            v.last_dx, v.last_dy = 0, 0
        self.drag_viewer = None

    def highlight_active_image_in_list(self, active_img_id):
        """Binds a highlight theme to the text label in the sidebar matching the image."""
        for img_id in self.controller.images.keys():
            label_tag = f"img_label_{img_id}"
            if dpg.does_item_exist(label_tag):
                if img_id == active_img_id:
                    dpg.bind_item_theme(label_tag, "active_image_list_theme")
                else:
                    dpg.bind_item_theme(label_tag, "")  # Reset to default

    def update_overlays(self):
        """Updates sidebar context on hover and refreshes on-image overlays."""
        hover_viewer = self.get_hovered_viewer()

        # Context Switch logic based on ViewState
        if hover_viewer and hover_viewer != self.context_viewer and not self.drag_viewer:
            # Remove highlight from the old viewer
            if self.context_viewer:
                dpg.bind_item_theme(f"win_{self.context_viewer.tag}", "viewer_theme")

            # Add highlight to the new viewer
            dpg.bind_item_theme(f"win_{hover_viewer.tag}", "active_viewer_theme")

            # Highlight the current image in the image list
            self.highlight_active_image_in_list(hover_viewer.image_id)

            # Update sidebar
            hover_viewer.update_sidebar_info()
            hover_viewer.update_sidebar_crosshair()
            self.context_viewer = hover_viewer

        # Always refresh the on-image text/crosshairs for all viewers
        for viewer in self.controller.viewers.values():
            viewer.update_overlay()
