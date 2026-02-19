import dearpygui.dearpygui as dpg
import numpy as np


def create_gui(controller):
    # 1. Menubar
    with dpg.viewport_menu_bar():
        with dpg.menu(label="File"):
            dpg.add_menu_item(label="Open Image...")
            dpg.add_menu_item(label="Exit")
        with dpg.menu(label="Link"):
            dpg.add_menu_item(label="Link All", callback=lambda: controller.link_all())

        # Define a theme for the viewers
        with dpg.theme() as viewer_theme:
            with dpg.theme_component(dpg.mvAll):
                # Change the background of the child window
                dpg.add_theme_color(dpg.mvThemeCol_ChildBg, [0, 0, 0], category=dpg.mvThemeCat_Core)
                # Change border color
                dpg.add_theme_color(dpg.mvThemeCol_Border, [50, 50, 50], category=dpg.mvThemeCat_Core)

        # We add a resize_callback to the primary window
        with dpg.window(tag="PrimaryWindow", on_close=controller.main_windows.cleanup):
            with dpg.item_handler_registry(tag="window_resize_handler"):
                dpg.add_item_resize_handler(callback=lambda: controller.main_windows.on_window_resize())
            dpg.bind_item_handler_registry("PrimaryWindow", "window_resize_handler")

            with dpg.group(horizontal=True):
                # 2. LEFT PANEL: Fixed width
                with dpg.child_window(width=250, tag="side_panel"):
                    dpg.add_text("Loaded Images", color=[0, 255, 127])
                    dpg.add_listbox(tag="ui_image_list", items=[], num_items=10)
                    # ...

                # 3. RIGHT PANEL: This group will contain the 4 viewers
                with dpg.group(tag="viewers_container"):
                    with dpg.group(horizontal=True):
                        create_viewer_widget("V1", controller)
                        create_viewer_widget("V2", controller)
                    with dpg.group(horizontal=True):
                        create_viewer_widget("V3", controller)
                        create_viewer_widget("V4", controller)

        # Bind the theme to all viewer windows
        for tag in ["V1", "V2", "V3", "V4"]:
            dpg.bind_item_theme(f"win_{tag}", viewer_theme)

    # Add this at the end of create_gui before viewport setup:
    with dpg.handler_registry():
        dpg.add_mouse_wheel_handler(callback=lambda s, d: controller.main_windows.on_global_scroll(d))
        dpg.add_mouse_drag_handler(callback=lambda s, d: controller.main_windows.on_global_drag(d))
        dpg.add_mouse_release_handler(callback=lambda: controller.main_windows.on_global_release())
        dpg.add_key_press_handler(callback=lambda s, d: controller.main_windows.on_key_press(d))


def create_viewer_widget(tag, controller):
    # We use no_scrollbar to keep the view clean
    with dpg.child_window(tag=f"win_{tag}",
                          border=True,
                          no_scrollbar=True,
                          no_scroll_with_mouse=True):
        # Overlay for coordinates and HU value # FIXME to change
        dpg.add_text("", tag=f"overlay_{tag}", color=[255, 255, 0], pos=[0, 0])
        dpg.add_image(f"tex_{tag}", tag=f"img_{tag}", pos=[0, 0])


class MainWindow:

    def __init__(self, controller):
        self.controller = controller

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

        # 2. Subtract the sidebar and margins
        side_panel_width = 250
        available_width = window_width - side_panel_width - 40
        available_height = window_height - 80

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

    def on_global_drag(self, data):
        viewer = self.get_hovered_viewer()
        if viewer:
            viewer.on_drag(data)

    def on_global_release(self):
        for v in self.controller.viewers.values():
            v.last_dx, v.last_dy = 0, 0

    def on_key_press(self, key):
        viewer = self.get_hovered_viewer()
        if not viewer: return
        if key == dpg.mvKey_I:
            viewer.on_zoom("in")
        elif key == dpg.mvKey_O:
            viewer.on_zoom("out")
        elif key == dpg.mvKey_R:  # Bonus: Reset pan/zoom
            viewer.zoom = 1.0
            viewer.pan_offset = [0, 0]
            self.on_window_resize()

    def update_overlays(self):
        """Coordinate probe logic adjusted for Zoom/Pan."""
        mouse_pos = dpg.get_mouse_pos(local=False)
        viewer = self.get_hovered_viewer()

        if not viewer or viewer.current_image_id is None:
            for tag in self.controller.viewers:
                dpg.set_value(f"overlay_{tag}", "")
            return

        img_tag = f"img_{viewer.tag}"
        win_pos = dpg.get_item_pos(f"win_{viewer.tag}")
        img_rel_pos = dpg.get_item_pos(img_tag)

        img_start_x = win_pos[0] + img_rel_pos[0]
        img_start_y = win_pos[1] + img_rel_pos[1]

        rel_mouse_x = mouse_pos[0] - img_start_x
        rel_mouse_y = mouse_pos[1] - img_start_y

        disp_w = dpg.get_item_width(img_tag)
        disp_h = dpg.get_item_height(img_tag)

        img_model = self.controller.images[viewer.current_image_id]
        real_h, real_w = img_model.data.shape[1], img_model.data.shape[2]

        vox_x = int((rel_mouse_x / disp_w) * real_w)
        vox_y = int((rel_mouse_y / disp_h) * real_h)

        if 0 <= vox_x < real_w and 0 <= vox_y < real_h:
            value = img_model.data[viewer.slice_idx, vox_y, vox_x]
            info = (f"X: {vox_x}, Y: {vox_y}, Z: {viewer.slice_idx}\n"
                    f"Val: {int(value)} HU\n"
                    f"WW: {int(img_model.ww)} WL: {int(img_model.wl)}\n"
                    f"Zoom: {viewer.zoom:.2f}x")
            dpg.set_value(f"overlay_{viewer.tag}", info)
        else:
            dpg.set_value(f"overlay_{viewer.tag}", "")


class SliceViewer:
    def __init__(self, tag_id, controller):
        self.tag = tag_id
        self.controller = controller
        self.current_image_id = None
        self.slice_idx = 0
        self.ww, self.wl = 400, 40
        self.texture_tag = f"tex_{tag_id}"
        self.image_tag = f"img_{tag_id}"
        # GUI options
        self.margin_left = 0
        self.margin_top = 0
        # used during mouse drag
        self.last_dy = 0
        self.last_dx = 0
        # Zoom and Pan states
        self.zoom = 1.0
        self.pan_offset = [0, 0]  # [x, y] in screen pixels

        # Initialize a default small texture; will be recreated on image load
        with dpg.texture_registry():
            dpg.add_dynamic_texture(width=1, height=1,
                                    default_value=np.zeros(4),
                                    tag=self.texture_tag)

    def set_image(self, img_id):
        self.current_image_id = img_id
        img = self.controller.images[img_id]

        # Recreate texture with correct dimensions for the real image size
        dpg.delete_item(self.texture_tag)
        with dpg.texture_registry():
            # Get dimensions from the ImageModel data (Z, Y, X) -> X=width, Y=height
            h, w = img.data.shape[1], img.data.shape[2]
            dpg.add_dynamic_texture(width=w, height=h,
                                    default_value=np.zeros(w * h * 4),
                                    tag=self.texture_tag)

        self.slice_idx = img.data.shape[0] // 2
        self.update_render()

    def update_render(self):
        if self.current_image_id is None:
            return

        img_model = self.controller.images[self.current_image_id]
        rgba_data = img_model.get_slice_rgba(self.slice_idx)

        # Update the texture data
        dpg.set_value(self.texture_tag, rgba_data)

    def on_scroll(self, delta):
        """Called by MainWindow when this viewer is hovered during a scroll."""
        if self.current_image_id is None: return

        increment = 1 if delta > 0 else -1
        img_model = self.controller.images[self.current_image_id]

        # Update slice index with bounds checking
        max_slices = img_model.data.shape[0] - 1
        self.slice_idx = np.clip(self.slice_idx + increment, 0, max_slices)

        self.update_render()

    def on_drag(self, data):
        if self.current_image_id is None: return

        step_x, step_y = data[1] - self.last_dx, data[2] - self.last_dy
        self.last_dx, self.last_dy = data[1], data[2]

        is_control = dpg.is_key_down(dpg.mvKey_LControl) or dpg.is_key_down(dpg.mvKey_RControl)
        is_shift = dpg.is_key_down(dpg.mvKey_LShift) or dpg.is_key_down(dpg.mvKey_RShift)

        if is_control and dpg.is_mouse_button_down(dpg.mvMouseButton_Left):
            self.pan_offset[0] += step_x
            self.pan_offset[1] += step_y
            self.controller.main_windows.on_window_resize()
        elif is_shift and dpg.is_mouse_button_down(dpg.mvMouseButton_Left):
            img_model = self.controller.images[self.current_image_id]
            img_model.ww = max(1, img_model.ww + step_x * 2)
            img_model.wl -= step_y * 2
            self.controller.update_all_viewers_of_image(self.current_image_id)

    def on_zoom(self, direction):
        """Zoom in ('i') or out ('o')."""
        if direction == "in":
            self.zoom *= 1.1
        else:
            self.zoom /= 1.1
        self.zoom = np.clip(self.zoom, 0.1, 20.0)
        # Re-trigger resize to update display dimensions
        self.controller.main_windows.on_window_resize()

    def resize(self, quad_w, quad_h):
        if not dpg.does_item_exist(f"win_{self.tag}"): return
        dpg.set_item_width(f"win_{self.tag}", quad_w)
        dpg.set_item_height(f"win_{self.tag}", quad_h)

        if self.current_image_id:
            img = self.controller.images[self.current_image_id]
            h, w = img.data.shape[1], img.data.shape[2]
            target_w, target_h = quad_w - self.margin_left, quad_h - self.margin_top
            #target_w, target_h = quad_w - 0, quad_h - 0

            # Base scale + User Zoom
            base_scale = min(target_w / w, target_h / h)
            final_scale = base_scale * self.zoom

            new_w, new_h = int(w * final_scale), int(h * final_scale)
            dpg.set_item_width(f"img_{self.tag}", new_w)
            dpg.set_item_height(f"img_{self.tag}", new_h)

            # Centering + Pan Offset
            dpg.set_item_pos(f"img_{self.tag}", [
                (target_w - new_w) // 2 + self.margin_left + self.pan_offset[0],
                (target_h - new_h) // 2 + self.margin_top + self.pan_offset[1]
            ])
