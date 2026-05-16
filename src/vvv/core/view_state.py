import numpy as np
from contextlib import contextmanager
from vvv.config import WL_PRESETS
from vvv.maths.geometry import SpatialEngine
from vvv.utils import ViewMode

_SENTINEL = object()


class CameraState:
    """Stores all transient spatial and navigation parameters."""

    _parent: "ViewState | None"

    # Type hints
    time_idx: int
    show_axis: bool
    show_tracker: bool
    show_crosshair: bool
    show_scalebar: bool
    show_grid: bool
    show_legend: bool
    show_profiles: bool
    show_filename: int

    # Fields that trigger a GEOMETRY redraw
    _GEOM_FIELDS = {
        "time_idx",
        "show_axis",
        "show_tracker",
        "show_crosshair",
        "show_scalebar",
        "show_grid",
        "show_legend",
        "show_profiles",
        "show_filename",
    }

    def __init__(self, volume, parent_vs: "ViewState | None" = None):
        self._parent = parent_vs
        self.zoom = {
            ViewMode.AXIAL: 1.0,
            ViewMode.SAGITTAL: 1.0,
            ViewMode.CORONAL: 1.0,
        }
        self.pan = {
            ViewMode.AXIAL: [0.0, 0.0],
            ViewMode.SAGITTAL: [0.0, 0.0],
            ViewMode.CORONAL: [0.0, 0.0],
        }
        self.slices = {
            ViewMode.AXIAL: volume.shape3d[0] // 2,
            ViewMode.SAGITTAL: volume.shape3d[2] // 2,
            ViewMode.CORONAL: volume.shape3d[1] // 2,
        }

        self.crosshair_voxel: list[float] | None = None
        self.crosshair_phys_coord: np.ndarray | None = None
        self.last_orientation = ViewMode.AXIAL

        self.time_idx = 0
        self.show_axis = True
        self.show_tracker = True
        self.show_crosshair = True
        self.show_scalebar = False
        self.show_grid = False
        self.show_legend = False
        self.show_profiles = True
        self.show_filename = 0

        # State-Only Sync Targets
        self.target_ppm = None
        self.target_center = None
        self.target_tracker_phys = None

    def __setattr__(self, name, value):
        if name in self._GEOM_FIELDS and getattr(self, name, _SENTINEL) != value:
            object.__setattr__(self, name, value)
            parent = getattr(self, "_parent", None)
            if parent is not None:
                parent.is_geometry_dirty = True
            return
        object.__setattr__(self, name, value)

    def to_dict(self):
        return {
            "zoom": {k.name: float(v) for k, v in self.zoom.items()},
            "pan": {k.name: [float(p) for p in v] for k, v in self.pan.items()},
            "slices": {k.name: int(v) for k, v in self.slices.items()},
            "time_idx": int(self.time_idx),
            "show_axis": bool(self.show_axis),
            "show_tracker": bool(self.show_tracker),
            "show_crosshair": bool(self.show_crosshair),
            "show_scalebar": bool(self.show_scalebar),
            "show_grid": bool(self.show_grid),
            "show_legend": bool(self.show_legend),
            "show_profiles": bool(self.show_profiles),
            "show_filename": int(self.show_filename),
            "last_orientation": self.last_orientation.name,
            "crosshair_voxel": (
                [float(x) for x in self.crosshair_voxel]
                if self.crosshair_voxel
                else None
            ),
            "crosshair_phys_coord": (
                [float(x) for x in self.crosshair_phys_coord]
                if self.crosshair_phys_coord is not None
                else None
            ),
        }

    def from_dict(self, d):
        def parse_dict(source_dict):
            res = {}
            for k, v in source_dict.items():
                clean_k = k.split(".")[-1] if "." in k else k
                if clean_k in ViewMode.__members__:
                    res[ViewMode[clean_k]] = v
            return res

        if "zoom" in d:
            self.zoom.update(parse_dict(d["zoom"]))
        if "pan" in d:
            self.pan.update(parse_dict(d["pan"]))
        if "slices" in d:
            self.slices.update(parse_dict(d["slices"]))

        self.time_idx = d.get("time_idx", self.time_idx)
        self.show_axis = d.get("show_axis", self.show_axis)
        self.show_tracker = d.get("show_tracker", self.show_tracker)
        self.show_crosshair = d.get("show_crosshair", self.show_crosshair)
        self.show_scalebar = d.get("show_scalebar", self.show_scalebar)
        self.show_grid = d.get("show_grid", self.show_grid)
        self.show_legend = d.get("show_legend", self.show_legend)
        self.show_profiles = d.get("show_profiles", self.show_profiles)
        self.show_filename = d.get("show_filename", self.show_filename)

        if "last_orientation" in d:
            self.last_orientation = ViewMode[d["last_orientation"]]
        if "crosshair_voxel" in d:
            self.crosshair_voxel = d["crosshair_voxel"]
        if "crosshair_phys_coord" in d and d["crosshair_phys_coord"] is not None:
            self.crosshair_phys_coord = np.array(d["crosshair_phys_coord"])


class DisplayState:
    """Stores all radiometric and rendering properties."""

    _parent: "ViewState | None"

    # Type hints
    ww: float
    wl: float
    colormap: str
    base_threshold: float | None
    overlay_id: str | None
    overlay_opacity: float
    overlay_mode: str
    overlay_checkerboard_size: float
    overlay_checkerboard_swap: bool
    pixelated_zoom: bool
    use_voxel_strips: bool

    # Fields that trigger a DATA redraw
    _DATA_FIELDS = {
        "ww",
        "wl",
        "colormap",
        "base_threshold",
        "overlay_id",
        "overlay_opacity",
        "overlay_mode",
        "overlay_checkerboard_size",
        "overlay_checkerboard_swap",
        "pixelated_zoom",
        "use_voxel_strips",
    }

    def __init__(self, parent_vs: "ViewState | None" = None):
        self._parent = parent_vs
        self.overlay_data: np.ndarray | None = None
        self._sitk_overlay_cache = None
        self.baked_overlay_translation = (0.0, 0.0, 0.0)
        self.ww = 1.0
        self.wl = 0.5
        self.colormap = "Grayscale"
        self.base_threshold = None
        self.overlay_id = None
        self.overlay_opacity = 0.5
        self.overlay_mode = "Alpha"
        self.overlay_checkerboard_size = 20.0
        self.overlay_checkerboard_swap = False
        self.pixelated_zoom = False
        self.use_voxel_strips = False

    def __setattr__(self, name, value):
        if name in self._DATA_FIELDS and getattr(self, name, _SENTINEL) != value:
            object.__setattr__(self, name, value)
            parent = getattr(self, "_parent", None)
            if parent is not None:
                parent.is_data_dirty = True
            return
        object.__setattr__(self, name, value)

    def to_dict(self):
        return {
            "ww": float(self.ww),
            "wl": float(self.wl),
            "colormap": str(self.colormap),
            "base_threshold": (
                float(self.base_threshold) if self.base_threshold is not None else None
            ),
            "pixelated_zoom": bool(self.pixelated_zoom),
            "use_voxel_strips": bool(self.use_voxel_strips),
            "overlay_opacity": float(self.overlay_opacity),
            "overlay_mode": str(self.overlay_mode),
            "overlay_checkerboard_size": float(self.overlay_checkerboard_size),
            "overlay_checkerboard_swap": bool(self.overlay_checkerboard_swap),
        }

    def from_dict(self, d):
        self.ww = d.get("ww", self.ww)
        self.wl = d.get("wl", self.wl)
        self.colormap = d.get("colormap", self.colormap)
        self.base_threshold = d.get("base_threshold", self.base_threshold)
        self.pixelated_zoom = d.get("pixelated_zoom", self.pixelated_zoom)
        self.use_voxel_strips = d.get("use_voxel_strips", self.use_voxel_strips)
        self.overlay_opacity = d.get("overlay_opacity", self.overlay_opacity)
        self.overlay_mode = d.get("overlay_mode", self.overlay_mode)
        self.overlay_checkerboard_size = d.get(
            "overlay_checkerboard_size", self.overlay_checkerboard_size
        )
        self.overlay_checkerboard_swap = d.get(
            "overlay_checkerboard_swap", self.overlay_checkerboard_swap
        )


class ExtractionState:
    """Stores parameters for interactive contour thresholding."""

    _parent: "ViewState | None"

    is_enabled: bool
    threshold_min: float
    threshold_max: float
    show_preview: bool
    preview_color_min: list
    preview_color_max: list
    subpixel_accurate: bool
    preview_thickness: float

    _GEOM_FIELDS = {
        "is_enabled",
        "threshold_min",
        "threshold_max",
        "show_preview",
        "preview_color_min",
        "preview_color_max",
        "subpixel_accurate",
        "preview_thickness",
    }

    def __init__(self, parent_vs: "ViewState | None" = None):
        self._parent = parent_vs
        self.is_enabled = False
        self.threshold_min = 0.0
        self.threshold_max = 100000.0
        self.show_preview = True
        self.preview_color_min = [255, 0, 0, 255]
        self.preview_color_max = [0, 0, 255, 255]
        self.subpixel_accurate = True
        self.preview_thickness = 1.0
        self.gen_bg_mode = "Constant"
        self.gen_bg_val = 0.0
        self.gen_fg_mode = "Constant"
        self.gen_fg_val = 1.0

    def __setattr__(self, name, value):
        if name in self._GEOM_FIELDS and getattr(self, name, _SENTINEL) != value:
            object.__setattr__(self, name, value)
            parent = getattr(self, "_parent", None)
            if parent is not None:
                parent.is_geometry_dirty = True
            return
        object.__setattr__(self, name, value)

    def to_dict(self):
        return {
            "is_enabled": bool(self.is_enabled),
            "threshold_min": float(self.threshold_min),
            "threshold_max": float(self.threshold_max),
            "show_preview": bool(self.show_preview),
            "preview_color_min": list(self.preview_color_min),
            "preview_color_max": list(self.preview_color_max),
            "subpixel_accurate": bool(self.subpixel_accurate),
            "preview_thickness": float(self.preview_thickness),
            "gen_bg_mode": str(self.gen_bg_mode),
            "gen_bg_val": float(self.gen_bg_val),
            "gen_fg_mode": str(self.gen_fg_mode),
            "gen_fg_val": float(self.gen_fg_val),
        }

    def from_dict(self, d):
        if not d:
            return

        # Schema migrations
        if "threshold" in d and "threshold_min" not in d:
            d["threshold_min"] = d["threshold"]
        if "preview_color" in d:
            if "preview_color_min" not in d:
                d["preview_color_min"] = d["preview_color"]
            if "preview_color_max" not in d:
                d["preview_color_max"] = d["preview_color"]

        self.is_enabled = d.get("is_enabled", self.is_enabled)
        self.threshold_min = d.get("threshold_min", self.threshold_min)
        self.threshold_max = d.get("threshold_max", self.threshold_max)
        self.show_preview = d.get("show_preview", self.show_preview)
        self.preview_color_min = d.get("preview_color_min", self.preview_color_min)
        self.preview_color_max = d.get("preview_color_max", self.preview_color_max)
        self.subpixel_accurate = d.get("subpixel_accurate", self.subpixel_accurate)
        self.preview_thickness = d.get("preview_thickness", self.preview_thickness)
        self.gen_bg_mode = d.get("gen_bg_mode", self.gen_bg_mode)
        self.gen_bg_val = d.get("gen_bg_val", self.gen_bg_val)
        self.gen_fg_mode = d.get("gen_fg_mode", self.gen_fg_mode)
        self.gen_fg_val = d.get("gen_fg_val", self.gen_fg_val)


class DVFState:
    """Stores parameters for Displacement Vector Field visualization."""

    _parent: "ViewState | None"

    display_mode: str
    vector_sampling: int
    vector_scale: float
    vector_thickness: float
    vector_color_min: list
    vector_color_max: list
    vector_color_max_mag: float
    vector_min_length_arrow: float
    vector_min_length_draw: float

    _GEOM_FIELDS = {
        "display_mode",
        "vector_sampling",
        "vector_scale",
        "vector_thickness",
        "vector_color_min",
        "vector_color_max",
        "vector_color_max_mag",
        "vector_min_length_arrow",
        "vector_min_length_draw",
    }

    def __init__(self, parent_vs: "ViewState | None" = None):
        self._parent = parent_vs
        self.display_mode = "Vector Field"  # Modes: "Component", "RGB", "Vector Field"
        self.vector_scale = 1.0
        self.vector_thickness = 1.0
        self.vector_min_length_arrow = 3.0
        self.vector_min_length_draw = 0.0
        self.vector_color_min = [0, 255, 255, 255]  # Cyan
        self.vector_color_max = [255, 0, 0, 255]

        self.vector_precision = 2
        self.vector_sampling = 5
        self.vector_color_max_mag = 10.0

        if (
            parent_vs
            and getattr(parent_vs, "volume", None)
            and getattr(parent_vs.volume, "is_dvf", False)
        ):
            import numpy as np

            vol = parent_vs.volume
            try:
                # 1. Compute true Max Magnitude (subsampled 2x for instant calculation)
                sub_data = vol.data[:, ::2, ::2, ::2]
                max_mag = float(np.max(np.linalg.norm(sub_data, axis=0)))
                self.vector_color_max_mag = max(0.1, max_mag)

                # 2. Dynamic Pixel Sampling (Aim for ~100 arrows across the largest dimension)
                max_dim = max(vol.shape3d)
                self.vector_sampling = max(1, int(round(max_dim / 100.0)))
            except Exception:
                pass

    def __setattr__(self, name, value):
        if name in self._GEOM_FIELDS and getattr(self, name, _SENTINEL) != value:
            object.__setattr__(self, name, value)
            parent = getattr(self, "_parent", None)
            if parent is not None:
                # Both geometry (arrow spacing) and data (RGB remap vs Component) need to be flagged
                parent.is_geometry_dirty = True
                parent.is_data_dirty = True
            return
        object.__setattr__(self, name, value)

    def to_dict(self):
        return {
            "display_mode": str(self.display_mode),
            "vector_sampling": int(self.vector_sampling),
            "vector_scale": float(self.vector_scale),
            "vector_thickness": float(self.vector_thickness),
            "vector_color_min": list(self.vector_color_min),
            "vector_color_max": list(self.vector_color_max),
            "vector_color_max_mag": float(self.vector_color_max_mag),
            "vector_min_length_arrow": float(self.vector_min_length_arrow),
            "vector_min_length_draw": float(self.vector_min_length_draw),
            "vector_precision": int(self.vector_precision),
        }

    def from_dict(self, d):
        if not d:
            return
        self.display_mode = d.get("display_mode", self.display_mode)
        self.vector_sampling = int(d.get("vector_sampling", self.vector_sampling))
        self.vector_scale = d.get("vector_scale", self.vector_scale)
        self.vector_thickness = d.get("vector_thickness", self.vector_thickness)
        self.vector_color_min = d.get(
            "vector_color_min", d.get("vector_color", self.vector_color_min)
        )
        self.vector_color_max = d.get("vector_color_max", self.vector_color_max)
        self.vector_color_max_mag = d.get(
            "vector_color_max_mag", self.vector_color_max_mag
        )
        self.vector_min_length_arrow = d.get(
            "vector_min_length_arrow", self.vector_min_length_arrow
        )
        self.vector_min_length_draw = d.get(
            "vector_min_length_draw", self.vector_min_length_draw
        )
        self.vector_precision = int(d.get("vector_precision", self.vector_precision))


class ProfileLineState:
    def __init__(self):
        self.id = ""
        self.name = ""
        self.color = [0, 255, 255, 255]
        self.pt1_phys = None
        self.pt2_phys = None
        self.orientation = ViewMode.AXIAL
        self.slice_idx = 0
        self.visible = True
        self.plot_open = False
        self.use_log = False

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "color": list(self.color),
            "pt1_phys": (
                [float(x) for x in self.pt1_phys] if self.pt1_phys is not None else None
            ),
            "pt2_phys": (
                [float(x) for x in self.pt2_phys] if self.pt2_phys is not None else None
            ),
            "orientation": self.orientation.name,
            "slice_idx": int(self.slice_idx),
            "visible": bool(self.visible),
            "plot_open": bool(self.plot_open),
            "use_log": bool(self.use_log),
        }

    def from_dict(self, d):
        self.id = d.get("id", self.id)
        self.name = d.get("name", self.name)
        self.color = d.get("color", self.color)
        if d.get("pt1_phys"):
            self.pt1_phys = np.array(d["pt1_phys"])
        if d.get("pt2_phys"):
            self.pt2_phys = np.array(d["pt2_phys"])
        if "orientation" in d:
            try:
                self.orientation = ViewMode[d["orientation"]]
            except KeyError:
                self.orientation = ViewMode.AXIAL
        self.slice_idx = d.get("slice_idx", self.slice_idx)
        self.visible = d.get("visible", self.visible)
        self.plot_open = False  # windows don't survive workspace reload
        self.use_log = d.get("use_log", False)


class ViewState:
    """
    The exclusive Source of Truth for an image's presentation state.

    ARCHITECTURE MANDATES (State-Only / Reactive):
    1. SOURCE OF TRUTH: This class owns all spatial and radiometric state. Viewers
       must never store their own permanent state; they must only reflect what
       is stored here during their 60fps tick loop.

    2. AUTOMATIC FLAGGING: Monitored fields in CameraState and DisplayState use
       __setattr__ to automatically flip 'is_geometry_dirty = True' when changed.
       Always use standard assignments (e.g., vs.camera.time_idx = 5) to trigger
       this reactive update.

    3. DECOUPLING: This class must remain ignorant of UI implementation details.
       It communicates purely through two high-level flags:
       - 'is_data_dirty': Underlying pixel data or overlays changed.
       - 'is_geometry_dirty': Camera, pan, zoom, or presentation settings changed.

    4. SERIALIZABILITY: All state must remain serializable. Maintain the 'to_dict'
       and 'from_dict' methods strictly to ensure workspace saves and history
       restoration remain pixel-perfect.

    5. SAFE COORDINATES: To maintain physical sync across the application,
       never allow 'camera.crosshair_voxel' to remain None after initialization.
       Use 'init_crosshair_to_slices()' during resets to provide a valid baseline.
    """

    def __init__(self, volume):
        self.volume = volume
        self.is_data_dirty = True
        self.is_geometry_dirty = True
        self.is_loading = False
        self.camera = CameraState(volume, parent_vs=self)
        self.display = DisplayState(parent_vs=self)
        self.extraction = ExtractionState(parent_vs=self)
        self.dvf = DVFState(parent_vs=self)
        self.sync_group = 0
        self.sync_wl_group = 0  # Radiometric group support
        self.rois = {}
        self.contours = {}
        self.profiles = {}
        self.crosshair_value = None  # This will be set by init_crosshair_to_slices
        self.space = SpatialEngine(
            volume, view_state=self
        )  # Pass self to SpatialEngine
        self.needs_resample: bool = (
            False  # True when transform changed since last resample
        )
        self._resample_job_counter: int = 0  # monotonically increasing job ID generator
        self._active_resample_job: int = 0  # 0 = idle, N = job N is currently running
        self.base_display_data: np.ndarray | None = None
        self._sitk_base_cache = None
        self._preview_R: "np.ndarray | None" = (
            None  # current rotation for on-demand preview
        )
        self._preview_center: "np.ndarray | None" = None
        self._preview_slice_needed: bool = False  # set by viewer on cache miss
        self.hist_data_x = None
        self.hist_data_y = None
        self.histogram_is_dirty = True
        self.use_log_y = True
        self.init_crosshair_to_slices()
        self.init_default_window_level()

    def compute_overlay_pixel_shift(self, overlay_vs, vol_spacing, orientation):
        """Return (dx_pix, dy_pix, dz_pix) for live overlay alignment.

        Computes the difference between the current transform translations and the
        translations that were baked into overlay_data at the last resample, converts
        to pixel units, then remaps axes to match the orientation-specific flipud/fliplr
        applied by SliceRenderer.extract_slice. If those flips change, the sign
        conventions here must change in sync.
        """
        base_tx, base_ty, base_tz = 0.0, 0.0, 0.0
        if self.space.transform and self.space.is_active:
            base_tx, base_ty, base_tz = self.space.transform.GetTranslation()

        ov_tx, ov_ty, ov_tz = 0.0, 0.0, 0.0
        if overlay_vs.space.transform and overlay_vs.space.is_active:
            ov_tx, ov_ty, ov_tz = overlay_vs.space.transform.GetTranslation()

        live_dx = ov_tx - base_tx
        live_dy = ov_ty - base_ty
        live_dz = ov_tz - base_tz

        baked_dx, baked_dy, baked_dz = getattr(
            self.display, "baked_overlay_translation", (0.0, 0.0, 0.0)
        )

        sp_x, sp_y, sp_z = vol_spacing
        px_x = (live_dx - baked_dx) / sp_x if sp_x else 0.0
        px_y = (live_dy - baked_dy) / sp_y if sp_y else 0.0
        px_z = (live_dz - baked_dz) / sp_z if sp_z else 0.0

        if orientation == ViewMode.AXIAL:
            return px_x, px_y, px_z
        elif orientation == ViewMode.CORONAL:
            return px_x, -px_z, px_y
        else:  # SAGITTAL
            return -px_y, -px_z, px_x

    def reset_preview_rotation(self):
        """Clear the shared rotation state used by all viewers for on-demand preview rendering.

        Setting _preview_R = None acts as a master switch: the render loop checks it
        before using any viewer-local slice caches, so stale viewer caches are silently
        ignored without needing the Controller to touch View objects directly.
        Viewer-local slice dicts (_preview_slices, _overlay_preview_slices) are
        managed by the View layer (RegistrationUI / Viewer) and are not cleared here.
        """
        self._preview_R = None
        self._preview_center = None

    def display_to_world(self, display_voxel, is_buffered):
        """Bypasses double-rotation for ITK buffered arrays. World = Native + Translation."""
        if is_buffered:
            phys = self.volume.voxel_coord_to_physic_coord(np.array(display_voxel[:3]))
            if self.space.transform and self.space.is_active:
                tx, ty, tz = self.space.transform.GetTranslation()
                phys += np.array([tx, ty, tz])
            return phys
        return self.space.display_to_world(display_voxel, is_buffered=False)

    def world_to_display(self, phys_coord, is_buffered):
        """Bypasses double-rotation for ITK buffered arrays. Native = World - Translation."""
        if is_buffered:
            p_temp = np.array(phys_coord[:3], dtype=float)
            if self.space.transform and self.space.is_active:
                tx, ty, tz = self.space.transform.GetTranslation()
                p_temp -= np.array([tx, ty, tz])
            return self.volume.physic_coord_to_voxel_coord(p_temp)
        return self.space.world_to_display(phys_coord, is_buffered=False)

    @contextmanager
    def loading_shield(self):
        """A context manager that guarantees the viewer shield is raised and lowered safely."""
        self.is_loading = True
        try:
            yield
        finally:
            self.is_loading = False

    def is_ct_image(self, flat_data):
        if flat_data is None or flat_data.size == 0:
            return False
        if hasattr(self.volume.sitk_image, "GetMetaData"):
            try:
                modality = self.volume.sitk_image.GetMetaData("Modality")
                if modality.upper() == "CT":
                    return True
            except Exception:
                pass
        min_val, max_val = np.min(flat_data), np.max(flat_data)
        if min_val < -500 and max_val > 1000 and (max_val - min_val) > 2000:
            return True
        return False

    def get_slice_shape(self, orientation):
        sh = self.volume.shape3d
        if orientation == ViewMode.AXIAL:
            return sh[1], sh[2]
        elif orientation == ViewMode.SAGITTAL:
            return sh[0], sh[1]
        elif orientation == ViewMode.CORONAL:
            return sh[0], sh[2]
        return 1, 1

    def _read_voxel_value(self, ix: int, iy: int, iz: int, use_buffer: bool = False):
        """
        Reads a voxel value. If use_buffer is True, it reads from the rotated
        display buffer. Otherwise, it reads from the native straightened data.
        """
        # Ensure indices are within bounds of the target data
        if use_buffer and self.base_display_data is not None:
            target_shape = (
                self.base_display_data.shape[1:]
                if self.base_display_data.ndim == 4
                else self.base_display_data.shape
            )
        else:
            target_shape = self.volume.shape3d

        if not (
            0 <= iz < target_shape[0]
            and 0 <= iy < target_shape[1]
            and 0 <= ix < target_shape[2]
        ):
            return None  # Out of bounds

        data = (
            self.base_display_data
            if use_buffer and self.base_display_data is not None
            else self.volume.data
        )

        if self.volume.num_timepoints > 1:
            t = min(self.camera.time_idx, self.volume.num_timepoints - 1)
            return data[t, iz, iy, ix]
        return data[iz, iy, ix]

    def mark_both_dirty(self):
        """Convenience method: mark both data and geometry as dirty in a single call."""
        self.is_data_dirty = True
        self.is_geometry_dirty = True

    def init_crosshair_to_slices(self):
        self.camera.crosshair_voxel = [
            self.camera.slices[ViewMode.SAGITTAL],
            self.camera.slices[ViewMode.CORONAL],
            self.camera.slices[ViewMode.AXIAL],
            self.camera.time_idx,
        ]
        _buf = self.base_display_data
        self.camera.crosshair_phys_coord = self.display_to_world(
            np.array(self.camera.crosshair_voxel[:3]), _buf is not None
        )
        self.crosshair_value = self._read_voxel_value(
            int(self.camera.crosshair_voxel[0]),
            int(self.camera.crosshair_voxel[1]),
            int(self.camera.crosshair_voxel[2]),
            use_buffer=False,
        )

    def init_default_window_level(self):
        total_pixels = getattr(self.volume.data, "size", 0)
        if total_pixels == 0:
            return
        max_sample_size = 100000
        if total_pixels > max_sample_size:
            stride = max(1, total_pixels // max_sample_size)
            sample_data = self.volume.data.flatten()[::stride]
        else:
            sample_data = self.volume.data.flatten()

        if self.is_ct_image(sample_data):
            self.set_ct_window_level(sample_data)
        else:
            p1, p99 = np.percentile(sample_data, [1, 99])
            p2, p98 = np.percentile(sample_data, [2, 98])
            self.display.ww = p98 - p2
            self.display.wl = (p98 + p2) / 2
            if self.display.ww <= 1e-20:
                self.display.ww = p99 - p1
                if self.display.ww <= 1e-20:
                    self.display.ww = max(abs(p1) * 0.1, 1e-20)
                    self.display.wl = (p99 + p1) / 2

    def update_crosshair_from_phys(self, new_phys_coord: np.ndarray):
        """
        Updates the crosshair's native voxel and physical coordinates based on a new physical point.
        This is the central point for all crosshair updates.
        """
        if new_phys_coord is None:
            return

        # 1. Update physical coordinate
        self.camera.crosshair_phys_coord = new_phys_coord

        # 2. Neutralization: Map world back to Native Voxel Space for the central record
        native_v: np.ndarray | None = self.world_to_display(
            new_phys_coord, is_buffered=False
        )
        if native_v is None:
            return

        self.camera.crosshair_voxel = [
            native_v[0],
            native_v[1],
            native_v[2],
            self.camera.time_idx,
        ]

        # 3. Update native slice indices based on the new native voxel
        # This ensures vs.camera.slices always reflects the native image's slice
        # corresponding to the crosshair's physical position.
        ix, iy, iz = [
            int(np.clip(np.round(c), 0, limit - 1))
            for c, limit in zip(
                native_v,
                [
                    self.volume.shape3d[2],
                    self.volume.shape3d[1],
                    self.volume.shape3d[0],
                ],
            )
        ]
        self.camera.slices[ViewMode.AXIAL] = iz
        self.camera.slices[ViewMode.SAGITTAL] = ix
        self.camera.slices[ViewMode.CORONAL] = iy

        # 4. Read value from the NATIVE data using native indices
        self.crosshair_value = self._read_voxel_value(ix, iy, iz, use_buffer=False)

        self.mark_both_dirty()

    def update_histogram(self):
        flat_data = self.volume.data.flatten()
        hist, bin_edges = np.histogram(flat_data, bins=256)
        self.hist_data_y = hist.astype(np.float32)
        self.hist_data_x = bin_edges[:-1].astype(np.float32)
        self.histogram_is_dirty = False

    def reset_view(self):
        self.camera.zoom = {
            ViewMode.AXIAL: 1.0,
            ViewMode.SAGITTAL: 1.0,
            ViewMode.CORONAL: 1.0,
        }
        self.camera.pan = {
            ViewMode.AXIAL: [0.0, 0.0],
            ViewMode.SAGITTAL: [0.0, 0.0],
            ViewMode.CORONAL: [0.0, 0.0],
        }
        self.camera.slices = {
            ViewMode.AXIAL: self.volume.shape3d[0] // 2,
            ViewMode.SAGITTAL: self.volume.shape3d[2] // 2,
            ViewMode.CORONAL: self.volume.shape3d[1] // 2,
        }
        self.init_crosshair_to_slices()
        self.is_data_dirty = True

    def hard_reset(self):
        self.camera = CameraState(self.volume, parent_vs=self)
        self.display = DisplayState(parent_vs=self)
        self.init_default_window_level()
        self.init_crosshair_to_slices()
        self.mark_both_dirty()

    def apply_wl_preset(self, preset_name):
        if getattr(self.volume, "is_rgb", False) or preset_name == "Custom":
            return
        total_pixels = getattr(self.volume.data, "size", 0)
        if total_pixels == 0:
            return
        if "Optimal" in preset_name:
            stride = max(1, total_pixels // 100000)
            sample_data = self.volume.data.flatten()[::stride]
            p2, p98 = np.percentile(sample_data, [2, 98])
            self.display.ww = max(1e-20, p98 - p2)
            self.display.wl = (p98 + p2) / 2
        elif "Min/Max" in preset_name:
            min_v = float(np.min(self.volume.data))
            max_v = float(np.max(self.volume.data))
            self.display.ww = max(1e-20, max_v - min_v)
            self.display.wl = (max_v + min_v) / 2
        elif preset_name in WL_PRESETS and WL_PRESETS[preset_name] is not None:
            self.display.ww = WL_PRESETS[preset_name]["ww"]
            self.display.wl = WL_PRESETS[preset_name]["wl"]

    def update_base_display_data(self):
        if not self.space.is_active or not self.space.has_rotation():
            self.base_display_data = None
            return

        import SimpleITK as sitk

        # The Tombstone Pattern
        self.base_display_data = None
        _ = self._sitk_base_cache  # keep sitk object alive until Execute() returns
        self._sitk_base_cache = None

        ref_img = sitk.Image(
            int(self.volume.shape3d[2]),
            int(self.volume.shape3d[1]),
            int(self.volume.shape3d[0]),
            sitk.sitkUInt8,
        )
        ref_img.SetSpacing(self.volume.spacing.tolist())
        ref_img.SetOrigin(self.volume.origin.tolist())
        ref_img.SetDirection(self.volume.matrix.flatten().tolist())

        resampler = sitk.ResampleImageFilter()
        resampler.SetReferenceImage(ref_img)
        resampler.SetInterpolator(sitk.sitkLinear)
        resampler.SetDefaultPixelValue(float(np.min(self.volume.data)))
        rot_transform = self.space.get_rotation_only_transform()
        resampler.SetTransform(rot_transform.GetInverse())

        target_dim = self.volume.sitk_image.GetDimension()
        if target_dim == 3:
            resampled_img = resampler.Execute(self.volume.sitk_image)
            self._sitk_base_cache = resampled_img
            self.base_display_data = sitk.GetArrayViewFromImage(resampled_img)
            if (
                getattr(self.volume, "is_dvf", False)
                and self.base_display_data.ndim == 4
            ):
                self.base_display_data = np.moveaxis(self.base_display_data, -1, 0)
        elif target_dim == 4:
            resampled_volumes = []
            for t in range(self.volume.num_timepoints):
                size = list(self.volume.sitk_image.GetSize())
                size[3] = 0
                index = [0, 0, 0, t]
                vol_3d = sitk.Extract(self.volume.sitk_image, size, index)
                resampled_volumes.append(resampler.Execute(vol_3d))
            joined_img = sitk.JoinSeries(resampled_volumes)
            self._sitk_base_cache = joined_img
            self.base_display_data = sitk.GetArrayViewFromImage(joined_img)

    def update_overlay_display_data(self, controller):
        """
        [ASYNC_BOUNDARY]: SimpleITK ResampleImageFilter.Execute()
        Releases the GIL. The Tombstone Pattern here is the only thing
        preventing the 60fps tick from reading dead memory.
        """
        if (
            not self.display.overlay_id
            or self.display.overlay_id not in controller.view_states
        ):
            return

        import SimpleITK as sitk

        ovs = controller.view_states[self.display.overlay_id]
        other_vol = ovs.volume

        # Late-tombstone pattern: keep the old overlay_data numpy view valid throughout
        # Execute() so renders during the long ITK computation still show the previous
        # overlay rather than Nothing (ghost). The old ITK object is kept alive via a
        # local reference and released only AFTER the new data is atomically assigned.
        _old_cache = self.display._sitk_overlay_cache
        self.display._sitk_overlay_cache = None

        # Build a safe 3D reference image to prevent ITK dimension mismatch exceptions
        # when mixing 3D and 4D volumes during fusion.
        ref_img = sitk.Image(
            int(self.volume.shape3d[2]),
            int(self.volume.shape3d[1]),
            int(self.volume.shape3d[0]),
            sitk.sitkUInt8,
        )
        ref_img.SetSpacing(self.volume.spacing.tolist())
        ref_img.SetOrigin(self.volume.origin.tolist())
        ref_img.SetDirection(self.volume.matrix.flatten().tolist())

        resampler = sitk.ResampleImageFilter()
        resampler.SetReferenceImage(ref_img)
        resampler.SetInterpolator(sitk.sitkLinear)
        resampler.SetDefaultPixelValue(np.min(other_vol.data).item())

        # Build the exact mapping from Base Physical to Overlay Physical
        composite = sitk.CompositeTransform(3)
        if ovs.space.transform and ovs.space.is_active:
            composite.AddTransform(ovs.space.transform.GetInverse())
        if self.space.transform and self.space.is_active:
            base_translation = sitk.TranslationTransform(3)
            base_translation.SetOffset(self.space.transform.GetTranslation())
            composite.AddTransform(base_translation)

        resampler.SetTransform(composite)

        target_dim = other_vol.sitk_image.GetDimension()
        if target_dim == 3:
            resampled_img = resampler.Execute(other_vol.sitk_image)
            self.display._sitk_overlay_cache = resampled_img
            self.display.overlay_data = sitk.GetArrayViewFromImage(resampled_img)
            if (
                getattr(other_vol, "is_dvf", False)
                and self.display.overlay_data.ndim == 4
            ):
                self.display.overlay_data = np.moveaxis(
                    self.display.overlay_data, -1, 0
                )
        elif target_dim == 4:
            resampled_volumes = []
            for t in range(other_vol.num_timepoints):
                size = list(other_vol.sitk_image.GetSize())
                size[3] = 0
                index = [0, 0, 0, t]
                vol_3d = sitk.Extract(other_vol.sitk_image, size, index)
                resampled_volumes.append(resampler.Execute(vol_3d))
            joined_img = sitk.JoinSeries(resampled_volumes)
            self.display._sitk_overlay_cache = joined_img
            self.display.overlay_data = sitk.GetArrayViewFromImage(joined_img)
        else:
            self.display._sitk_overlay_cache = None
            self.display.overlay_data = other_vol.data

        # Release old ITK object now that overlay_data points to new data.
        # Doing it here (after assignment) guarantees the old numpy view was never
        # accessed after the old cache was freed.
        _old_cache = None  # noqa: F841

        # Record what was baked in so the 2D shift can subtract it.
        baked_tx, baked_ty, baked_tz = 0.0, 0.0, 0.0
        if ovs.space.transform and ovs.space.is_active:
            baked_tx, baked_ty, baked_tz = ovs.space.transform.GetTranslation()

        base_tx, base_ty, base_tz = 0.0, 0.0, 0.0
        if self.space.transform and self.space.is_active:
            base_tx, base_ty, base_tz = self.space.transform.GetTranslation()

        self.display.baked_overlay_translation = (
            baked_tx - base_tx,
            baked_ty - base_ty,
            baked_tz - base_tz,
        )
        self.is_data_dirty = True

    def set_overlay(self, overlay_id, other_vol, controller=None):
        if overlay_id is None or other_vol is None:
            self.display.overlay_id = None
            self.display.overlay_data = None
            self.display._sitk_overlay_cache = None
            self.display.baked_overlay_translation = (0.0, 0.0, 0.0)
            self.is_data_dirty = True
            return True

        if getattr(other_vol, "is_rgb", False):
            return False

        self.display.overlay_id = overlay_id
        self.display.overlay_opacity = 0.5
        self.display.overlay_mode = "Alpha"

        if controller:
            self.update_overlay_display_data(controller)
        return True

    def set_ct_window_level(self, flat_data):
        if flat_data is None or flat_data.size == 0:
            return
        p5, p95 = np.percentile(flat_data, [5, 95])
        data_range = p95 - p5
        image_shape = self.volume.data.shape

        if len(image_shape) == 3 and image_shape[0] > 300:
            preset = {"ww": 600, "wl": 0}
        elif data_range > 1500:
            preset = WL_PRESETS["CT: Bone"]
        elif p5 < -800:
            preset = WL_PRESETS["CT: Lung"]
        elif -200 < p5 < 200 and data_range < 500:
            preset = WL_PRESETS["CT: Brain"]
        else:
            preset = WL_PRESETS["CT: Soft Tissue"]

        self.display.ww = preset["ww"]
        self.display.wl = preset["wl"]
