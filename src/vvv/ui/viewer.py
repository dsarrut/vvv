from vvv.utils import *
import dearpygui.dearpygui as dpg
from vvv.ui.drawing import OverlayDrawer
from vvv.maths.image import SliceRenderer, RenderLayer, ROILayer


class ViewportMapper:
    """Handles pure 2D spatial math: screen coordinates, zoom, and panning."""

    def __init__(self, margin_left=4, margin_top=4):
        self.margin_left = margin_left
        self.margin_top = margin_top
        # pmin and pmax are recalculated dynamically
        # Every time the user zooms, pans, or resizes the application window.
        # = 2D bounding box on the screen
        self.pmin = [0, 0]
        self.pmax = [1, 1]
        self.disp_w = 1
        self.disp_h = 1

    @property
    def current_pmin(self):
        return self.pmin

    @property
    def current_pmax(self):
        return self.pmax

    def update(
        self, quad_w, quad_h, real_w, real_h, spacing_w, spacing_h, zoom, pan_offset
    ):
        mm_w = max(1e-5, real_w * spacing_w)
        mm_h = max(1e-5, real_h * spacing_h)
        target_w, target_h = (
            quad_w - self.margin_left * 2.0,
            quad_h - self.margin_top * 2.0,
        )

        base_scale = min(target_w / mm_w, target_h / mm_h)
        final_scale = base_scale * zoom
        new_w, new_h = mm_w * final_scale, mm_h * final_scale

        off_x = (target_w - new_w) / 2.0 + pan_offset[0]
        off_y = (target_h - new_h) / 2.0 + pan_offset[1]

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
        mm_w = max(1e-5, real_w * spacing_w)
        mm_h = max(1e-5, real_h * spacing_h)
        target_w, target_h = (
            quad_w - self.margin_left * 2.0,
            quad_h - self.margin_top * 2.0,
        )

        base_scale = min(target_w / mm_w, target_h / mm_h)
        final_scale = base_scale * zoom
        new_w, new_h = mm_w * final_scale, mm_h * final_scale

        origin_x = (target_w - new_w) / 2.0
        origin_y = (target_h - new_h) / 2.0

        cx_zero_pan_x = (tx / real_w) * new_w + origin_x
        cx_zero_pan_y = (ty / real_h) * new_h + origin_y

        return [(target_w / 2.0) - cx_zero_pan_x, (target_h / 2.0) - cx_zero_pan_y]

    def calculate_zoom_pan_delta(self, mouse_x, mouse_y, old_zoom, new_zoom):
        old_zoom = max(1e-5, old_zoom)
        ratio = new_zoom / old_zoom
        ow, oh = self.disp_w, self.disp_h
        dw, dh = (ow * ratio) - ow, (oh * ratio) - oh
        rx, ry = mouse_x - self.pmin[0], mouse_y - self.pmin[1]

        dx = -(rx * (ratio - 1)) + (dw / 2.0)
        dy = -(ry * (ratio - 1)) + (dh / 2.0)

        return dx, dy


class SliceViewer:
    """
    An autonomous rendering agent for a single viewport.

    ARCHITECTURE MANDATES (State-Only / Reactive):
    1. AUTONOMOUS TICK: This class is driven by a 60fps tick() loop. It must
       independently detect state changes by watching its assigned 'ViewState'.
       It should never wait for external commands to redraw.

    2. STATE-READ-ONLY: Viewers must never be the Source of Truth for permanent
       state. Any user interaction (pan, zoom, slice change) must be written
       immediately to the 'ViewState'. On the next tick, the viewer will
       reactively render that new state.

    3. DIRTY FLAG SYNC:
       - 'is_viewer_data_dirty': Triggered when pixel data or overlays change.
         Requires a full texture re-upload to the GPU.
       - 'is_geometry_dirty': Triggered when camera, zoom, or pan change.
         Requires recalculating 2D coordinate mapping but NOT a texture upload.

    4. DECOUPLED RENDERING: All drawing logic is delegated to the 'OverlayDrawer'.
       The viewer focuses on coordinate math and state synchronization.

    5. NO IMPERATIVE PINGS: Never call GUI update functions directly from this
       class. If the viewer changes something that the UI needs to know about
       (e.g., crosshair value), it must set 'controller.ui_needs_refresh = True'.
    """

    def __init__(self, tag_id, controller):
        self.tag = tag_id
        self.controller = controller
        self.image_id = None

        self.active_strips_node = None
        self.active_grid_node = None

        self.is_geometry_dirty = True
        self.is_viewer_data_dirty = True
        self.needs_recenter = None
        self.last_rgba_flat = None

        self.texture_tag = f"tex_{tag_id}"
        self.image_tag = f"img_{tag_id}"
        self.img_node_tag = f"img_node_{tag_id}"
        self.strips_a_tag = f"strips_node_A_{tag_id}"
        self.strips_b_tag = f"strips_node_B_{tag_id}"
        self.grid_a_tag = f"grid_node_A_{tag_id}"
        self.grid_b_tag = f"grid_node_B_{tag_id}"
        self.axis_a_tag = f"axes_node_A_{tag_id}"
        self.axis_b_tag = f"axes_node_B_{tag_id}"
        self.tracker_tag = f"tracker_{tag_id}"
        self.filename_text_tag = f"filename_text_{tag_id}"
        self.contour_node_tag = f"contour_node_{tag_id}"
        self.crosshair_tag = f"crosshair_node_{tag_id}"
        self.legend_tag = f"legend_node_{tag_id}"
        self.xh_line_h = f"xh_h_{tag_id}"
        self.xh_line_v = f"xh_v_{tag_id}"
        self.scale_bar_tag = f"scale_bar_node_{tag_id}"
        self.xh_initialized = False

        # For the shortkey
        self._shortcut_map = None

        self.quad_w = 100
        self.quad_h = 100

        self.last_dy = 0
        self.last_dx = 0
        self.mapper = ViewportMapper()
        self.orientation = ViewMode.AXIAL

        # For dynamic WL sensitivity
        self.drag_start_wl = None

        self.mouse_phys_coord = None
        self.mouse_voxel = None
        self.mouse_value = None

        self.axes_nodes = None
        self.active_axes_idx = 0

        self.drag_start_mouse = None
        self.drag_start_pan = None

        # State-Only Sync Trackers
        self.last_consumed_ppm = None
        self.last_consumed_center = None

        # Sub-modules
        self.drawer = OverlayDrawer(self)
        self.init_shortcut_dispatcher()

        if not dpg.does_item_exist("global_texture_registry"):
            with dpg.texture_registry(show=False, tag="global_texture_registry"):
                pass

        if not dpg.does_item_exist(self.texture_tag):
            dpg.add_dynamic_texture(
                width=1,
                height=1,
                default_value=np.zeros(4, dtype=np.float32),
                tag=self.texture_tag,
                parent="global_texture_registry",
            )

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
        if not self.view_state or self.orientation not in self.view_state.camera.slices:
            return 0
        return self.view_state.camera.slices[self.orientation]

    @slice_idx.setter
    def slice_idx(self, value):
        if self.view_state:
            self.view_state.camera.slices[self.orientation] = value

    @property
    def pan_offset(self):
        if not self.view_state or self.orientation not in self.view_state.camera.pan:
            return [0, 0]
        return self.view_state.camera.pan[self.orientation]

    @pan_offset.setter
    def pan_offset(self, value):
        if self.view_state:
            self.view_state.camera.pan[self.orientation] = value

    @property
    def zoom(self):
        if not self.view_state or self.orientation not in self.view_state.camera.zoom:
            return 1.0
        return self.view_state.camera.zoom[self.orientation]

    @zoom.setter
    def zoom(self, value):
        if self.view_state:
            self.view_state.camera.zoom[self.orientation] = value

    @property
    def num_slices(self):
        if not self.volume:
            return 0
        if self.orientation == ViewMode.AXIAL:
            return self.volume.shape3d[0]
        elif self.orientation == ViewMode.SAGITTAL:
            return self.volume.shape3d[2]
        elif self.orientation == ViewMode.CORONAL:
            return self.volume.shape3d[1]
        return 0

    @property
    def show_legend(self):
        return self.view_state.camera.show_legend if self.view_state else False

    @show_legend.setter
    def show_legend(self, value):
        if self.view_state:
            self.view_state.camera.show_legend = value

    def set_image(self, img_id):
        # 1. Detect if this is a genuinely new image
        is_new_image = self.image_id != img_id

        self.image_id = img_id

        # --- BUG FIX #2: WIPE STALE MEMORY ---
        # Clear the old tracking variables so the viewer evaluates the incoming
        # synced camera state as genuinely "new" on the very next tick.
        if is_new_image:
            self.last_consumed_ppm = None
            self.last_consumed_center = None

        # Look for a master image in the same sync group to act as the "Source of Truth"
        if self.view_state and self.view_state.sync_group > 0:
            target_group = self.view_state.sync_group
            master_vs_id = None

            # --- BUG FIX #1: PRIORITIZE ACTIVE VIEWERS ---
            # We must prioritize a master that is actively being rendered on screen!
            # Otherwise, we might pull coordinates from a hidden image that hasn't updated its camera yet.
            active_vs_ids = [
                v.image_id for v in self.controller.viewers.values() if v.image_id
            ]
            for vs_id in active_vs_ids:
                if (
                    vs_id != self.image_id
                    and self.controller.view_states[vs_id].sync_group == target_group
                ):
                    master_vs_id = vs_id
                    break

            # Fallback: If no active viewer is showing a synced image, just pick any from the group
            if not master_vs_id:
                for vs_id, vs in self.controller.view_states.items():
                    if vs_id != self.image_id and vs.sync_group == target_group:
                        master_vs_id = vs_id
                        break

            if master_vs_id:
                self.controller.sync.propagate_sync(master_vs_id)
                self.controller.sync.propagate_camera_to_viewer(master_vs_id, self)
                self.controller.sync.propagate_window_level(master_vs_id)
                self.controller.sync.propagate_colormap(master_vs_id)

        # 2. Autonomously flag for a camera reset if the underlying ID changed
        if is_new_image:
            self.needs_recenter = True

        self.set_current_slice_to_crosshair()

        self.is_geometry_dirty = True
        if self.view_state:
            self.view_state.is_data_dirty = True

        if self.controller:
            self.controller.ui_needs_refresh = True

    def set_current_slice_to_crosshair(self):
        if not self.view_state or not self.volume:
            return

        # Abort if history safely wiped the out-of-bounds crosshair
        if self.view_state.camera.crosshair_voxel is None:
            return

        vx, vy, vz = self.view_state.camera.crosshair_voxel[:3]
        if self.orientation == ViewMode.AXIAL:
            self.slice_idx = int(np.clip(vz, 0, self.volume.shape3d[0] - 1))
        elif self.orientation == ViewMode.SAGITTAL:
            self.slice_idx = int(np.clip(vx, 0, self.volume.shape3d[2] - 1))
        elif self.orientation == ViewMode.CORONAL:
            self.slice_idx = int(np.clip(vy, 0, self.volume.shape3d[1] - 1))

    def set_orientation(self, orientation):
        if self.orientation == orientation:
            return

        is_old_image = self.is_image_orientation()
        old_ppm = self.get_pixels_per_mm() if is_old_image else None
        old_center = self.get_center_physical_coord() if is_old_image else None

        self.orientation = orientation

        if self.view_state:
            self.view_state.camera.last_orientation = orientation

        if self.image_id:
            self.set_image(self.image_id)

        if self.is_image_orientation():
            if old_ppm and old_ppm > 0:
                self.set_pixels_per_mm(old_ppm)
            if old_center is not None:
                self.center_on_physical_coord(old_center)
            self.controller.sync.propagate_camera(self)

    def ensure_texture_exists(self):
        if not self.is_image_orientation() or not self.volume:
            return False

        shape = self.get_slice_shape()
        h, w = shape[0], shape[1]

        if self.view_state and self.view_state.display.pixelated_zoom:
            # Instead of the original image size, the texture size becomes the exact screen canvas size!
            layout = self.controller.gui.ui_cfg["layout"]
            pad = layout.get("viewport_padding", 4) * 2
            w = int(max(1, self.quad_w - pad))
            h = int(max(1, self.quad_h - pad))

        # 1. Generate a unique tag based on the viewer and the specific dimensions
        new_texture_tag = f"tex_{self.tag}_{w}x{h}"

        # Always unhide the parent canvas.
        if dpg.does_item_exist(self.img_node_tag):
            dpg.configure_item(self.img_node_tag, show=True)

        # 2. If the current texture tag perfectly matches the new one, reuse the VRAM
        if self.texture_tag == new_texture_tag and dpg.does_item_exist(
            self.texture_tag
        ):
            return False

        # Store the old texture for safe deletion in the binding phase
        if self.texture_tag and self.texture_tag != new_texture_tag:
            self._old_texture_to_delete = self.texture_tag

        if not dpg.does_item_exist(new_texture_tag):
            dpg.add_dynamic_texture(
                width=w,
                height=h,
                default_value=np.zeros(w * h * 4, dtype=np.float32),
                tag=new_texture_tag,
                parent="global_texture_registry",
            )

        # 6. Update the viewer's state to track the new texture
        self.texture_tag = new_texture_tag
        return True

    def bind_texture_to_node(self):
        # 1. Cleanly delete the old drawing command
        if dpg.does_item_exist(self.img_node_tag):
            dpg.delete_item(self.img_node_tag, children_only=True)

        # 2. Safely defer deleting the old texture from VRAM until the next frame
        old_tex = getattr(self, "_old_texture_to_delete", None)
        if old_tex:
            if not hasattr(self, "_textures_to_delete"):
                self._textures_to_delete = []
            self._textures_to_delete.append(old_tex)
        self._old_texture_to_delete = None

        # 3. Re-bind the image quad to the screen
        if dpg.does_item_exist(self.img_node_tag):
            self.image_tag = dpg.draw_image(
                self.texture_tag,
                self.current_pmin,
                self.current_pmax,
                parent=self.img_node_tag,
            )

    def drop_image(self):
        self.image_id = None

        # Hide ALL overlay nodes and text, not just the image! ---
        nodes_to_hide = [
            self.img_node_tag,
            self.contour_node_tag,
            self.strips_a_tag,
            self.strips_b_tag,
            self.grid_a_tag,
            self.grid_b_tag,
            self.axis_a_tag,
            self.axis_b_tag,
            self.scale_bar_tag,
            self.crosshair_tag,
            self.legend_tag,
            self.filename_text_tag,
        ]

        for node_tag in nodes_to_hide:
            if dpg.does_item_exist(node_tag):
                dpg.configure_item(node_tag, show=False)

        if dpg.does_item_exist(self.tracker_tag):
            dpg.set_value(self.tracker_tag, "")

        if self.controller:
            self.controller.ui_needs_refresh = True

    def is_image_orientation(self):
        return self.orientation in [ViewMode.AXIAL, ViewMode.SAGITTAL, ViewMode.CORONAL]

    def get_slice_shape(self):
        if not self.view_state:
            return 1, 1
        return self.view_state.get_slice_shape(self.orientation)

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

        cx = (win_w - self.mapper.margin_left * 2.0) / 2.0
        cy = (win_h - self.mapper.margin_top * 2.0) / 2.0
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
        is_buf = self.view_state.base_display_data is not None
        return self.view_state.space.display_to_world(np.array(v), is_buffered=is_buf)

    def get_mouse_slice_coords(self, ignore_hover=False, allow_outside=False):
        if not self.image_id or not self.volume:
            return None, None
        if not ignore_hover and not dpg.is_item_hovered(f"win_{self.tag}"):
            return None, None

        shape = self.get_slice_shape()
        real_h, real_w = shape[0], shape[1]

        try:
            mx, my = dpg.get_drawing_mouse_pos()
            return self.mapper.screen_to_image(
                mx + 0.5, my + 0.5, real_w, real_h, allow_outside
            )
        except Exception:
            return None, None

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
            win_w - self.mapper.margin_left * 2.0,
            win_h - self.mapper.margin_top * 2.0,
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
            win_w - self.mapper.margin_left * 2.0,
            win_h - self.mapper.margin_top * 2.0,
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

        is_buf = self.view_state.base_display_data is not None
        v = self.view_state.space.world_to_display(phys_coord, is_buffered=is_buf)
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

        self.quad_w = quad_w
        self.quad_h = quad_h

        if not dpg.does_item_exist(f"win_{self.tag}"):
            return

        dpg.set_item_width(f"win_{self.tag}", quad_w)
        dpg.set_item_height(f"win_{self.tag}", quad_h)

        # The true rendering canvas is now 8 pixels smaller due to the 4px WindowPadding
        layout = self.controller.gui.ui_cfg["layout"]
        pad = layout.get("viewport_padding", 4) * 2
        canvas_w = int(max(1, quad_w - pad))
        canvas_h = int(max(1, quad_h - pad))

        if dpg.does_item_exist(f"drawlist_{self.tag}"):
            dpg.set_item_width(f"drawlist_{self.tag}", canvas_w)
            dpg.set_item_height(f"drawlist_{self.tag}", canvas_h)

        if self.image_id is None or not self.is_image_orientation() or not self.volume:
            return

        sw, sh = self.volume.get_physical_aspect_ratio(self.orientation)
        shape = self.get_slice_shape()
        real_h, real_w = shape[0], shape[1]

        if self.needs_recenter:
            # Use canvas_w/canvas_h instead of quad_w/quad_h
            self.pan_offset = self.calculate_pan_to_center_crosshair(canvas_w, canvas_h)
            self.needs_recenter = False

        # Use canvas_w/canvas_h instead of quad_w/quad_h
        pmin, pmax = self.mapper.update(
            canvas_w, canvas_h, real_w, real_h, sw, sh, self.zoom, self.pan_offset
        )

        if dpg.does_item_exist(self.image_tag):
            if self.view_state.display.pixelated_zoom:
                # Lock the Quad to the window and let Python do the math instead of the GPU
                dpg.configure_item(
                    self.image_tag, pmin=[0, 0], pmax=[canvas_w, canvas_h]
                )
            else:
                dpg.configure_item(self.image_tag, pmin=pmin, pmax=pmax)

    def calculate_pan_to_center_crosshair(self, win_w, win_h):
        if (
            not self.view_state
            or not self.volume
            or self.view_state.camera.crosshair_voxel is None
        ):
            return [0, 0]

        shape = self.get_slice_shape()
        real_h, real_w = shape[0], shape[1]
        sw, sh = self.volume.get_physical_aspect_ratio(self.orientation)

        vx, vy, vz = self.view_state.camera.crosshair_voxel[:3]
        tx, ty = voxel_to_slice(vx, vy, vz, self.orientation, shape)

        return self.mapper.calculate_center_pan(
            tx, ty, win_w, win_h, real_w, real_h, sw, sh, self.zoom
        )

    def draw_crosshair(self):
        """Proxy to the drawing module for external callers (e.g. controller.py)."""
        self.drawer.draw_crosshair()

    def hide_everything(self):
        new_state = not self.view_state.camera.show_crosshair
        self.view_state.camera.show_axis = new_state
        self.view_state.camera.show_crosshair = new_state
        self.view_state.camera.show_tracker = new_state
        self.view_state.camera.show_scalebar = new_state
        self.view_state.camera.show_filename = 1 if new_state else 0
        self.view_state.camera.show_grid = False
        self.view_state.camera.show_contour = new_state

        self.view_state.is_data_dirty = True

    def tick(self):
        # Safely clean up textures from the previous frame
        if hasattr(self, "_textures_to_delete") and self._textures_to_delete:
            for tex in self._textures_to_delete:
                if dpg.does_item_exist(tex):
                    dpg.delete_item(tex)
            self._textures_to_delete.clear()

        target_id = self.controller.layout.get(self.tag)
        if target_id != self.image_id:
            if target_id is None:
                self.drop_image()
            else:
                self.set_image(target_id)

        if not self.view_state or getattr(self.view_state, "is_loading", False):
            self.last_drawn_image_id = None
            return False

        did_update_data = False
        win_w = dpg.get_item_width(f"win_{self.tag}")
        win_h = dpg.get_item_height(f"win_{self.tag}")

        if win_w <= 0 or win_h <= 0:
            return False

        # --- 1. STATE TRIGGERS ---
        size_changed = win_w != getattr(self, "last_w", 0) or win_h != getattr(
            self, "last_h", 0
        )
        image_changed = self.image_id != getattr(self, "last_drawn_image_id", None)
        orientation_changed = self.orientation != getattr(
            self, "last_orientation", None
        )
        current_shape = self.get_slice_shape()
        shape_changed = current_shape != getattr(self, "last_drawn_shape", None)

        pixelated = self.view_state.display.pixelated_zoom if self.view_state else False
        pixelated_changed = pixelated != getattr(self, "last_pixelated", None)

        # If pixelated zoom is active, size_changed MUST trigger a texture rebuild
        # because the texture dimension literally matches the screen dimension.
        rebuild_texture = (
            image_changed
            or orientation_changed
            or shape_changed
            or pixelated_changed
            or (pixelated and size_changed)
        )

        if size_changed:
            self.last_w = win_w
            self.last_h = win_h
            self.quad_w = int(win_w)
            self.quad_h = int(win_h)
            self.is_geometry_dirty = True

        if rebuild_texture:
            self.last_drawn_image_id = self.image_id
            self.last_orientation = self.orientation
            self.last_drawn_shape = current_shape
            self.last_pixelated = pixelated
            self.is_viewer_data_dirty = True

        # --- 2. CAMERA SYNC MATH ---
        vs_ppm = getattr(self.view_state.camera, "target_ppm", None)
        vs_center = getattr(self.view_state.camera, "target_center", None)

        last_ppm = getattr(self, "last_consumed_ppm", None)
        ppm_changed = (vs_ppm is not None) and (
            last_ppm is None or abs(vs_ppm - last_ppm) > 1e-5
        )

        last_center = getattr(self, "last_consumed_center", None)
        center_changed = False
        if vs_center is not None:
            if last_center is None:
                center_changed = True
            else:
                center_changed = (
                    abs(vs_center[0] - last_center[0]) > 1e-5
                    or abs(vs_center[1] - last_center[1]) > 1e-5
                    or abs(vs_center[2] - last_center[2]) > 1e-5
                )

        if ppm_changed or center_changed:
            if ppm_changed:
                self.set_pixels_per_mm(vs_ppm)
                self.last_consumed_ppm = vs_ppm
            if center_changed:
                self.center_on_physical_coord(vs_center)
                self.last_consumed_center = list(vs_center)
            self.needs_recenter = False
            self.is_geometry_dirty = True

        # --- 3. PRE-CALCULATE PERFECT BOUNDS ---
        if (
            rebuild_texture
            or getattr(self, "needs_recenter", False)
            or self.is_geometry_dirty
        ):
            layout = self.controller.gui.ui_cfg["layout"]
            pad = layout.get("viewport_padding", 4) * 2
            canvas_w = int(max(1, win_w - pad))
            canvas_h = int(max(1, win_h - pad))
            sw, sh = self.volume.get_physical_aspect_ratio(self.orientation)

            if getattr(self, "needs_recenter", False):
                self.pan_offset = self.calculate_pan_to_center_crosshair(
                    canvas_w, canvas_h
                )
                self.needs_recenter = False

            self.mapper.update(
                canvas_w,
                canvas_h,
                current_shape[1],
                current_shape[0],
                sw,
                sh,
                self.zoom,
                self.pan_offset,
            )

        # --- 4. ATOMIC UI CREATION (Part 1: Texture) ---
        texture_changed = False
        if rebuild_texture:
            texture_changed = self.ensure_texture_exists()

        # --- 5. DATA UPLOAD ---
        needs_reblend = self.view_state.is_data_dirty or self.is_viewer_data_dirty
        needs_nn_remap = (
            self.is_geometry_dirty and pixelated and not self.should_use_voxels_strips()
        )

        if needs_reblend or needs_nn_remap:
            self.is_viewer_data_dirty = False
            self.update_render(force_reblend=needs_reblend)
            self.is_geometry_dirty = True
            did_update_data = True

        # --- 4. ATOMIC UI CREATION (Part 2: Binding) ---
        if rebuild_texture and texture_changed:
            self.bind_texture_to_node()

        # --- 6. GEOMETRY PUSH ---
        if self.is_geometry_dirty:
            # ONLY call resize if we didn't just create the node via draw_image
            if not (rebuild_texture and texture_changed):
                self.resize(win_w, win_h)
            self.update_stuff_in_image_only()
            self.is_geometry_dirty = False

        return did_update_data

    def _get_screen_mapped_texture(self, rgba_img, pmin, pmax, canvas_w, canvas_h):
        """Extracts the exact viewport region and upscales using pure Nearest Neighbor math."""
        h, w = rgba_img.shape[:2]

        # Shift the sampling point to the exact geometric center of each screen pixel.
        # This prevents float boundaries from rapidly flipping indices during sub-pixel zooms.
        screen_x = np.arange(canvas_w) + 0.5
        screen_y = np.arange(canvas_h) + 0.5

        disp_w = max(1e-5, pmax[0] - pmin[0])
        disp_h = max(1e-5, pmax[1] - pmin[1])

        # Map screen pixels back to image index
        ix = (screen_x - pmin[0]) * w / disp_w
        iy = (screen_y - pmin[1]) * h / disp_h

        # Add a tiny epsilon to prevent float64 boundary jitter (e.g., 3.9999999 dropping to 3)
        ix = np.floor(ix + 1e-5).astype(np.int32)
        iy = np.floor(iy + 1e-5).astype(np.int32)

        valid_x = (ix >= 0) & (ix < w)
        valid_y = (iy >= 0) & (iy < h)

        ix = np.clip(ix, 0, w - 1)
        iy = np.clip(iy, 0, h - 1)

        IY, IX = np.meshgrid(iy, ix, indexing="ij")
        mapped = rgba_img[IY, IX]

        valid_mask = valid_x[None, :] & valid_y[:, None]
        mapped[~valid_mask] = 0.0

        return mapped

    def apply_local_auto_window(self, fov_fraction=0.20, target="base"):
        if self.image_id is None or not self.volume:
            return

        pix_x, pix_y = self.get_mouse_slice_coords(ignore_hover=True)
        if pix_x is None:
            return

        pmin, pmax = self.current_pmin, self.current_pmax
        disp_w, disp_h = pmax[0] - pmin[0], pmax[1] - pmin[1]
        if disp_w <= 0 or disp_h <= 0:
            return

        win_w = self.quad_w
        win_h = self.quad_h
        if not win_w or not win_h:
            return

        if target == "overlay":
            if (
                not self.view_state.display.overlay_id
                or self.view_state.display.overlay_data is None
            ):
                return
            ov_vol = self.controller.volumes[self.view_state.display.overlay_id]
            is_ov_rgb = getattr(ov_vol, "is_rgb", False)
            ov_time_idx = min(
                self.view_state.camera.time_idx, ov_vol.num_timepoints - 1
            )
            slice_data = SliceRenderer.extract_slice(
                self.view_state.display.overlay_data,
                is_ov_rgb,
                ov_time_idx,
                self.slice_idx,
                self.orientation,
            )
        else:
            if getattr(self.volume, "is_rgb", False):
                return

            # Make sure Auto-Window reads from the transformed buffer too!
            display_data = (
                self.view_state.base_display_data
                if getattr(self.view_state, "base_display_data", None) is not None
                else self.volume.data
            )

            slice_data = SliceRenderer.get_raw_slice(
                display_data,
                getattr(self.volume, "is_rgb", False),
                self.view_state.camera.time_idx,
                self.slice_idx,
                self.orientation,
            )

        if slice_data is None:
            return

        real_h, real_w = slice_data.shape[:2]
        screen_radius_x = (win_w * fov_fraction) / 2.0
        screen_radius_y = (win_h * fov_fraction) / 2.0

        vx_r_x = max(1, int((screen_radius_x / disp_w) * real_w))
        vx_r_y = max(1, int((screen_radius_y / disp_h) * real_h))

        x0, x1 = max(0, int(pix_x) - vx_r_x), min(real_w, int(pix_x) + vx_r_x)
        y0, y1 = max(0, int(pix_y) - vx_r_y), min(real_h, int(pix_y) + vx_r_y)

        if x1 <= x0 or y1 <= y0:
            return

        patch = slice_data[y0:y1, x0:x1]

        if target == "overlay":
            thr = self.view_state.display.base_threshold
            if thr is not None:
                patch = patch[patch >= thr]

        if patch.size > 0:
            p_min, p_max = np.percentile(patch, [2, 98])
            ww = max(1e-20, p_max - p_min)
            wl = (p_max + p_min) / 2

            if target == "overlay":
                ovs = self.controller.view_states[self.view_state.display.overlay_id]
                ovs.display.ww = ww
                ovs.display.wl = wl
                self.controller.sync.propagate_window_level(
                    self.view_state.display.overlay_id
                )
            else:
                self.update_window_level(ww, wl)

    def update_window_level(self, ww, wl):
        if (
            not self.is_image_orientation()
            or not self.volume
            or getattr(self.volume, "is_rgb", False)
        ):
            return
        self.view_state.display.ww = max(1e-20, ww)
        self.view_state.display.wl = wl
        if dpg.does_item_exist("combo_wl_presets"):
            dpg.set_value("combo_wl_presets", "Custom")
        self.controller.sync.propagate_window_level(self.image_id)

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

    def update_filename_overlay(self):
        if not self.image_id or not self.view_state or not self.volume:
            dpg.configure_item(self.filename_text_tag, show=False)
            return

        # Read state safely, defaulting to 0
        show_state = getattr(self.view_state.camera, "show_filename", 0)
        if isinstance(show_state, bool):
            show_state = 1 if show_state else 0

        if show_state == 0 or not self.is_image_orientation():
            dpg.configure_item(self.filename_text_tag, show=False)
            return

        dpg.configure_item(self.filename_text_tag, show=True)

        if show_state == 1:
            f_name, _ = self.controller.get_image_display_name(self.image_id)
        else:
            try:
                img_idx = (
                    list(self.controller.view_states.keys()).index(self.image_id) + 1
                )
            except ValueError:
                img_idx = "?"
            f_name = f"({img_idx}) {self.volume.get_human_readable_file_path()}"

        dpg.set_value(self.filename_text_tag, f_name)

        # Calculate width manually based on string length.
        # (This prevents the 1-frame centering lag caused by get_item_rect_size)
        tw = len(f_name) * 7.2  # 7.2 pixels per char is the standard ImGui font average

        # Center it dynamically at the top of the viewer
        dpg.set_item_pos(
            self.filename_text_tag, [max(5, int((self.quad_w - tw) / 2)), 5]
        )

    def _package_base_layer(self):
        # Use the display buffer if it exists, otherwise fall back to raw data
        display_data = (
            self.view_state.base_display_data
            if getattr(self.view_state, "base_display_data", None) is not None
            else self.volume.data
        )

        # Tombstone failsafe: Prevent the renderer from choking on dead memory
        if display_data is None:
            display_data = np.zeros((1, 1, 1), dtype=np.float32)

        return RenderLayer(
            data=display_data,
            is_rgb=getattr(self.volume, "is_rgb", False),
            num_components=self.volume.num_components,
            ww=self.view_state.display.ww,
            wl=self.view_state.display.wl,
            cmap_name=self.view_state.display.colormap,
            threshold=self.view_state.display.base_threshold,
            time_idx=self.view_state.camera.time_idx,
            spacing_2d=self.volume.get_physical_aspect_ratio(self.orientation),
        )

    def _package_overlay_layer(self):
        if self.view_state.display.overlay_data is None:
            return None
        if self.view_state.display.overlay_id not in self.controller.view_states:
            return None

        ovs = self.controller.view_states[self.view_state.display.overlay_id]

        # ---Calculate Relative Pixel Shift ---
        base_vs = self.view_state
        base_tx, base_ty, base_tz = 0.0, 0.0, 0.0
        if base_vs.space.transform and base_vs.space.is_active:
            base_tx, base_ty, base_tz = base_vs.space.transform.GetTranslation()

        ov_tx, ov_ty, ov_tz = 0.0, 0.0, 0.0
        if ovs.space.transform and ovs.space.is_active:
            ov_tx, ov_ty, ov_tz = ovs.space.transform.GetTranslation()

        # How many mm has the overlay moved LIVE relative to the base?
        live_dx = ov_tx - base_tx
        live_dy = ov_ty - base_ty
        live_dz = ov_tz - base_tz

        # Subtract the translation that is ALREADY baked into the 3D array!
        baked_dx, baked_dy, baked_dz = getattr(
            self.view_state.display, "baked_overlay_translation", (0.0, 0.0, 0.0)
        )

        dx_mm = live_dx - baked_dx
        dy_mm = live_dy - baked_dy
        dz_mm = live_dz - baked_dz

        sp_x, sp_y, sp_z = self.volume.spacing

        px_x = dx_mm / sp_x if sp_x else 0
        px_y = dy_mm / sp_y if sp_y else 0
        px_z = dz_mm / sp_z if sp_z else 0

        off_x, off_y, off_slice = 0, 0, 0
        if self.orientation == ViewMode.AXIAL:
            off_x = int(round(px_x))
            off_y = int(round(px_y))
            off_slice = int(round(px_z))
        elif self.orientation == ViewMode.CORONAL:
            off_x = int(round(px_x))
            off_y = int(round(-px_z))
            off_slice = int(round(px_y))
        elif self.orientation == ViewMode.SAGITTAL:
            off_x = int(round(-px_y))
            off_y = int(round(-px_z))
            off_slice = int(round(px_x))

        return RenderLayer(
            data=self.view_state.display.overlay_data,
            is_rgb=getattr(ovs.volume, "is_rgb", False),
            num_components=ovs.volume.num_components,
            ww=ovs.display.ww,
            wl=ovs.display.wl,
            cmap_name=ovs.display.colormap,
            threshold=ovs.display.base_threshold,
            time_idx=min(
                self.view_state.camera.time_idx, ovs.volume.num_timepoints - 1
            ),
            spacing_2d=self.volume.get_physical_aspect_ratio(self.orientation),
            offset_x=off_x,
            offset_y=off_y,
            offset_slice=off_slice,
        )

    def _package_roi_layers(self):
        active_rois = []
        for roi_id, roi_state in self.view_state.rois.items():
            if (
                not roi_state.visible
                or roi_state.opacity <= 0.0
                or getattr(roi_state, "is_contour", False)
            ):
                continue

            roi_vol = self.controller.volumes.get(roi_id)
            if not roi_vol or not hasattr(roi_vol, "roi_bbox"):
                continue

            z0, z1, y0, y1, x0, x1 = roi_vol.roi_bbox
            if z0 == z1:
                continue

            t_idx = min(self.view_state.camera.time_idx, roi_vol.num_timepoints - 1)
            base_z, base_y, base_x = self.volume.shape3d
            roi_slice = None
            offset_x, offset_y = 0, 0

            if self.orientation == ViewMode.AXIAL:
                if z0 <= self.slice_idx < z1:
                    if roi_vol.data.ndim == 4:
                        roi_slice = roi_vol.data[t_idx, self.slice_idx - z0, :, :]
                    else:
                        roi_slice = roi_vol.data[self.slice_idx - z0, :, :]
                    offset_x, offset_y = x0, y0
            elif self.orientation == ViewMode.CORONAL:
                if y0 <= self.slice_idx < y1:
                    if roi_vol.data.ndim == 4:
                        roi_slice = np.flipud(
                            roi_vol.data[t_idx, :, self.slice_idx - y0, :]
                        )
                    else:
                        roi_slice = np.flipud(roi_vol.data[:, self.slice_idx - y0, :])
                    offset_x = x0
                    offset_y = base_z - z1
            elif self.orientation == ViewMode.SAGITTAL:
                if x0 <= self.slice_idx < x1:
                    if roi_vol.data.ndim == 4:
                        roi_slice = np.flipud(
                            np.fliplr(roi_vol.data[t_idx, :, :, self.slice_idx - x0])
                        )
                    else:
                        roi_slice = np.flipud(
                            np.fliplr(roi_vol.data[:, :, self.slice_idx - x0])
                        )
                    offset_x = base_y - y1
                    offset_y = base_z - z1

            if roi_slice is not None and roi_slice.size > 0:
                active_rois.append(
                    ROILayer(
                        data=roi_slice,
                        color=roi_state.color,
                        opacity=roi_state.opacity,
                        is_contour=roi_state.is_contour,
                        offset_x=offset_x,
                        offset_y=offset_y,
                    )
                )
        return active_rois

    def update_render(self, force_reblend=True):
        win_tag = f"win_{self.tag}"

        # If the window is too small or doesn't exist, flag to try again next frame
        if self.quad_w <= 1 or not dpg.does_item_exist(win_tag):
            self.is_viewer_data_dirty = True
            return

        """state = dpg.get_item_state(win_tag)
        # If the window is hidden behind a tab, flag to try again when visible
        if state and not state.get("visible", True):
            self.is_viewer_data_dirty = True
            return"""

        if self.image_id is None or not self.volume or not self.view_state:
            return

        drawlist_tag = f"drawlist_{self.tag}"
        plot_tag = f"plot_{self.tag}"

        if not self.is_image_orientation():
            if dpg.does_item_exist(drawlist_tag):
                dpg.configure_item(drawlist_tag, show=False)
            self.drawer.draw_histogram_view()
            return
        else:
            if dpg.does_item_exist(drawlist_tag):
                dpg.configure_item(drawlist_tag, show=True)
            if dpg.does_item_exist(plot_tag):
                dpg.configure_item(plot_tag, show=False)

        if force_reblend or getattr(self, "last_rgba_flat", None) is None:
            # 1. Cleanly package all layers
            base_layer = self._package_base_layer()
            overlay_layer = self._package_overlay_layer()
            active_rois = self._package_roi_layers()

            # 2. Render
            rgba_flat, _ = SliceRenderer.get_slice_rgba(
                base=base_layer,
                overlay=overlay_layer,
                overlay_opacity=self.view_state.display.overlay_opacity,
                overlay_mode=self.view_state.display.overlay_mode,
                slice_idx=self.slice_idx,
                orientation=self.orientation,
                checkerboard_size=self.view_state.display.overlay_checkerboard_size,
                checkerboard_swap=self.view_state.display.overlay_checkerboard_swap,
                rois=active_rois,
            )
            self.last_rgba_flat = rgba_flat
        else:
            rgba_flat = self.last_rgba_flat

        # ---- APPLY NEAREST NEIGHBOR SCREEN MAPPING ----
        if (
            self.view_state.display.pixelated_zoom
            and not self.should_use_voxels_strips()
        ):
            layout = self.controller.gui.ui_cfg["layout"]
            pad = layout.get("viewport_padding", 4) * 2
            canvas_w = int(max(1, self.quad_w - pad))
            canvas_h = int(max(1, self.quad_h - pad))

            shape = self.get_slice_shape()
            rgba_2d = rgba_flat.reshape((shape[0], shape[1], 4))
            rgba_mapped = self._get_screen_mapped_texture(
                rgba_2d, self.current_pmin, self.current_pmax, canvas_w, canvas_h
            )
            rgba_flat = rgba_mapped.ravel()

        if dpg.does_item_exist(self.texture_tag):
            dpg.set_value(self.texture_tag, rgba_flat)

    def should_use_voxels_strips(self):
        if (
            not self.view_state
            or not self.volume
            or not self.view_state.display.use_voxel_strips
        ):
            return False

        win_w, win_h = self.quad_w, self.quad_h
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
        is_active = 0 < (end_x - start_x) * (end_y - start_y) < m
        return is_active

    def update_stuff_in_image_only(self):
        if not self.is_image_orientation() or not self.view_state or not self.volume:
            return

        shape = self.get_slice_shape()
        h, w = shape[0], shape[1]

        if (
            self.should_use_voxels_strips()
            and getattr(self, "last_rgba_flat", None) is not None
        ):
            if dpg.does_item_exist(self.image_tag):
                dpg.configure_item(self.image_tag, show=False)
            self.drawer.draw_voxels_as_strips(self.last_rgba_flat, h, w)
        else:
            if dpg.does_item_exist(self.active_strips_node):
                dpg.configure_item(self.active_strips_node, show=False)

            if dpg.does_item_exist(self.image_tag):
                dpg.configure_item(self.image_tag, show=True)
                if self.view_state.display.pixelated_zoom:
                    layout = self.controller.gui.ui_cfg["layout"]
                    pad = layout.get("viewport_padding", 4) * 2
                    canvas_w = int(max(1, self.quad_w - pad))
                    canvas_h = int(max(1, self.quad_h - pad))
                    dpg.configure_item(
                        self.image_tag, pmin=[0, 0], pmax=[canvas_w, canvas_h]
                    )
                else:
                    dpg.configure_item(
                        self.image_tag, pmin=self.current_pmin, pmax=self.current_pmax
                    )

        if self.view_state.camera.show_grid:
            self.drawer.draw_voxel_grid(h, w)
        elif dpg.does_item_exist(self.active_grid_node):
            dpg.configure_item(self.active_grid_node, show=False)

        if self.view_state.camera.show_axis:
            self.drawer.draw_orientation_axes()
        else:
            dpg.configure_item(self.axis_a_tag, show=False)
            dpg.configure_item(self.axis_b_tag, show=False)

        # Unhide the overlay nodes that drop_image() disabled
        for tag in [self.scale_bar_tag, self.legend_tag, self.crosshair_tag]:
            if dpg.does_item_exist(tag):
                dpg.configure_item(tag, show=True)

        self.drawer.draw_scale_bar()
        self.drawer.draw_legend()
        self.drawer.draw_crosshair()

        # Ensure extraction preview is computed before delegating to the View drawer
        ext = getattr(self.view_state, "extraction", None)
        if ext and ext.is_enabled and ext.show_preview:
            self.controller.extraction.update_preview(
                self.image_id,
                self.volume,
                self.view_state,
                ext.threshold_min,
                ext.threshold_max,
                [(self.orientation, self.slice_idx)],
            )

        self.controller.roi.update_roi_contours(self)

        self.drawer.draw_contours()
        self.update_tracker()
        self.update_filename_overlay()

    def update_tracker(self):
        if (
            self.image_id is None
            or not self.view_state
            or not self.volume
            or not self.view_state.camera.show_tracker
            or not self.is_image_orientation()
        ):
            dpg.set_value(self.tracker_tag, "")
            self._external_tracker_active = False
            return

        is_dragging = False
        if self.controller.gui and hasattr(self.controller.gui, "interaction"):
            active_tool = self.controller.gui.interaction.active_tool
            is_dragging = getattr(active_tool, "drag_viewer", None) == self

        # 1. LOCAL VIEWER: Are we the active hover source?
        pix_x, pix_y = self.get_mouse_slice_coords(
            ignore_hover=is_dragging, allow_outside=is_dragging
        )

        if pix_x is not None:
            self._was_hovered = True
            self._external_tracker_active = False

            idx = self.slice_idx
            shape = self.get_slice_shape()
            v = slice_to_voxel(pix_x, pix_y, idx, self.orientation, shape)
            is_buf = self.view_state.base_display_data is not None
            phys = self.view_state.space.display_to_world(
                np.array(v), is_buffered=is_buf
            )

            # Clear our own passive target so we don't fight ourselves
            self.view_state.camera.target_tracker_phys = None

            if self.view_state.sync_group > 0:
                self.controller.sync.propagate_tracker(self, phys)

            is_external = False
        else:
            # 2. PASSIVE VIEWER: We are not hovered, check memory for a target!

            # Send the "clear" signal exactly once when the mouse leaves us
            if getattr(self, "_was_hovered", False):
                self._was_hovered = False
                if self.view_state.sync_group > 0 and not is_dragging:
                    self.controller.sync.propagate_tracker(self, None)

            phys = self.view_state.camera.target_tracker_phys
            if phys is None:
                dpg.set_value(self.tracker_tag, "")
                self._external_tracker_active = False
                return

            self._external_tracker_active = True
            is_external = True
            is_buf = self.view_state.base_display_data is not None
            v = self.view_state.space.world_to_display(phys, is_buffered=is_buf)

        # --- The drawing logic remains exactly the same! ---
        col = self.controller.settings.data["colors"]["tracker_text"]
        dpg.configure_item(self.tracker_tag, color=col)

        # Look up the value at the physical coordinate
        info = self.controller.get_pixel_values_at_phys(
            self.image_id, phys, self.view_state.camera.time_idx
        )

        if info is not None:
            val = info["base_val"]

            if not is_external:
                self.mouse_value, self.mouse_voxel, self.mouse_phys_coord = (
                    val,
                    [v[0], v[1], v[2], self.view_state.camera.time_idx],
                    phys,
                )

            if val is None:
                val_str = "-"
            else:
                val_str = (
                    f"{val[0]:g} {val[1]:g} {val[2]:g}"
                    if getattr(self.volume, "is_rgb", False)
                    else f"{val:g}"
                )
            text_lines = [f"{val_str}"]

            if info["overlay_val"] is not None:
                text_lines[0] += f" ({info['overlay_val']:g})"

            if info["rois"]:
                text_lines[0] += f"  {', '.join(info['rois'])}"

            # Format the text differently depending on if we are active or passive
            if is_external:
                final_text = text_lines[0]
            else:
                if self.volume.num_timepoints > 1:
                    text_lines.append(
                        f"{v[0]:.1f} {v[1]:.1f} {v[2]:.1f} {self.view_state.camera.time_idx}"
                    )
                else:
                    text_lines.append(fmt(v, 1))

                text_lines.append(f"{fmt(phys, 1)} mm")
                final_text = "\n".join(text_lines)

            dpg.set_value(self.tracker_tag, final_text)
            est_h = final_text.count("\n") * 16 + 25
        else:
            dpg.set_value(self.tracker_tag, "Out of image" if not is_external else "")
            est_h = 25

        win_h = self.quad_h
        dpg.set_item_pos(
            self.tracker_tag,
            [8, max(5, win_h - est_h - 15)],
        )

    # --- ACTIONS & KEYBINDING DISPATCHER ---

    def init_shortcut_dispatcher(self):
        self._shortcut_map = {
            "next_image": self.action_next_image,
            "auto_window": lambda: self.apply_local_auto_window(
                fov_fraction=self.controller.settings.data["physics"].get(
                    "auto_window_fov", 0.20
                ),
                target="base",
            ),
            "auto_window_overlay": lambda: self.apply_local_auto_window(
                fov_fraction=self.controller.settings.data["physics"].get(
                    "auto_window_fov", 0.20
                ),
                target="overlay",
            ),
            "scroll_up": lambda: self.on_scroll(1),
            "scroll_down": lambda: self.on_scroll(-1),
            "fast_scroll_up": lambda: self.on_scroll(
                self.controller.settings.data["interaction"]["fast_scroll_steps"]
            ),
            "fast_scroll_down": lambda: self.on_scroll(
                -self.controller.settings.data["interaction"]["fast_scroll_steps"]
            ),
            "time_forward": lambda: self.on_time_scroll(1),
            "time_backward": lambda: self.on_time_scroll(-1),
            "zoom_in": lambda: self.on_zoom("in"),
            "zoom_out": lambda: self.on_zoom("out"),
            "reset_view": self.action_reset_view,
            "center_view": self.action_center_view,
            "view_axial": lambda: self.set_orientation(ViewMode.AXIAL),
            "view_sagittal": lambda: self.set_orientation(ViewMode.SAGITTAL),
            "view_coronal": lambda: self.set_orientation(ViewMode.CORONAL),
            "view_histogram": self.action_view_histogram,
            "toggle_interp": self.action_toggle_pixelated_zoom,
            "toggle_strips": self.action_toggle_strips,
            "toggle_legend": self.action_toggle_legend,
            "toggle_filename": self.action_toggle_filename,
            "toggle_grid": self.action_toggle_grid,
            "toggle_axis": self.action_toggle_axis,
            "toggle_scalebar": self.action_toggle_scalebar,
            "hide_all": self.hide_everything,
        }

    def action_next_image(self):
        next_id = self.controller.get_next_image_id(self.image_id)
        if next_id and next_id != self.image_id:
            # State-Only: Just tell the layout dictionary we want a new image!
            self.controller.layout[self.tag] = next_id
            self.controller.ui_needs_refresh = True

    def action_reset_view(self):
        # Check if either Left Shift or Right Shift is currently held down
        is_shift = dpg.is_key_down(dpg.mvKey_LShift) or dpg.is_key_down(
            dpg.mvKey_RShift
        )

        if is_shift:
            # self.view_state.hard_reset()
            self.controller.reset_image_view(self.image_id, hard=True)
            self.controller.update_all_viewers_of_image(self.image_id)
            # Because W/L, colormaps, and overlays changed, we must push syncs
            self.controller.sync.propagate_window_level(self.image_id)
            self.controller.sync.propagate_colormap(self.image_id)
            self.controller.sync.propagate_overlay_mode(self.image_id)
        else:
            # self.view_state.reset_view()
            self.controller.reset_image_view(self.image_id, hard=False)

        self.is_geometry_dirty = True
        self.controller.sync.propagate_sync(self.image_id)
        self.controller.update_all_viewers_of_image(self.image_id)

        # If the active viewer was reset, flag the UI for a reactive refresh
        if self.controller.gui and self.controller.gui.context_viewer == self:
            self.controller.ui_needs_refresh = True

    def action_center_view(self):
        self.needs_recenter = True
        self.is_geometry_dirty = True
        self.controller.sync.propagate_camera(self)

    def action_view_histogram(self):
        self.set_orientation(ViewMode.HISTOGRAM)

    def action_toggle_pixelated_zoom(self):
        if self.view_state.display.use_voxel_strips:
            self.view_state.display.use_voxel_strips = False
            self.view_state.display.pixelated_zoom = False
        else:
            self.view_state.display.pixelated_zoom = (
                not self.view_state.display.pixelated_zoom
            )
        self.view_state.is_data_dirty = True

    def action_toggle_strips(self):
        self.view_state.display.use_voxel_strips = (
            not self.view_state.display.use_voxel_strips
        )
        self.view_state.is_data_dirty = True

    def action_toggle_legend(self):
        self.show_legend = not self.show_legend

    def action_toggle_grid(self):
        self.view_state.camera.show_grid = not self.view_state.camera.show_grid

    def action_toggle_axis(self):
        self.view_state.camera.show_axis = not self.view_state.camera.show_axis

    def action_toggle_scalebar(self):
        self.view_state.camera.show_scalebar = not self.view_state.camera.show_scalebar

    def action_toggle_filename(self):
        current = getattr(self.view_state.camera, "show_filename", 0)
        if isinstance(current, bool):
            current = 1 if current else 0
        self.view_state.camera.show_filename = (current + 1) % 3

    def on_key_press(self, key):
        if not self.view_state:
            return

        shortcuts = self.controller.settings.data["shortcuts"]
        for action_name, action_func in self._shortcut_map.items():
            val = shortcuts.get(action_name)

            if val is None and action_name == "toggle_filename":
                val = dpg.mvKey_F

            mapped_key = (
                getattr(dpg, f"mvKey_{val}", val) if isinstance(val, str) else val
            )
            if key == mapped_key:
                action_func()
                return

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
        self.controller.sync.propagate_sync(self.image_id)
        self.is_viewer_data_dirty = True

    def on_time_scroll(self, delta):
        if self.image_id is None or not self.view_state or not self.volume:
            return
        nt = self.volume.num_timepoints
        if nt <= 1:
            return

        # Loop the time index
        self.view_state.camera.time_idx = (self.view_state.camera.time_idx + delta) % nt

        self.update_crosshair_from_slice()
        self.controller.sync.propagate_sync(self.image_id)
        self.view_state.is_data_dirty = True

    def on_mouse_down(self):
        if (
            self.image_id is None
            or not self.is_image_orientation()
            or not self.view_state
        ):
            return

        # 1. Capture the absolute starting mouse position for Pan/Zoom
        self.drag_start_mouse = dpg.get_mouse_pos(local=False)

        # 2. Snapshot the current pan so the drag delta can be added to it
        self.drag_start_pan = list(self.pan_offset)

    def on_drag(self, data):
        if (
            self.image_id is None
            or not self.is_image_orientation()
            or not self.view_state
        ):
            return

        # --- 3. CALCULATE ABSOLUTE DRAG ---
        current_pos = dpg.get_mouse_pos(local=False)
        if getattr(self, "drag_start_mouse", None) is None:
            return

        total_dx = current_pos[0] - self.drag_start_mouse[0]
        total_dy = current_pos[1] - self.drag_start_mouse[1]

        is_button = dpg.is_mouse_button_down(dpg.mvMouseButton_Left)
        is_ctrl = dpg.is_key_down(dpg.mvKey_LControl) or dpg.is_key_down(
            dpg.mvKey_RControl
        )
        is_shift = dpg.is_key_down(dpg.mvKey_LShift) or dpg.is_key_down(
            dpg.mvKey_RShift
        )

        if not is_ctrl and not is_shift and is_button:
            px, py = self.get_mouse_slice_coords(ignore_hover=True, allow_outside=True)
            if px is not None:
                self.update_crosshair_data(px, py)
                self.controller.sync.propagate_sync(self.image_id)

        elif is_ctrl and is_button:
            self.pan_offset[0] = self.drag_start_pan[0] + total_dx
            self.pan_offset[1] = self.drag_start_pan[1] + total_dy
            self.is_geometry_dirty = True
            self.controller.sync.propagate_camera(self)
            # Prevent self-snapping
            cent = self.get_center_physical_coord()
            if cent is not None:
                self.last_consumed_center = list(cent)

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
        new_zoom = max(
            1e-5, self.zoom * (speed if direction == "in" else (1.0 / speed))
        )
        self.zoom = new_zoom

        dx, dy = self.mapper.calculate_zoom_pan_delta(mx + 0.5, my + 0.5, oz, self.zoom)
        self.pan_offset[0] += dx
        self.pan_offset[1] += dy

        self.is_geometry_dirty = True
        self.controller.sync.propagate_camera(self)

        # Prevent self-snapping
        self.last_consumed_ppm = self.get_pixels_per_mm()
        cent = self.get_center_physical_coord()
        if cent is not None:
            self.last_consumed_center = list(cent)
