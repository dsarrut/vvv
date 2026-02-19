import dearpygui.dearpygui as dpg
import numpy as np


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

    def get_mouse_to_pixel_coords(self):
        if not self.current_image_id: return None, None

        mouse_pos = dpg.get_mouse_pos(local=False)  # Global screen space
        img_tag = f"img_{self.tag}"

        # Get the global screen position of the image widget top-left
        if not dpg.does_item_exist(img_tag): return None, None
        img_rect_min = dpg.get_item_rect_min(img_tag)

        rel_m_x = mouse_pos[0] - img_rect_min[0]
        rel_m_y = mouse_pos[1] - img_rect_min[1]

        # Scale to image pixels
        disp_w = dpg.get_item_width(img_tag)
        disp_h = dpg.get_item_height(img_tag)
        if disp_w <= 0 or disp_h <= 0: return None, None

        img_model = self.controller.images[self.current_image_id]
        _, shape = img_model.get_slice_rgba(self.slice_idx, self.orientation)
        real_h, real_w = shape[0], shape[1]

        return (rel_m_x / disp_w) * real_w, (rel_m_y / disp_h) * real_h

    def resize(self, quad_w, quad_h):
        if not dpg.does_item_exist(f"win_{self.tag}"):
            return
        dpg.set_item_width(f"win_{self.tag}", quad_w)
        dpg.set_item_height(f"win_{self.tag}", quad_h)

        # Explicitly resize the drawlist to match the quadrant
        if dpg.does_item_exist(f"drawlist_{self.tag}"):
            dpg.set_item_width(f"drawlist_{self.tag}", quad_w)
            dpg.set_item_height(f"drawlist_{self.tag}", quad_h)

        if self.current_image_id is None:
            return

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

    def sync_other_views(self):
        """Synchronizes other views of the same image to the current mouse position."""
        if self.current_image_id is None:
            return

        # 1. Get the 3D voxel index under the mouse in THIS viewer
        pix_x, pix_y = self.get_mouse_to_pixel_coords()
        if pix_x is None:
            return

        # 1. Update the crosshair in the current window
        self.draw_crosshair(pix_x, pix_y)

        img_model = self.controller.images[self.current_image_id]
        _, shape = img_model.get_slice_rgba(self.slice_idx, self.orientation)
        real_h, real_w = shape[0], shape[1]

        # Map 2D mouse pixels -> 3D Voxel coordinates (V_x, V_y, V_z)
        # Using your existing orientation mapping logic
        if self.orientation == "Axial":
            vx, vy, vz = pix_x, pix_y, self.slice_idx
        elif self.orientation == "Sagittal":
            vx, vy, vz = self.slice_idx, real_w - pix_x, real_h - pix_y
        else:  # Coronal
            vx, vy, vz = pix_x, self.slice_idx, real_h - pix_y

        # 2. Update and draw in all other viewers
        for viewer in self.controller.viewers.values():
            if viewer.current_image_id == self.current_image_id and viewer.tag != self.tag:
                # We need the dimensions of the target viewer to project correctly
                _, v_shape = img_model.get_slice_rgba(0, viewer.orientation)
                vh, vw = v_shape[0], v_shape[1]

                if viewer.orientation == "Axial":
                    viewer.slice_indices["Axial"] = int(np.clip(vz, 0, img_model.data.shape[0] - 1))
                    viewer.draw_crosshair(vx, vy)
                elif viewer.orientation == "Sagittal":
                    viewer.slice_indices["Sagittal"] = int(np.clip(vx, 0, img_model.data.shape[2] - 1))
                    viewer.draw_crosshair(vw - vy, vh - vz)  # Projected coords
                elif viewer.orientation == "Coronal":
                    viewer.slice_indices["Coronal"] = int(np.clip(vy, 0, img_model.data.shape[1] - 1))
                    viewer.draw_crosshair(vx, vh - vz)  # Projected coords

                viewer.update_render()

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

        # 1. Use the mutualized helper to get image-space coordinates
        pix_x, pix_y = self.get_mouse_to_pixel_coords()

        # If the mouse isn't hovering over this specific viewer, pix_x will be None
        if pix_x is None:
            return

        img_model = self.controller.images[self.current_image_id]

        # 2. Map 2D pixels back to 3D Voxel Indices (v)
        # Using the same mapping logic as your original code
        idx = self.slice_idx
        _, shape = img_model.get_slice_rgba(idx, self.orientation)
        real_h, real_w = shape[0], shape[1]

        if self.orientation == "Axial":
            v = np.array([pix_x, pix_y, idx])
        elif self.orientation == "Sagittal":
            v = np.array([idx, real_w - pix_x, real_h - pix_y])
        else:  # Coronal
            v = np.array([pix_x, idx, real_h - pix_y])

        # 3. Convert to Physical World Coordinates (mm)
        phys = img_model.voxel_to_physic_coord(v)

        # 4. Fetch Voxel Value
        ix, iy, iz = int(v[0]), int(v[1]), int(v[2])
        max_z, max_y, max_x = img_model.data.shape

        if 0 <= ix < max_x and 0 <= iy < max_y and 0 <= iz < max_z:
            val = img_model.data[iz, iy, ix]
            overlay_text = (
                f"{self.orientation} {val:.1f}\n"
                f"Vox: {v[0]:.1f}, {v[1]:.1f}, {v[2]:.1f}\n"
                f"Phys: {phys[0]:.1f}, {phys[1]:.1f}, {phys[2]:.1f} mm"
            )
            dpg.set_value(f"overlay_{self.tag}", overlay_text)
        else:
            dpg.set_value(f"overlay_{self.tag}", "Out of image")

        # 5. Position the text at the bottom-left of the viewer window
        win_h = dpg.get_item_height(f"win_{self.tag}")
        text_size = dpg.get_item_rect_size(f"overlay_{self.tag}")
        text_h = text_size[1] if text_size[1] > 0 else 60

        dpg.set_item_pos(f"overlay_{self.tag}", [5, win_h - text_h - 5])

    def apply_local_auto_window(self, search_radius=25):
        """Sets WW/WL based on a local neighborhood around the mouse."""
        if self.current_image_id is None: return

        pix_x, pix_y = self.get_mouse_to_pixel_coords()
        if pix_x is None: return

        img_model = self.controller.images[self.current_image_id]
        _, shape = img_model.get_slice_rgba(self.slice_idx, self.orientation)
        real_h, real_w = shape[0], shape[1]

        # Map search_radius (screen pixels) to voxel units using the current display ratio
        img_tag = f"img_{self.tag}"
        disp_w = dpg.get_item_width(img_tag)
        disp_h = dpg.get_item_height(img_tag)

        vox_radius_x = (search_radius / disp_w) * real_w
        vox_radius_y = (search_radius / disp_h) * real_h

        # Define bounds (clamped to image dimensions)
        x0, x1 = int(max(0, pix_x - vox_radius_x)), int(min(real_w, pix_x + vox_radius_x))
        y0, y1 = int(max(0, pix_y - vox_radius_y)), int(min(real_h, pix_y + vox_radius_y))

        if x1 <= x0 or y1 <= y0: return

        # Extract local patch (using your orientation logic)
        if self.orientation == "Axial":
            patch = img_model.data[self.slice_indices["Axial"], y0:y1, x0:x1]
        elif self.orientation == "Sagittal":
            # Correcting for flippings in your get_slice_rgba logic
            z_idx0 = int(max(0, real_h - (pix_y + vox_radius_y)))
            z_idx1 = int(min(img_model.data.shape[0], real_h - (pix_y - vox_radius_y)))
            y_idx0 = int(max(0, real_w - (pix_x + vox_radius_x)))
            y_idx1 = int(min(img_model.data.shape[1], real_w - (pix_x - vox_radius_x)))
            patch = img_model.data[z_idx0:z_idx1, y_idx0:y_idx1, int(self.slice_indices["Sagittal"])]
        else:  # Coronal
            z_idx0 = int(max(0, real_h - (pix_y + vox_radius_y)))
            z_idx1 = int(min(img_model.data.shape[0], real_h - (pix_y - vox_radius_y)))
            patch = img_model.data[z_idx0:z_idx1, y0:y1, int(self.slice_indices["Coronal"])]

        if patch.size > 0:
            p_min, p_max = np.percentile(patch, [2, 98])
            img_model.ww = max(1, p_max - p_min)
            img_model.wl = (p_max + p_min) / 2
            self.controller.update_all_viewers_of_image(self.current_image_id)

    def draw_crosshair(self, pix_x, pix_y):
        """Draws a crosshair at the specified image pixel coordinates."""
        node_tag = f"crosshair_node_{self.tag}"
        if not dpg.does_item_exist(node_tag): return
        dpg.delete_item(node_tag, children_only=True)

        img_tag = f"img_{self.tag}"
        disp_w = dpg.get_item_width(img_tag)
        disp_h = dpg.get_item_height(img_tag)

        img_model = self.controller.images[self.current_image_id]
        _, shape = img_model.get_slice_rgba(self.slice_idx, self.orientation)
        real_h, real_w = shape[0], shape[1]

        # Convert image pixels to screen coordinates within the drawlist
        img_pos = dpg.get_item_pos(img_tag)
        screen_x = (pix_x / real_w) * disp_w + img_pos[0]
        screen_y = (pix_y / real_h) * disp_h + img_pos[1]

        # Draw horizontal and vertical lines (Cyan for visibility)
        color = [0, 255, 255, 180]
        # Vertical
        dpg.draw_line([screen_x, img_pos[1]], [screen_x, img_pos[1] + disp_h],
                      color=color, thickness=1, parent=node_tag)
        # Horizontal
        dpg.draw_line([img_pos[0], screen_y], [img_pos[0] + disp_w, screen_y],
                      color=color, thickness=1, parent=node_tag)

    def on_key_press(self, key):
        """Handle orientation switching."""
        if key == dpg.mvKey_I:
            self.on_zoom("in")
        elif key == dpg.mvKey_O:
            self.on_zoom("out")
        elif key == dpg.mvKey_R:
            # Reset pan/zoom
            self.zoom = 1.0
            self.pan_offset = [0, 0]
            self.on_window_resize()
        elif key == dpg.mvKey_F1:
            self.set_orientation("Axial")
        elif key == dpg.mvKey_F2:
            self.set_orientation("Sagittal")
        elif key == dpg.mvKey_F3:
            self.set_orientation("Coronal")
        elif key == dpg.mvKey_W:
            self.apply_local_auto_window()

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
        if self.current_image_id is None:
            return

        step_x, step_y = data[1] - self.last_dx, data[2] - self.last_dy
        self.last_dx, self.last_dy = data[1], data[2]

        # Key modifiers?
        is_control = dpg.is_key_down(dpg.mvKey_LControl) or dpg.is_key_down(dpg.mvKey_RControl)
        is_shift = dpg.is_key_down(dpg.mvKey_LShift) or dpg.is_key_down(dpg.mvKey_RShift)

        # Navigation / Sync (Plain Left Click Drag)
        if not is_control and not is_shift and dpg.is_mouse_button_down(dpg.mvMouseButton_Left):
            pix_x, pix_y = self.get_mouse_to_pixel_coords()
            if pix_x is not None:
                # Force crosshair and sync to update EVERY frame
                self.draw_crosshair(pix_x, pix_y)
                self.sync_other_views()

        # Pan (Control + Drag)
        elif is_control and dpg.is_mouse_button_down(dpg.mvMouseButton_Left):
            self.pan_offset[0] += step_x
            self.pan_offset[1] += step_y
            self.controller.main_windows.on_window_resize()

        # Window/Level (Shift + Drag)
        elif is_shift and dpg.is_mouse_button_down(dpg.mvMouseButton_Left):
            img_model = self.controller.images[self.current_image_id]
            img_model.ww = max(1, img_model.ww + step_x * 2)
            img_model.wl -= step_y * 2
            self.controller.update_all_viewers_of_image(self.current_image_id)

    def on_zoom(self, direction):
        if self.current_image_id is None: return

        # Get screen-space relative mouse (before zoom)
        cont_pos = dpg.get_item_pos("viewers_container")
        win_pos = dpg.get_item_pos(f"win_{self.tag}")
        img_rel_pos = dpg.get_item_pos(f"img_{self.tag}")
        mouse_pos = dpg.get_mouse_pos(local=False)

        img_screen_x = cont_pos[0] + win_pos[0] + img_rel_pos[0]
        img_screen_y = cont_pos[1] + win_pos[1] + img_rel_pos[1]

        rel_m_x = mouse_pos[0] - img_screen_x
        rel_m_y = mouse_pos[1] - img_screen_y

        # Apply zoom
        old_zoom = self.zoom
        self.zoom = np.clip(self.zoom * (1.1 if direction == "in" else 0.9), 0.1, 20.0)
        ratio = self.zoom / old_zoom

        # Calculate growth and centering shift compensation
        old_w = dpg.get_item_width(f"img_{self.tag}")
        old_h = dpg.get_item_height(f"img_{self.tag}")
        dw, dh = (old_w * ratio) - old_w, (old_h * ratio) - old_h

        # Update Pan: subtract growth, add back centering shift from resize()
        self.pan_offset[0] -= (rel_m_x * (ratio - 1)) - (dw / 2)
        self.pan_offset[1] -= (rel_m_y * (ratio - 1)) - (dh / 2)

        self.controller.main_windows.on_window_resize()
