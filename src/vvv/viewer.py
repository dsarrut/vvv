import dearpygui.dearpygui as dpg
import numpy as np
from .utils import *


# from .core import ViewState


class SliceViewer:
    def __init__(self, tag_id, controller):
        self.tag = tag_id
        self.controller = controller
        # self.view_state = None  # slice/pan/zoom variables
        self.image_id = None
        self.image_model = None
        self.active_strips_node = None  # FIXME in image model
        self.active_grid_node = None  # FIXME in image model
        # dpg tags
        self.texture_tag = f"tex_{tag_id}"
        self.image_tag = f"img_{tag_id}"
        self.strips_a_tag = f"strips_node_A_{tag_id}"
        self.strips_b_tag = f"strips_node_B_{tag_id}"
        self.grid_a_tag = f"grid_node_A_{tag_id}"
        self.grid_b_tag = f"grid_node_B_{tag_id}"
        self.overlay_tag = f"overlay_{tag_id}"
        self.crosshair_tag = f"crosshair_node_{tag_id}"
        # --- GUI options ---
        # Use a 4-pixel buffer to prevent the window border from cutting the image
        self.margin_left = 4
        self.margin_top = 4
        # used during mouse drag
        self.last_dy = 0
        self.last_dx = 0
        self.current_pmin = [0, 0]
        self.current_pmax = [1, 1]
        self.orientation = "Axial"
        # Transient mouse data (Viewer specific)
        self.mouse_phys_coord = None
        self.mouse_pixel_coord = None
        self.mouse_pixel_value = None

        # default init texture
        with dpg.texture_registry():
            dpg.add_dynamic_texture(width=1, height=1,
                                    default_value=np.zeros(4),
                                    tag=self.texture_tag)

    @property
    def slice_idx(self):
        return self.image_model.slices[self.orientation] if self.image_model else None

    @slice_idx.setter
    def slice_idx(self, value):
        if self.image_model: self.image_model.slices[self.orientation] = value

    @property
    def pan_offset(self):
        return self.image_model.pan[self.orientation] if self.image_model else [0, 0]

    @pan_offset.setter
    def pan_offset(self, value):
        if self.image_model: self.image_model.pan[self.orientation] = value

    @property
    def zoom(self):
        return self.image_model.zoom if self.image_model else 1.0

    @zoom.setter
    def zoom(self, value):
        if self.image_model: self.image_model.zoom = value

    def set_image(self, img_id):
        # set the image info to this viewer
        self.image_id = img_id
        self.image_model = self.controller.images[self.image_id]
        print(f"set image {self.tag} {img_id}")

        # Sync viewer slice to image crosshair if it exists
        self.set_current_slice_to_crosshair()

        # create the image (texture)
        self.init_slice_texture()

        # resize to update the zoom
        win_w = dpg.get_item_width(f"win_{self.tag}")
        win_h = dpg.get_item_height(f"win_{self.tag}")
        self.resize(win_w, win_h)

        # update the other elements (sidebar, overlay, crosshair)
        self.update_sidebar_info()
        self.update_overlay()
        self.draw_crosshair()  # also update sidebar_crosshair
        self.update_render()

    def set_current_slice_to_crosshair(self):
        img_model = self.image_model
        vx, vy, vz = img_model.crosshair_pixel_coord
        print(f"current is {self.slice_idx}")
        if self.orientation == "Axial":
            self.slice_idx = int(np.clip(vz, 0, img_model.data.shape[0] - 1))
        elif self.orientation == "Sagittal":
            self.slice_idx = int(np.clip(vx, 0, img_model.data.shape[2] - 1))
        elif self.orientation == "Coronal":
            self.slice_idx = int(np.clip(vy, 0, img_model.data.shape[1] - 1))
        print(f"===> after is {self.slice_idx}")

    def init_slice_texture(self):
        """Manages dynamic texture creation for the image."""
        img = self.image_model
        _, shape = img.get_slice_rgba(self.slice_idx, self.orientation)
        h, w = shape[0], shape[1]

        new_texture_tag = f"tex_{self.tag}_{self.orientation}_{w}x{h}"

        if not dpg.does_item_exist(new_texture_tag):
            with dpg.texture_registry():
                dpg.add_dynamic_texture(width=w, height=h, default_value=np.zeros(w * h * 4), tag=new_texture_tag)

        if self.texture_tag != new_texture_tag and dpg.does_item_exist(self.texture_tag):
            if "Axial_1x1" not in self.texture_tag:
                dpg.delete_item(self.texture_tag)

        self.texture_tag = new_texture_tag
        if dpg.does_item_exist(self.image_tag):
            dpg.configure_item(self.image_tag, texture_tag=self.texture_tag)

    def init_crosshair_NOPE(self):
        """Initializes the slice position and crosshair state."""
        img = self.image_model
        if img.crosshair_pixel_coord is not None:
            # Sync viewer slice to image crosshair if it exists
            vx, vy, vz = img.crosshair_pixel_coord
            if self.orientation == "Axial":
                self.slice_idx = int(vz)
            elif self.orientation == "Sagittal":
                self.slice_idx = int(vx)
            else:
                self.slice_idx = int(vy)
        else:
            # Otherwise, default to the center and compute initial crosshair data
            _, shape = img.get_slice_rgba(self.slice_idx, self.orientation)
            self.update_crosshair_data(shape[1] // 2, shape[0] // 2)

    def update_crosshair_data(self, pix_x, pix_y):
        """COMPUTATION: Maps 2D pixels back to 3D Voxel Indices and stores in Model."""
        img_model = self.image_model
        _, shape = img_model.get_slice_rgba(self.slice_idx, self.orientation)
        real_h, real_w = shape[0], shape[1]

        print(self.orientation)
        if self.orientation == "Axial":
            v = [pix_x, pix_y, self.slice_idx]
        elif self.orientation == "Sagittal":
            v = [self.slice_idx, real_w - pix_x, real_h - pix_y]
        else:
            v = [pix_x, self.slice_idx, real_h - pix_y]

        img_model.crosshair_pixel_coord = v
        print(v)
        img_model.crosshair_phys_coord = img_model.voxel_coord_to_physic_coord(np.array(v))
        ix, iy, iz = [int(np.clip(c, 0, limit - 1)) for c, limit in
                      zip(v, [img_model.data.shape[2], img_model.data.shape[1], img_model.data.shape[0]])]
        img_model.crosshair_pixel_value = img_model.data[iz, iy, ix]

    def set_image_good(self, img_id):
        self.image_id = img_id
        self.image_model = self.controller.images[self.image_id]

        # Create a persistent state for this view
        print(f'set_image called {self.tag} {img_id}, create view state')
        # self.view_state = ViewState(self.current_image_model)

        # Sync viewer slice to image crosshair if it exists
        img = self.image_model
        if img.crosshair_pixel_coord is not None:
            vx, vy, vz = img.crosshair_pixel_coord
            if self.orientation == "Axial":
                self.slice_idx = int(vz)
            elif self.orientation == "Sagittal":
                self.slice_idx = int(vx)
            else:
                self.slice_idx = int(vy)
            self.reposition_crosshair_from_3d()
        else:
            _, shape = img.get_slice_rgba(self.slice_idx, self.orientation)
            self.draw_crosshair(shape[1] // 2, shape[0] // 2)

        _, shape = img.get_slice_rgba(self.slice_idx, self.orientation)
        h, w = shape[0], shape[1]

        new_texture_tag = f"tex_{self.tag}_{self.orientation}_{w}x{h}"

        if not dpg.does_item_exist(new_texture_tag):
            with dpg.texture_registry():
                dpg.add_dynamic_texture(width=w, height=h, default_value=np.zeros(w * h * 4), tag=new_texture_tag)

        if self.texture_tag != new_texture_tag and dpg.does_item_exist(self.texture_tag):
            if "Axial_1x1" not in self.texture_tag: dpg.delete_item(self.texture_tag)

        self.texture_tag = new_texture_tag
        if dpg.does_item_exist(self.image_tag):
            dpg.configure_item(self.image_tag, texture_tag=self.texture_tag)

        self.update_sidebar_info()
        self.update_render()

    def reposition_crosshair_from_3d(self):
        img_model = self.image_model
        if img_model.crosshair_pixel_coord is None or self.image_id is None:
            return

        vx, vy, vz = img_model.crosshair_pixel_coord
        _, shape = img_model.get_slice_rgba(self.slice_idx, self.orientation)
        real_h, real_w = shape[0], shape[1]

        if self.orientation == "Axial":
            tx, ty = vx, vy
        elif self.orientation == "Sagittal":
            tx, ty = real_w - vy, real_h - vz
        else:
            tx, ty = vx, real_h - vz

        self.draw_crosshair(tx, ty)

    def set_orientation(self, orientation):
        self.orientation = orientation
        if self.image_id:
            # Re-initialize view for new orientation
            self.set_image(self.image_id)
        self.controller.main_windows.on_window_resize()

    def get_mouse_to_pixel_coords(self, ignore_hover=False):
        if not self.image_id: return None, None
        if not ignore_hover and not dpg.is_item_hovered(f"win_{self.tag}"): return None, None

        mouse_x, mouse_y = dpg.get_drawing_mouse_pos()
        pmin, pmax = self.current_pmin, self.current_pmax
        rel_x, rel_y = mouse_x - pmin[0], mouse_y - pmin[1]
        disp_w, disp_h = pmax[0] - pmin[0], pmax[1] - pmin[1]

        if not (0 <= rel_x <= disp_w and 0 <= rel_y <= disp_h): return None, None

        img_model = self.controller.images[self.image_id]
        _, shape = img_model.get_slice_rgba(self.slice_idx, self.orientation)
        h, w = shape[0], shape[1]

        return (rel_x / disp_w) * w, (rel_y / disp_h) * h

    def resize(self, quad_w, quad_h):
        if not dpg.does_item_exist(f"win_{self.tag}"): return
        dpg.set_item_width(f"win_{self.tag}", quad_w)
        dpg.set_item_height(f"win_{self.tag}", quad_h)

        if dpg.does_item_exist(f"drawlist_{self.tag}"):
            dpg.set_item_width(f"drawlist_{self.tag}", quad_w)
            dpg.set_item_height(f"drawlist_{self.tag}", quad_h)

        if self.image_id is None: return

        img = self.controller.images[self.image_id]
        _, shape = img.get_slice_rgba(self.slice_idx, self.orientation)
        pix_h, pix_w = shape[0], shape[1]

        sw, sh = img.get_physical_aspect_ratio(self.orientation)
        mm_w, mm_h = pix_w * sw, pix_h * sh

        target_w, target_h = quad_w - self.margin_left, quad_h - self.margin_top
        base_scale = min(target_w / mm_w, target_h / mm_h)
        final_scale = base_scale * self.zoom

        new_w, new_h = int(mm_w * final_scale), int(mm_h * final_scale)

        off_x = (target_w - new_w) // 2 + self.margin_left + self.pan_offset[0]
        off_y = (target_h - new_h) // 2 + self.margin_top + self.pan_offset[1]

        self.current_pmin = [off_x, off_y]
        self.current_pmax = [off_x + new_w, off_y + new_h]
        print(f"resize: {self.current_pmin}, {self.current_pmax}")

        # Update the standard image primitive
        if dpg.does_item_exist(self.image_tag):
            dpg.configure_item(self.image_tag, pmin=self.current_pmin, pmax=self.current_pmax)

        # Refresh the display (this will choose between Texture or Rectangles)
        self.update_render()

    def sync_other_views(self):
        if self.image_id is None: return
        pix_x, pix_y = self.get_mouse_to_pixel_coords(ignore_hover=True)
        if pix_x is None: return

        # 1. Update the state for the current image
        self.update_crosshair_data(pix_x, pix_y)

        img_model = self.image_model
        vx, vy, vz = img_model.crosshair_pixel_coord

        # 2. Update and draw in all other viewers with the same image
        for viewer in self.controller.viewers.values():
            if viewer.image_id == self.image_id:
                # Update slice indices to match the 3D voxel
                if viewer.orientation == "Axial":
                    viewer.slice_idx = int(np.clip(vz, 0, img_model.data.shape[0] - 1))
                elif viewer.orientation == "Sagittal":
                    viewer.slice_idx = int(np.clip(vx, 0, img_model.data.shape[2] - 1))
                elif viewer.orientation == "Coronal":
                    viewer.slice_idx = int(np.clip(vy, 0, img_model.data.shape[1] - 1))

                viewer.draw_crosshair()  # also update the sidebar crosshair
                viewer.update_render()

        self.controller.main_windows.on_window_resize()

    def sync_other_views_good(self):
        """Synchronizes other views and centers them on the crosshair."""
        if self.image_id is None:
            return

        # Get the 3D voxel index under the mouse in THIS viewer
        pix_x, pix_y = self.get_mouse_to_pixel_coords(ignore_hover=True)
        if pix_x is None:
            return

        # Update the crosshair in the current window
        self.draw_crosshair(pix_x, pix_y)

        img_model = self.controller.images[self.image_id]
        _, shape = img_model.get_slice_rgba(self.slice_idx, self.orientation)
        real_h, real_w = shape[0], shape[1]

        # Use the voxel indices stored in ImageModel by draw_crosshair
        vx, vy, vz = img_model.crosshair_pixel_coord

        for viewer in self.controller.viewers.values():
            if viewer.image_id == self.image_id and viewer.tag != self.tag:
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

                viewer.draw_crosshair(tx, ty)
                viewer.update_render()

        self.controller.main_windows.on_window_resize()

    def draw_voxel_grid(self, h, w):
        node_a, node_b = self.grid_a_tag, self.grid_b_tag
        back_node = node_b if self.active_grid_node == node_a else node_a

        if dpg.does_item_exist(back_node):
            dpg.delete_item(back_node, children_only=True)
        else:
            return

        pmin, pmax = self.current_pmin, self.current_pmax
        vox_w, vox_h = (pmax[0] - pmin[0]) / w, (pmax[1] - pmin[1]) / h
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
        if dpg.does_item_exist(self.active_grid_node): dpg.configure_item(self.active_grid_node, show=False)
        self.active_grid_node = back_node

    def draw_crosshair(self):
        """DRAWING: Render the crosshair lines based on the ImageModel state."""
        print(f"draw_crosshair: {self.orientation}")
        node_tag = self.crosshair_tag
        if not dpg.does_item_exist(node_tag) or self.image_model.crosshair_pixel_coord is None:
            return
        dpg.delete_item(node_tag, children_only=True)

        img_model = self.image_model
        vx, vy, vz = img_model.crosshair_pixel_coord
        print(f"draw_crosshair: {vx}, {vy}, {vz}")
        # FIXME why get slice here ?
        _, shape = img_model.get_slice_rgba(self.slice_idx, self.orientation)
        real_h, real_w = shape[0], shape[1]

        # Map 3D Voxel back to this viewer's 2D space
        if self.orientation == "Axial":
            tx, ty = vx, vy
        elif self.orientation == "Sagittal":
            tx, ty = real_w - vy, real_h - vz
        else:
            tx, ty = vx, real_h - vz

        pmin, pmax = self.current_pmin, self.current_pmax
        disp_w, disp_h = pmax[0] - pmin[0], pmax[1] - pmin[1]
        screen_x = (tx / real_w) * disp_w + pmin[0]
        screen_y = (ty / real_h) * disp_h + pmin[1]

        color = [0, 246, 7, 180]
        dpg.draw_line([screen_x, pmin[1]], [screen_x, pmin[1] + disp_h], color=color, parent=node_tag)
        dpg.draw_line([pmin[0], screen_y], [pmin[0] + disp_w, screen_y], color=color, parent=node_tag)
        self.update_sidebar_crosshair()

    def draw_crosshair_good(self, pix_x, pix_y):
        node_tag = self.crosshair_tag
        if not dpg.does_item_exist(node_tag): return
        dpg.delete_item(node_tag, children_only=True)

        img_model = self.image_model
        _, shape = img_model.get_slice_rgba(self.slice_idx, self.orientation)
        real_h, real_w = shape[0], shape[1]

        if self.orientation == "Axial":
            v = [pix_x, pix_y, self.slice_idx]
        elif self.orientation == "Sagittal":
            v = [self.slice_idx, real_w - pix_x, real_h - pix_y]
        else:
            v = [pix_x, self.slice_idx, real_h - pix_y]

        # 2. Save these to the ImageModel
        img_model.crosshair_pixel_coord = v
        img_model.crosshair_phys_coord = img_model.voxel_coord_to_physic_coord(np.array(v))

        # 3. Fetch the pixel value safely
        ix, iy, iz = [int(np.clip(c, 0, limit - 1)) for c, limit in
                      zip(v, [img_model.data.shape[2], img_model.data.shape[1], img_model.data.shape[0]])]
        img_model.crosshair_pixel_value = img_model.data[iz, iy, ix]

        pmin, pmax = self.current_pmin, self.current_pmax
        disp_w, disp_h = pmax[0] - pmin[0], pmax[1] - pmin[1]
        screen_x = (pix_x / real_w) * disp_w + pmin[0]
        screen_y = (pix_y / real_h) * disp_h + pmin[1]

        color = [0, 246, 7, 180]
        dpg.draw_line([screen_x, pmin[1]], [screen_x, pmin[1] + disp_h], color=color, parent=node_tag)
        dpg.draw_line([pmin[0], screen_y], [pmin[0] + disp_w, screen_y], color=color, parent=node_tag)
        self.update_sidebar_crosshair()

    def draw_voxels_as_strips(self, rgba_flat, h, w):
        node_a, node_b = self.strips_a_tag, self.strips_b_tag
        back_node = node_b if self.active_strips_node == node_a else node_a
        dpg.delete_item(back_node, children_only=True)

        pmin, pmax = self.current_pmin, self.current_pmax
        vox_w, vox_h = (pmax[0] - pmin[0]) / w, (pmax[1] - pmin[1]) / h
        win_w, win_h = dpg.get_item_width(f"win_{self.tag}"), dpg.get_item_height(f"win_{self.tag}")
        if not win_w or not win_h: return

        start_x, end_x = max(0, int(-pmin[0] / vox_w)), min(w, int((win_w - pmin[0]) / vox_w) + 1)
        start_y, end_y = max(0, int(-pmin[1] / vox_h)), min(h, int((win_h - pmin[1]) / vox_h) + 1)
        pixels = rgba_flat.reshape(h, w, 4)

        for y in range(start_y, end_y):
            y_pos = pmin[1] + (y * vox_h) + (vox_h / 2)
            for x in range(start_x, end_x):
                x1 = pmin[0] + (x * vox_w)
                color = [int(c * 255) for c in pixels[y, x]]
                dpg.draw_line([x1, y_pos], [x1 + vox_w, y_pos], color=color, thickness=vox_h + 1, parent=back_node)

        dpg.configure_item(back_node, show=True)
        if dpg.does_item_exist(self.active_strips_node): dpg.configure_item(self.active_strips_node, show=False)
        self.active_strips_node = back_node

    def should_use_voxels_strips(self):
        if not self.image_model or self.image_model.interpolation_linear: return False
        win_w, win_h = dpg.get_item_width(f"win_{self.tag}"), dpg.get_item_height(f"win_{self.tag}")
        if not win_w or not win_h: return False
        pmin, pmax = self.current_pmin, self.current_pmax
        _, shape = self.image_model.get_slice_rgba(self.slice_idx, self.orientation)
        vox_w, vox_h = (pmax[0] - pmin[0]) / shape[1], (pmax[1] - pmin[1]) / shape[0]
        start_x, end_x = max(0, int(-pmin[0] / vox_w)), min(shape[1], int((win_w - pmin[0]) / vox_w) + 1)
        start_y, end_y = max(0, int(-pmin[1] / vox_h)), min(shape[0], int((win_h - pmin[1]) / vox_h) + 1)
        return 0 < (end_x - start_x) * (end_y - start_y) < 1500

    def apply_local_auto_window(self, search_radius=25):
        if self.image_id is None: return
        pix_x, pix_y = self.get_mouse_to_pixel_coords(ignore_hover=True)
        if pix_x is None: return
        img_model = self.image_model
        _, shape = img_model.get_slice_rgba(self.slice_idx, self.orientation)
        real_h, real_w = shape[0], shape[1]
        pmin, pmax = self.current_pmin, self.current_pmax
        disp_w, disp_h = pmax[0] - pmin[0], pmax[1] - pmin[1]
        if disp_w <= 0 or disp_h <= 0: return
        vx_r_x, vx_r_y = (search_radius / disp_w) * real_w, (search_radius / disp_h) * real_h
        x0, x1 = int(max(0, pix_x - vx_r_x)), int(min(real_w, pix_x + vx_r_x))
        y0, y1 = int(max(0, pix_y - vx_r_y)), int(min(real_h, pix_y + vx_r_y))
        if x1 <= x0 or y1 <= y0: return
        if self.orientation == "Axial":
            patch = img_model.data[self.slice_idx, y0:y1, x0:x1]
        elif self.orientation == "Sagittal":
            z_idx0, z_idx1 = int(max(0, real_h - y1)), int(min(img_model.data.shape[0], real_h - y0))
            y_idx0, y_idx1 = int(max(0, real_w - x1)), int(min(img_model.data.shape[1], real_w - x0))
            patch = img_model.data[z_idx0:z_idx1, y_idx0:y_idx1, self.slice_idx]
        else:
            z_idx0, z_idx1 = int(max(0, real_h - y1)), int(min(img_model.data.shape[0], real_h - y0))
            patch = img_model.data[z_idx0:z_idx1, self.slice_idx, x0:x1]
        if patch.size > 0:
            p_min, p_max = np.percentile(patch, [2, 98])
            self.update_window_level(max(1, p_max - p_min), (p_max + p_min) / 2)

    def update_render(self):
        if self.image_id is None:
            return

        # compute the slice texture
        img_model = self.image_model
        rgba_flat, shape = img_model.get_slice_rgba(self.slice_idx, self.orientation)

        # close zoom mode
        if self.should_use_voxels_strips():
            dpg.configure_item(self.image_tag, show=False)
            self.draw_voxels_as_strips(rgba_flat, shape[0], shape[1])
        else:
            if dpg.does_item_exist(self.active_strips_node): dpg.configure_item(self.active_strips_node, show=False)
            dpg.configure_item(self.image_tag, show=True)
            dpg.set_value(self.texture_tag, rgba_flat)

        # grid mode
        if self.image_model.grid_mode:
            self.draw_voxel_grid(shape[0], shape[1])
        elif dpg.does_item_exist(self.active_grid_node):
            dpg.configure_item(self.active_grid_node, show=False)

    def update_overlay(self):
        if self.image_id is None:
            dpg.set_value(self.overlay_tag, "")
            return
        pix_x, pix_y = self.get_mouse_to_pixel_coords()
        if pix_x is None:
            dpg.set_value(self.overlay_tag, "")
            return
        img_model = self.image_model
        idx = self.slice_idx
        _, shape = img_model.get_slice_rgba(idx, self.orientation)
        real_h, real_w = shape[0], shape[1]
        if self.orientation == "Axial":
            v = np.array([pix_x, pix_y, idx])
        elif self.orientation == "Sagittal":
            v = np.array([idx, real_w - pix_x, real_h - pix_y])
        else:
            v = np.array([pix_x, idx, real_h - pix_y])
        phys = img_model.voxel_coord_to_physic_coord(v)
        ix, iy, iz = int(v[0]), int(v[1]), int(v[2])
        max_z, max_y, max_x = img_model.data.shape
        if 0 <= ix < max_x and 0 <= iy < max_y and 0 <= iz < max_z:
            val = img_model.data[iz, iy, ix]
            self.mouse_pixel_value, self.mouse_pixel_coord, self.mouse_phys_coord = val, v, phys
            dpg.set_value(self.overlay_tag,
                          f"{img_model.get_orientation_str(self.orientation)} {val:.1f}\nVox: {v[0]:.1f}, {v[1]:.1f}, {v[2]:.1f}\nPhys: {phys[0]:.1f}, {phys[1]:.1f}, {phys[2]:.1f} mm")
        else:
            dpg.set_value(self.overlay_tag, "Out of image")
        win_h = dpg.get_item_height(f"win_{self.tag}")
        ts = dpg.get_item_rect_size(self.overlay_tag)
        dpg.set_item_pos(self.overlay_tag, [5, win_h - (ts[1] if ts[1] > 0 else 60) - 5])

    def update_window_level(self, ww, wl):
        self.view_state.ww, self.view_state.wl = ww, wl
        self.update_sidebar_window_level()
        self.controller.update_all_viewers_of_image(self.image_id)

    def update_sidebar_crosshair(self):
        img = self.image_model
        if img and img.crosshair_pixel_coord is not None:
            dpg.set_value("info_vox", fmt(img.crosshair_pixel_coord, 1))
            dpg.set_value("info_phys", fmt(img.crosshair_phys_coord, 1))
            dpg.set_value("info_val", f"{img.crosshair_pixel_value:g}")

    def update_sidebar_info(self):
        if self.image_id is None:
            for t in ["info_name", "info_size", "info_spacing", "info_origin", "info_memory"]: dpg.set_value(t, "")
            return
        img = self.image_model
        dpg.set_value("info_name", img.name)
        dpg.set_value("info_name_label", self.tag)
        dpg.set_value("info_voxel_type", f"{img.pixel_type}")
        dpg.set_value("info_size", f"{img.data.shape[2]} x {img.data.shape[1]} x {img.data.shape[0]}")
        dpg.set_value("info_spacing", fmt(img.spacing, 4))
        dpg.set_value("info_origin", fmt(img.origin, 2))
        dpg.set_value("info_matrix", fmt(img.matrix, 1))
        dpg.set_value("info_memory", f"{img.sitk_image.GetNumberOfPixels():,} px    {img.memory_mb:g} MB")
        self.update_sidebar_window_level()

    def update_sidebar_window_level(self):
        # if self.view_state:
        dpg.set_value("info_window", f"{self.image_model.ww:g}")
        dpg.set_value("info_level", f"{self.image_model.wl:g}")

    def on_key_press(self, key):
        if key == dpg.mvKey_I:
            self.on_zoom("in")
        elif key == dpg.mvKey_O:
            self.on_zoom("out")
        elif key == dpg.mvKey_R:
            self.zoom, self.pan_offset = 1.0, [0, 0]
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
            self.image_model.interpolation_linear = not self.image_model.interpolation_linear
            for v in self.controller.viewers.values(): v.update_render()
        elif key == dpg.mvKey_G:
            self.image_model.grid_mode = not self.image_model.grid_mode
            for v in self.controller.viewers.values(): v.update_render()

    def on_scroll(self, delta):
        if self.image_id is None: return
        inc = 1 if delta > 0 else -1
        img = self.image_model
        if self.orientation == "Axial":
            max_s = img.data.shape[0] - 1
        elif self.orientation == "Sagittal":
            max_s = img.data.shape[2] - 1
        else:
            max_s = img.data.shape[1] - 1
        self.slice_idx = np.clip(self.slice_idx + inc, 0, max_s)
        self.update_render()

    def on_drag(self, data):
        if self.image_id is None: return
        sx, sy = data[1] - self.last_dx, data[2] - self.last_dy
        self.last_dx, self.last_dy = data[1], data[2]
        is_ctrl, is_shift = dpg.is_key_down(dpg.mvKey_LControl) or dpg.is_key_down(dpg.mvKey_RControl), dpg.is_key_down(
            dpg.mvKey_LShift) or dpg.is_key_down(dpg.mvKey_RShift)
        if not is_ctrl and not is_shift and dpg.is_mouse_button_down(dpg.mvMouseButton_Left):
            px, py = self.get_mouse_to_pixel_coords(ignore_hover=True)
            if px is not None: self.sync_other_views()
        elif is_ctrl and dpg.is_mouse_button_down(dpg.mvMouseButton_Left):
            self.pan_offset[0] += sx
            self.pan_offset[1] += sy
            self.controller.main_windows.on_window_resize()
        elif is_shift and dpg.is_mouse_button_down(dpg.mvMouseButton_Left):
            self.update_window_level(max(1, self.image_model.ww + sx * 2), self.image_model.wl - sy * 2)

    def on_zoom(self, direction):
        if self.image_id is None: return
        mx, my = dpg.get_drawing_mouse_pos()
        pmin, pmax = self.current_pmin, self.current_pmax
        ow, oh = pmax[0] - pmin[0], pmax[1] - pmin[1]
        rx, ry = mx - pmin[0], my - pmin[1]
        oz = self.zoom
        self.zoom = np.clip(self.zoom * (1.1 if direction == "in" else 0.9), 0.1, 200.0)
        ratio = self.zoom / oz
        dw, dh = (ow * ratio) - ow, (oh * ratio) - oh
        self.pan_offset[0] -= (rx * (ratio - 1)) - (dw / 2)
        self.pan_offset[1] -= (ry * (ratio - 1)) - (dh / 2)
        self.controller.main_windows.on_window_resize()
