import dearpygui.dearpygui as dpg
import numpy as np
from .utils import *
from .core import SliceRenderer


class ViewportMapper:
    """Handles pure 2D spatial math: screen coordinates, zoom, and panning."""

    def __init__(self, margin_left=4, margin_top=4):
        self.margin_left = margin_left
        self.margin_top = margin_top
        self.pmin = [0, 0]
        self.pmax = [1, 1]
        self.disp_w = 1
        self.disp_h = 1

    def update(
        self, quad_w, quad_h, real_w, real_h, spacing_w, spacing_h, zoom, pan_offset
    ):
        mm_w, mm_h = real_w * spacing_w, real_h * spacing_h
        target_w, target_h = quad_w - self.margin_left, quad_h - self.margin_top

        base_scale = min(target_w / mm_w, target_h / mm_h)
        final_scale = base_scale * zoom
        new_w, new_h = int(mm_w * final_scale), int(mm_h * final_scale)

        off_x = (target_w - new_w) // 2 + self.margin_left + pan_offset[0]
        off_y = (target_h - new_h) // 2 + self.margin_top + pan_offset[1]

        self.pmin = [off_x, off_y]
        self.pmax = [off_x + new_w, off_y + new_h]
        self.disp_w = new_w
        self.disp_h = new_h

        return self.pmin, self.pmax

    def screen_to_image(self, screen_x, screen_y, real_w, real_h, allow_outside=False):
        if self.disp_w == 0 or self.disp_h == 0:
            return None, None

        rel_x, rel_y = screen_x - self.pmin[0], screen_y - self.pmin[1]

        if not allow_outside:
            if not (0 <= rel_x <= self.disp_w and 0 <= rel_y <= self.disp_h):
                return None, None

        return (rel_x / self.disp_w) * real_w, (rel_y / self.disp_h) * real_h

    def calculate_center_pan(
        self, tx, ty, quad_w, quad_h, real_w, real_h, spacing_w, spacing_h, zoom
    ):
        mm_w, mm_h = real_w * spacing_w, real_h * spacing_h
        target_w, target_h = quad_w - self.margin_left, quad_h - self.margin_top

        base_scale = min(target_w / mm_w, target_h / mm_h)
        final_scale = base_scale * zoom
        new_w, new_h = int(mm_w * final_scale), int(mm_h * final_scale)

        origin_x = (target_w - new_w) // 2 + self.margin_left
        origin_y = (target_h - new_h) // 2 + self.margin_top

        cx_zero_pan_x = (tx / real_w) * new_w + origin_x
        cx_zero_pan_y = (ty / real_h) * new_h + origin_y

        return [(quad_w / 2) - cx_zero_pan_x, (quad_h / 2) - cx_zero_pan_y]

    def calculate_zoom_pan_delta(self, mouse_x, mouse_y, old_zoom, new_zoom):
        ratio = new_zoom / old_zoom
        ow, oh = self.disp_w, self.disp_h
        dw, dh = (ow * ratio) - ow, (oh * ratio) - oh
        rx, ry = mouse_x - self.pmin[0], mouse_y - self.pmin[1]

        dx = -(rx * (ratio - 1)) + (dw / 2)
        dy = -(ry * (ratio - 1)) + (dh / 2)

        return dx, dy


class SliceViewer:
    def __init__(self, tag_id, controller):
        self.tag = tag_id
        self.controller = controller
        self.image_id = None

        self.active_strips_node = None
        self.active_grid_node = None

        self.is_geometry_dirty = True
        self.needs_recenter = None

        self.texture_tag = f"tex_{tag_id}"
        self.image_tag = f"img_{tag_id}"
        self.img_node_tag = f"img_node_{tag_id}"
        self.strips_a_tag = f"strips_node_A_{tag_id}"
        self.strips_b_tag = f"strips_node_B_{tag_id}"
        self.grid_a_tag = f"grid_node_A_{tag_id}"
        self.grid_b_tag = f"grid_node_B_{tag_id}"
        self.axis_a_tag = f"axes_node_A_{tag_id}"
        self.axis_b_tag = f"axes_node_B_{tag_id}"
        self.overlay_tag = f"overlay_{tag_id}"
        self.crosshair_tag = f"crosshair_node_{tag_id}"
        self.xh_line_h = f"xh_h_{tag_id}"
        self.xh_line_v = f"xh_v_{tag_id}"
        self.scale_bar_tag = f"scale_bar_node_{tag_id}"
        self.xh_initialized = False

        self.last_dy = 0
        self.last_dx = 0
        self.mapper = ViewportMapper()
        self.orientation = ViewMode.AXIAL

        self.mouse_phys_coord = None
        self.mouse_voxel = None
        self.mouse_value = None

        self.axes_nodes = None
        self.active_axes_idx = 0

        with dpg.texture_registry():
            dpg.add_dynamic_texture(
                width=1, height=1, default_value=np.zeros(4), tag=self.texture_tag
            )

    # --- DYNAMIC PROPERTY ROUTING ---
    @property
    def view_state(self):
        return self.controller.view_states.get(self.image_id) if self.image_id else None

    @property
    def volume(self):
        return self.view_state.volume if self.view_state else None

    @property
    def current_pmin(self):
        return self.mapper.pmin

    @property
    def current_pmax(self):
        return self.mapper.pmax

    @property
    def slice_idx(self):
        if not self.view_state or self.orientation not in self.view_state.slices:
            return 0
        return self.view_state.slices[self.orientation]

    @slice_idx.setter
    def slice_idx(self, value):
        if self.view_state:
            self.view_state.slices[self.orientation] = value

    @property
    def pan_offset(self):
        if not self.view_state or self.orientation not in self.view_state.pan:
            return [0, 0]
        return self.view_state.pan[self.orientation]

    @pan_offset.setter
    def pan_offset(self, value):
        if self.view_state:
            self.view_state.pan[self.orientation] = value

    @property
    def zoom(self):
        if not self.view_state or self.orientation not in self.view_state.zoom:
            return 1.0
        return self.view_state.zoom[self.orientation]

    @zoom.setter
    def zoom(self, value):
        if self.view_state:
            self.view_state.zoom[self.orientation] = value

    @property
    def num_slices(self):
        if not self.volume:
            return 0
        if self.orientation == ViewMode.AXIAL:
            return self.volume.data.shape[0]
        elif self.orientation == ViewMode.SAGITTAL:
            return self.volume.data.shape[2]
        elif self.orientation == ViewMode.CORONAL:
            return self.volume.data.shape[1]
        return 0

    def get_slice_shape(self):
        """Helper to get dimensions quickly without reading 3D array memory."""
        if not self.view_state:
            return 1, 1
        return self.view_state.get_slice_shape(self.orientation)

    def set_image(self, img_id):
        self.image_id = img_id
        self.set_current_slice_to_crosshair()
        self.init_slice_texture()

        win_w = dpg.get_item_width(f"win_{self.tag}")
        win_h = dpg.get_item_height(f"win_{self.tag}")
        self.resize(win_w, win_h)

        if self.view_state:
            self.view_state.is_data_dirty = True
        self.update_render()

    def set_current_slice_to_crosshair(self):
        if not self.view_state or not self.volume:
            return
        vx, vy, vz = self.view_state.crosshair_voxel
        if self.orientation == ViewMode.AXIAL:
            self.slice_idx = int(np.clip(vz, 0, self.volume.data.shape[0] - 1))
        elif self.orientation == ViewMode.SAGITTAL:
            self.slice_idx = int(np.clip(vx, 0, self.volume.data.shape[2] - 1))
        elif self.orientation == ViewMode.CORONAL:
            self.slice_idx = int(np.clip(vy, 0, self.volume.data.shape[1] - 1))

    def set_orientation(self, orientation):
        self.orientation = orientation
        if self.image_id:
            self.set_image(self.image_id)
        self.controller.gui.on_window_resize()

    def init_slice_texture(self):
        if not self.is_image_orientation() or not self.volume:
            return

        shape = self.get_slice_shape()
        h, w = shape[0], shape[1]

        new_texture_tag = f"tex_{self.tag}_{self.image_id}_{self.orientation}_{w}x{h}"

        if self.texture_tag == new_texture_tag:
            return

        if not dpg.does_item_exist(new_texture_tag):
            with dpg.texture_registry():
                dpg.add_dynamic_texture(
                    width=w,
                    height=h,
                    default_value=np.zeros(w * h * 4),
                    tag=new_texture_tag,
                )

        if dpg.does_item_exist(self.img_node_tag):
            dpg.delete_item(self.img_node_tag, children_only=True)
            self.image_tag = dpg.draw_image(
                new_texture_tag,
                self.current_pmin,
                self.current_pmax,
                parent=self.img_node_tag,
            )

        self.texture_tag = new_texture_tag

    def drop_image(self):
        self.image_id = None
        if dpg.does_item_exist(self.image_tag):
            dpg.configure_item(self.image_tag, show=False)

        if self.texture_tag and dpg.does_item_exist(self.texture_tag):
            dpg.delete_item(self.texture_tag)
            self.texture_tag = None

        self.update_render()

    def is_image_orientation(self):
        return self.orientation in [ViewMode.AXIAL, ViewMode.SAGITTAL, ViewMode.CORONAL]

    def get_axis_labels(self):
        if self.orientation == ViewMode.AXIAL:
            return ("x", "y"), (1, 1)
        elif self.orientation == ViewMode.SAGITTAL:
            return ("y", "z"), (-1, -1)
        else:
            return ("x", "z"), (1, -1)

    def get_center_physical_coord(self):
        if not self.view_state or not self.volume:
            return None

        win_w = dpg.get_item_width(f"win_{self.tag}")
        win_h = dpg.get_item_height(f"win_{self.tag}")
        if not win_w or not win_h:
            return None

        cx, cy = win_w / 2, win_h / 2
        shape = self.get_slice_shape()
        real_h, real_w = shape[0], shape[1]
        sw, sh = self.volume.get_physical_aspect_ratio(self.orientation)

        pmin, pmax = self.mapper.update(
            win_w, win_h, real_w, real_h, sw, sh, self.zoom, self.pan_offset
        )
        disp_w, disp_h = pmax[0] - pmin[0], pmax[1] - pmin[1]

        if disp_w <= 0 or disp_h <= 0:
            return None

        rel_x, rel_y = cx - pmin[0], cy - pmin[1]
        slice_x = (rel_x / disp_w) * real_w
        slice_y = (rel_y / disp_h) * real_h

        v = slice_to_voxel(slice_x, slice_y, self.slice_idx, self.orientation, shape)
        return self.volume.voxel_coord_to_physic_coord(v)

    def get_mouse_slice_coords(self, ignore_hover=False, allow_outside=False):
        if not self.image_id or not self.volume:
            return None, None
        if not ignore_hover and not dpg.is_item_hovered(f"win_{self.tag}"):
            return None, None

        shape = self.get_slice_shape()
        real_h, real_w = shape[0], shape[1]

        mx, my = dpg.get_drawing_mouse_pos()
        return self.mapper.screen_to_image(mx, my, real_w, real_h, allow_outside)

    def get_pixels_per_mm(self):
        if not self.view_state or not self.volume:
            return 1.0

        win_w = dpg.get_item_width(f"win_{self.tag}")
        win_h = dpg.get_item_height(f"win_{self.tag}")
        if not win_w or not win_h:
            return 1.0

        sw, sh = self.volume.get_physical_aspect_ratio(self.orientation)
        shape = self.get_slice_shape()
        real_w, real_h = shape[1], shape[0]

        mm_w, mm_h = real_w * sw, real_h * sh
        target_w, target_h = (
            win_w - self.mapper.margin_left,
            win_h - self.mapper.margin_top,
        )

        base_scale = min(target_w / mm_w, target_h / mm_h)
        return base_scale * self.zoom

    def set_pixels_per_mm(self, target_ppm):
        if not self.view_state or not self.volume:
            return

        win_w = dpg.get_item_width(f"win_{self.tag}")
        win_h = dpg.get_item_height(f"win_{self.tag}")
        if not win_w or not win_h:
            return

        sw, sh = self.volume.get_physical_aspect_ratio(self.orientation)
        shape = self.get_slice_shape()
        real_w, real_h = shape[1], shape[0]

        mm_w, mm_h = real_w * sw, real_h * sh
        target_w, target_h = (
            win_w - self.mapper.margin_left,
            win_h - self.mapper.margin_top,
        )

        base_scale = min(target_w / mm_w, target_h / mm_h)

        if base_scale > 0:
            self.zoom = target_ppm / base_scale
            self.is_geometry_dirty = True

    def center_on_physical_coord(self, phys_coord):
        if not self.view_state or not self.volume or phys_coord is None:
            return

        win_w = dpg.get_item_width(f"win_{self.tag}")
        win_h = dpg.get_item_height(f"win_{self.tag}")
        if not win_w or not win_h:
            return

        v = (
            phys_coord - self.volume.origin + self.volume.spacing / 2
        ) / self.volume.spacing
        shape = self.get_slice_shape()
        real_h, real_w = shape[0], shape[1]
        sw, sh = self.volume.get_physical_aspect_ratio(self.orientation)

        tx, ty = voxel_to_slice(v[0], v[1], v[2], self.orientation, shape)
        self.pan_offset = self.mapper.calculate_center_pan(
            tx, ty, win_w, win_h, real_w, real_h, sw, sh, self.zoom
        )
        self.is_geometry_dirty = True

    def resize(self, quad_w, quad_h):
        if quad_w <= 0 or quad_h <= 0:
            return
        if not dpg.does_item_exist(f"win_{self.tag}"):
            return

        dpg.set_item_width(f"win_{self.tag}", quad_w)
        dpg.set_item_height(f"win_{self.tag}", quad_h)

        if dpg.does_item_exist(f"drawlist_{self.tag}"):
            dpg.set_item_width(f"drawlist_{self.tag}", quad_w)
            dpg.set_item_height(f"drawlist_{self.tag}", quad_h)

        if self.image_id is None or not self.is_image_orientation() or not self.volume:
            return

        sw, sh = self.volume.get_physical_aspect_ratio(self.orientation)
        shape = self.get_slice_shape()
        real_h, real_w = shape[0], shape[1]

        if self.needs_recenter:
            self.pan_offset = self.calculate_pan_to_center_crosshair(quad_w, quad_h)
            self.needs_recenter = False

        pmin, pmax = self.mapper.update(
            quad_w, quad_h, real_w, real_h, sw, sh, self.zoom, self.pan_offset
        )

        if dpg.does_item_exist(self.image_tag):
            dpg.configure_item(self.image_tag, pmin=pmin, pmax=pmax)

    def calculate_pan_to_center_crosshair(self, win_w, win_h):
        if (
            not self.view_state
            or not self.volume
            or self.view_state.crosshair_voxel is None
        ):
            return [0, 0]

        shape = self.get_slice_shape()
        real_h, real_w = shape[0], shape[1]
        sw, sh = self.volume.get_physical_aspect_ratio(self.orientation)

        vx, vy, vz = self.view_state.crosshair_voxel
        tx, ty = voxel_to_slice(vx, vy, vz, self.orientation, shape)

        return self.mapper.calculate_center_pan(
            tx, ty, win_w, win_h, real_w, real_h, sw, sh, self.zoom
        )

    def draw_voxel_grid(self, h, w):
        node_a, node_b = self.grid_a_tag, self.grid_b_tag
        back_node = node_b if self.active_grid_node == node_a else node_a

        if dpg.does_item_exist(back_node):
            dpg.delete_item(back_node, children_only=True)
        else:
            return

        pmin, pmax = self.current_pmin, self.current_pmax
        if h == 0 or w == 0:
            return

        vox_w, vox_h = (pmax[0] - pmin[0]) / w, (pmax[1] - pmin[1]) / h
        if vox_w <= 0 or vox_h <= 0:
            return

        color = self.controller.settings.data["colors"]["grid"]

        for x in range(w + 1):
            lx = pmin[0] + x * vox_w
            dpg.draw_line([lx, pmin[1]], [lx, pmax[1]], color=color, parent=back_node)

        for y in range(h + 1):
            ly = pmin[1] + y * vox_h
            dpg.draw_line([pmin[0], ly], [pmax[0], ly], color=color, parent=back_node)

        dpg.configure_item(back_node, show=True)
        if dpg.does_item_exist(self.active_grid_node):
            dpg.configure_item(self.active_grid_node, show=False)
        self.active_grid_node = back_node

    def draw_crosshair(self):
        if not self.is_image_orientation() or not self.view_state or not self.volume:
            return

        node_tag = self.crosshair_tag

        if (
            not self.view_state.show_crosshair
            or self.view_state.crosshair_voxel is None
        ):
            if dpg.does_item_exist(self.xh_line_h):
                dpg.configure_item(self.xh_line_h, show=False)
                dpg.configure_item(self.xh_line_v, show=False)
            return

        vx, vy, vz = self.view_state.crosshair_voxel
        shape = self.get_slice_shape()
        real_h, real_w = shape[0], shape[1]

        tx, ty = voxel_to_slice(vx, vy, vz, self.orientation, shape)
        pmin, pmax = self.current_pmin, self.current_pmax

        disp_w, disp_h = pmax[0] - pmin[0], pmax[1] - pmin[1]
        screen_x = (tx / real_w) * disp_w + pmin[0]
        screen_y = (ty / real_h) * disp_h + pmin[1]

        color = self.controller.settings.data["colors"]["crosshair"]

        if not self.xh_initialized:
            dpg.draw_line(
                [screen_x, pmin[1]],
                [screen_x, pmin[1] + disp_h],
                color=color,
                parent=node_tag,
                tag=self.xh_line_v,
            )
            dpg.draw_line(
                [pmin[0], screen_y],
                [pmin[0] + disp_w, screen_y],
                color=color,
                parent=node_tag,
                tag=self.xh_line_h,
            )
            self.xh_initialized = True
        else:
            dpg.configure_item(
                self.xh_line_v,
                p1=[screen_x, pmin[1]],
                p2=[screen_x, pmin[1] + disp_h],
                color=color,
                show=True,
            )
            dpg.configure_item(
                self.xh_line_h,
                p1=[pmin[0], screen_y],
                p2=[pmin[0] + disp_w, screen_y],
                color=color,
                show=True,
            )

    def draw_voxels_as_strips(self, rgba_flat, h, w):
        node_a, node_b = self.strips_a_tag, self.strips_b_tag
        back_node = node_b if self.active_strips_node == node_a else node_a
        dpg.delete_item(back_node, children_only=True)

        pmin, pmax = self.current_pmin, self.current_pmax
        if h == 0 or w == 0:
            return

        vox_w, vox_h = (pmax[0] - pmin[0]) / w, (pmax[1] - pmin[1]) / h
        if vox_w <= 0 or vox_h <= 0:
            return

        win_w, win_h = dpg.get_item_width(f"win_{self.tag}"), dpg.get_item_height(
            f"win_{self.tag}"
        )
        if not win_w or not win_h:
            return

        start_x, end_x = max(0, int(-pmin[0] / vox_w)), min(
            w, int((win_w - pmin[0]) / vox_w) + 1
        )
        start_y, end_y = max(0, int(-pmin[1] / vox_h)), min(
            h, int((win_h - pmin[1]) / vox_h) + 1
        )
        pixels = rgba_flat.reshape(h, w, 4)

        for y in range(start_y, end_y):
            y_pos = pmin[1] + (y * vox_h) + (vox_h / 2)
            for x in range(start_x, end_x):
                x1 = pmin[0] + (x * vox_w)
                color = [int(c * 255) for c in pixels[y, x]]
                dpg.draw_line(
                    [x1, y_pos],
                    [x1 + vox_w, y_pos],
                    color=color,
                    thickness=vox_h + 1,
                    parent=back_node,
                )

        dpg.configure_item(back_node, show=True)
        if dpg.does_item_exist(self.active_strips_node):
            dpg.configure_item(self.active_strips_node, show=False)
        self.active_strips_node = back_node

    def draw_orientation_axes(self):
        if not self.is_image_orientation():
            if self.axes_nodes:
                dpg.configure_item(self.axes_nodes[0], show=False)
                dpg.configure_item(self.axes_nodes[1], show=False)
            return

        back_idx = 1 - self.active_axes_idx
        back_node = self.axes_nodes[back_idx]
        front_node = self.axes_nodes[self.active_axes_idx]

        dpg.delete_item(back_node, children_only=True)
        labels, directions = self.get_axis_labels()
        axis_colors = self.controller.settings.data["colors"]

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

        dpg.draw_arrow(
            end_h, origin, color=color_h, thickness=2, size=4, parent=back_node
        )
        h_text_off = 5 if directions[0] > 0 else -18
        dpg.draw_text(
            [end_h[0] + h_text_off, end_h[1] - 7],
            labels[0],
            color=color_h,
            size=14,
            parent=back_node,
        )

        dpg.draw_arrow(
            end_v, origin, color=color_v, thickness=2, size=4, parent=back_node
        )
        v_text_off = 5 if directions[1] > 0 else -18
        dpg.draw_text(
            [end_v[0] - 5, end_v[1] + v_text_off],
            labels[1],
            color=color_v,
            size=14,
            parent=back_node,
        )

        dpg.configure_item(back_node, show=True)
        dpg.configure_item(front_node, show=False)
        self.active_axes_idx = back_idx

    def draw_histogram_view(self):
        if not self.view_state:
            return
        plot_tag = f"plot_{self.tag}"

        if not dpg.does_item_exist(plot_tag):
            with dpg.plot(
                label=f"Histogram: {self.volume.name}",
                parent=f"win_{self.tag}",
                tag=plot_tag,
                width=-1,
                height=-1,
            ):
                dpg.add_plot_axis(
                    dpg.mvXAxis, label="Voxel Value", tag=f"x_axis_{self.tag}"
                )
                dpg.add_plot_axis(dpg.mvYAxis, label="Count", tag=f"y_axis_{self.tag}")
                dpg.add_line_series(
                    [],
                    [],
                    label="Freq",
                    parent=f"y_axis_{self.tag}",
                    tag=f"series_{self.tag}",
                )
            self.view_state.histogram_is_dirty = True

        dpg.configure_item(plot_tag, show=True)

        if self.view_state.histogram_is_dirty:
            self.view_state.update_histogram()
        else:
            return

        y_data = (
            np.log10(self.view_state.hist_data_y + 1)
            if self.view_state.use_log_y
            else self.view_state.hist_data_y
        )
        dpg.set_value(
            f"series_{self.tag}",
            [self.view_state.hist_data_x.tolist(), y_data.tolist()],
        )
        dpg.fit_axis_data(f"x_axis_{self.tag}")
        dpg.fit_axis_data(f"y_axis_{self.tag}")

    def draw_scale_bar(self):
        dpg.delete_item(self.scale_bar_tag, children_only=True)

        if (
            not self.is_image_orientation()
            or not self.view_state
            or not self.view_state.show_scalebar
        ):
            return

        win_w = dpg.get_item_width(f"win_{self.tag}")
        win_h = dpg.get_item_height(f"win_{self.tag}")
        if not win_w or not win_h:
            return

        ppm = self.get_pixels_per_mm()
        if ppm <= 0:
            return

        target_px = win_w * 0.15
        target_mm = target_px / ppm
        magnitude = 10 ** np.floor(np.log10(target_mm))
        normalized = target_mm / magnitude

        if normalized < 1.5:
            factor = 1
        elif normalized < 3.5:
            factor = 2
        elif normalized < 7.5:
            factor = 5
        else:
            factor = 10

        bar_mm = factor * magnitude
        bar_px = bar_mm * ppm

        x2 = int(win_w - 20)
        x1 = int(x2 - bar_px)
        y = int(win_h - 20)

        color = self.controller.settings.data["colors"]["overlay_text"]

        dpg.draw_rectangle(
            [x1, y - 1], [x2, y + 1], color=color, fill=color, parent=self.scale_bar_tag
        )
        dpg.draw_rectangle(
            [x1 - 1, y - 5],
            [x1 + 1, y + 5],
            color=color,
            fill=color,
            parent=self.scale_bar_tag,
        )
        dpg.draw_rectangle(
            [x2 - 1, y - 5],
            [x2 + 1, y + 5],
            color=color,
            fill=color,
            parent=self.scale_bar_tag,
        )

        text = f"{bar_mm:g} mm"
        text_x = int(x1 + (bar_px / 2) - ((len(text) * 7) / 2))
        dpg.draw_text(
            [text_x, int(y - 20)], text, color=color, size=14, parent=self.scale_bar_tag
        )

    def hide_everything(self):
        new_state = not self.view_state.show_crosshair
        self.view_state.show_axis = new_state
        self.view_state.show_crosshair = new_state
        self.view_state.show_overlay = new_state
        self.view_state.show_scalebar = new_state
        self.view_state.grid_mode = False

        dpg.set_value("check_axis", new_state)
        dpg.set_value("check_crosshair", new_state)
        dpg.set_value("check_overlay", new_state)
        dpg.set_value("check_scalebar", new_state)
        dpg.set_value("check_grid", False)

        self.controller.update_all_viewers_of_image(self.image_id)

    def should_use_voxels_strips(self):
        if (
            not self.view_state
            or not self.volume
            or self.view_state.interpolation_linear
        ):
            return False

        win_w, win_h = dpg.get_item_width(f"win_{self.tag}"), dpg.get_item_height(
            f"win_{self.tag}"
        )
        if not win_w or not win_h:
            return False

        pmin, pmax = self.current_pmin, self.current_pmax
        shape = self.get_slice_shape()

        vox_w, vox_h = (pmax[0] - pmin[0]) / shape[1], (pmax[1] - pmin[1]) / shape[0]
        if vox_w <= 0 or vox_h <= 0:
            return False

        start_x, end_x = max(0, int(-pmin[0] / vox_w)), min(
            shape[1], int((win_w - pmin[0]) / vox_w) + 1
        )
        start_y, end_y = max(0, int(-pmin[1] / vox_h)), min(
            shape[0], int((win_h - pmin[1]) / vox_h) + 1
        )

        m = self.controller.settings.data["physics"]["voxel_strip_threshold"]
        return 0 < (end_x - start_x) * (end_y - start_y) < m

    def apply_local_auto_window(self, fov_fraction=0.20):
        if (
            self.image_id is None
            or not self.volume
            or getattr(self.volume, "is_rgb", False)
        ):
            return

        pix_x, pix_y = self.get_mouse_slice_coords(ignore_hover=True)
        if pix_x is None:
            return

        pmin, pmax = self.current_pmin, self.current_pmax
        disp_w, disp_h = pmax[0] - pmin[0], pmax[1] - pmin[1]
        if disp_w <= 0 or disp_h <= 0:
            return

        win_w = dpg.get_item_width(f"win_{self.tag}")
        win_h = dpg.get_item_height(f"win_{self.tag}")
        if not win_w or not win_h:
            return

        slice_data = self.view_state.get_raw_slice(self.slice_idx, self.orientation)
        real_h, real_w = slice_data.shape

        # Define the sampling box as a fraction of the physical screen viewport
        screen_radius_x = (win_w * fov_fraction) / 2.0
        screen_radius_y = (win_h * fov_fraction) / 2.0

        # Translate the screen radius into voxel units, ensuring at least 1 voxel
        vx_r_x = max(1, int((screen_radius_x / disp_w) * real_w))
        vx_r_y = max(1, int((screen_radius_y / disp_h) * real_h))

        x0, x1 = max(0, int(pix_x) - vx_r_x), min(real_w, int(pix_x) + vx_r_x)
        y0, y1 = max(0, int(pix_y) - vx_r_y), min(real_h, int(pix_y) + vx_r_y)

        if x1 <= x0 or y1 <= y0:
            return

        patch = slice_data[y0:y1, x0:x1]
        if patch.size > 0:
            p_min, p_max = np.percentile(patch, [2, 98])
            ww = max(1e-5, p_max - p_min)
            self.update_window_level(ww, (p_max + p_min) / 2)

    def update_window_level(self, ww, wl):
        if (
            not self.is_image_orientation()
            or not self.volume
            or getattr(self.volume, "is_rgb", False)
        ):
            return
        self.view_state.ww = max(1e-5, ww)
        self.view_state.wl = wl
        self.controller.propagate_window_level(self.image_id)

    def update_crosshair_data(self, pix_x, pix_y):
        if self.view_state:
            self.view_state.update_crosshair_from_2d(
                pix_x, pix_y, self.slice_idx, self.orientation
            )

    def update_crosshair_from_slice(self):
        if self.view_state:
            self.view_state.update_crosshair_from_slice_scroll(
                self.slice_idx, self.orientation
            )

    def tick(self):
        """Called every frame. Evaluates dirty flags and updates rendering."""
        if not self.view_state:
            return False

        did_update_data = False

        # 1. Handle Data / Pixel Changes
        if self.view_state.is_data_dirty:
            self.update_render()
            self.is_geometry_dirty = (
                True  # Force overlays to update over new pixel data
            )
            did_update_data = True

        # 2. Handle Window Resize / Pan / Zoom
        if self.is_geometry_dirty:
            win_w = dpg.get_item_width(f"win_{self.tag}")
            win_h = dpg.get_item_height(f"win_{self.tag}")
            self.resize(win_w, win_h)
            self.update_overlays_only()
            self.is_geometry_dirty = False

        return did_update_data

    def update_render(self):
        """Reslices the 3D volume and pushes the flat pixel array to the GPU."""
        if self.image_id is None or not self.volume or not self.view_state:
            return

        drawlist_tag = f"drawlist_{self.tag}"
        plot_tag = f"plot_{self.tag}"

        if not self.is_image_orientation():
            if dpg.does_item_exist(drawlist_tag):
                dpg.configure_item(drawlist_tag, show=False)
            self.draw_histogram_view()
            return
        else:
            if dpg.does_item_exist(drawlist_tag):
                dpg.configure_item(drawlist_tag, show=True)
            if dpg.does_item_exist(plot_tag):
                dpg.configure_item(plot_tag, show=False)

        # THIS IS THE SLOWEST LINE IN THE APP:
        # rgba_flat, _ = self.view_state.get_slice_rgba(self.slice_idx, self.orientation)

        # Check if we have a valid overlay and get its visual parameters
        over_data = self.view_state.overlay_data
        over_ww, over_wl, over_cmap = 1.0, 0.5, "Hot"
        if (
            over_data is not None
            and self.view_state.overlay_id in self.controller.view_states
        ):
            ovs = self.controller.view_states[self.view_state.overlay_id]
            over_ww, over_wl, over_cmap = ovs.ww, ovs.wl, ovs.colormap

        # Generate the fused pixel array
        rgba_flat, _ = SliceRenderer.get_slice_rgba(
            self.volume.data,
            getattr(self.volume, "is_rgb", False),
            self.volume.num_components,
            self.view_state.ww,
            self.view_state.wl,
            self.view_state.colormap,
            over_data,
            over_ww,
            over_wl,
            over_cmap,
            self.view_state.overlay_opacity,
            self.view_state.overlay_threshold,
            self.slice_idx,
            self.orientation,
        )

        # Cache this flat array so overlays can use it during zooming without reslicing!
        self.last_rgba_flat = rgba_flat

        # Push strictly the texture to the GPU. Overlays are handled elsewhere.
        if dpg.does_item_exist(self.image_tag):
            dpg.set_value(self.texture_tag, rgba_flat)

    def update_overlays_only(self):
        """Redraws grids, axes, scalebar, and strips WITHOUT re-slicing the 3D volume."""
        if not self.is_image_orientation() or not self.view_state or not self.volume:
            return

        shape = self.get_slice_shape()
        h, w = shape[0], shape[1]

        # 1. Update Voxel Strips (If zoomed in very far)
        if self.should_use_voxels_strips() and hasattr(self, "last_rgba_flat"):
            dpg.configure_item(self.image_tag, show=False)
            self.draw_voxels_as_strips(self.last_rgba_flat, h, w)
        else:
            if dpg.does_item_exist(self.active_strips_node):
                dpg.configure_item(self.active_strips_node, show=False)
            dpg.configure_item(self.image_tag, show=True)

        # 2. Update Overlay Geometries
        if self.view_state.grid_mode:
            self.draw_voxel_grid(h, w)
        elif dpg.does_item_exist(self.active_grid_node):
            dpg.configure_item(self.active_grid_node, show=False)

        if self.view_state.show_axis:
            dpg.configure_item(self.axes_nodes[0], show=True)
            dpg.configure_item(self.axes_nodes[1], show=True)
            self.draw_orientation_axes()
        else:
            dpg.configure_item(self.axis_a_tag, show=False)
            dpg.configure_item(self.axis_b_tag, show=False)

        self.draw_scale_bar()
        self.draw_crosshair()
        self.update_overlay()

    def update_overlay(self):
        if (
            self.image_id is None
            or not self.view_state
            or not self.volume
            or not self.view_state.show_overlay
            or not self.is_image_orientation()
        ):
            dpg.set_value(self.overlay_tag, "")
            return

        is_dragging = self.controller.gui.drag_viewer == self
        pix_x, pix_y = self.get_mouse_slice_coords(
            ignore_hover=is_dragging, allow_outside=is_dragging
        )
        if pix_x is None:
            dpg.set_value(self.overlay_tag, "")
            return

        idx = self.slice_idx
        shape = self.get_slice_shape()
        v = slice_to_voxel(pix_x, pix_y, idx, self.orientation, shape)
        phys = self.volume.voxel_coord_to_physic_coord(v)

        ix, iy, iz = int(v[0]), int(v[1]), int(v[2])
        max_z, max_y, max_x = self.volume.data.shape[:3]
        col = self.controller.settings.data["colors"]["overlay_text"]
        dpg.configure_item(self.overlay_tag, color=col)

        if 0 <= ix < max_x and 0 <= iy < max_y and 0 <= iz < max_z:
            val = self.volume.data[iz, iy, ix]
            self.mouse_value, self.mouse_voxel, self.mouse_phys_coord = val, v, phys
            val_str = (
                f"{val[0]:g} {val[1]:g} {val[2]:g}"
                if getattr(self.volume, "is_rgb", False)
                else f"{val:g}"
            )
            dpg.set_value(
                self.overlay_tag, f"{val_str}\n{fmt(v, 1)}\n{fmt(phys, 1)} mm"
            )
        else:
            dpg.set_value(self.overlay_tag, "Out of image")

        win_h = dpg.get_item_height(f"win_{self.tag}")
        ts = dpg.get_item_rect_size(self.overlay_tag)
        dpg.set_item_pos(
            self.overlay_tag, [5, win_h - (ts[1] if ts[1] > 0 else 60) - 5]
        )

    def on_key_press(self, key):
        if not self.view_state:
            return

        # Helper to resolve string shortcuts to DPG keycodes dynamically
        def _k(action):
            val = self.controller.settings.data["shortcuts"].get(action)
            # If it's a string ("W"), append mvKey_. If it's an int (517), pass it through.
            return getattr(dpg, f"mvKey_{val}", val) if isinstance(val, str) else val

        # Handle next_image before the safety check, so we can Tab into an empty viewer

        if key == _k("next_image"):
            next_id = self.controller.get_next_image_id(self.image_id)
            if next_id and next_id != self.image_id:
                self.set_image(next_id)
                # Tell the GUI to update the checkboxes and sidebar
                if self.controller.gui:
                    self.controller.gui.refresh_image_list_ui()
                    if self.controller.gui.context_viewer == self:
                        self.controller.gui.update_sidebar_info(self)
            return

        if not self.view_state:
            return

        if key == _k("auto_window"):
            fov = self.controller.settings.data["physics"].get("auto_window_fov", 0.20)
            self.apply_local_auto_window(fov_fraction=fov)
        elif key == _k("scroll_up"):
            self.on_scroll(1)
        elif key == _k("scroll_down"):
            self.on_scroll(-1)
        elif key == _k("fast_scroll_up"):
            self.on_scroll(
                self.controller.settings.data["interaction"]["fast_scroll_steps"]
            )
        elif key == _k("fast_scroll_down"):
            self.on_scroll(
                -self.controller.settings.data["interaction"]["fast_scroll_steps"]
            )
            self.on_scroll(-10)
        elif key == _k("zoom_in"):
            self.on_zoom("in")
        elif key == _k("zoom_out"):
            self.on_zoom("out")
        elif key == _k("reset_view"):
            self.view_state.reset_view()
            self.is_geometry_dirty = True
            self.controller.propagate_sync(self.image_id)
            self.controller.update_all_viewers_of_image(self.image_id)
        elif key == _k("center_view"):
            self.needs_recenter = True
            self.is_geometry_dirty = True
            if self.view_state.sync_group != 0:
                group_id = self.view_state.sync_group
                for v in self.controller.viewers.values():
                    if v.view_state and v.view_state.sync_group == group_id:
                        v.needs_recenter = True
                        v.is_geometry_dirty = True
        elif key == _k("view_axial"):
            self.set_orientation(ViewMode.AXIAL)
        elif key == _k("view_sagittal"):
            self.set_orientation(ViewMode.SAGITTAL)
        elif key == _k("view_coronal"):
            self.set_orientation(ViewMode.CORONAL)
        elif key == _k("view_histogram"):
            self.set_orientation(
                ViewMode.HISTOGRAM
                if self.is_image_orientation()
                else ViewMode.HISTOGRAM
            )
        elif key == _k("toggle_interp"):
            self.view_state.interpolation_linear = (
                not self.view_state.interpolation_linear
            )
            self.view_state.is_data_dirty = True
        elif key == _k("toggle_grid"):
            self.view_state.grid_mode = not self.view_state.grid_mode
            self.view_state.is_data_dirty = True
        elif key == _k("hide_all"):
            self.hide_everything()

    def on_scroll(self, delta=1):
        if (
            self.image_id is None
            or not self.is_image_orientation()
            or not self.view_state
        ):
            return
        self.slice_idx += delta
        if self.slice_idx < 0:
            self.slice_idx = 0
        elif self.slice_idx >= self.num_slices:
            self.slice_idx = self.num_slices - 1

        self.update_crosshair_from_slice()
        self.controller.propagate_sync(self.image_id)
        self.view_state.is_data_dirty = True

    def on_drag(self, data):
        if (
            self.image_id is None
            or not self.is_image_orientation()
            or not self.view_state
        ):
            return

        sx, sy = data[1] - self.last_dx, data[2] - self.last_dy
        self.last_dx, self.last_dy = data[1], data[2]

        is_button = dpg.is_mouse_button_down(dpg.mvMouseButton_Left)
        is_ctrl, is_shift = dpg.is_key_down(dpg.mvKey_LControl) or dpg.is_key_down(
            dpg.mvKey_RControl
        ), dpg.is_key_down(dpg.mvKey_LShift) or dpg.is_key_down(dpg.mvKey_RShift)

        if not is_ctrl and not is_shift and is_button:
            px, py = self.get_mouse_slice_coords(ignore_hover=True, allow_outside=True)
            if px is not None:
                self.update_crosshair_data(px, py)
                self.controller.propagate_sync(self.image_id)
        elif is_ctrl and is_button:
            self.pan_offset[0] += sx
            self.pan_offset[1] += sy
            self.is_geometry_dirty = True
            self.controller.propagate_camera(self)
        elif is_shift and is_button:
            sens = self.controller.settings.data["interaction"]["wl_drag_sensitivity"]
            ww = max(1e-9, self.view_state.ww + sx * sens)
            wl = self.view_state.wl - sy * sens
            self.update_window_level(ww, wl)

    def on_zoom(self, direction):
        if (
            self.image_id is None
            or not self.is_image_orientation()
            or not self.view_state
            or not self.volume
        ):
            return

        mx, my = dpg.get_drawing_mouse_pos()
        oz = self.zoom
        speed = self.controller.settings.data["interaction"]["zoom_speed"]
        self.zoom = self.zoom * (speed if direction == "in" else (1.0 / speed))

        dx, dy = self.mapper.calculate_zoom_pan_delta(mx, my, oz, self.zoom)
        self.pan_offset[0] += dx
        self.pan_offset[1] += dy

        if self.view_state.sync_group == 0:
            win_w = dpg.get_item_width(f"win_{self.tag}")
            win_h = dpg.get_item_height(f"win_{self.tag}")
            if win_w and win_h:
                sw, sh = self.volume.get_physical_aspect_ratio(self.orientation)
                shape = self.get_slice_shape()
                real_w, real_h = shape[1], shape[0]

                mm_w, mm_h = real_w * sw, real_h * sh
                target_w, target_h = (
                    win_w - self.mapper.margin_left,
                    win_h - self.mapper.margin_top,
                )

                base_scale = min(target_w / mm_w, target_h / mm_h)
                self.view_state.shared_ppm = base_scale * self.zoom

        self.is_geometry_dirty = True
        self.controller.propagate_camera(self)
