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
                # force 0 padding inside the viewer windows
                dpg.add_theme_style(dpg.mvStyleVar_WindowPadding, 0, 0, category=dpg.mvThemeCat_Core)
                dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing, 0, 0, category=dpg.mvThemeCat_Core)
                dpg.add_theme_style(dpg.mvStyleVar_FramePadding, 0, 0, category=dpg.mvThemeCat_Core)

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
    viewer = controller.viewers[tag]
    with dpg.child_window(tag=f"win_{tag}",
                          border=True,
                          no_scrollbar=True,
                          no_scroll_with_mouse=True):
        # Add the image first
        border_color = [100, 100, 100, 255]
        border_color = [100, 100, 100, 0]
        dpg.add_image(viewer.texture_tag,
                      tag=f"img_{tag}",
                      pos=[0, 0],
                      border_color=border_color)
        # Overlay for coordinates and HU value
        dpg.add_text("", tag=f"overlay_{tag}", color=[0, 246, 7])


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
        if not window_width or not window_height:
            return  # Safety

        # 2. Subtract the sidebar and margins
        side_panel_width = 250
        available_width = window_width - side_panel_width - 15
        available_height = window_height - 35  # Adjusted for menu bar

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

        # Orientation keys
        if key in [dpg.mvKey_F1, dpg.mvKey_F2, dpg.mvKey_F3]:
            viewer.on_key_press(key)
        elif key == dpg.mvKey_I:
            viewer.on_zoom("in")
        elif key == dpg.mvKey_O:
            viewer.on_zoom("out")
        elif key == dpg.mvKey_R:  # Bonus: Reset pan/zoom
            viewer.zoom = 1.0
            viewer.pan_offset = [0, 0]
            self.on_window_resize()

    def update_overlays(self):
        """Delegates overlay calculation to each individual viewer."""
        for viewer in self.controller.viewers.values():
            viewer.update_overlay()


class SliceViewer:
    def __init__(self, tag_id, controller):
        self.tag = tag_id
        self.controller = controller
        self.current_image_id = None
        self.texture_tag = f"tex_{tag_id}"
        self.image_tag = f"img_{tag_id}"
        # GUI options
        # Use a 4-pixel buffer to prevent the window border from cutting the image
        self.margin_left = 4
        self.margin_top = 4
        # used during mouse drag
        self.last_dy = 0
        self.last_dx = 0
        # Zoom and Pan states
        self.zoom = 1.0
        self.pan_offsets = {
            "Axial": [0, 0],
            "Sagittal": [0, 0],
            "Coronal": [0, 0]
        }
        # current orientation
        self.orientation = "Axial"
        # Dictionary to store the last slice index for each view
        self.slice_indices = {
            "Axial": None,
            "Sagittal": None,
            "Coronal": None
        }

        # Initialize a default small texture; will be recreated on image load
        with dpg.texture_registry():
            dpg.add_dynamic_texture(width=1, height=1,
                                    default_value=np.zeros(4),
                                    tag=self.texture_tag)

    @property
    def slice_idx(self):
        return self.slice_indices[self.orientation]

    @slice_idx.setter
    def slice_idx(self, value):
        self.slice_indices[self.orientation] = value

    @property
    def pan_offset(self):
        return self.pan_offsets[self.orientation]

    @pan_offset.setter
    def pan_offset(self, value):
        self.pan_offsets[self.orientation] = value

    def set_image(self, img_id):
        self.current_image_id = img_id
        img = self.controller.images[img_id]

        # Initialize slice index in the middle if it's the first time for this orientation
        if self.slice_indices[self.orientation] is None:
            if self.orientation == "Axial":
                self.slice_indices["Axial"] = img.data.shape[0] // 2
            elif self.orientation == "Sagittal":
                self.slice_indices["Sagittal"] = img.data.shape[2] // 2
            elif self.orientation == "Coronal":
                self.slice_indices["Coronal"] = img.data.shape[1] // 2

        # Get shape based on orientation
        # Expecting img.get_slice_rgba to return (flattened_data, (height, width))
        _, shape = img.get_slice_rgba(self.slice_idx, self.orientation)
        h, w = shape[0], shape[1]

        # Generate a unique tag for this specific viewer/orientation/size combo
        new_texture_tag = f"tex_{self.tag}_{self.orientation}_{w}x{h}"

        # If this is a new tag, create the texture
        if not dpg.does_item_exist(new_texture_tag):
            with dpg.texture_registry():
                dpg.add_dynamic_texture(
                    width=w,
                    height=h,
                    default_value=np.zeros(w * h * 4),
                    tag=new_texture_tag
                )

        # Delete the OLD texture if it's different from the new one
        if self.texture_tag != new_texture_tag and dpg.does_item_exist(self.texture_tag):
            # Only delete if it's not the startup placeholder
            if "Axial_1x1" not in self.texture_tag:
                dpg.delete_item(self.texture_tag)

        # Update the reference and re-bind the image widget
        self.texture_tag = new_texture_tag
        if dpg.does_item_exist(f"img_{self.tag}"):
            dpg.configure_item(f"img_{self.tag}", texture_tag=self.texture_tag)

        self.update_render()

    def set_orientation(self, orientation):
        self.orientation = orientation
        # When orientation changes, dimensions change -> Recreate Texture
        if self.current_image_id:
            self.set_image(self.current_image_id)  # Re-runs texture creation logic
        self.controller.main_windows.on_window_resize()

    def resize(self, quad_w, quad_h):
        if not dpg.does_item_exist(f"win_{self.tag}"): return
        dpg.set_item_width(f"win_{self.tag}", quad_w)
        dpg.set_item_height(f"win_{self.tag}", quad_h)

        if self.current_image_id:
            img = self.controller.images[self.current_image_id]

            # Get pixel dimensions
            # Axial: (Y, X), Sagittal: (Z, Y), Coronal: (Z, X)
            _, shape = img.get_slice_rgba(self.slice_idx, self.orientation)
            pix_h, pix_w = shape[0], shape[1]

            # Get physical spacing (mm per pixel)
            sw, sh = img.get_physical_aspect_ratio(self.orientation)

            # Physical dimensions in mm
            mm_w = pix_w * sw
            mm_h = pix_h * sh

            target_w, target_h = quad_w - self.margin_left, quad_h - self.margin_top

            # Base scale: how many screen pixels per mm?
            base_scale = min(target_w / mm_w, target_h / mm_h)
            final_scale = base_scale * self.zoom

            # New display size in screen pixels
            new_w = int(mm_w * final_scale)
            new_h = int(mm_h * final_scale)

            dpg.set_item_width(f"img_{self.tag}", new_w)
            dpg.set_item_height(f"img_{self.tag}", new_h)

            # Centering + Pan Offset
            dpg.set_item_pos(f"img_{self.tag}", [
                (target_w - new_w) // 2 + self.margin_left + self.pan_offset[0],
                (target_h - new_h) // 2 + self.margin_top + self.pan_offset[1]
            ])

    def update_render(self):
        if self.current_image_id is None:
            return
        img_model = self.controller.images[self.current_image_id]
        rgba, slice_shape = img_model.get_slice_rgba(self.slice_idx, self.orientation)
        dpg.set_value(self.texture_tag, rgba)

    def update_overlay(self):
        """Calculates coordinates and HU values for this specific viewer."""
        if self.current_image_id is None:
            dpg.set_value(f"overlay_{self.tag}", "")
            return

        # 1. Check if mouse is over THIS viewer's window
        if not dpg.is_item_hovered(f"win_{self.tag}"):
            return

        mouse_pos = dpg.get_mouse_pos(local=False)
        img_tag = f"img_{self.tag}"
        win_pos = dpg.get_item_pos(f"win_{self.tag}")
        img_rel_pos = dpg.get_item_pos(img_tag)

        # 2. Localize mouse to image pixels
        img_start_x = win_pos[0] + img_rel_pos[0]
        img_start_y = win_pos[1] + img_rel_pos[1]
        rel_mouse_x = mouse_pos[0] - img_start_x
        rel_mouse_y = mouse_pos[1] - img_start_y

        disp_w = dpg.get_item_width(img_tag)
        disp_h = dpg.get_item_height(img_tag)
        img_model = self.controller.images[self.current_image_id]

        # Get the pixel shape of the current 2D orientation
        _, shape = img_model.get_slice_rgba(self.slice_idx, self.orientation)
        real_h, real_w = shape[0], shape[1]

        # 3. Calculate floating-point pixel coordinates [0, real_dim]
        # Accounts for Zoom/Pan because disp_w/h change with them
        pix_x = (rel_mouse_x / disp_w) * real_w
        pix_y = (rel_mouse_y / disp_h) * real_h

        # 4. Map 2D pixels back to 3D Voxel Indices (v)
        idx = self.slice_idx
        if self.orientation == "Axial":
            v = np.array([pix_x, pix_y, idx])
        elif self.orientation == "Sagittal":
            v = np.array([idx, real_w - pix_x, real_h - pix_y])
        else:
            v = np.array([pix_x, idx, real_h - pix_y])

        # 5. Convert to Physical World Coordinates (mm)
        phys = img_model.voxel_to_physic_coord(v)

        # 6. Fetch Voxel Value. Round or not ??
        # ix, iy, iz = int(round(v[0])), int(round(v[1])), int(round(v[2]))
        ix, iy, iz = int(v[0]), int(v[1]), int(v[2])
        max_z, max_y, max_x = img_model.data.shape

        if 0 <= ix < max_x and 0 <= iy < max_y and 0 <= iz < max_z:
            val = img_model.data[iz, iy, ix]
            overlay_text = (
                f"{self.orientation} {val:.1f}\n"
                f"{v[0]:.1f}, {v[1]:.1f}, {v[2]:.1f}\n"
                f"{phys[0]:.1f} {phys[1]:.1f} {phys[2]:.1f} mm"
            )
            dpg.set_value(f"overlay_{self.tag}", overlay_text)
        else:
            dpg.set_value(f"overlay_{self.tag}", "Out of image")

        # --- Dynamic Bottom-Left Positioning ---
        # 1. Get the current window height
        win_h = dpg.get_item_height(f"win_{self.tag}")

        # 2. Get the current text size
        text_size = dpg.get_item_rect_size(f"overlay_{self.tag}")
        text_h = text_size[1] if text_size[1] > 0 else 60  # fallback height

        # 3. Calculate Y to pin to bottom (with 5px margin)
        pos_y = win_h - text_h - 5

        # 4. Apply position (keeping X at 5 for the left side)
        dpg.set_item_pos(f"overlay_{self.tag}", [5, pos_y])

    def on_key_press(self, key):
        """Handle orientation switching."""
        if key == dpg.mvKey_F1:
            self.set_orientation("Axial")
        elif key == dpg.mvKey_F2:
            self.set_orientation("Sagittal")
        elif key == dpg.mvKey_F3:
            self.set_orientation("Coronal")

    def on_scroll(self, delta):
        """Called by MainWindow when this viewer is hovered during a scroll."""
        if self.current_image_id is None: return

        increment = 1 if delta > 0 else -1
        img_model = self.controller.images[self.current_image_id]

        # Get max bounds based on current orientation
        if self.orientation == "Axial":
            max_s = img_model.data.shape[0] - 1
        elif self.orientation == "Sagittal":
            max_s = img_model.data.shape[2] - 1
        else:
            max_s = img_model.data.shape[1] - 1

        # Update the orientation-specific index
        new_idx = self.slice_indices[self.orientation] + increment
        self.slice_indices[self.orientation] = np.clip(new_idx, 0, max_s)

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
        """Zoom while keeping the image pixel under the mouse fixed on screen."""
        if self.current_image_id is None:
            return

        # 1. Get current screen state
        img_tag = f"img_{self.tag}"
        win_pos = dpg.get_item_pos(f"win_{self.tag}")
        img_rel_pos = dpg.get_item_pos(img_tag)  # relative to window
        mouse_pos = dpg.get_mouse_pos(local=False)

        # 2. Current width/height on screen
        old_w = dpg.get_item_width(img_tag)
        old_h = dpg.get_item_height(img_tag)
        if old_w <= 0 or old_h <= 0: return

        # 3. Calculate mouse position relative to the image's top-left corner
        # We don't use local=True because it can be jittery during widget movement
        img_screen_x = win_pos[0] + img_rel_pos[0]
        img_screen_y = win_pos[1] + img_rel_pos[1]

        rel_mouse_x = mouse_pos[0] - img_screen_x
        rel_mouse_y = mouse_pos[1] - img_screen_y

        # 4. Apply the zoom change
        old_zoom = self.zoom
        zoom_step = 1.1 if direction == "in" else 0.9
        self.zoom = np.clip(self.zoom * zoom_step, 0.1, 20.0)

        # Calculate actual ratio (handling clipping at min/max zoom)
        actual_ratio = self.zoom / old_zoom

        # 5. Calculate the size change
        new_w = old_w * actual_ratio
        new_h = old_h * actual_ratio
        dw = new_w - old_w
        dh = new_h - old_h

        # 6. PAN COMPENSATION
        # Logic:
        # A) Because of growth, the pixel at rel_mouse_x moves by: rel_mouse_x * (ratio - 1)
        # B) Because of centering in resize(), the image shifts by: -dw / 2
        # We need to subtract the growth movement but add back the centering shift
        self.pan_offset[0] -= (rel_mouse_x * (actual_ratio - 1)) - (dw / 2)
        self.pan_offset[1] -= (rel_mouse_y * (actual_ratio - 1)) - (dh / 2)

        # 7. Apply via the standard resize path
        self.controller.main_windows.on_window_resize()
