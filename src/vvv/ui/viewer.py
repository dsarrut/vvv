import time
import numpy as np
from vvv.utils import ViewMode, slice_to_voxel, voxel_to_slice, fmt
import dearpygui.dearpygui as dpg
from vvv.ui.drawing import OverlayDrawer
from vvv.maths.image import SliceRenderer, RenderLayer, ROILayer, VolumeData
from vvv.config import COLORMAPS
from vvv.core.view_state import ViewState
from vvv.ui.render_strategy import (
    compute_software_nearest_neighbor,
    compute_native_voxel_overlay,
    compute_native_voxel_base,
    blend_slices_cpu,
    GL_NEAREST_SUPPORTED,
    try_set_gl_nearest,
    NNMode,
    DEFAULT_NN_MODE,
    select_nn_mode,
    should_use_lazy_lin,
    _NUMBA_AVAILABLE,
)
from typing import Any


class ViewportMapper:
    """Handles pure 2D spatial math: screen coordinates, zoom, and panning."""

    def __init__(self, margin_left=4, margin_top=4):
        self.margin_left = margin_left
        self.margin_top = margin_top
        # pmin and pmax are recalculated dynamically
        # Every time the user zooms, pans, or resizes the application window.
        # = 2D bounding box on the screen
        self.pmin = [0.0, 0.0]
        self.pmax = [1.0, 1.0]
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
        self.image_id: str | None = None

        self.active_strips_node: str | None = None
        self.active_grid_node: str | None = None

        self.is_geometry_dirty = True
        self.is_viewer_data_dirty = True
        self.needs_recenter = False
        self.last_rgba_flat: np.ndarray | None = None

        # Dynamic tracking states to satisfy strict type checkers
        self.last_w: int | float = 0
        self.last_h: int | float = 0
        self.last_drawn_image_id: str | None = None
        self.last_orientation: ViewMode | None = None
        self.last_drawn_shape: tuple | None = None
        self.last_pixelated = False
        self.last_nn_mode: NNMode | None = None
        self.lazy_settle_ms: int = 150   # ms of inactivity before NN re-upload fires
        self._last_move_time: float = 0.0
        self._nn_settle_done: bool = True
        self._lazy_live_flag: bool = False  # stable within a tick; avoids time.time() races
        self._old_texture_to_delete: str | None = None
        self._textures_to_delete: list[str] = []

        self.overlay_texture_tag = f"tex_ov_{tag_id}"
        self.overlay_image_tag = f"img_ov_{tag_id}"
        self.active_overlay_shift_x = 0.0
        self.active_overlay_shift_y = 0.0
        self.last_overlay_rgba_flat: np.ndarray | None = None
        self._last_tracker_state: tuple | None = None
        self._was_hovered = False
        self._external_tracker_active = False

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
        self.vector_field_node_tag = f"vector_field_node_{tag_id}"
        self.crosshair_tag = f"crosshair_node_{tag_id}"
        self.legend_tag = f"legend_node_{tag_id}"
        self.xh_line_h = f"xh_h_{tag_id}"
        self.xh_line_v = f"xh_v_{tag_id}"
        self.scale_bar_tag = f"scale_bar_node_{tag_id}"
        self.xh_initialized = False

        # For the shortkey
        self._shortcut_map: dict | None = None

        self.quad_w = 100
        self.quad_h = 100

        self.last_dy = 0
        self.last_dx = 0
        self.mapper = ViewportMapper()
        self.orientation = ViewMode.AXIAL

        self.mouse_phys_coord: np.ndarray | None = None
        self.mouse_voxel: list[float] | None = None
        self.mouse_value: float | np.ndarray | None = None

        self.axes_nodes: list[str] | None = None
        self.active_axes_idx = 0

        self.drag_start_mouse: Any | None = None
        self.drag_start_pan: list[float] | None = None

        # State-Only Sync Trackers
        self.last_consumed_ppm: float | None = None
        self.last_consumed_center: list[float] | None = None

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
                default_value=np.zeros(4, dtype=np.float32),  # type: ignore
                tag=self.texture_tag,
                parent="global_texture_registry",
            )

        if not dpg.does_item_exist(self.overlay_texture_tag):
            dpg.add_dynamic_texture(
                width=1,
                height=1,
                default_value=np.zeros(4, dtype=np.float32),  # type: ignore
                tag=self.overlay_texture_tag,
                parent="global_texture_registry",
            )

    @property
    def has_fusion(self) -> bool:
        vs = self.view_state
        return bool(vs and vs.display.overlay_id and vs.display.overlay_mode == "Alpha")

    @property
    def nn_mode(self) -> NNMode:
        cfg = self.controller.settings.data.get("rendering", {})
        return select_nn_mode(cfg, self.has_fusion)

    @property
    def lazy_lin(self) -> bool:
        cfg = self.controller.settings.data.get("rendering", {})
        use_numba = _NUMBA_AVAILABLE and cfg.get("numba", True)
        return should_use_lazy_lin(cfg, self.has_fusion, self._is_hw_gl, use_numba)

    @property
    def view_state(self) -> ViewState | None:
        return self.controller.view_states.get(self.image_id) if self.image_id else None

    @property
    def volume(self) -> VolumeData | None:
        return self.view_state.volume if self.view_state else None

    @property
    def current_pmin(self):
        return self.mapper.pmin

    @property
    def current_pmax(self):
        return self.mapper.pmax

    @property
    def pan_offset(self):
        vs = self.view_state
        if not vs or self.orientation not in vs.camera.pan:
            return [0.0, 0.0]
        return vs.camera.pan[self.orientation]

    @pan_offset.setter
    def pan_offset(self, value):
        vs = self.view_state
        if vs:
            vs.camera.pan[self.orientation] = value

    @property
    def zoom(self):
        vs = self.view_state
        if not vs or self.orientation not in vs.camera.zoom:
            return 1.0
        return vs.camera.zoom[self.orientation]

    @zoom.setter
    def zoom(self, value):
        vs = self.view_state
        if vs:
            vs.camera.zoom[self.orientation] = value

    # Mapping for: (Voxel Index, Shape3D Index, Axis Labels, Axis Flip)
    _ORIENTATION_MAP = {
        ViewMode.AXIAL: (2, 0, ("x", "y"), (1, 1)),
        ViewMode.SAGITTAL: (0, 2, ("y", "z"), (-1, -1)),
        ViewMode.CORONAL: (1, 1, ("x", "z"), (1, -1)),
    }

    def _is_buffered(self) -> bool:
        vs = self.view_state
        return (
            vs is not None
            and vs.base_display_data is not None
            and vs.space.has_rotation()
        )

    def _get_current_image_shape(self):
        vs = self.view_state
        vol = self.volume
        if not vs or not vol:
            return (1, 1, 1)
        if self._is_buffered() and vs.base_display_data is not None:
            if vs.base_display_data.ndim == 4:
                return vs.base_display_data.shape[1:]
            return vs.base_display_data.shape
        return vol.shape3d

    def _get_crosshair_display_voxel(self) -> "np.ndarray | None":
        vs = self.view_state
        if vs is None or vs.camera.crosshair_phys_coord is None:
            return None
        v = vs.world_to_display(
            vs.camera.crosshair_phys_coord, is_buffered=self._is_buffered()
        )
        if v is None:
            v = vs.world_to_display(
                vs.camera.crosshair_phys_coord, is_buffered=False
            )
        return v

    def get_display_num_slices(self):
        if not self.view_state or not self.volume:
            return 0
        s = self._get_current_image_shape()
        if self.orientation == ViewMode.AXIAL:
            return s[0]  # Z-dimension
        elif self.orientation == ViewMode.SAGITTAL:
            return s[2]  # X-dimension
        elif self.orientation == ViewMode.CORONAL:
            return s[1]  # Y-dimension
        return 0

    @property
    def num_slices(self):
        return self.get_display_num_slices()

    @property
    def show_legend(self):
        vs = self.view_state
        return vs.camera.show_legend if vs else False

    @show_legend.setter
    def show_legend(self, value):
        vs = self.view_state
        if vs:
            vs.camera.show_legend = value

    @property
    def slice_idx(self):
        display_voxel = self._get_crosshair_display_voxel()
        if display_voxel is None:
            return 0
        # Use np.round to prevent float-to-int truncation jumping (e.g. 49.999 -> 49)
        v_idx, _, _, _ = self._ORIENTATION_MAP.get(self.orientation, (0, 0, None, None))
        return int(np.round(display_voxel[v_idx])) if v_idx is not None else 0

    @slice_idx.setter
    def slice_idx(self, value):
        vs = self.view_state
        vol = self.volume
        if not vs or not vol or vs.camera.crosshair_phys_coord is None:
            return

        current_display_voxel = self._get_crosshair_display_voxel()
        if current_display_voxel is None:
            return

        # Construct the new display voxel with the new slice index
        new_display_voxel = list(current_display_voxel[:3])
        if self.orientation == ViewMode.AXIAL:
            new_display_voxel[2] = value
        elif self.orientation == ViewMode.SAGITTAL:
            new_display_voxel[0] = value
        elif self.orientation == ViewMode.CORONAL:
            new_display_voxel[1] = value

        # Convert this new display voxel back to physical world coordinates
        new_phys = vs.display_to_world(
            np.array(new_display_voxel), is_buffered=self._is_buffered()
        )
        if new_phys is None:
            return

        # Update the ViewState's crosshair based on this new physical coordinate
        # This will update vs.camera.crosshair_voxel (native) and vs.camera.slices (native)
        vs.update_crosshair_from_phys(new_phys)

    def set_image(self, img_id):
        # 1. Detect if this is a genuinely new image
        is_new_image = self.image_id != img_id

        self.image_id = img_id
        vs = self.view_state

        # --- BUG FIX #2: WIPE STALE MEMORY ---
        # Clear the old tracking variables so the viewer evaluates the incoming
        # synced camera state as genuinely "new" on the very next tick.
        if is_new_image:
            self.last_consumed_ppm = None
            self.last_consumed_center = None

        # Look for a master image in the same sync group to act as the "Source of Truth"
        if vs and vs.sync_group > 0:
            target_group = vs.sync_group
            master_vs_id: str | None = None

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

        # Update the viewer's slice_idx (which is the display slice index)
        # based on the crosshair's physical position.
        self.set_current_slice_to_crosshair()

        self.is_geometry_dirty = True
        if vs:
            vs.is_data_dirty = True

        if is_new_image and self.controller:
            self.controller.ui_needs_refresh = True

    def set_current_slice_to_crosshair(self):
        display_voxel = self._get_crosshair_display_voxel()
        if display_voxel is None:
            return
        v_idx, _, _, _ = self._ORIENTATION_MAP.get(self.orientation, (0, 0, None, None))
        if v_idx is not None:
            self.slice_idx = int(np.round(display_voxel[v_idx]))

    def set_orientation(self, orientation):
        if self.orientation == orientation:
            return

        is_old_image = self.is_image_orientation()
        old_ppm = self.get_pixels_per_mm() if is_old_image else None
        old_center = self.get_center_physical_coord() if is_old_image else None

        self.orientation = orientation

        vs = self.view_state
        if vs:
            vs.camera.last_orientation = orientation

        # Re-evaluate the current slice index based on the new orientation and update crosshair
        if self.image_id:
            # This will trigger set_current_slice_to_crosshair again, but it's idempotent.
            # It also handles sync propagation.
            self.set_image(self.image_id)

        if self.is_image_orientation():
            if old_ppm and old_ppm > 0:
                self.set_pixels_per_mm(old_ppm)
            if old_center is not None:
                self.center_on_physical_coord(old_center)
            self.set_current_slice_to_crosshair()
            self.controller.sync.propagate_camera(self)

    def ensure_texture_exists(self):
        vs = self.view_state
        vol = self.volume
        if not self.is_image_orientation() or not vol:
            return False

        display_slice_shape = self.get_slice_shape()
        h, w = display_slice_shape[0], display_slice_shape[1]

        is_hw_gl = self._is_hw_gl
        nn_active = self._effective_pixelated_zoom()
        nn_needs_canvas = nn_active and not is_hw_gl

        if nn_needs_canvas:
            base_w, base_h = self._get_canvas_size()
            ov_w, ov_h = base_w, base_h
        else:
            base_w, base_h = w, h
            ov_w, ov_h = w, h

        # Track current texture dimensions for safe upload validation
        self._tex_w, self._tex_h = base_w, base_h
        self._ov_tex_w, self._ov_tex_h = ov_w, ov_h

        # 1. Generate unique tags based on dimensions
        new_texture_tag    = f"tex_{self.tag}_{base_w}x{base_h}"
        new_ov_texture_tag = f"tex_ov_{self.tag}_{ov_w}x{ov_h}"

        # Always unhide the parent canvas.
        if dpg.does_item_exist(self.img_node_tag):
            dpg.configure_item(self.img_node_tag, show=True)

        # 2. If both tags match existing textures, nothing to do
        base_exists = self.texture_tag == new_texture_tag and dpg.does_item_exist(self.texture_tag)
        ov_exists   = (hasattr(self, "overlay_texture_tag")
                       and self.overlay_texture_tag == new_ov_texture_tag
                       and dpg.does_item_exist(self.overlay_texture_tag))
        if base_exists and ov_exists:
            return False

        # Store old textures for safe deletion in the binding phase
        if self.texture_tag and self.texture_tag != new_texture_tag:
            self._old_texture_to_delete = self.texture_tag

        if (
            hasattr(self, "overlay_texture_tag")
            and self.overlay_texture_tag
            and self.overlay_texture_tag != new_ov_texture_tag
        ):
            self._textures_to_delete.append(self.overlay_texture_tag)

        if not dpg.does_item_exist(new_texture_tag):
            dpg.add_dynamic_texture(
                width=base_w,
                height=base_h,
                default_value=np.zeros(base_w * base_h * 4, dtype=np.float32),  # type: ignore
                tag=new_texture_tag,
                parent="global_texture_registry",
            )
            if is_hw_gl:
                try_set_gl_nearest()

        if not dpg.does_item_exist(new_ov_texture_tag):
            dpg.add_dynamic_texture(
                width=ov_w,
                height=ov_h,
                default_value=np.zeros(ov_w * ov_h * 4, dtype=np.float32),  # type: ignore
                tag=new_ov_texture_tag,
                parent="global_texture_registry",
            )
            if is_hw_gl:
                try_set_gl_nearest()

        # Update viewer state
        self.texture_tag = new_texture_tag
        self.overlay_texture_tag = new_ov_texture_tag
        return True

    def bind_texture_to_node(self):
        # Defer deletion of the old texture to the next frame
        if self._old_texture_to_delete:
            self._textures_to_delete.append(self._old_texture_to_delete)
            self._old_texture_to_delete = None

        if not dpg.does_item_exist(self.img_node_tag):
            return

        # DPG does not support dynamically updating 'texture_tag' via configure_item.
        # We must safely delete the old draw items and recreate them to point to the new VRAM.
        if dpg.does_item_exist(self.image_tag):
            dpg.delete_item(self.image_tag)
        if hasattr(self, "overlay_image_tag") and dpg.does_item_exist(
            self.overlay_image_tag
        ):
            dpg.delete_item(self.overlay_image_tag)

        self.image_tag = dpg.draw_image(
            self.texture_tag,
            self.current_pmin,
            self.current_pmax,
            parent=self.img_node_tag,
            tag=self.image_tag,
        )
        self.overlay_image_tag = dpg.draw_image(
            self.overlay_texture_tag,
            self.current_pmin,
            self.current_pmax,
            parent=self.img_node_tag,
            show=False,
            tag=self.overlay_image_tag,
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
            self.vector_field_node_tag,
        ]

        for node_tag in nodes_to_hide:
            if dpg.does_item_exist(node_tag):
                dpg.configure_item(node_tag, show=False)

        if dpg.does_item_exist(self.tracker_tag):
            dpg.set_value(self.tracker_tag, "")

        if hasattr(self, "overlay_image_tag") and dpg.does_item_exist(
            self.overlay_image_tag
        ):
            dpg.configure_item(self.overlay_image_tag, show=False)

        if self.controller:
            self.controller.ui_needs_refresh = True

    def is_image_orientation(self):
        return self.orientation in [ViewMode.AXIAL, ViewMode.SAGITTAL, ViewMode.CORONAL]

    def get_slice_shape(self):
        if not self.view_state or not self.volume:
            return 1, 1
        s = self._get_current_image_shape()
        if self.orientation == ViewMode.AXIAL:
            return s[1], s[2]  # Y, X
        elif self.orientation == ViewMode.SAGITTAL:
            return s[0], s[1]  # Z, Y
        elif self.orientation == ViewMode.CORONAL:
            return s[0], s[2]  # Z, X
        return 1, 1

    def get_axis_labels(self):
        if self.orientation == ViewMode.AXIAL:
            return ("x", "y"), (1, 1)
        elif self.orientation == ViewMode.SAGITTAL:
            return ("y", "z"), (-1, -1)
        else:
            return ("x", "z"), (1, -1)

    def get_center_physical_coord(self):
        vs = self.view_state
        vol = self.volume
        if not vs or not vol:
            return None

        win_w = dpg.get_item_width(f"win_{self.tag}")
        win_h = dpg.get_item_height(f"win_{self.tag}")
        if not win_w or not win_h:
            return None

        cx = (win_w - self.mapper.margin_left * 2.0) / 2.0
        cy = (win_h - self.mapper.margin_top * 2.0) / 2.0
        shape = self.get_slice_shape()
        real_h, real_w = shape[0], shape[1]
        sw, sh = vol.get_physical_aspect_ratio(self.orientation)

        pmin, pmax = self.mapper.update(
            win_w, win_h, real_w, real_h, sw, sh, self.zoom, self.pan_offset
        )
        disp_w, disp_h = pmax[0] - pmin[0], pmax[1] - pmin[1]

        if disp_w <= 0 or disp_h <= 0:
            return None

        rel_x, rel_y = cx - pmin[0], cy - pmin[1]
        slice_x = (rel_x / disp_w) * real_w
        slice_y = (rel_y / disp_h) * real_h

        # Use the viewer's current slice_idx (which is the display slice index)
        v = slice_to_voxel(slice_x, slice_y, self.slice_idx, self.orientation, shape)
        return vs.display_to_world(np.array(v), is_buffered=self._is_buffered())

    def get_mouse_slice_coords(self, ignore_hover=False, allow_outside=False):
        vol = self.volume
        if not self.image_id or not vol:
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
        vs = self.view_state
        vol = self.volume
        if not vs or not vol:
            return 1.0

        win_w = dpg.get_item_width(f"win_{self.tag}")
        win_h = dpg.get_item_height(f"win_{self.tag}")
        if not win_w or not win_h:
            return 1.0

        sw, sh = vol.get_physical_aspect_ratio(self.orientation)
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
        vs = self.view_state
        vol = self.volume
        if not vs or not vol:
            return

        win_w = dpg.get_item_width(f"win_{self.tag}")
        win_h = dpg.get_item_height(f"win_{self.tag}")
        if not win_w or not win_h:
            return

        sw, sh = vol.get_physical_aspect_ratio(self.orientation)
        shape = self.get_slice_shape()
        real_w, real_h = shape[1], shape[0]

        mm_w, mm_h = real_w * sw, real_h * sh
        target_w, target_h = (
            win_w - self.mapper.margin_left * 2.0,
            win_h - self.mapper.margin_top * 2.0,
        )

        base_scale = min(target_w / mm_w, target_h / mm_h)

        if base_scale > 0:
            if vs:
                vs.clear_reg_anchors()
            self.zoom = target_ppm / base_scale
            self.is_geometry_dirty = True

    def center_on_physical_coord(self, phys_coord):
        vs = self.view_state
        vol = self.volume
        if vs:
            vs.clear_reg_anchors()
        if not vs or not vol or phys_coord is None:
            return

        win_w = dpg.get_item_width(f"win_{self.tag}")
        win_h = dpg.get_item_height(f"win_{self.tag}")
        if not win_w or not win_h:
            return

        v = vs.world_to_display(phys_coord, is_buffered=self._is_buffered())
        if v is None:
            return
        shape = self.get_slice_shape()
        real_h, real_w = shape[0], shape[1]
        sw, sh = vol.get_physical_aspect_ratio(self.orientation)

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

        vs = self.view_state
        vol = self.volume
        if (
            self.image_id is None
            or not self.is_image_orientation()
            or not vol
            or not vs
        ):
            return

        sw, sh = vol.get_physical_aspect_ratio(self.orientation)
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
            # GL_NEAREST handles NN upscaling on the GPU, so the base image always
            # uses its physical screen position regardless of pixelated_zoom.
            dpg.configure_item(self.image_tag, pmin=pmin, pmax=pmax)

    def calculate_pan_to_center_crosshair(self, win_w, win_h):
        vs = self.view_state
        vol = self.volume
        if not vs or not vol or vs.camera.crosshair_voxel is None:
            return [0.0, 0.0]

        display_voxel = self._get_crosshair_display_voxel()
        if display_voxel is None:
            return [0.0, 0.0]

        shape = self.get_slice_shape()
        real_h, real_w = shape[0], shape[1]
        sw, sh = vol.get_physical_aspect_ratio(self.orientation)

        tx, ty = voxel_to_slice(
            display_voxel[0],
            display_voxel[1],
            display_voxel[2],
            self.orientation,
            shape,
        )

        return self.mapper.calculate_center_pan(
            tx, ty, win_w, win_h, real_w, real_h, sw, sh, self.zoom
        )

    def draw_crosshair(self):
        """Proxy to the drawing module for external callers (e.g. controller.py)."""
        self.drawer.draw_crosshair()

    def hide_everything(self):
        vs = self.view_state
        if not vs:
            return
        new_state = not vs.camera.show_crosshair
        vs.camera.show_axis = new_state
        vs.camera.show_tracker = new_state
        vs.camera.show_crosshair = new_state
        vs.camera.show_scalebar = new_state
        vs.camera.show_filename = 1 if new_state else 0
        vs.camera.show_grid = False
        vs.camera.show_contour = new_state
        vs.is_data_dirty = True

    def tick(self):
        # Safely clean up textures from the previous frame
        if self._textures_to_delete:
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

        vs = self.view_state
        if not vs or getattr(vs, "is_loading", False):
            self.last_drawn_image_id = None
            return False

        vol = self.volume
        if not vol:
            return False

        did_update_data = False
        win_w = dpg.get_item_width(f"win_{self.tag}")
        win_h = dpg.get_item_height(f"win_{self.tag}")

        if not win_w or not win_h or win_w <= 0 or win_h <= 0:
            return False

        # --- 1. STATE TRIGGERS ---
        size_changed = win_w != self.last_w or win_h != self.last_h
        image_changed = self.image_id != self.last_drawn_image_id
        orientation_changed = self.orientation != self.last_orientation
        current_shape = self.get_slice_shape()
        shape_changed = current_shape != self.last_drawn_shape

        pixelated = self._effective_pixelated_zoom()
        pixelated_changed = pixelated != self.last_pixelated
        current_nn_mode = self.nn_mode
        mode_changed = current_nn_mode != self.last_nn_mode

        if pixelated_changed:
            self.is_geometry_dirty = True

        ov_id = vs.display.overlay_id if vs else None
        has_nn_overlay = (
            ov_id is not None
            and ov_id in self.controller.view_states
            and vs.display.overlay_mode == "Alpha"
        )
        is_hw_gl = self._is_hw_gl
        is_canvas_sized = pixelated and not is_hw_gl

        rebuild_texture = (
            image_changed
            or orientation_changed
            or shape_changed
            or pixelated_changed
            or mode_changed
            or (size_changed and is_canvas_sized)
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
            self.last_nn_mode = current_nn_mode
            self.is_viewer_data_dirty = True

        # --- 2. CAMERA SYNC MATH ---
        vs_ppm: float | None = vs.camera.target_ppm
        vs_center: list | tuple | np.ndarray | None = vs.camera.target_center

        last_ppm = self.last_consumed_ppm
        ppm_changed = (vs_ppm is not None) and (
            last_ppm is None or abs(vs_ppm - last_ppm) > 1e-5
        )

        last_center = self.last_consumed_center
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
            if ppm_changed and vs_ppm is not None:
                self.set_pixels_per_mm(vs_ppm)
                self.last_consumed_ppm = vs_ppm
            if center_changed and vs_center is not None:
                self.center_on_physical_coord(vs_center)
                self.last_consumed_center = list(vs_center)
            self.needs_recenter = False
            self.is_geometry_dirty = True

        # --- 3. PRE-CALCULATE PERFECT BOUNDS ---
        if rebuild_texture or self.needs_recenter or self.is_geometry_dirty:
            layout = self.controller.gui.ui_cfg["layout"]
            pad = layout.get("viewport_padding", 4) * 2
            canvas_w = int(max(1, win_w - pad))
            canvas_h = int(max(1, win_h - pad))
            sw, sh = vol.get_physical_aspect_ratio(self.orientation)

            if self.needs_recenter:
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
        # texture_changed means a brand-new (empty) texture was just created → must fill it.
        needs_reblend = vs.is_data_dirty or self.is_viewer_data_dirty or texture_changed
        
        needs_nn_remap = False
        if self.is_geometry_dirty and pixelated and not self.should_use_voxels_strips():
            if not is_hw_gl:
                needs_nn_remap = True

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
            if rebuild_texture and texture_changed:
                # bind_texture_to_node already created the draw_image node; no need to
                # reconfigure the image quad inside resize(). But the DPG window and
                # drawlist dimensions must still be updated on any size change.
                if size_changed:
                    layout = self.controller.gui.ui_cfg["layout"]
                    pad = layout.get("viewport_padding", 4) * 2
                    cw = int(max(1, win_w - pad))
                    ch = int(max(1, win_h - pad))
                    if dpg.does_item_exist(f"win_{self.tag}"):
                        dpg.set_item_width(f"win_{self.tag}", win_w)
                        dpg.set_item_height(f"win_{self.tag}", win_h)
                    if dpg.does_item_exist(f"drawlist_{self.tag}"):
                        dpg.set_item_width(f"drawlist_{self.tag}", cw)
                        dpg.set_item_height(f"drawlist_{self.tag}", ch)
            else:
                self.resize(win_w, win_h)
            self.update_stuff_in_image_only()
            self.is_geometry_dirty = False

        # Lazy settle: once the interaction window has expired, restore full NN rendering.
        if (not self._nn_settle_done
                and self._last_move_time > 0
                and time.time() - self._last_move_time >= self.lazy_settle_ms / 1000.0):
            self._nn_settle_done = True
            self._lazy_live_flag = False  # cleared here so next tick sees stable False
            vs_lazy = self.view_state
            if vs_lazy and vs_lazy.display.pixelated_zoom and not self._is_hw_gl:
                if self.lazy_lin:
                    self.is_geometry_dirty = True
                    self.is_viewer_data_dirty = True

        return did_update_data

    def apply_local_auto_window(self, fov_fraction=0.20, target="base"):
        vol = self.volume
        if self.image_id is None or not vol:
            return

        vs = self.view_state
        if not vs:
            return

        pix_x, pix_y = self.get_mouse_slice_coords(ignore_hover=True)
        if pix_x is None or pix_y is None:
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
            if not vs.display.overlay_id or vs.display.overlay_data is None:
                return
            ov_vol = self.controller.volumes[vs.display.overlay_id]
            is_ov_rgb = getattr(ov_vol, "is_rgb", False)
            ov_time_idx = min(vs.camera.time_idx, ov_vol.num_timepoints - 1)
            slice_data = SliceRenderer.extract_slice(
                vs.display.overlay_data,
                is_ov_rgb,
                ov_time_idx,
                self.slice_idx,
                self.orientation,
            )
        else:
            if getattr(vol, "is_rgb", False):
                return

            # Make sure Auto-Window reads from the transformed buffer too!
            display_data = (
                vs.base_display_data
                if getattr(vs, "base_display_data", None) is not None
                else vol.data
            )

            slice_data = SliceRenderer.get_raw_slice(
                display_data,
                getattr(vol, "is_rgb", False),
                vs.camera.time_idx,
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
            ovs = self.controller.view_states.get(vs.display.overlay_id)
            if ovs:
                thr = ovs.display.base_threshold
                if thr is not None:
                    patch = patch[patch >= thr]

        if patch.size > 0:
            p_min, p_max = np.percentile(patch, [2, 98])
            ww = max(1e-20, p_max - p_min)
            wl = (p_max + p_min) / 2

            self._mark_lazy_interaction()

            if target == "overlay":
                ovs = self.controller.view_states.get(vs.display.overlay_id)
                if ovs:
                    ovs.display.ww = ww
                    ovs.display.wl = wl
                    self.controller.sync.propagate_window_level(vs.display.overlay_id)
            else:
                self.update_window_level(ww, wl)

    def update_window_level(self, ww, wl):
        vs = self.view_state
        vol = self.volume
        if (
            not vs
            or not self.is_image_orientation()
            or not vol
            or getattr(vol, "is_rgb", False)
        ):
            return
        vs.display.ww = max(1e-20, ww)
        vs.display.wl = wl
        if dpg.does_item_exist("combo_wl_presets"):
            dpg.set_value("combo_wl_presets", "Custom")
        self.controller.sync.propagate_window_level(self.image_id)

    def update_crosshair_data(self, pix_x, pix_y):
        vs = self.view_state
        if not vs:
            return

        vol = self.volume
        if not vol:
            return

        display_slice_shape = self.get_slice_shape()
        display_voxel = slice_to_voxel(
            pix_x, pix_y, self.slice_idx, self.orientation, display_slice_shape
        )
        phys = vs.display_to_world(
            np.array(display_voxel[:3]), is_buffered=self._is_buffered()
        )
        if phys is None:
            return

        vs.update_crosshair_from_phys(phys)

    def update_crosshair_from_slice(self):
        # This method is now redundant as slice_idx setter calls update_crosshair_from_phys
        # and set_current_slice_to_crosshair handles initial setup.
        pass

    def update_filename_overlay(self):
        vol = self.volume
        if not self.image_id or not self.view_state or not vol:
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
            img_idx_str = "?"
            if self.image_id is not None:
                try:
                    idx = (
                        list(self.controller.view_states.keys()).index(self.image_id)
                        + 1
                    )
                    img_idx_str = str(idx)
                except ValueError:
                    pass
            f_name = f"({img_idx_str}) {vol.get_human_readable_file_path()}"

        dpg.set_value(self.filename_text_tag, f_name)

        # Calculate width manually based on string length.
        # (This prevents the 1-frame centering lag caused by get_item_rect_size)
        tw = len(f_name) * 7.2  # 7.2 pixels per char is the standard ImGui font average

        # Center it dynamically at the top of the viewer
        dpg.set_item_pos(
            self.filename_text_tag, [max(5, int((self.quad_w - tw) / 2)), 5]
        )

    def _package_base_layer(self):
        vs = self.view_state
        vol = self.volume
        if not vs or not vol:
            return None

        # Use the display buffer if it exists, otherwise fall back to raw data
        display_data = (
            vs.base_display_data
            if getattr(vs, "base_display_data", None) is not None
            else vol.data
        )

        # Tombstone failsafe: Prevent the renderer from choking on dead memory
        if display_data is None:
            display_data = np.zeros((1, 1, 1), dtype=np.float32)

        dvf_mode = vs.dvf.display_mode if getattr(vol, "is_dvf", False) else "Component"

        return RenderLayer(
            data=display_data,
            is_rgb=getattr(vol, "is_rgb", False),
            num_components=vol.num_components,
            ww=vs.display.ww,
            wl=vs.display.wl,
            cmap_name=vs.display.colormap,
            threshold=vs.display.base_threshold,
            time_idx=vs.camera.time_idx,
            spacing_2d=vol.get_physical_aspect_ratio(self.orientation),
            dvf_mode=dvf_mode,
        )

    def _package_overlay_layer(self):
        vs = self.view_state
        vol = self.volume
        if not vs or not vol or vs.display.overlay_data is None:
            return None
        if vs.display.overlay_id not in self.controller.view_states:
            return None

        ovs = self.controller.view_states[vs.display.overlay_id]

        # ---------------------------------------------------------
        # 2D OVERLAY PHYSICAL CLAMPING
        # ---------------------------------------------------------
        # If the overlay is inherently 2D, verify the base camera is actually looking at its physical plane
        if min(ovs.volume.shape3d) == 1:
            center_phys = self.get_center_physical_coord()
            if center_phys is not None:
                # Map the base view back into the overlay's native index space
                ov_vox = ovs.space.world_to_display(center_phys, is_buffered=False)
                if ov_vox is not None:
                    # Check out-of-plane distances. Continuous index > 0.5 means we scrolled past it.
                    if ovs.volume.shape3d[2] == 1 and abs(ov_vox[0]) > 0.5:
                        return None
                    if ovs.volume.shape3d[1] == 1 and abs(ov_vox[1]) > 0.5:
                        return None
                    if ovs.volume.shape3d[0] == 1 and abs(ov_vox[2]) > 0.5:
                        return None

        # ---Calculate Relative Pixel Shift ---
        base_vs = vs
        base_tx, base_ty, base_tz = 0.0, 0.0, 0.0
        if base_vs.space.transform and base_vs.space.is_active:
            base_tx, base_ty, base_tz = base_vs.space.transform.GetTranslation()

        ov_tx, ov_ty, ov_tz = 0.0, 0.0, 0.0
        if ovs.space.transform and ovs.space.is_active:
            ov_tx, ov_ty, ov_tz = ovs.space.transform.GetTranslation()

        live_dx = ov_tx - base_tx
        live_dy = ov_ty - base_ty
        live_dz = ov_tz - base_tz

        baked_dx, baked_dy, baked_dz = getattr(
            vs.display, "baked_overlay_translation", (0.0, 0.0, 0.0)
        )

        # Mathematical safeguard: 2D translation offset is only valid if there is NO interactive rotation happening!
        if getattr(ovs, "_is_interactive_rotation", False) or getattr(base_vs, "_is_interactive_rotation", False):
            dx_mm, dy_mm, dz_mm = 0.0, 0.0, 0.0
        else:
            dx_mm = live_dx - baked_dx
            dy_mm = live_dy - baked_dy
            dz_mm = live_dz - baked_dz

        sp_x, sp_y, sp_z = vol.spacing

        px_x = dx_mm / sp_x if sp_x else 0
        px_y = dy_mm / sp_y if sp_y else 0
        px_z = dz_mm / sp_z if sp_z else 0

        off_x, off_y, off_slice = 0, 0, 0
        dx, dy, dz = 0.0, 0.0, 0.0

        # Sign conventions mirror the flipud/fliplr applied in SliceRenderer.extract_slice.
        # If those flips change, these signs must change in sync.
        if self.orientation == ViewMode.AXIAL:
            dx, dy, dz = px_x, px_y, px_z
        elif self.orientation == ViewMode.CORONAL:
            dx, dy, dz = px_x, -px_z, px_y
        elif self.orientation == ViewMode.SAGITTAL:
            dx, dy, dz = -px_y, -px_z, px_x

        self.active_overlay_shift_x = dx
        self.active_overlay_shift_y = dy

        # Delegate to GPU if Alpha or DVF, fallback to CPU Array Slicing if Registration/Checkerboard
        if vs.display.overlay_mode in ("Alpha", "DVF"):
            off_x, off_y = 0, 0
        else:
            off_x = int(round(dx))
            off_y = int(round(dy))
            self.active_overlay_shift_x = 0.0
            self.active_overlay_shift_y = 0.0

        off_slice = int(round(dz))

        return RenderLayer(
            data=vs.display.overlay_data,
            is_rgb=getattr(ovs.volume, "is_rgb", False),
            num_components=ovs.volume.num_components,
            ww=ovs.display.ww,
            wl=ovs.display.wl,
            cmap_name=ovs.display.colormap,
            threshold=ovs.display.base_threshold,
            time_idx=min(vs.camera.time_idx, ovs.volume.num_timepoints - 1),
            spacing_2d=vol.get_physical_aspect_ratio(self.orientation),
            offset_x=off_x,
            offset_y=off_y,
            offset_slice=off_slice,
        )

    def _package_roi_layers(self):
        vs = self.view_state
        vol = self.volume
        if not vs or not vol:
            return []

        active_rois = []
        for roi_id, roi_state in vs.rois.items():
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

            t_idx = min(vs.camera.time_idx, roi_vol.num_timepoints - 1)
            base_z, base_y, base_x = vol.shape3d
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

        vs = self.view_state
        vol = self.volume
        if self.image_id is None or not vol or not vs:
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

        if force_reblend or self.last_rgba_flat is None:
            self._compute_raw_slice_buffers()

        if self.should_use_voxels_strips():
            return

        self._upload_base_texture()
        self._upload_overlay_texture()

    def _compute_raw_slice_buffers(self):
        vs = self.view_state
        base_layer = self._package_base_layer()
        overlay_layer = self._package_overlay_layer()
        active_rois = self._package_roi_layers()

        if not vs or base_layer is None:
            return

        # Render Base & Overlay Separately
        if vs.display.overlay_mode == "Alpha" and overlay_layer is not None:
            self.last_rgba_flat, self.last_rgba_shape = SliceRenderer.get_slice_rgba(
                base=base_layer,
                overlay=None,
                overlay_opacity=1.0,
                overlay_mode="Alpha",
                slice_idx=self.slice_idx,
                orientation=self.orientation,
                rois=active_rois,
            )

            self.last_overlay_rgba_flat, self.last_overlay_rgba_shape = SliceRenderer.get_slice_rgba(
                base=overlay_layer,
                overlay=None,
                overlay_opacity=1.0,
                overlay_mode="Alpha",
                slice_idx=self.slice_idx - overlay_layer.offset_slice,
                orientation=self.orientation,
                rois=[],
            )
        else:
            self.last_rgba_flat, self.last_rgba_shape = SliceRenderer.get_slice_rgba(
                base=base_layer,
                overlay=overlay_layer,
                overlay_opacity=vs.display.overlay_opacity,
                overlay_mode=vs.display.overlay_mode,
                slice_idx=self.slice_idx,
                orientation=self.orientation,
                checkerboard_size=vs.display.overlay_checkerboard_size,
                checkerboard_swap=vs.display.overlay_checkerboard_swap,
                rois=active_rois,
            )
            self.last_overlay_rgba_flat = None
            self.last_overlay_rgba_shape = None

    def _upload_base_texture(self):
        if not dpg.does_item_exist(self.texture_tag) or self.last_rgba_flat is None:
            return

        vs = self.view_state
        if not vs:
            return

        is_pixelated_sw = (self._effective_pixelated_zoom()
                           and not self._is_hw_gl
                           and not self.should_use_voxels_strips())

        # --- Interactive rotation preview (works in any zoom mode) ---
        if vs._is_interactive_rotation:
            # Full 3D MPR affine kernel for both in-plane and out-of-plane
            if is_pixelated_sw:
                canvas_w, canvas_h = self._get_canvas_size()
                fast_rgba = compute_native_voxel_base(
                    self, self.current_pmin, self.current_pmax, canvas_w, canvas_h
                )
            else:
                sh, sw = self.get_slice_shape()
                fast_rgba = compute_native_voxel_base(
                    self, [0.0, 0.0], [float(sw), float(sh)], sw, sh
                )
            if fast_rgba is not None:
                self._safe_set_texture(self.texture_tag, fast_rgba,
                                       getattr(self, "_tex_w", 1), getattr(self, "_tex_h", 1))
                return

        # --- Normal rendering path ---
        if not is_pixelated_sw:
            self._safe_set_texture(self.texture_tag, self.last_rgba_flat,
                                   getattr(self, "_tex_w", 1), getattr(self, "_tex_h", 1))
            return

        canvas_w, canvas_h = self._get_canvas_size()
        actual_shape = getattr(self, "last_rgba_shape", self.get_slice_shape())
        rgba_2d = np.asarray(self.last_rgba_flat).reshape(actual_shape[0], actual_shape[1], 4)

        has_alpha_overlay = (
            vs.display.overlay_id
            and vs.display.overlay_mode == "Alpha"
            and self.last_overlay_rgba_flat is not None
        )

        is_lazy_live = False

        # SW_SINGLE_MERGED: CPU alpha-blend overlay into base before NN scaling
        if not is_lazy_live and self.nn_mode == NNMode.SW_SINGLE_MERGED and has_alpha_overlay:
            ov_actual_shape = getattr(self, "last_overlay_rgba_shape", self.get_slice_shape())
            ov_rgba_2d = np.asarray(self.last_overlay_rgba_flat).reshape(ov_actual_shape[0], ov_actual_shape[1], 4)
            rgba_2d = blend_slices_cpu(
                rgba_2d, ov_rgba_2d,
                vs.display.overlay_opacity,
                self.active_overlay_shift_x,
                self.active_overlay_shift_y,
            )

        if not hasattr(self, "_nn_base_buf") or self._nn_base_buf.shape[:2] != (canvas_h, canvas_w):
            self._nn_base_buf = np.zeros((canvas_h, canvas_w, 4), dtype=np.float32)
            self._nn_base_crop = None

        nn_base, crop = compute_software_nearest_neighbor(
            rgba_2d, self.current_pmin, self.current_pmax, canvas_w, canvas_h,
            out_buffer=self._nn_base_buf, last_crop=self._nn_base_crop
        )
        self._nn_base_crop = crop

        # SW_SINGLE_NATIVE: paint overlay at native voxel resolution into the NN base
        if not is_lazy_live and self.nn_mode == NNMode.SW_SINGLE_NATIVE and has_alpha_overlay:
            if nn_base is rgba_2d:  # identity pass returned the slice cache — copy first
                self._nn_base_buf[:rgba_2d.shape[0], :rgba_2d.shape[1]] = rgba_2d
                nn_base = self._nn_base_buf
            compute_native_voxel_overlay(
                self, self.current_pmin, self.current_pmax, canvas_w, canvas_h,
                target_buffer=nn_base, opacity=vs.display.overlay_opacity
            )

        self._safe_set_texture(self.texture_tag, nn_base.ravel(),
                               getattr(self, "_tex_w", 1), getattr(self, "_tex_h", 1))

    def _upload_overlay_texture(self):
        if not hasattr(self, "overlay_texture_tag") or not dpg.does_item_exist(self.overlay_texture_tag):
            return

        vs = self.view_state
        if not vs or not vs.display.overlay_id or vs.display.overlay_mode != "Alpha":
            return

        if self.last_overlay_rgba_flat is None:
            return

        is_sw_nn = self._effective_pixelated_zoom() and not self._is_hw_gl and not self.should_use_voxels_strips()

        if not is_sw_nn:
            self._safe_set_texture(self.overlay_texture_tag, self.last_overlay_rgba_flat,
                                   getattr(self, "_ov_tex_w", 1), getattr(self, "_ov_tex_h", 1))
            return

        # Modes SW_SINGLE_MERGED and SW_SINGLE_NATIVE precomposite the overlay into the
        # base texture on the CPU — no separate overlay upload needed.
        if self.nn_mode in (NNMode.SW_SINGLE_MERGED, NNMode.SW_SINGLE_NATIVE):
            return

        canvas_w, canvas_h = self._get_canvas_size()

        if self.nn_mode == NNMode.SW_DUAL_NATIVE:
            ov_rgba_display = compute_native_voxel_overlay(
                self, self.current_pmin, self.current_pmax, canvas_w, canvas_h
            )
            if ov_rgba_display is not None:
                self._safe_set_texture(self.overlay_texture_tag, ov_rgba_display,
                                       getattr(self, "_ov_tex_w", 1), getattr(self, "_ov_tex_h", 1))
        else:
            # SW_DUAL_RESAMPLED: NN-scale the ITK-resampled overlay
            ov_actual_shape = getattr(self, "last_overlay_rgba_shape", self.get_slice_shape())
            ov_rgba_2d = np.asarray(self.last_overlay_rgba_flat).reshape(ov_actual_shape[0], ov_actual_shape[1], 4)

            if not hasattr(self, "_nn_ov_buf") or self._nn_ov_buf.shape[:2] != (canvas_h, canvas_w):
                self._nn_ov_buf = np.zeros((canvas_h, canvas_w, 4), dtype=np.float32)
                self._nn_ov_crop = None

            nn_ov, crop = compute_software_nearest_neighbor(
                ov_rgba_2d, self.current_pmin, self.current_pmax, canvas_w, canvas_h,
                out_buffer=self._nn_ov_buf, last_crop=self._nn_ov_crop
            )
            self._nn_ov_crop = crop
            self._safe_set_texture(self.overlay_texture_tag, nn_ov.ravel(),
                                   getattr(self, "_ov_tex_w", 1), getattr(self, "_ov_tex_h", 1))

    def _safe_set_texture(self, tag: str, data, tex_w: int, tex_h: int) -> bool:
        """Upload data to a DPG texture after validating the buffer size matches.
        Returns False (and marks dirty for retry) if there is a size mismatch."""
        expected = tex_w * tex_h * 4
        actual = len(data) if hasattr(data, "__len__") else -1
        if actual != expected:
            self.is_viewer_data_dirty = True
            return False
        dpg.set_value(tag, data)  # type: ignore
        return True

    def _get_canvas_size(self) -> tuple[int, int]:
        """Returns (canvas_w, canvas_h) in pixels, accounting for viewport padding."""
        pad = self.controller.gui.ui_cfg["layout"].get("viewport_padding", 4) * 2
        return int(max(1, self.quad_w - pad)), int(max(1, self.quad_h - pad))

    @property
    def _is_hw_gl(self) -> bool:
        """True when the hardware GL_NEAREST path is active (Linux/Windows only)."""
        return GL_NEAREST_SUPPORTED and self.nn_mode == NNMode.HW_GL_NEAREST

    def _is_lazy_live(self) -> bool:
        """True while the user is actively interacting (stable within one tick)."""
        return self._lazy_live_flag

    def _mark_lazy_interaction(self):
        """Record interaction time and raise the live flag on all lazy-enabled viewers."""
        now = time.time()
        for v in self.controller.viewers.values():
            if v.lazy_lin:
                v._last_move_time = now
                v._nn_settle_done = False
                v._lazy_live_flag = True

    def _effective_pixelated_zoom(self) -> bool:
        """Returns False during lazy_lin interaction so the whole pipeline uses GPU bilinear."""
        vs = self.view_state
        if not vs or not vs.display.pixelated_zoom:
            return False
        if self.lazy_lin and self._is_lazy_live():
            return False
        return True

    def should_use_voxels_strips(self):
        vs = self.view_state
        if not vs or not self.volume or not vs.display.use_voxel_strips:
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
        vs = self.view_state
        vol = self.volume
        if not self.is_image_orientation() or not vs or not vol:
            return

        if getattr(self, "last_rgba_shape", None) is not None:
            h, w = self.last_rgba_shape
        else:
            shape = self.get_slice_shape()
            h, w = shape[0], shape[1]

        if self.should_use_voxels_strips() and self.last_rgba_flat is not None:
            if dpg.does_item_exist(self.image_tag):
                dpg.configure_item(self.image_tag, show=False)
            if hasattr(self, "overlay_image_tag") and dpg.does_item_exist(
                self.overlay_image_tag
            ):
                dpg.configure_item(self.overlay_image_tag, show=False)
            self.drawer.draw_voxels_as_strips(self.last_rgba_flat, h, w)
        else:
            if self.active_strips_node and dpg.does_item_exist(self.active_strips_node):
                dpg.configure_item(self.active_strips_node, show=False)

            if dpg.does_item_exist(self.image_tag):
                dpg.configure_item(self.image_tag, show=True)

                op = int(vs.display.overlay_opacity * 255)
                has_overlay = (
                    self.last_overlay_rgba_flat is not None
                    and hasattr(self, "overlay_image_tag")
                    and dpg.does_item_exist(self.overlay_image_tag)
                )

                # Base image positioning: on Linux/Windows GL_NEAREST handles NN upscaling
                # so the slice-sized texture is positioned at its physical screen extent.
                # On macOS the canvas-sized NN texture covers the full canvas instead.
                is_sw_nn = self._effective_pixelated_zoom() and not self._is_hw_gl and not self.should_use_voxels_strips()

                if is_sw_nn:
                    canvas_w, canvas_h = self._get_canvas_size()
                    dpg.configure_item(
                        self.image_tag, pmin=[0, 0], pmax=[canvas_w, canvas_h]
                    )
                else:
                    dpg.configure_item(
                        self.image_tag, pmin=self.current_pmin, pmax=self.current_pmax
                    )

                if has_overlay:
                    is_precomposited = is_sw_nn and self.nn_mode in (NNMode.SW_SINGLE_MERGED, NNMode.SW_SINGLE_NATIVE)

                    if is_precomposited:
                        if dpg.does_item_exist(self.overlay_image_tag):
                            dpg.configure_item(self.overlay_image_tag, show=False)
                    elif is_sw_nn:
                        canvas_w, canvas_h = self._get_canvas_size()
                        dpg.configure_item(
                            self.overlay_image_tag,
                            pmin=[0, 0],
                            pmax=[canvas_w, canvas_h],
                            color=[255, 255, 255, op],
                            show=True,
                        )
                    else:
                        disp_w = self.current_pmax[0] - self.current_pmin[0]
                        disp_h = self.current_pmax[1] - self.current_pmin[1]
                        shift_x = (
                            self.active_overlay_shift_x * (disp_w / w) if w > 0 else 0
                        )
                        shift_y = (
                            self.active_overlay_shift_y * (disp_h / h) if h > 0 else 0
                        )
                        dpg.configure_item(
                            self.overlay_image_tag,
                            pmin=[self.current_pmin[0] + shift_x,
                                  self.current_pmin[1] + shift_y],
                            pmax=[self.current_pmax[0] + shift_x,
                                  self.current_pmax[1] + shift_y],
                            color=[255, 255, 255, op],
                            show=True,
                        )

                if (
                    not has_overlay
                    and hasattr(self, "overlay_image_tag")
                    and dpg.does_item_exist(self.overlay_image_tag)
                ):
                    dpg.configure_item(self.overlay_image_tag, show=False)

        if vs.camera.show_grid:
            self.drawer.draw_voxel_grid(h, w)
        elif self.active_grid_node and dpg.does_item_exist(self.active_grid_node):
            dpg.configure_item(self.active_grid_node, show=False)

        if vs.camera.show_axis:
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
        ext = getattr(vs, "extraction", None)
        if ext and ext.is_enabled and ext.show_preview:
            self.controller.extraction.update_preview(
                self.image_id,
                vol,
                vs,
                ext.threshold_min,
                ext.threshold_max,
                [
                    (self.orientation, self.slice_idx)
                ],  # This is now the display slice index
            )

        self.controller.roi.update_roi_contours(self)

        self.drawer.draw_contours()
        self.drawer.draw_vector_field()
        self.update_tracker()
        self.update_filename_overlay()

    def update_tracker(self):
        vs = self.view_state
        vol = self.volume
        if (
            self.image_id is None
            or not vs
            or not vol
            or not vs.camera.show_tracker
            or not self.is_image_orientation()
        ):
            dpg.set_value(self.tracker_tag, "")
            self._external_tracker_active = False
            return

        is_dragging = False
        if self.controller.gui and hasattr(self.controller.gui, "interaction"):
            active_tool = self.controller.gui.interaction.active_tool
            is_dragging = getattr(active_tool, "drag_viewer", None) == self

        try:
            mx, my = dpg.get_drawing_mouse_pos()
        except Exception:
            mx, my = -1, -1

        target_phys = vs.camera.target_tracker_phys
        target_phys_tuple = tuple(target_phys) if target_phys is not None else None

        # Throttle: Only run heavy ITK physics if the spatial reality actually shifted
        tracker_state = (
            mx,
            my,
            self.slice_idx,  # This is now the display slice index
            vs.camera.time_idx,
            self.zoom,
            self.pan_offset[0],
            self.pan_offset[1],
            is_dragging,
            target_phys_tuple,
        )
        if self._last_tracker_state == tracker_state:
            return
        self._last_tracker_state = tracker_state

        # 1. LOCAL VIEWER: Are we the active hover source?
        pix_x, pix_y = self.get_mouse_slice_coords(
            ignore_hover=is_dragging, allow_outside=is_dragging
        )

        if pix_x is not None:
            self._was_hovered = True
            self._external_tracker_active = False

            # Use the viewer's current slice_idx (which is the display slice index)
            idx = self.slice_idx
            shape = self.get_slice_shape()
            v = slice_to_voxel(pix_x, pix_y, idx, self.orientation, shape)
            phys = vs.display_to_world(
                np.array(v), is_buffered=self._is_buffered()
            )

            # Clear our own passive target so we don't fight ourselves
            vs.camera.target_tracker_phys = None

            if vs.sync_group > 0:
                self.controller.sync.propagate_tracker(self, phys)

            is_external = False
        else:
            # 2. PASSIVE VIEWER: We are not hovered, check memory for a target!

            # Send the "clear" signal exactly once when the mouse leaves us
            if self._was_hovered:
                self._was_hovered = False
                if vs.sync_group > 0 and not is_dragging:
                    self.controller.sync.propagate_tracker(self, None)

            phys = vs.camera.target_tracker_phys
            if phys is None:
                dpg.set_value(self.tracker_tag, "")
                self._external_tracker_active = False
                return

            self._external_tracker_active = True
            is_external = True
        v = vs.world_to_display(phys, is_buffered=self._is_buffered())

        # --- THE NEUTRALIZED SPATIAL ENGINE ---
        # Even if we are viewing a rotated buffer, we consistently calculate the 'Native Voxel'
        # for reporting. This ensures tracker text and crosshair math remain resilient to
        # 'Straighten on Load' and manual registration offsets.
        native_v = vs.world_to_display(phys, is_buffered=False)

        # --- The drawing logic remains exactly the same! ---
        col = self.controller.settings.data["colors"]["tracker_text"]
        dpg.configure_item(self.tracker_tag, color=col)

        # Look up the value at the physical coordinate
        info = self.controller.get_pixel_values_at_phys(
            self.image_id, phys, vs.camera.time_idx
        )

        if info is not None:
            val = info["base_val"]

            if not is_external:
                # This assertion helps Pylance understand that 'native_v' cannot be None
                # in this branch, resolving the incorrect type warning.
                assert native_v is not None

                self.mouse_value, self.mouse_voxel, self.mouse_phys_coord = (
                    val,
                    [native_v[0], native_v[1], native_v[2], vs.camera.time_idx],
                    phys,
                )

            if val is None:
                val_str = "-"
            else:
                if getattr(vol, "is_rgb", False):
                    val_str = f"{val[0]:g} {val[1]:g} {val[2]:g}"
                elif getattr(vol, "is_dvf", False):
                    mag = np.linalg.norm(val)
                    comps = []
                    for i, v in enumerate(val):
                        s = fmt(v, 2)
                        comps.append(f"*{s}" if i == vs.camera.time_idx else s)
                    val_str = f"[{' '.join(comps)}] L:{fmt(mag, 2)}"
                else:
                    val_str = f"{val:g}"
            text_lines = [f"{val_str}"]

            if info["overlay_val"] is not None:
                ov_val = info["overlay_val"]
                ov_id = vs.display.overlay_id
                ov_vol = self.controller.volumes.get(ov_id)
                if ov_vol and getattr(ov_vol, "is_dvf", False):
                    mag = np.linalg.norm(ov_val)
                    comps = []
                    for i, v in enumerate(ov_val):
                        s = fmt(v, 2)
                        comps.append(f"*{s}" if i == vs.camera.time_idx else s)
                    text_lines[0] += f" ([{' '.join(comps)}] L:{fmt(mag, 2)})"
                elif ov_vol and getattr(ov_vol, "is_rgb", False):
                    text_lines[0] += f" ({ov_val[0]:g} {ov_val[1]:g} {ov_val[2]:g})"
                else:
                    text_lines[0] += f" ({ov_val:g})"

            if info["rois"]:
                text_lines[0] += f"  {', '.join(info['rois'])}"

            # Format the text differently depending on if we are active or passive
            if is_external:
                final_text = text_lines[0]
            else:
                # This assertion helps Pylance understand that 'native_v' cannot be None
                # in this branch, resolving the incorrect type warning.
                assert native_v is not None

                if vol.num_timepoints > 1:
                    t_str = str(vs.camera.time_idx)
                    if getattr(vol, "is_dvf", False):
                        t_str = (
                            ["dx", "dy", "dz"][vs.camera.time_idx]
                            if vs.camera.time_idx < 3
                            else t_str
                        )
                    text_lines.append(
                        f"{native_v[0]:.1f} {native_v[1]:.1f} {native_v[2]:.1f} {t_str}"
                    )
                else:
                    text_lines.append(fmt(native_v, 1))

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
        vs = self.view_state
        if vs:
            vs.clear_reg_anchors()
        self.needs_recenter = True
        self.is_geometry_dirty = True
        self.controller.sync.propagate_camera(self)

    def action_view_histogram(self):
        self.set_orientation(ViewMode.HISTOGRAM)

    def action_toggle_pixelated_zoom(self):
        vs = self.view_state
        if not vs:
            return
        if vs.display.use_voxel_strips:
            vs.display.use_voxel_strips = False
            vs.display.pixelated_zoom = False
        else:
            vs.display.pixelated_zoom = not vs.display.pixelated_zoom
        vs.is_data_dirty = True

    def action_toggle_strips(self):
        vs = self.view_state
        if not vs:
            return
        vs.display.use_voxel_strips = not vs.display.use_voxel_strips
        vs.is_data_dirty = True

    def action_toggle_legend(self):
        self.show_legend = not self.show_legend

    def action_toggle_grid(self):
        vs = self.view_state
        if vs:
            vs.camera.show_grid = not vs.camera.show_grid

    def action_toggle_axis(self):
        vs = self.view_state
        if vs:
            vs.camera.show_axis = not vs.camera.show_axis

    def action_toggle_scalebar(self):
        vs = self.view_state
        if vs:
            vs.camera.show_scalebar = not vs.camera.show_scalebar

    def action_toggle_filename(self):
        vs = self.view_state
        if vs:
            current = getattr(vs.camera, "show_filename", 0)
            if isinstance(current, bool):
                current = 1 if current else 0
            vs.camera.show_filename = (current + 1) % 3

    def on_key_press(self, key):
        if not self.view_state or self._shortcut_map is None:
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
                
        # Secret developer debugging bindings
        if getattr(self.controller, "debug_mode", False):
            if key == dpg.mvKey_J:
                cfg = self.controller.settings.data.setdefault("rendering", {})
                st = cfg.get("single_texture", "Auto")
                nv = cfg.get("native_voxel", "Auto")
                if st == "Auto": st, nv = True, True
                elif st is True and nv is True: st, nv = True, False
                elif st is True and nv is False: st, nv = False, False
                elif st is False and nv is False: st, nv = False, True
                else: st, nv = "Auto", "Auto"
                cfg["single_texture"] = st
                cfg["native_voxel"] = nv
                self.controller.save_settings()
                self.controller._flag_all_viewers_dirty()
                self.controller.status_message = f"Debug NN: Single={st}, Native={nv}"
                self.controller.ui_needs_refresh = True
                if self.controller.gui:
                    self.controller.gui._init_rendering_menu()
                return
            if key == dpg.mvKey_T:
                cfg = self.controller.settings.data.setdefault("rendering", {})
                ll = cfg.get("lazy_lin", "Auto")
                if ll == "Auto": ll = True
                elif ll is True: ll = False
                else: ll = "Auto"
                cfg["lazy_lin"] = ll
                self.controller.save_settings()
                self.controller._flag_all_viewers_dirty()
                self.controller.status_message = f"Debug Lazy-Lin: {ll}"
                self.controller.ui_needs_refresh = True
                if self.controller.gui:
                    self.controller.gui._init_rendering_menu()
                return

    def on_scroll(self, delta=1):
        vs = self.view_state
        vol = self.volume
        if (
            self.image_id is None
            or not self.is_image_orientation()
            or not vs
            or not vol
        ):
            return

        current_display_slice_idx = self.slice_idx
        max_display_slice_idx = self.get_display_num_slices() - 1

        new_display_slice_idx = current_display_slice_idx + delta
        new_display_slice_idx = np.clip(new_display_slice_idx, 0, max_display_slice_idx)

        # Update the slice_idx property, which will internally call vs.update_crosshair_from_phys
        self.slice_idx = int(new_display_slice_idx)

        self.controller.sync.propagate_sync(self.image_id)
        self.is_viewer_data_dirty = True

    def on_time_scroll(self, delta):
        vs = self.view_state
        if vs is None:
            return

        vol = self.volume
        if self.image_id is None or not vs or not vol:
            return
        nt = vol.num_timepoints
        if nt <= 1:
            return

        # Loop the time index
        vs.camera.time_idx = (vs.camera.time_idx + delta) % nt

        # Update the crosshair's physical position based on the new time index
        if vs.camera.crosshair_phys_coord is not None:
            vs.update_crosshair_from_phys(vs.camera.crosshair_phys_coord)
        self.controller.sync.propagate_time_idx(self.image_id)
        self.controller.sync.propagate_sync(self.image_id)
        vs.is_data_dirty = True

    def on_mouse_down(self):
        vs = self.view_state
        if self.image_id is None or not self.is_image_orientation() or not vs:
            return

        # 1. Capture the absolute starting mouse position for Pan/Zoom
        self.drag_start_mouse = dpg.get_mouse_pos(local=False)

        # 2. Snapshot the current pan so the drag delta can be added to it
        self.drag_start_pan = list(self.pan_offset)

    def on_drag(self, data):
        vs = self.view_state
        if self.image_id is None or not self.is_image_orientation() or not vs:
            return

        # --- 3. CALCULATE ABSOLUTE DRAG ---
        current_pos = dpg.get_mouse_pos(local=False)
        if self.drag_start_mouse is None:
            return

        total_dx = current_pos[0] - self.drag_start_mouse[0]
        total_dy = current_pos[1] - self.drag_start_mouse[1]

        is_button_left = dpg.is_mouse_button_down(dpg.mvMouseButton_Left)
        is_button_mid = dpg.is_mouse_button_down(dpg.mvMouseButton_Middle)

        is_cmd = dpg.is_key_down(getattr(dpg, "mvKey_LWin", 343)) or dpg.is_key_down(getattr(dpg, "mvKey_RWin", 347)) or dpg.is_key_down(343) or dpg.is_key_down(347)
        is_ctrl = dpg.is_key_down(dpg.mvKey_LControl) or dpg.is_key_down(dpg.mvKey_RControl)
        is_shift = dpg.is_key_down(dpg.mvKey_LShift) or dpg.is_key_down(dpg.mvKey_RShift)

        is_pan_mod = is_cmd or is_ctrl
        is_pan_drag = (is_pan_mod and is_button_left) or is_button_mid

        if not is_pan_drag and not is_shift and is_button_left:
            px, py = self.get_mouse_slice_coords(ignore_hover=True, allow_outside=True)
            if px is not None:
                # Performance: Dragging the crosshair forces other orthogonal synced viewers 
                # to slice rapidly. To keep the crosshair drag at 60fps, we selectively trigger 
                # lazy modes on them, but keep the active viewer perfectly sharp.
                now = time.time()
                my_vs = self.view_state
                for v in self.controller.viewers.values():
                    if v.orientation != self.orientation and v.lazy_lin:
                        v_vs = v.view_state
                        if v_vs and my_vs and (v.image_id == self.image_id or (my_vs.sync_group > 0 and my_vs.sync_group == v_vs.sync_group)):
                            v._last_move_time = now
                            v._nn_settle_done = False
                            v._lazy_live_flag = True

                self.update_crosshair_data(px, py)
                self.controller.sync.propagate_sync(self.image_id)

        elif is_pan_drag and self.drag_start_pan is not None:
            if vs:
                vs.clear_reg_anchors()
            self.pan_offset[0] = self.drag_start_pan[0] + total_dx
            self.pan_offset[1] = self.drag_start_pan[1] + total_dy
            self.is_geometry_dirty = True
            self._mark_lazy_interaction()  # no-op if no viewer has lazy_lin; covers synced viewers that do
            self.controller.sync.propagate_camera(self)
            # Prevent self-snapping
            cent = self.get_center_physical_coord()
            if cent is not None:
                self.last_consumed_center = list(cent)

    def on_zoom(self, direction):
        vs = self.view_state
        vol = self.volume
        if (
            self.image_id is None
            or not self.is_image_orientation()
            or not vs
            or not vol
        ):
            return

        mx, my = dpg.get_drawing_mouse_pos()
        oz = self.zoom
        speed = self.controller.settings.data["interaction"]["zoom_speed"]
        if vs:
            vs.clear_reg_anchors()
        new_zoom = max(
            1e-5, self.zoom * (speed if direction == "in" else (1.0 / speed))
        )
        self.zoom = new_zoom

        dx, dy = self.mapper.calculate_zoom_pan_delta(mx + 0.5, my + 0.5, oz, self.zoom)
        self.pan_offset[0] += dx
        self.pan_offset[1] += dy

        self.is_geometry_dirty = True
        self._mark_lazy_interaction()  # no-op if no viewer has lazy_lin; covers synced viewers that do
        self.controller.sync.propagate_camera(self)

        # Prevent self-snapping
        self.last_consumed_ppm = self.get_pixels_per_mm()
        cent = self.get_center_physical_coord()
        if cent is not None:
            self.last_consumed_center = list(cent)
