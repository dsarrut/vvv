import dearpygui.dearpygui as dpg
import numpy as np
from .utils import *


class SliceViewer:
    def __init__(self, tag_id, controller):
        self.tag = tag_id
        self.controller = controller
        self.image_id = None
        self.image_model = None
        self.active_strips_node = None  # FIXME in image model ?
        self.active_grid_node = None  # FIXME in image model ?

        """
        The dirty flag: if True the image, should be rendered
        Scope = Local
        The data is the same, but the camera moved or the UI decoration changed.
        Ex: Panning, Zooming, toggling the "Crosshair" visibility, or resizing the window.
        """
        self.needs_refresh = True
        self.needs_recenter = None

        # dpg tags
        self.texture_tag = f"tex_{tag_id}"
        self.image_tag = f"img_{tag_id}"
        self.strips_a_tag = f"strips_node_A_{tag_id}"
        self.strips_b_tag = f"strips_node_B_{tag_id}"
        self.grid_a_tag = f"grid_node_A_{tag_id}"
        self.grid_b_tag = f"grid_node_B_{tag_id}"
        self.axis_a_tag = f"axes_node_A_{tag_id}"
        self.axis_b_tag = f"axes_node_B_{tag_id}"
        self.overlay_tag = f"overlay_{tag_id}"
        self.crosshair_tag = f"crosshair_node_{tag_id}"
        self.xh_line_h = f"xh_h_{tag_id}"  # Tag for horizontal line
        self.xh_line_v = f"xh_v_{tag_id}"  # Tag for vertical line
        self.xh_initialized = False

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

        # for double buffering axis
        self.axes_nodes = None
        self.active_axes_idx = 0

        # default init texture
        with dpg.texture_registry():
            dpg.add_dynamic_texture(width=1, height=1,
                                    default_value=np.zeros(4),
                                    tag=self.texture_tag)

    @property
    def slice_idx(self):
        if not self.image_model or self.orientation not in self.image_model.slices:
            return 0  # Safe default for Histogram mode
        return self.image_model.slices[self.orientation]

    @slice_idx.setter
    def slice_idx(self, value):
        if self.image_model: self.image_model.slices[self.orientation] = value

    @property
    def pan_offset(self):
        if not self.image_model or self.orientation not in self.image_model.pan:
            return [0, 0]
        return self.image_model.pan[self.orientation]

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

        # Render
        self.image_model.needs_render = True

    def set_current_slice_to_crosshair(self):
        img_model = self.image_model
        vx, vy, vz = img_model.crosshair_pixel_coord
        if self.orientation == "Axial":
            self.slice_idx = int(np.clip(vz, 0, img_model.data.shape[0] - 1))
        elif self.orientation == "Sagittal":
            self.slice_idx = int(np.clip(vx, 0, img_model.data.shape[2] - 1))
        elif self.orientation == "Coronal":
            self.slice_idx = int(np.clip(vy, 0, img_model.data.shape[1] - 1))

    def set_orientation(self, orientation):
        self.orientation = orientation
        if self.image_id:
            # Re-initialize the view for a new orientation
            self.set_image(self.image_id)
        self.controller.main_windows.on_window_resize()

    def init_slice_texture(self):
        """Manages dynamic texture creation for the image."""
        if self.orientation == "Histogram":
            return

        img = self.image_model
        _, shape = img.get_slice_rgba(self.slice_idx, self.orientation)
        h, w = shape[0], shape[1]

        # Create a unique tag per Viewer, Image, and Orientation
        # This acts as a cache key
        new_texture_tag = f"tex_{self.tag}_{self.image_id}_{self.orientation}_{w}x{h}"

        # 1. Create it ONLY if it has never been created before
        if not dpg.does_item_exist(new_texture_tag):
            with dpg.texture_registry():
                dpg.add_dynamic_texture(width=w, height=h,
                                        default_value=np.zeros(w * h * 4),
                                        tag=new_texture_tag)

        # 2. Switch the image primitive to this texture
        if dpg.does_item_exist(self.image_tag):
            dpg.configure_item(self.image_tag, texture_tag=new_texture_tag)

        # 3. Simply update our reference without deleting anything
        self.texture_tag = new_texture_tag

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

    def get_axis_labels(self):
        """Returns (horizontal_axis, vertical_axis) and their directions."""
        if self.orientation == "Axial":
            # Horizontal is X (+), Vertical is Y (+)
            return ("x", "y"), (1, 1)
        elif self.orientation == "Sagittal":
            # Horizontal is Y (-), Vertical is Z (-)
            return ("y", "z"), (-1, -1)
        else:  # Coronal
            # Horizontal is X (+), Vertical is Z (-)
            return ("x", "z"), (1, -1)

    def resize(self, quad_w, quad_h):
        if not dpg.does_item_exist(f"win_{self.tag}"): return
        dpg.set_item_width(f"win_{self.tag}", quad_w)
        dpg.set_item_height(f"win_{self.tag}", quad_h)

        if dpg.does_item_exist(f"drawlist_{self.tag}"):
            dpg.set_item_width(f"drawlist_{self.tag}", quad_w)
            dpg.set_item_height(f"drawlist_{self.tag}", quad_h)

        if self.image_id is None: return

        if self.orientation == "Histogram":
            return

        if self.needs_recenter:
            self.pan_offset = self.calculate_pan_to_center_crosshair(quad_w, quad_h)
            self.needs_recenter = False

        new_w, new_h, real_w, real_h, target_w, target_h = self.get_geometry_params(quad_w, quad_h)

        off_x = (target_w - new_w) // 2 + self.margin_left + self.pan_offset[0]
        off_y = (target_h - new_h) // 2 + self.margin_top + self.pan_offset[1]

        self.current_pmin = [off_x, off_y]
        self.current_pmax = [off_x + new_w, off_y + new_h]

        # Update the standard image primitive
        if dpg.does_item_exist(self.image_tag):
            dpg.configure_item(self.image_tag, pmin=self.current_pmin, pmax=self.current_pmax)

        # Refresh the display (this will choose between Texture or Rectangles)
        self.image_model.needs_render = True

    def draw_voxel_grid(self, h, w):
        node_a, node_b = self.grid_a_tag, self.grid_b_tag
        back_node = node_b if self.active_grid_node == node_a else node_a

        if dpg.does_item_exist(back_node):
            dpg.delete_item(back_node, children_only=True)
        else:
            return

        pmin, pmax = self.current_pmin, self.current_pmax
        vox_w, vox_h = (pmax[0] - pmin[0]) / w, (pmax[1] - pmin[1]) / h
        color = self.controller.settings.data["colors"]["grid"]

        # Draw Vertical Lines (along the width)
        for x in range(w + 1):
            lx = pmin[0] + x * vox_w
            dpg.draw_line([lx, pmin[1]], [lx, pmax[1]], color=color, parent=back_node)

        # Draw Horizontal Lines (along the height)
        for y in range(h + 1):
            ly = pmin[1] + y * vox_h
            dpg.draw_line([pmin[0], ly], [pmax[0], ly], color=color, parent=back_node)

        dpg.configure_item(back_node, show=True)
        if dpg.does_item_exist(self.active_grid_node): dpg.configure_item(self.active_grid_node, show=False)
        self.active_grid_node = back_node

    def draw_crosshair(self):
        """DRAWING: Render the crosshair lines based on the ImageModel state."""
        if self.orientation == "Histogram" or not self.image_model:
            return

        node_tag = self.crosshair_tag
        img_model = self.image_model

        # Handle Visibility Toggle
        if not img_model.show_crosshair or img_model.crosshair_pixel_coord is None:
            if dpg.does_item_exist(self.xh_line_h):
                dpg.configure_item(self.xh_line_h, show=False)
                dpg.configure_item(self.xh_line_v, show=False)
            return

        vx, vy, vz = img_model.crosshair_pixel_coord
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

        color = self.controller.settings.data["colors"]["crosshair"]

        if not self.xh_initialized:
            # Create them for the first time
            dpg.draw_line([screen_x, pmin[1]], [screen_x, pmin[1] + disp_h],
                          color=color, parent=node_tag, tag=self.xh_line_v)
            dpg.draw_line([pmin[0], screen_y], [pmin[0] + disp_w, screen_y],
                          color=color, parent=node_tag, tag=self.xh_line_h)
            self.xh_initialized = True
        else:
            # Just update positions - avoid flickering
            dpg.configure_item(self.xh_line_v, p1=[screen_x, pmin[1]],
                               p2=[screen_x, pmin[1] + disp_h], color=color, show=True)
            dpg.configure_item(self.xh_line_h, p1=[pmin[0], screen_y],
                               p2=[pmin[0] + disp_w, screen_y], color=color, show=True)

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

    def draw_orientation_axes(self):
        if self.orientation == "Histogram":
            # Hide axes if they were visible
            if self.axes_nodes:
                dpg.configure_item(self.axes_nodes[0], show=False)
                dpg.configure_item(self.axes_nodes[1], show=False)
            return

        # Determine which node is currently hidden (the "back" buffer)
        back_idx = 1 - self.active_axes_idx
        back_node = self.axes_nodes[back_idx]
        front_node = self.axes_nodes[self.active_axes_idx]

        # Clear only the back node
        dpg.delete_item(back_node, children_only=True)

        labels, directions = self.get_axis_labels()
        axis_colors = self.controller.settings.data["colors"]

        # Position of the axis
        origin = [12, 12]
        length = 30
        if directions[0] == -1:
            origin[0] = 50
        if directions[1] == -1:
            origin[1] = 50

        color_h = axis_colors[labels[0]]
        color_v = axis_colors[labels[1]]
        end_h = [origin[0] + (length * directions[0]), origin[1]]
        end_v = [origin[0], origin[1] + (length * directions[1])]

        # Draw to the BACK node
        dpg.draw_arrow(end_h, origin, color=color_h, thickness=2, size=4, parent=back_node)
        h_text_off = 5 if directions[0] > 0 else -18
        dpg.draw_text([end_h[0] + h_text_off, end_h[1] - 7], labels[0], color=color_h, size=14, parent=back_node)

        dpg.draw_arrow(end_v, origin, color=color_v, thickness=2, size=4, parent=back_node)
        v_text_off = 5 if directions[1] > 0 else -18
        dpg.draw_text([end_v[0] - 5, end_v[1] + v_text_off], labels[1], color=color_v, size=14, parent=back_node)

        # --- THE SWAP ---
        dpg.configure_item(back_node, show=True)
        dpg.configure_item(front_node, show=False)
        self.active_axes_idx = back_idx

    def draw_histogram_view(self):
        img = self.image_model
        plot_tag = f"plot_{self.tag}"

        # Create the plot if it doesn't exist
        if not dpg.does_item_exist(plot_tag):
            # We place it inside the window, but OUTSIDE the drawlist
            # to avoid coordinate confusion
            with dpg.plot(label=f"Histogram: {img.name}", parent=f"win_{self.tag}",
                          tag=plot_tag, width=-1, height=-1):
                dpg.add_plot_axis(dpg.mvXAxis, label="Voxel Value", tag=f"x_axis_{self.tag}")
                dpg.add_plot_axis(dpg.mvYAxis, label="Count", tag=f"y_axis_{self.tag}")
                dpg.add_line_series([], [], label="Freq", parent=f"y_axis_{self.tag}", tag=f"series_{self.tag}")

        # Ensure the plot is visible
        dpg.configure_item(plot_tag, show=True)

        # Update data
        y_data = np.log10(img.hist_data_y + 1) if img.use_log_y else img.hist_data_y
        dpg.set_value(f"series_{self.tag}", [img.hist_data_x.tolist(), y_data.tolist()])

        # Auto-fit the axes on first load or data change
        dpg.fit_axis_data(f"x_axis_{self.tag}")
        dpg.fit_axis_data(f"y_axis_{self.tag}")

    def hide_everything(self):
        # Determine the new state (Toggle logic)
        # If the crosshair is currently shown, we hide everything. Otherwise, show.
        new_state = not self.image_model.show_crosshair

        # Update the ImageModel data
        img = self.image_model
        img.show_axis = new_state
        img.show_crosshair = new_state
        img.show_overlay = new_state
        img.grid_mode = False

        # Synchronize the GUI checkboxes
        # We use the tags defined in your MainGUI.create_window_level_controls
        dpg.set_value("check_axis", new_state)
        dpg.set_value("check_crosshair", new_state)
        dpg.set_value("check_overlay", new_state)
        dpg.set_value("check_grid", False)

        # Refresh all viewers using this image to reflect changes
        self.controller.update_all_viewers_of_image(self.image_id)

    def should_use_voxels_strips(self):
        if not self.image_model or self.image_model.interpolation_linear:
            return False

        win_w, win_h = dpg.get_item_width(f"win_{self.tag}"), dpg.get_item_height(f"win_{self.tag}")
        if not win_w or not win_h:
            return False

        pmin, pmax = self.current_pmin, self.current_pmax
        _, shape = self.image_model.get_slice_rgba(self.slice_idx, self.orientation)

        vox_w, vox_h = (pmax[0] - pmin[0]) / shape[1], (pmax[1] - pmin[1]) / shape[0]
        start_x, end_x = max(0, int(-pmin[0] / vox_w)), min(shape[1], int((win_w - pmin[0]) / vox_w) + 1)
        start_y, end_y = max(0, int(-pmin[1] / vox_h)), min(shape[0], int((win_h - pmin[1]) / vox_h) + 1)

        m = self.controller.settings.data['physics']['voxel_strip_threshold']
        return 0 < (end_x - start_x) * (end_y - start_y) < m

    def apply_local_auto_window(self, search_radius=25):
        if self.image_id is None:
            return
        pix_x, pix_y = self.get_mouse_to_pixel_coords(ignore_hover=True)
        if pix_x is None:
            return

        img_model = self.image_model
        _, shape = img_model.get_slice_rgba(self.slice_idx, self.orientation)
        real_h, real_w = shape[0], shape[1]
        pmin, pmax = self.current_pmin, self.current_pmax
        disp_w, disp_h = pmax[0] - pmin[0], pmax[1] - pmin[1]
        if disp_w <= 0 or disp_h <= 0:
            return

        vx_r_x, vx_r_y = (search_radius / disp_w) * real_w, (search_radius / disp_h) * real_h
        x0, x1 = int(max(0, pix_x - vx_r_x)), int(min(real_w, pix_x + vx_r_x))
        y0, y1 = int(max(0, pix_y - vx_r_y)), int(min(real_h, pix_y + vx_r_y))
        if x1 <= x0 or y1 <= y0:
            return

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

    def get_geometry_params(self, quad_w, quad_h):
        """Single source of truth for image scaling math."""
        img = self.image_model
        sw, sh = img.get_physical_aspect_ratio(self.orientation)
        _, shape = img.get_slice_rgba(self.slice_idx, self.orientation)
        real_h, real_w = shape[0], shape[1]
        mm_w, mm_h = real_w * sw, real_h * sh

        target_w, target_h = quad_w - self.margin_left, quad_h - self.margin_top
        base_scale = min(target_w / mm_w, target_h / mm_h)
        final_scale = base_scale * self.zoom
        return int(mm_w * final_scale), int(mm_h * final_scale), real_w, real_h, target_w, target_h

    def calculate_pan_to_center_crosshair(self, win_w, win_h):
        """
        Computes the exact [x, y] pixels needed to put the 3D crosshair
        at the center of the current window.
        """
        if not self.image_model or self.image_model.crosshair_pixel_coord is None:
            return [0, 0]

        img = self.image_model

        new_w, new_h, real_w, real_h, target_w, target_h = self.get_geometry_params(win_w, win_h)

        # 2. Identify the 'Zero-Pan' origin
        origin_x = (target_w - new_w) // 2 + self.margin_left
        origin_y = (target_h - new_h) // 2 + self.margin_top

        # 3. Map 3D Voxel to 2D Texture coordinates
        vx, vy, vz = img.crosshair_pixel_coord
        if self.orientation == "Axial":
            tx, ty = vx, vy
        elif self.orientation == "Sagittal":
            tx, ty = real_w - vy, real_h - vz
        else:  # Coronal
            tx, ty = vx, real_h - vz

        # 4. Find where that voxel sits on screen IF pan was 0,0
        cx_zero_pan_x = (tx / real_w) * new_w + origin_x
        cx_zero_pan_y = (ty / real_h) * new_h + origin_y

        # 5. Return the vector from that point to the Screen Center
        return [(win_w / 2) - cx_zero_pan_x, (win_h / 2) - cx_zero_pan_y]

    def update_crosshair_data(self, pix_x, pix_y):
        """COMPUTATION: Maps 2D pixels back to 3D Voxel Indices and stores in Model."""
        img_model = self.image_model
        _, shape = img_model.get_slice_rgba(self.slice_idx, self.orientation)
        real_h, real_w = shape[0], shape[1]

        if self.orientation == "Axial":
            v = [pix_x, pix_y, self.slice_idx]
        elif self.orientation == "Sagittal":
            v = [self.slice_idx, real_w - pix_x, real_h - pix_y]
        else:
            v = [pix_x, self.slice_idx, real_h - pix_y]

        img_model.crosshair_pixel_coord = v
        img_model.crosshair_phys_coord = img_model.voxel_coord_to_physic_coord(np.array(v))
        ix, iy, iz = [int(np.clip(c, 0, limit - 1)) for c, limit in
                      zip(v, [img_model.data.shape[2], img_model.data.shape[1], img_model.data.shape[0]])]
        img_model.crosshair_pixel_value = img_model.data[iz, iy, ix]

    def update_render(self):
        if self.image_id is None:
            return

        drawlist_tag = f"drawlist_{self.tag}"
        plot_tag = f"plot_{self.tag}"

        if self.orientation == "Histogram":
            # Hide the 2D image drawing area
            if dpg.does_item_exist(drawlist_tag):
                dpg.configure_item(drawlist_tag, show=False)
            self.draw_histogram_view()
            return
        else:
            # Show the 2D image drawing area
            if dpg.does_item_exist(drawlist_tag):
                dpg.configure_item(drawlist_tag, show=True)
            # Hide the plot
            if dpg.does_item_exist(plot_tag):
                dpg.configure_item(plot_tag, show=False)

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

        # Axis visibility
        if self.image_model.show_axis:
            dpg.configure_item(self.axes_nodes[0], show=True)  # or call draw_orientation_axes()
            dpg.configure_item(self.axes_nodes[1], show=True)
            self.draw_orientation_axes()
        else:
            dpg.configure_item(self.axis_a_tag, show=False)
            dpg.configure_item(self.axis_b_tag, show=False)

    def update_overlay(self):
        if self.image_id is None or not self.image_model.show_overlay or self.orientation == "Histogram":
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
        col = self.controller.settings.data["colors"]["overlay_text"]
        dpg.configure_item(self.overlay_tag, color=col)

        if 0 <= ix < max_x and 0 <= iy < max_y and 0 <= iz < max_z:
            val = img_model.data[iz, iy, ix]
            self.mouse_pixel_value, self.mouse_pixel_coord, self.mouse_phys_coord = val, v, phys
            dpg.set_value(self.overlay_tag,
                          f"{val:g}\n"
                          f"{fmt(v, 1)}\n"
                          f"{fmt(phys, 1)} mm")
        else:
            dpg.set_value(self.overlay_tag, "Out of image")

        win_h = dpg.get_item_height(f"win_{self.tag}")
        ts = dpg.get_item_rect_size(self.overlay_tag)
        dpg.set_item_pos(self.overlay_tag, [5, win_h - (ts[1] if ts[1] > 0 else 60) - 5])

    def update_window_level(self, ww, wl):
        self.image_model.ww, self.image_model.wl = ww, wl
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
        dpg.set_value("info_window", f"{self.image_model.ww:g}")
        dpg.set_value("info_level", f"{self.image_model.wl:g}")

    def update_crosshair_from_slice(self):
        """Updates the 3D physical crosshair based on the current 2D slice index."""
        img_model = self.image_model
        vx, vy, vz = img_model.crosshair_pixel_coord

        # Update only the coordinate corresponding to the current orientation
        if self.orientation == "Axial":
            vz = self.slice_idx
        elif self.orientation == "Sagittal":
            vx = self.slice_idx
        elif self.orientation == "Coronal":
            vy = self.slice_idx

        new_v = [vx, vy, vz]
        img_model.crosshair_pixel_coord = new_v
        img_model.crosshair_phys_coord = img_model.voxel_coord_to_physic_coord(np.array(new_v))

        # Update the pixel value for the sidebar
        ix, iy, iz = [int(np.clip(c, 0, limit - 1)) for c, limit in
                      zip(new_v, [img_model.data.shape[2], img_model.data.shape[1], img_model.data.shape[0]])]
        img_model.crosshair_pixel_value = img_model.data[iz, iy, ix]

    def on_key_press(self, key):
        img = self.image_model
        if not img:
            return

        if key == dpg.mvKey_W:
            self.apply_local_auto_window(search_radius=self.controller.settings.data["physics"]["search_radius"])

        elif key == dpg.mvKey_Up:
            self.on_scroll(1)

        elif key == dpg.mvKey_Down:
            self.on_scroll(-1)

        elif key == 517:  # page up
            self.on_scroll(10)

        elif key == 518:  # page down
            self.on_scroll(-10)

        elif key == dpg.mvKey_I:
            self.on_zoom("in")

        elif key == dpg.mvKey_O:
            self.on_zoom("out")

        elif key == dpg.mvKey_R:
            self.zoom, self.pan_offset = 1.0, [0, 0]
            self.controller.main_windows.on_window_resize()

        elif key == dpg.mvKey_C:
            # Set the flag to signal that we want to re-anchor the view
            self.needs_recenter = True
            self.needs_refresh = True
            # If synced, tell the controller to update the group
            if self.image_model and self.image_model.sync_group != 0:
                group_id = self.image_model.sync_group
                for v in self.controller.viewers.values():
                    if v.image_model and v.image_model.sync_group == group_id:
                        v.needs_recenter = True
                        v.needs_refresh = True

        elif key == dpg.mvKey_F1:
            self.set_orientation("Axial")

        elif key == dpg.mvKey_F2:
            self.set_orientation("Sagittal")

        elif key == dpg.mvKey_F3:
            self.set_orientation("Coronal")

        elif key == dpg.mvKey_F4:
            self.set_orientation("Histogram")

        elif key == dpg.mvKey_L:  # FIXME to remove or change
            img.interpolation_linear = not img.interpolation_linear
            img.needs_render = True

        elif key == dpg.mvKey_G:
            img.grid_mode = not img.grid_mode
            img.needs_render = True

        elif key == dpg.mvKey_H:
            self.hide_everything()

    def on_scroll(self, delta=1):
        if self.image_id is None or self.orientation == "Histogram":
            return  # Disable scrolling in histogram mode

        # Update the local slice index
        self.slice_idx += delta

        # Update the 3D crosshair position to match this new slice plane
        self.update_crosshair_from_slice()

        # Broadcast the new physical position to all synced viewers
        self.controller.propagate_sync(self.image_id)

        self.image_model.needs_render = True

    def on_drag(self, data):
        if self.image_id is None or self.orientation == "Histogram":
            return  # Disable pan/zoom/WL drag in histogram mode

        sx, sy = data[1] - self.last_dx, data[2] - self.last_dy
        self.last_dx, self.last_dy = data[1], data[2]

        # FIXME => check is button logic here

        is_button = dpg.is_mouse_button_down(dpg.mvMouseButton_Left)
        is_ctrl, is_shift = dpg.is_key_down(dpg.mvKey_LControl) or dpg.is_key_down(dpg.mvKey_RControl), dpg.is_key_down(
            dpg.mvKey_LShift) or dpg.is_key_down(dpg.mvKey_RShift)

        # Drag without Ctrl and without Shift
        if not is_ctrl and not is_shift and is_button:
            px, py = self.get_mouse_to_pixel_coords(ignore_hover=True)
            if px is not None:
                self.update_crosshair_data(px, py)
                self.controller.propagate_sync(self.image_id)

        # Drag with Ctrl and without Shift
        elif is_ctrl and is_button:
            self.pan_offset[0] += sx
            self.pan_offset[1] += sy
            self.needs_refresh = True

        # Drag with Ctrl and with Shift
        elif is_shift and is_button:
            ww = max(1, self.image_model.ww + sx * 2)
            wl = self.image_model.wl - sy * 2
            self.update_window_level(ww, wl)

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

        self.needs_refresh = True
        self.controller.propagate_sync(self.image_id)
