import dearpygui.dearpygui as dpg
import numpy as np
from .utils import *


class SliceViewer:
    def __init__(self, tag_id, controller):
        self.tag = tag_id
        self.controller = controller
        self.current_image_id = None
        self.current_image_model = None
        self.active_strips_node = None
        self.active_grid_node = None
        # dpg tags
        self.texture_tag = f"tex_{tag_id}"
        self.image_tag = f"img_{tag_id}"
        self.strips_a_tag = f"strips_node_A_{tag_id}"
        self.strips_b_tag = f"strips_node_B_{tag_id}"
        self.grid_a_tag = f"grid_node_A_{tag_id}"
        self.grid_b_tag = f"grid_node_B_{tag_id}"
        self.overlay_tag = f"overlay_{tag_id}"
        self.crosshair_tag = f"crosshair_node_{tag_id}"
        # GUI options
        # Use a 4-pixel buffer to prevent the window border from cutting the image
        self.margin_left = 4
        self.margin_top = 4
        # used during mouse drag
        self.last_dy = 0
        self.last_dx = 0
        self.current_pmin = [0, 0]
        self.current_pmax = [1, 1]
        # Zoom and Pan states
        # self.zoom = 1.0
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
        # current voxel information under the mouse
        self.mouse_phys_coord = None
        self.mouse_pixel_coord = None
        self.mouse_pixel_value = None
        # current voxel information under the crosshair
        self.crosshair_phys_coord = None
        self.crosshair_pixel_coord = None
        self.crosshair_pixel_value = None

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

    @property
    def zoom(self):
        if self.current_image_id is None:
            return 1.0
        return self.current_image_model.zoom

    @zoom.setter
    def zoom(self, value):
        if self.current_image_id is None:
            return
        self.current_image_model.zoom = value

    def set_image(self, img_id):
        self.current_image_id = img_id
        self.current_image_model = self.controller.images[self.current_image_id]
        img = self.current_image_model

        # Initialize the slice index in the middle if it's the first time for this orientation
        if self.slice_indices[self.orientation] is None:
            if self.orientation == "Axial":
                self.slice_idx = img.data.shape[0] // 2
            elif self.orientation == "Sagittal":
                self.slice_idx = img.data.shape[2] // 2
            elif self.orientation == "Coronal":
                self.slice_idx = img.data.shape[1] // 2

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
        if dpg.does_item_exist(self.image_tag):
            dpg.configure_item(self.image_tag, texture_tag=self.texture_tag)

        self.update_sidebar_info()
        self.update_render()

    def set_orientation(self, orientation):
        self.orientation = orientation
        # When orientation changes, dimensions change -> Recreate Texture
        if self.current_image_id:
            self.set_image(self.current_image_id)  # Re-runs texture creation logic
        self.controller.main_windows.on_window_resize()

    def get_mouse_to_pixel_coords(self, ignore_hover=False):
        if not self.current_image_id:
            return None, None

        # Check if the viewer is actually being hovered
        if not ignore_hover and not dpg.is_item_hovered(f"win_{self.tag}"):
            return None, None

        # This is local to the drawlist [0,0]
        mouse_x, mouse_y = dpg.get_drawing_mouse_pos()

        # Retrieve stored image boundaries (local to the drawlist)
        pmin = self.current_pmin
        pmax = self.current_pmax

        # Calculate mouse relative to the image top-left
        rel_x = mouse_x - pmin[0]
        rel_y = mouse_y - pmin[1]

        # Displayed width/height of the image on screen
        disp_w = pmax[0] - pmin[0]
        disp_h = pmax[1] - pmin[1]

        # Bounds check: only return coords if the mouse is actually OVER the image
        if not (0 <= rel_x <= disp_w and 0 <= rel_y <= disp_h):
            return None, None

        img_model = self.controller.images[self.current_image_id]
        _, shape = img_model.get_slice_rgba(self.slice_idx, self.orientation)
        h, w = shape[0], shape[1]

        # Scale to voxel units
        return (rel_x / disp_w) * w, (rel_y / disp_h) * h

    def resize(self, quad_w, quad_h):
        if not dpg.does_item_exist(f"win_{self.tag}"):
            return
        dpg.set_item_width(f"win_{self.tag}", quad_w)
        dpg.set_item_height(f"win_{self.tag}", quad_h)

        if dpg.does_item_exist(f"drawlist_{self.tag}"):
            dpg.set_item_width(f"drawlist_{self.tag}", quad_w)
            dpg.set_item_height(f"drawlist_{self.tag}", quad_h)

        if self.current_image_id is None:
            return

        img = self.controller.images[self.current_image_id]
        _, shape = img.get_slice_rgba(self.slice_idx, self.orientation)
        pix_h, pix_w = shape[0], shape[1]

        sw, sh = img.get_physical_aspect_ratio(self.orientation)
        mm_w, mm_h = pix_w * sw, pix_h * sh

        target_w, target_h = quad_w - self.margin_left, quad_h - self.margin_top
        base_scale = min(target_w / mm_w, target_h / mm_h)
        final_scale = base_scale * self.zoom

        new_w, new_h = int(mm_w * final_scale), int(mm_h * final_scale)

        # Calculate and store pmin/pmax
        off_x = (target_w - new_w) // 2 + self.margin_left + self.pan_offsets[self.orientation][0]
        off_y = (target_h - new_h) // 2 + self.margin_top + self.pan_offsets[self.orientation][1]

        self.current_pmin = [off_x, off_y]
        self.current_pmax = [off_x + new_w, off_y + new_h]

        # Update the standard image primitive
        if dpg.does_item_exist(self.image_tag):
            dpg.configure_item(self.image_tag, pmin=self.current_pmin, pmax=self.current_pmax)

        # Refresh the display (this will choose between Texture or Rectangles)
        self.update_render()

    def sync_other_views(self):
        """Synchronizes other views and centers them on the crosshair."""
        if self.current_image_id is None:
            return

        # Get the 3D voxel index under the mouse in THIS viewer
        pix_x, pix_y = self.get_mouse_to_pixel_coords(ignore_hover=True)
        if pix_x is None:
            return

        # Update the crosshair in the current window
        self.draw_crosshair(pix_x, pix_y)

        img_model = self.controller.images[self.current_image_id]
        _, shape = img_model.get_slice_rgba(self.slice_idx, self.orientation)
        real_h, real_w = shape[0], shape[1]

        # Map 2D mouse pixels -> 3D Voxel coordinates (V_x, V_y, V_z)
        if self.orientation == "Axial":
            vx, vy, vz = pix_x, pix_y, self.slice_idx
        elif self.orientation == "Sagittal":
            vx, vy, vz = self.slice_idx, real_w - pix_x, real_h - pix_y
        else:  # Coronal
            vx, vy, vz = pix_x, self.slice_idx, real_h - pix_y

        # Update and draw in all other viewers
        for viewer in self.controller.viewers.values():
            if viewer.current_image_id == self.current_image_id and viewer.tag != self.tag:
                # 1. Update Slice Index
                if viewer.orientation == "Axial":
                    viewer.slice_idx = int(np.clip(vz, 0, img_model.data.shape[0] - 1))
                elif viewer.orientation == "Sagittal":
                    viewer.slice_idx = int(np.clip(vx, 0, img_model.data.shape[2] - 1))
                elif viewer.orientation == "Coronal":
                    viewer.slice_idx = int(np.clip(vy, 0, img_model.data.shape[1] - 1))

                # 2. Calculate the target voxel position in the target viewer's 2D space
                _, v_shape = img_model.get_slice_rgba(viewer.slice_idx, viewer.orientation)
                vh, vw = v_shape[0], v_shape[1]

                if viewer.orientation == "Axial":
                    tx, ty = vx, vy
                elif viewer.orientation == "Sagittal":
                    tx, ty = vw - vy, vh - vz
                elif viewer.orientation == "Coronal":
                    tx, ty = vx, vh - vz

                # 3. Calculate Pan adjustment to center the crosshair
                # We need to know where the crosshair would be on screen without the current pan
                # Then move the pan so that position matches the window center.
                win_w = dpg.get_item_width(f"win_{viewer.tag}")
                win_h = dpg.get_item_height(f"win_{viewer.tag}")

                if win_w and win_h:
                    # Determine physical size and scale as done in resize()
                    sw, sh = img_model.get_physical_aspect_ratio(viewer.orientation)
                    mm_w, mm_h = vw * sw, vh * sh

                    target_w, target_h = win_w - viewer.margin_left, win_h - viewer.margin_top
                    base_scale = min(target_w / mm_w, target_h / mm_h)
                    final_scale = base_scale * viewer.zoom

                    # Target screen position relative to image top-left (un-panned)
                    # Note: x is scaled by sw, y by sh
                    screen_v_x = (tx * sw) * final_scale
                    screen_v_y = (ty * sh) * final_scale

                    # Current image top-left (centered in window, no pan)
                    base_off_x = (target_w - (mm_w * final_scale)) / 2 + viewer.margin_left
                    base_off_y = (target_h - (mm_h * final_scale)) / 2 + viewer.margin_top

                    # Desired pan = (Window Center) - (Base Offset + Scaled Voxel Position)
                    viewer.pan_offset[0] = (win_w / 2) - (base_off_x + screen_v_x)
                    viewer.pan_offset[1] = (win_h / 2) - (base_off_y + screen_v_y)

                # 4. Finalize render
                viewer.draw_crosshair(tx, ty)
                viewer.update_render()

        # Necessary to update pmin/pmax for all viewers after pan change
        self.controller.main_windows.on_window_resize()

    def draw_voxel_grid(self, h, w):
        # Use the same double-buffering logic as strips
        node_a = self.grid_a_tag
        node_b = self.grid_b_tag

        # Determine which is currently hidden to use as back-buffer
        back_node = node_b if self.active_grid_node == node_a else node_a

        # Clear the back-buffer
        if dpg.does_item_exist(back_node):
            dpg.delete_item(back_node, children_only=True)
        else:
            return  # Safety

        pmin = self.current_pmin
        pmax = self.current_pmax
        vox_w = (pmax[0] - pmin[0]) / w
        vox_h = (pmax[1] - pmin[1]) / h

        # Optimization: Don't draw if voxels are too small to see the grid
        # if vox_w < 2 or vox_h < 2:
        #    dpg.configure_item(self.active_grid_node, show=False)
        #    return

        color = [255, 255, 255, 40]

        # 1. Draw Vertical Lines (along the width)
        for x in range(w + 1):
            lx = pmin[0] + x * vox_w
            dpg.draw_line([lx, pmin[1]], [lx, pmax[1]], color=color, parent=back_node)

        # 2. Draw Horizontal Lines (along the height)
        for y in range(h + 1):
            ly = pmin[1] + y * vox_h
            dpg.draw_line([pmin[0], ly], [pmax[0], ly], color=color, parent=back_node)

        dpg.configure_item(back_node, show=True)
        if dpg.does_item_exist(self.active_grid_node):
            dpg.configure_item(self.active_grid_node, show=False)

        self.active_grid_node = back_node

    def draw_crosshair(self, pix_x, pix_y):
        node_tag = self.crosshair_tag
        if not dpg.does_item_exist(node_tag): return
        dpg.delete_item(node_tag, children_only=True)

        pmin = self.current_pmin
        pmax = self.current_pmax
        disp_w, disp_h = pmax[0] - pmin[0], pmax[1] - pmin[1]

        img_model = self.controller.images[self.current_image_id]
        _, shape = img_model.get_slice_rgba(self.slice_idx, self.orientation)
        real_h, real_w = shape[0], shape[1]

        # Map voxel back to screen-space within the drawlist
        screen_x = (pix_x / real_w) * disp_w + pmin[0]
        screen_y = (pix_y / real_h) * disp_h + pmin[1]

        color = [0, 246, 7, 180]  # Cyan
        dpg.draw_line([screen_x, pmin[1]], [screen_x, pmin[1] + disp_h], color=color, parent=node_tag)
        dpg.draw_line([pmin[0], screen_y], [pmin[0] + disp_w, screen_y], color=color, parent=node_tag)

    def draw_voxels_as_strips(self, rgba_flat, h, w):
        # Determine which node is hidden (our back-buffer)
        node_a = self.strips_a_tag
        node_b = self.strips_b_tag

        # If A is active, we draw to B. If B is active, we draw to A.
        back_node = node_b if self.active_strips_node == node_a else node_a

        # Clear ONLY the back-buffer before drawing
        dpg.delete_item(back_node, children_only=True)

        pmin, pmax = self.current_pmin, self.current_pmax
        vox_w, vox_h = (pmax[0] - pmin[0]) / w, (pmax[1] - pmin[1]) / h
        win_w = dpg.get_item_width(f"win_{self.tag}")
        win_h = dpg.get_item_height(f"win_{self.tag}")

        if not win_w or not win_h: return

        # Culling logic
        start_x = max(0, int(-pmin[0] / vox_w))
        end_x = min(w, int((win_w - pmin[0]) / vox_w) + 1)
        start_y = max(0, int(-pmin[1] / vox_h))
        end_y = min(h, int((win_h - pmin[1]) / vox_h) + 1)

        pixels = rgba_flat.reshape(h, w, 4)

        # Draw to the hidden node
        for y in range(start_y, end_y):
            y_pos = pmin[1] + (y * vox_h) + (vox_h / 2)
            for x in range(start_x, end_x):
                x1 = pmin[0] + (x * vox_w)
                x2 = x1 + vox_w
                color = [int(c * 255) for c in pixels[y, x]]
                # thickness + 1 to avoid slight lines at the boundary
                dpg.draw_line([x1, y_pos], [x2, y_pos], color=color, thickness=vox_h + 1, parent=back_node)

        # Atomic Swap: Show the new drawing and hide the old one
        dpg.configure_item(back_node, show=True)
        dpg.configure_item(self.active_strips_node, show=False)

        # Update the tracker
        self.active_strips_node = back_node

    def should_use_voxels_strips(self):
        """
        Returns True if we should render using vector rectangles (NN)
        instead of the GPU texture (Linear).

        This function determines if the current zoom level and visible area
        justify switching from standard texture mapping to a manual
        "Nearest Neighbor" (NN) rendering using DPG draw primitives.

        It calculates the number of voxels currently visible within the
        window bounds. If the count is low (e.g., when zoomed in significantly),
        it returns True to trigger a pixel-perfect rendering mode that
        avoids GPU linear interpolation artifacts.
        """
        if self.current_image_model.interpolation_linear or self.current_image_id is None:
            return False

        # Get the parent quadrant size
        win_w = dpg.get_item_width(f"win_{self.tag}")
        win_h = dpg.get_item_height(f"win_{self.tag}")
        if not win_w or not win_h:
            return False

        # Get voxel dimensions on screen
        pmin = self.current_pmin
        pmax = self.current_pmax

        img_model = self.controller.images[self.current_image_id]
        _, shape = img_model.get_slice_rgba(self.slice_idx, self.orientation)
        h, w = shape[0], shape[1]

        vox_w = (pmax[0] - pmin[0]) / w
        vox_h = (pmax[1] - pmin[1]) / h

        # Calculate visible voxel range (Culling)
        start_x = max(0, int(-pmin[0] / vox_w))
        end_x = min(w, int((win_w - pmin[0]) / vox_w) + 1)
        start_y = max(0, int(-pmin[1] / vox_h))
        end_y = min(h, int((win_h - pmin[1]) / vox_h) + 1)

        # Criteria: If the number of voxels to draw is small (e.g. < 5000)
        num_visible_voxels = (end_x - start_x) * (end_y - start_y)
        return 0 < num_visible_voxels < 1500

    def apply_local_auto_window(self, search_radius=25):
        """Sets WW/WL based on a local neighborhood around the mouse."""
        if self.current_image_id is None:
            return

        # Use ignore_hover=True if calling from a key press while the mouse is moving
        pix_x, pix_y = self.get_mouse_to_pixel_coords(ignore_hover=True)
        if pix_x is None:
            return

        img_model = self.current_image_model
        _, shape = img_model.get_slice_rgba(self.slice_idx, self.orientation)
        real_h, real_w = shape[0], shape[1]

        # Use stored pmin/pmax to avoid ZeroDivisionError from get_item_width
        pmin = self.current_pmin
        pmax = self.current_pmax
        disp_w = pmax[0] - pmin[0]
        disp_h = pmax[1] - pmin[1]

        if disp_w <= 0 or disp_h <= 0:
            return

        # Map search_radius (screen pixels) to voxel units
        vox_radius_x = (search_radius / disp_w) * real_w
        vox_radius_y = (search_radius / disp_h) * real_h

        # Define bounds (clamped to image dimensions)
        x0, x1 = int(max(0, pix_x - vox_radius_x)), int(min(real_w, pix_x + vox_radius_x))
        y0, y1 = int(max(0, pix_y - vox_radius_y)), int(min(real_h, pix_y + vox_radius_y))

        if x1 <= x0 or y1 <= y0:
            return

        # Extract local patch matching the flipping logic in core.py
        # Note: img_model.data is (Z, Y, X)
        if self.orientation == "Axial":
            # Axial is not flipped: slice_idx is Z, y is Y, x is X
            patch = img_model.data[self.slice_idx, y0:y1, x0:x1]

        elif self.orientation == "Sagittal":
            # Sagittal in core.py uses flipud(fliplr(data[:, :, slice_idx]))
            # This means screen_y maps to inverted Z, and screen_x maps to inverted Y
            z_idx0 = int(max(0, real_h - y1))
            z_idx1 = int(min(img_model.data.shape[0], real_h - y0))
            y_idx0 = int(max(0, real_w - x1))
            y_idx1 = int(min(img_model.data.shape[1], real_w - x0))
            patch = img_model.data[z_idx0:z_idx1, y_idx0:y_idx1, self.slice_idx]

        else:  # Coronal
            # Coronal in core.py uses flipud(data[:, slice_idx, :])
            # This means screen_y maps to inverted Z, and screen_x maps to X
            z_idx0 = int(max(0, real_h - y1))
            z_idx1 = int(min(img_model.data.shape[0], real_h - y0))
            patch = img_model.data[z_idx0:z_idx1, self.slice_idx, x0:x1]

        if patch.size > 0:
            p_min, p_max = np.percentile(patch, [2, 98])
            #img_model.ww = max(1, p_max - p_min)
            #img_model.wl = (p_max + p_min) / 2
            ## Refresh all views showing this image
            #self.update_sidebar_window_level()
            #self.controller.update_all_viewers_of_image(self.current_image_id)
            self.update_window_level(max(1, p_max - p_min), (p_max + p_min) / 2)

    def update_crosshair_position(self, viewer):
        self.crosshair_pixel_coord = viewer.mouse_pixel_coord
        self.crosshair_phys_coord = viewer.mouse_phys_coord
        self.crosshair_pixel_value = viewer.mouse_pixel_value

    def update_render(self):
        if self.current_image_id is None:
            return

        img_model = self.controller.images[self.current_image_id]
        rgba_flat, shape = img_model.get_slice_rgba(self.slice_idx, self.orientation)
        h, w = shape[0], shape[1]

        # 1. Image Base Layer Logic
        # decide if we should use vector "Strips" for perfect sharpness
        use_strips = self.should_use_voxels_strips()

        if use_strips:
            # Vector Mode: Hide GPU texture, Draw Strips
            dpg.configure_item(self.image_tag, show=False)
            self.draw_voxels_as_strips(rgba_flat, h, w)
        else:
            # GPU Mode: Hide Strips, Update Texture
            if dpg.does_item_exist(self.active_strips_node):
                dpg.configure_item(self.active_strips_node, show=False)
            dpg.configure_item(self.image_tag, show=True)
            dpg.set_value(self.texture_tag, rgba_flat)

        # 2. Grid Overlay Logic (Independent of Image Mode)
        if self.current_image_model.grid_mode:
            self.draw_voxel_grid(h, w)
        else:
            # Ensure grid is hidden if mode is toggled off
            if dpg.does_item_exist(self.active_grid_node):
                dpg.configure_item(self.active_grid_node, show=False)

    def update_overlay(self):
        """Calculates coordinates and HU values for this specific viewer."""
        if self.current_image_id is None:
            dpg.set_value(self.overlay_tag, "")
            return

        # 1. Use the mutualized helper to get image-space coordinates
        pix_x, pix_y = self.get_mouse_to_pixel_coords()

        # If the mouse isn't hovering over this specific viewer, pix_x will be None
        # is_hover = dpg.is_item_hovered(f"win_{self.tag}")
        if pix_x is None:
            dpg.set_value(self.overlay_tag, "")
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
            t = self.current_image_model.get_orientation_str(self.orientation)
            self.mouse_pixel_value = val
            self.mouse_pixel_coord = v
            self.mouse_phys_coord = phys
            overlay_text = (
                f"{t} {val:.1f}\n"
                f"Vox: {v[0]:.1f}, {v[1]:.1f}, {v[2]:.1f}\n"
                f"Phys: {phys[0]:.1f}, {phys[1]:.1f}, {phys[2]:.1f} mm"
            )
            dpg.set_value(self.overlay_tag, overlay_text)
        else:
            dpg.set_value(self.overlay_tag, "Out of image")

        # 5. Position the text at the bottom-left of the viewer window
        win_h = dpg.get_item_height(f"win_{self.tag}")
        text_size = dpg.get_item_rect_size(self.overlay_tag)
        text_h = text_size[1] if text_size[1] > 0 else 60

        dpg.set_item_pos(self.overlay_tag, [5, win_h - text_h - 5])

    def update_window_level(self, ww, wl):
        self.current_image_model.ww = ww
        self.current_image_model.wl = wl
        self.update_sidebar_window_level()
        self.controller.update_all_viewers_of_image(self.current_image_id)


    def update_sidebar_crosshair(self):
        """Explicitly updates the sidebar with current crosshair data."""
        if self.crosshair_pixel_coord is not None and self.crosshair_phys_coord is not None:
            dpg.set_value("info_vox", fmt(self.crosshair_pixel_coord, 1))
            dpg.set_value("info_phys", fmt(self.crosshair_phys_coord, 1))
            dpg.set_value("info_val", f"{self.crosshair_pixel_value:g}")

    def update_sidebar_info(self):
        """Pushes static image metadata to the sidebar."""
        if self.current_image_id is None:
            dpg.set_value("info_name", "No active image")
            dpg.set_value("info_size", "")
            dpg.set_value("info_spacing", "")
            dpg.set_value("info_origin", "")
            dpg.set_value("info_memory", "")
            return

        img = self.current_image_model
        dpg.set_value("info_name", self.current_image_model.name)
        dpg.set_value("info_name_label", self.tag)
        dpg.set_value("info_voxel_type", f"{img.pixel_type}")
        dpg.set_value("info_size", f"{img.data.shape[2]} x {img.data.shape[1]} x {img.data.shape[1]}")

        # display spacing and origin (rounded)
        dpg.set_value("info_spacing", fmt(img.spacing, 4))
        dpg.set_value("info_origin", fmt(img.origin, 2))

        # orientation matrix ?
        dpg.set_value("info_matrix", fmt(img.matrix, 1))

        # Memory Calculation
        im = self.current_image_model
        dpg.set_value("info_memory", f"{im.sitk_image.GetNumberOfPixels():,} pixels    {im.memory_mb:g} MB")

        self.update_sidebar_window_level()

    def update_sidebar_window_level(self):
        img_model = self.current_image_model
        dpg.set_value("info_window", f"{img_model.ww:g}")
        dpg.set_value("info_level", f"{img_model.wl:g}")

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
            # self.on_window_resize()
            self.controller.main_windows.on_window_resize()
        elif key == dpg.mvKey_F1:
            self.set_orientation("Axial")
        elif key == dpg.mvKey_F2:
            self.set_orientation("Sagittal")
        elif key == dpg.mvKey_F3:
            self.set_orientation("Coronal")
        elif key == dpg.mvKey_W:
            self.apply_local_auto_window()
        elif key == dpg.mvKey_L:
            # Toggle interpolation state
            self.current_image_model.interpolation_linear = not self.current_image_model.interpolation_linear
            # Refresh all viewers
            for v in self.controller.viewers.values():
                v.update_render()
        elif key == dpg.mvKey_G:
            # Toggle grid state
            self.current_image_model.grid_mode = not self.current_image_model.grid_mode
            # Refresh all viewers
            for v in self.controller.viewers.values():
                v.update_render()

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
        new_idx = self.slice_idx + increment
        self.slice_idx = np.clip(new_idx, 0, max_s)

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
            pix_x, pix_y = self.get_mouse_to_pixel_coords(ignore_hover=True)
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
            # Adjust sensitivity if needed
            #img_model.ww = max(1, img_model.ww + step_x * 2)
            #img_model.wl -= step_y * 2
            #self.update_sidebar_window_level()
            #self.controller.update_all_viewers_of_image(self.current_image_id)
            img_model.ww = max(1, img_model.ww + step_x * 2)
            img_model.wl -= step_y * 2
            self.update_window_level(img_model.ww, img_model.wl)

    def on_zoom(self, direction):
        if self.current_image_id is None:
            return

        # 1. Use drawing coordinates (local to the drawlist) for precision
        mouse_x, mouse_y = dpg.get_drawing_mouse_pos()

        # 2. Get the actual current display dimensions from your stored state
        pmin = self.current_pmin
        pmax = self.current_pmax
        old_w = pmax[0] - pmin[0]
        old_h = pmax[1] - pmin[1]

        # 3. Calculate mouse relative to the image top-left
        rel_m_x = mouse_x - pmin[0]
        rel_m_y = mouse_y - pmin[1]

        # 4. Apply zoom factor
        old_zoom = self.zoom
        self.zoom = np.clip(self.zoom * (1.1 if direction == "in" else 0.9), 0.1, 200.0)
        ratio = self.zoom / old_zoom

        # 5. Calculate growth
        dw = (old_w * ratio) - old_w
        dh = (old_h * ratio) - old_h

        # 6. Update Pan: The (dw / 2) term compensates for the
        # automatic centering shift performed in the resize() function.
        self.pan_offset[0] -= (rel_m_x * (ratio - 1)) - (dw / 2)
        self.pan_offset[1] -= (rel_m_y * (ratio - 1)) - (dh / 2)

        # 7. Trigger resize to recalculate pmin/pmax and refresh render
        self.controller.main_windows.on_window_resize()
