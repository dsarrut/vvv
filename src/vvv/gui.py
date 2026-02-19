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

    # Add this at the end of create_gui before viewport setup:
    with dpg.handler_registry():
        dpg.add_mouse_wheel_handler(callback=lambda s, d: controller.main_windows.on_global_scroll(d))
        dpg.add_mouse_drag_handler(callback=lambda s, d: controller.main_windows.on_global_drag(d))
        dpg.add_mouse_release_handler(callback=lambda: controller.main_windows.on_global_release())


def create_viewer_widget(tag, controller):
    # We use no_scrollbar to keep the view clean
    with dpg.child_window(tag=f"win_{tag}", border=True, no_scrollbar=True):
        dpg.add_text(f"Viewer {tag}", tag=f"txt_{tag}")
        # Overlay for coordinates and HU value
        dpg.add_text("", tag=f"overlay_{tag}", color=[255, 255, 0], pos=[15, 60])
        dpg.add_image(f"tex_{tag}", tag=f"img_{tag}", pos=[10, 40])


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

        # 3. Calculate size for each quadrant (2x2)
        quad_w = available_width // 2
        quad_h = available_height // 2

        for tag, viewer in self.controller.viewers.items():
            if not dpg.does_item_exist(f"win_{tag}"):
                continue

            # Set the container size
            dpg.set_item_width(f"win_{tag}", quad_w)
            dpg.set_item_height(f"win_{tag}", quad_h)

            # 4. Aspect Ratio Calculation
            if viewer.current_image_id is not None:
                img = self.controller.images[viewer.current_image_id]
                img_h, img_w = img.data.shape[1], img.data.shape[2]

                # Available space for the image (accounting for title/margins)
                target_w = quad_w - 20
                target_h = quad_h - 60

                # Determine scaling factor
                # Use the smaller ratio to ensure it fits both ways
                scale = min(target_w / img_w, target_h / img_h)

                new_w = int(img_w * scale)
                new_h = int(img_h * scale)

                if dpg.does_item_exist(f"img_{tag}"):
                    dpg.set_item_width(f"img_{tag}", new_w)
                    dpg.set_item_height(f"img_{tag}", new_h)

                    # Optional: Center the image in the quadrant
                    padding_x = (target_w - new_w) // 2
                    dpg.set_item_pos(f"img_{tag}", [padding_x + 10, 40])

    def on_global_scroll(self, delta):
        viewer = self.get_hovered_viewer()
        if viewer:
            viewer.on_scroll(delta)
            # Add linking logic here:
            # if viewer.is_linked: sync others...

    def on_global_drag(self, data):
        viewer = self.get_hovered_viewer()
        if viewer:
            viewer.on_drag(data)

    def on_global_release(self):
        for v in self.controller.viewers.values():
            v.last_dx, v.last_dy = 0, 0

    def update_overlays(self):
        """Calculates voxel coordinates and values under the mouse."""
        mouse_pos = dpg.get_mouse_pos(local=False)
        viewer = self.get_hovered_viewer()

        if not viewer or viewer.current_image_id is None:
            # Clear all overlays if not hovering a valid viewer
            for tag in self.controller.viewers:
                dpg.set_value(f"overlay_{tag}", "")
            return

        # Get image widget transform info
        img_tag = f"img_{viewer.tag}"
        win_tag = f"win_{viewer.tag}"

        # Screen position of the viewer window
        win_pos = dpg.get_item_pos(win_tag)
        # Position of the image relative to the viewer window
        img_rel_pos = dpg.get_item_pos(img_tag)

        # Absolute screen position of the image start
        img_start_x = win_pos[0] + img_rel_pos[0]
        img_start_y = win_pos[1] + img_rel_pos[1]

        # Mouse position relative to the image top-left
        rel_mouse_x = mouse_pos[0] - img_start_x
        rel_mouse_y = mouse_pos[1] - img_start_y

        # Get current displayed size to calculate scale
        disp_w = dpg.get_item_width(img_tag)
        disp_h = dpg.get_item_height(img_tag)

        img_model = self.controller.images[viewer.current_image_id]
        real_h, real_w = img_model.data.shape[1], img_model.data.shape[2]

        # Map to voxel indices
        vox_x = int((rel_mouse_x / disp_w) * real_w)
        vox_y = int((rel_mouse_y / disp_h) * real_h)

        # Check bounds
        if 0 <= vox_x < real_w and 0 <= vox_y < real_h:
            value = img_model.data[viewer.slice_idx, vox_y, vox_x]
            info = f"X: {vox_x}, Y: {vox_y}, Z: {viewer.slice_idx}\nVal: {int(value)} HU"
            dpg.set_value(f"overlay_{viewer.tag}", info)
        else:
            dpg.set_value(f"overlay_{viewer.tag}", "")


class SliceViewer:
    def __init__(self, tag_id, controller):
        self.last_dy = 0
        self.last_dx = 0
        self.tag = tag_id
        self.controller = controller
        self.current_image_id = None
        self.slice_idx = 0
        self.ww, self.wl = 400, 40
        self.texture_tag = f"tex_{tag_id}"
        self.image_tag = f"img_{tag_id}"

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
            print(f'Creating texture for image {img_id} with size {w}x{h}...')
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
        """Window/Level logic linked to ImageModel, triggered by Shift."""
        if self.current_image_id is None: return

        total_dx, total_dy = data[1], data[2]
        step_x = total_dx - self.last_dx
        step_y = total_dy - self.last_dy
        self.last_dx, self.last_dy = total_dx, total_dy

        # Use mvKey_LShift for Mac/Linux compatibility
        is_shift = dpg.is_key_down(dpg.mvKey_LShift) or dpg.is_key_down(dpg.mvKey_RShift)

        if is_shift and dpg.is_mouse_button_down(dpg.mvMouseButton_Left):
            img_model = self.controller.images[self.current_image_id]

            # Sensitivity adjustment for medical imaging
            img_model.ww = max(1, img_model.ww + step_x * 2)
            img_model.wl = img_model.wl - step_y * 2

            # Sync all viewers showing this image
            self.controller.update_all_viewers_of_image(self.current_image_id)