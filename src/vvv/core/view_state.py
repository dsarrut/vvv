import numpy as np
import SimpleITK as sitk
from vvv.config import WL_PRESETS
from contextlib import contextmanager
from vvv.math.geometry import SpatialEngine
from vvv.utils import ViewMode, slice_to_voxel

_SENTINEL = object()


class CameraState:
    """Stores all transient spatial and navigation parameters."""

    # 1. Type Hints (Keeps PyCharm/VSCode autocomplete happy)
    time_idx: int
    show_axis: bool
    show_tracker: bool
    show_crosshair: bool
    show_scalebar: bool
    show_grid: bool
    show_legend: bool
    show_filename: int

    # 2. The exact fields that should trigger a GEOMETRY redraw
    _GEOM_FIELDS = {
        "time_idx",
        "show_axis",
        "show_tracker",
        "show_crosshair",
        "show_scalebar",
        "show_grid",
        "show_legend",
        "show_filename",
    }

    def __init__(self, volume, parent_vs=None):
        self._parent = parent_vs
        self.zoom = {
            ViewMode.AXIAL: 1.0,
            ViewMode.SAGITTAL: 1.0,
            ViewMode.CORONAL: 1.0,
        }
        self.pan = {
            ViewMode.AXIAL: [0, 0],
            ViewMode.SAGITTAL: [0, 0],
            ViewMode.CORONAL: [0, 0],
        }
        self.slices = {
            ViewMode.AXIAL: volume.shape3d[0] // 2,
            ViewMode.SAGITTAL: volume.shape3d[2] // 2,
            ViewMode.CORONAL: volume.shape3d[1] // 2,
        }

        # Non-flagged attributes
        self.crosshair_voxel = None
        self.crosshair_phys_coord = None
        self.last_orientation = ViewMode.AXIAL

        # Default values for flagged attributes
        self.time_idx = 0
        self.show_axis = True
        self.show_tracker = True
        self.show_crosshair = True
        self.show_scalebar = False
        self.show_grid = False
        self.show_legend = False
        self.show_filename = 0

        # State-Only Sync Targets
        self.target_ppm = None
        self.target_center = None
        self.target_tracker_phys = None

    def __setattr__(self, name, value):
        # Intercept assignments: if it's a GEOM field AND the value is actually changing
        if name in self._GEOM_FIELDS and getattr(self, name, _SENTINEL) != value:
            object.__setattr__(self, name, value)  # Set the value

            # Flag the parent automatically
            if getattr(self, "_parent", None):
                self._parent.is_geometry_dirty = True
            return

        # Standard assignment for everything else (like dictionaries and _parent)
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

        # Using the setters!
        self.time_idx = d.get("time_idx", self.time_idx)
        self.show_axis = d.get("show_axis", self.show_axis)
        self.show_tracker = d.get("show_tracker", self.show_tracker)
        self.show_crosshair = d.get("show_crosshair", self.show_crosshair)
        self.show_scalebar = d.get("show_scalebar", self.show_scalebar)
        self.show_grid = d.get("show_grid", self.show_grid)
        self.show_legend = d.get("show_legend", self.show_legend)
        self.show_filename = d.get("show_filename", self.show_filename)

        if "last_orientation" in d:
            self.last_orientation = ViewMode[d["last_orientation"]]

        if "crosshair_voxel" in d:
            self.crosshair_voxel = d["crosshair_voxel"]
        if "crosshair_phys_coord" in d and d["crosshair_phys_coord"] is not None:
            self.crosshair_phys_coord = np.array(d["crosshair_phys_coord"])


class DisplayState:
    """Stores all radiometric and rendering properties."""

    # 1. Type Hints
    ww: float
    wl: float
    colormap: str
    base_threshold: float
    overlay_id: str
    overlay_opacity: float
    overlay_mode: str
    overlay_checkerboard_size: float
    overlay_checkerboard_swap: bool
    pixelated_zoom: bool
    use_voxel_strips: bool

    # 2. The exact fields that should trigger a DATA redraw
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

    def __init__(self, parent_vs=None):
        self._parent = parent_vs

        # Non-flagged attributes
        self.overlay_data = None
        self._sitk_overlay_cache = None
        self.baked_overlay_translation = (0.0, 0.0, 0.0)

        # Default values for flagged attributes
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
        # Intercept assignments: if it's a DATA field AND the value is actually changing
        if name in self._DATA_FIELDS and getattr(self, name, _SENTINEL) != value:
            object.__setattr__(self, name, value)  # Set the value

            # Flag the parent automatically
            if getattr(self, "_parent", None):
                self._parent.is_data_dirty = True
            return

        # Standard assignment for everything else
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

        # Self-managed state flags
        self.is_data_dirty = True
        self.is_geometry_dirty = True
        self.is_loading = False

        # Link children to self
        self.camera = CameraState(volume, parent_vs=self)
        self.display = DisplayState(parent_vs=self)
        self.extraction = ExtractionState(parent_vs=self)

        self.sync_group = 0
        self.sync_wl_group = 0  # Radiometric group support
        self.rois = {}
        self.contours = {}

        self.crosshair_value = None
        self.space = SpatialEngine(volume)
        self.base_display_data = None
        self._sitk_base_cache = None

        self.hist_data_x = None
        self.hist_data_y = None
        self.histogram_is_dirty = True
        self.use_log_y = True

        self.init_crosshair_to_slices()
        self.init_default_window_level()

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
            except:
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

    def init_crosshair_to_slices(self):
        self.camera.crosshair_voxel = [
            self.camera.slices[ViewMode.SAGITTAL],
            self.camera.slices[ViewMode.CORONAL],
            self.camera.slices[ViewMode.AXIAL],
            self.camera.time_idx,
        ]

        is_buf = self.base_display_data is not None
        self.camera.crosshair_phys_coord = self.space.display_to_world(
            np.array(self.camera.crosshair_voxel[:3]), is_buf
        )

        v = self.camera.crosshair_voxel
        ix, iy, iz = int(v[0]), int(v[1]), int(v[2])
        display_data = self.base_display_data if is_buf else self.volume.data

        if self.volume.num_timepoints > 1:
            t_idx = min(self.camera.time_idx, self.volume.num_timepoints - 1)
            self.crosshair_value = display_data[t_idx, iz, iy, ix]
        else:
            self.crosshair_value = display_data[iz, iy, ix]

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

        is_ct = self.is_ct_image(sample_data)

        if is_ct:
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

    def update_crosshair_from_slice_scroll(self, new_slice_idx, orientation):
        if self.camera.crosshair_voxel is None:
            self.init_crosshair_to_slices()

        vx, vy, vz = self.camera.crosshair_voxel[:3]
        if orientation == ViewMode.AXIAL:
            vz = new_slice_idx
        elif orientation == ViewMode.SAGITTAL:
            vx = new_slice_idx
        elif orientation == ViewMode.CORONAL:
            vy = new_slice_idx

        new_v = [vx, vy, vz, self.camera.time_idx]
        self.camera.crosshair_voxel = new_v

        is_buf = self.base_display_data is not None
        self.camera.crosshair_phys_coord = self.space.display_to_world(
            np.array(new_v[:3]), is_buf
        )

        ix, iy, iz = [
            int(np.clip(np.floor(c + 0.5), 0, limit - 1))
            for c, limit in zip(
                new_v[:3],
                [
                    self.volume.shape3d[2],
                    self.volume.shape3d[1],
                    self.volume.shape3d[0],
                ],
            )
        ]

        display_data = self.base_display_data if is_buf else self.volume.data
        if self.volume.num_timepoints > 1:
            t_idx = min(self.camera.time_idx, self.volume.num_timepoints - 1)
            self.crosshair_value = display_data[t_idx, iz, iy, ix]
        else:
            self.crosshair_value = display_data[iz, iy, ix]

    def update_crosshair_from_2d(self, slice_x, slice_y, slice_idx, orientation):
        shape = self.get_slice_shape(orientation)
        v = slice_to_voxel(slice_x, slice_y, slice_idx, orientation, shape)

        self.camera.crosshair_voxel = [v[0], v[1], v[2], self.camera.time_idx]

        is_buf = self.base_display_data is not None
        self.camera.crosshair_phys_coord = self.space.display_to_world(
            np.array(v[:3]), is_buf
        )

        ix, iy, iz = [
            int(np.clip(np.floor(c + 0.5), 0, limit - 1))
            for c, limit in zip(
                v,
                [
                    self.volume.shape3d[2],
                    self.volume.shape3d[1],
                    self.volume.shape3d[0],
                ],
            )
        ]

        display_data = self.base_display_data if is_buf else self.volume.data
        if self.volume.num_timepoints > 1:
            t_idx = min(self.camera.time_idx, self.volume.num_timepoints - 1)
            self.crosshair_value = display_data[t_idx, iz, iy, ix]
        else:
            self.crosshair_value = display_data[iz, iy, ix]

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
            ViewMode.AXIAL: [0, 0],
            ViewMode.SAGITTAL: [0, 0],
            ViewMode.CORONAL: [0, 0],
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

        # Mandatory: Rule 4 requires crosshair initialization
        self.init_crosshair_to_slices()

        self.is_data_dirty = True
        self.is_geometry_dirty = True

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

        # The Tombstone Pattern
        self.base_display_data = None
        old_cache = self._sitk_base_cache
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

        min_val = float(np.min(self.volume.data))
        resampler.SetDefaultPixelValue(min_val)

        rot_transform = self.space.get_rotation_only_transform()
        resampler.SetTransform(rot_transform.GetInverse())

        target_dim = self.volume.sitk_image.GetDimension()
        if target_dim == 3:
            resampled_img = resampler.Execute(self.volume.sitk_image)
            self._sitk_base_cache = resampled_img
            self.base_display_data = sitk.GetArrayViewFromImage(resampled_img)
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

        ovs = controller.view_states[self.display.overlay_id]
        other_vol = ovs.volume

        # The Tombstone Pattern
        # Sever the Numpy view BEFORE releasing the GIL to SimpleITK!
        self.display.overlay_data = None
        old_cache = self.display._sitk_overlay_cache  # Keep alive until end of scope
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
            composite.AddTransform(self.space.transform)

        resampler.SetTransform(composite)

        # Execute Resample
        target_dim = other_vol.sitk_image.GetDimension()
        if target_dim == 3:
            resampled_img = resampler.Execute(other_vol.sitk_image)
            self.display._sitk_overlay_cache = resampled_img
            self.display.overlay_data = sitk.GetArrayViewFromImage(resampled_img)
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
            return

        self.display.overlay_id = overlay_id
        self.display.overlay_opacity = 0.5
        self.display.overlay_mode = "Alpha"

        if controller:
            self.update_overlay_display_data(controller)

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


class ExtractionState:
    """Stores parameters for interactive contour thresholding."""

    is_enabled: bool
    threshold: float
    show_preview: bool
    preview_color: list
    subpixel_accurate: bool

    _DATA_FIELDS = {"is_enabled", "threshold", "show_preview", "preview_color"}

    def __init__(self, parent_vs=None):
        self._parent = parent_vs
        self.is_enabled = False
        self.threshold = 0.0
        self.show_preview = True
        self.preview_color = (255, 255, 0, 255)
        self.subpixel_accurate = True
        self.computed_counts = {
            ViewMode.AXIAL: 0,
            ViewMode.SAGITTAL: 0,
            ViewMode.CORONAL: 0,
        }

    def __setattr__(self, name, value):
        if name in self._DATA_FIELDS and getattr(self, name, _SENTINEL) != value:
            object.__setattr__(self, name, value)
            if getattr(self, "_parent", None):
                self._parent.is_geometry_dirty = True
            return
        object.__setattr__(self, name, value)
