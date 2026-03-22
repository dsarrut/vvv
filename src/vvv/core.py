import os
import copy
import json
import numpy as np
import SimpleITK as sitk
from pathlib import Path
from vvv.utils import ViewMode, slice_to_voxel
from vvv.config import DEFAULT_SETTINGS, WL_PRESETS, COLORMAPS
from vvv.image import VolumeData, SliceRenderer, RenderLayer
from vvv.utils import get_history_path_key, resolve_history_path_key


class SettingsManager:
    def __init__(self):
        if os.name == "nt":
            self.config_dir = Path(os.getenv("APPDATA")) / "VVV"
        else:
            self.config_dir = Path.home() / ".config" / "vvv"

        self.config_path = self.config_dir / ".vv_settings"
        self.data = copy.deepcopy(DEFAULT_SETTINGS)
        self.load()

    def _deep_update(self, default_dict, user_dict):
        for key, value in user_dict.items():
            if (
                isinstance(value, dict)
                and key in default_dict
                and isinstance(default_dict[key], dict)
            ):
                self._deep_update(default_dict[key], value)
            else:
                default_dict[key] = value

    def load(self):
        if self.config_path.exists():
            try:
                with open(self.config_path, "r") as f:
                    user_settings = json.load(f)
                    self._deep_update(self.data, user_settings)
            except Exception as e:
                print(f"Error loading settings: {e}")

    def reset(self):
        self.data = copy.deepcopy(DEFAULT_SETTINGS)

    def save(self):
        self.config_dir.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, "w") as f:
            json.dump(self.data, f, indent=4)
        return str(self.config_path)


class HistoryManager:
    def __init__(self):
        if os.name == "nt":
            self.config_dir = Path(os.getenv("APPDATA")) / "VVV"
        else:
            self.config_dir = Path.home() / ".config" / "vvv"

        self.history_path = self.config_dir / "history.json"
        self.data = {}
        self.max_history_files = 100  # Enforce limit
        self.load()

    def load(self):
        if self.history_path.exists():
            try:
                with open(self.history_path, "r") as f:
                    self.data = json.load(f)
            except Exception as e:
                pass

    def save(self):
        self.config_dir.mkdir(parents=True, exist_ok=True)
        with open(self.history_path, "w") as f:
            json.dump(self.data, f, indent=4)

    def save_image_state(self, controller, vs_id):
        vs = controller.view_states[vs_id]
        vol = controller.volumes[vs_id]
        primary_path = vol.file_paths[0]
        key = get_history_path_key(primary_path)

        # Extract Overlay Path
        overlay_path = None
        if vs.display.overlay_id and vs.display.overlay_id in controller.volumes:
            ov_path = controller.volumes[vs.display.overlay_id].file_paths[0]
            overlay_path = get_history_path_key(ov_path)

        # Remove the key if it exists so we can push it to the "end" of the dictionary (LRU logic)
        if key in self.data:
            del self.data[key]

        # Extract ROI paths and states
        rois_list = []
        for roi_id, roi_state in vs.rois.items():
            if roi_id in controller.volumes:
                r_vol = controller.volumes[roi_id]
                if r_vol.file_paths:
                    r_path = get_history_path_key(r_vol.file_paths[0])
                    rois_list.append({"path": r_path, "state": roi_state.to_dict()})

        # Cast NumPy arrays to native Python types
        self.data[key] = {
            "shape3d": [int(x) for x in vol.shape3d],
            "spacing": [float(x) for x in vol.spacing],
            "origin": [float(x) for x in vol.origin],
            "camera": vs.camera.to_dict(),
            "display": vs.display.to_dict(),
            "overlay_path": overlay_path,
            "rois": rois_list,
        }

        # Enforce the 100 files limit by deleting the oldest item(s) at the front of the dict
        while len(self.data) > self.max_history_files:
            oldest_key = next(iter(self.data))
            del self.data[oldest_key]

        self.save()

    def get_image_state(self, volume):
        primary_path = volume.file_paths[0]
        key = get_history_path_key(primary_path)

        if key not in self.data:
            return None

        entry = self.data[key]

        # Strict Geometry Validation (No more mtime!)
        if entry.get("shape3d") != list(volume.shape3d):
            return None

        if not np.allclose(entry.get("spacing"), volume.spacing, atol=1e-4):
            return None

        # Validate origin (with a safe fallback if loading an old history file)
        if "origin" in entry:
            if not np.allclose(entry.get("origin"), volume.origin, atol=1e-4):
                return None

        return entry


class CameraState:
    """Stores all transient spatial and navigation parameters."""

    def __init__(self, volume):
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
        self.crosshair_phys_coord = None
        self.crosshair_voxel = None
        self.time_idx = 0  # For 4D images

        # Visibility toggles (these are spatially relevant)
        self.show_axis = True
        self.show_tracker = True
        self.show_crosshair = True
        self.show_scalebar = False
        self.show_grid = False
        self.show_legend = False

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
        # Helper to safely convert JSON strings back to ViewMode Enums
        def parse_dict(source_dict):
            res = {}
            for k, v in source_dict.items():
                # .split() cleans up old corrupted keys like "ViewMode.AXIAL" if they exist
                clean_k = k.split(".")[-1] if "." in k else k
                if clean_k in ViewMode.__members__:
                    res[ViewMode[clean_k]] = v
            return res

        # Safely update dictionaries instead of overwriting them
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

        if "crosshair_voxel" in d:
            self.crosshair_voxel = d["crosshair_voxel"]
        if "crosshair_phys_coord" in d and d["crosshair_phys_coord"] is not None:
            self.crosshair_phys_coord = np.array(d["crosshair_phys_coord"])


class DisplayState:
    """Stores all radiometric and rendering properties."""

    def __init__(self):
        # Window Level
        self.ww = 2000.0
        self.wl = 270.0
        self.colormap = "Grayscale"
        # Voxels with value below this threshold are not display (black)
        self.base_threshold = -1e8
        # FIXME : not really linear interpolation : draw squares pixels on large zoom
        self.interpolation_linear = False

        # Overlay parameters
        self.overlay_id = None
        self.overlay_data = None
        self.overlay_opacity = 0.5
        self.overlay_mode = "Alpha"  # Alpha, Registration, Checkboard, ...
        self.overlay_threshold = -1  # Not displayed if below this value
        self.overlay_checkerboard_size = 20.0  # In mm
        self.overlay_checkerboard_swap = False

    def to_dict(self):
        return {
            "ww": float(self.ww),
            "wl": float(self.wl),
            "colormap": str(self.colormap),
            "base_threshold": float(self.base_threshold),
            "interpolation_linear": bool(self.interpolation_linear),
            "overlay_opacity": float(self.overlay_opacity),
            "overlay_mode": str(self.overlay_mode),
            "overlay_threshold": float(self.overlay_threshold),
            "overlay_checkerboard_size": float(self.overlay_checkerboard_size),
            "overlay_checkerboard_swap": bool(self.overlay_checkerboard_swap),
        }

    def from_dict(self, d):
        self.ww = d.get("ww", self.ww)
        self.wl = d.get("wl", self.wl)
        self.colormap = d.get("colormap", self.colormap)
        self.base_threshold = d.get("base_threshold", self.base_threshold)
        self.interpolation_linear = d.get(
            "interpolation_linear", self.interpolation_linear
        )
        self.overlay_opacity = d.get("overlay_opacity", self.overlay_opacity)
        self.overlay_mode = d.get("overlay_mode", self.overlay_mode)
        self.overlay_threshold = d.get("overlay_threshold", self.overlay_threshold)
        self.overlay_checkerboard_size = d.get(
            "overlay_checkerboard_size", self.overlay_checkerboard_size
        )
        self.overlay_checkerboard_swap = d.get(
            "overlay_checkerboard_swap", self.overlay_checkerboard_swap
        )


class ViewState:
    """Stores all transient UI and camera parameters."""

    def __init__(self, volume):
        self.volume = volume
        self.is_data_dirty = True
        self.sync_group = 0

        # The main elements Camera + Display
        self.camera = CameraState(volume)
        self.display = DisplayState()
        self.rois = {}

        # Derived value based on camera coords and display data
        self.crosshair_value = None

        # Registration transform
        self.transform = None
        self.transform_file = "None"
        self.transform_active = False
        self.base_display_data = None

        self.hist_data_x = None
        self.hist_data_y = None
        self.histogram_is_dirty = True
        self.use_log_y = True

        self.init_crosshair_to_slices()
        self.init_default_window_level()

    # ==========================================
    # The property bridge
    # Routes top-level requests to the new sub-states
    # ==========================================

    # --- Camera Properties ---
    @property
    def zoom(self):
        return self.camera.zoom

    @zoom.setter
    def zoom(self, v):
        self.camera.zoom = v

    @property
    def pan(self):
        return self.camera.pan

    @pan.setter
    def pan(self, v):
        self.camera.pan = v

    @property
    def slices(self):
        return self.camera.slices

    @slices.setter
    def slices(self, v):
        self.camera.slices = v

    @property
    def crosshair_phys_coord(self):
        return self.camera.crosshair_phys_coord

    @crosshair_phys_coord.setter
    def crosshair_phys_coord(self, v):
        self.camera.crosshair_phys_coord = v

    @property
    def crosshair_voxel(self):
        return self.camera.crosshair_voxel

    @crosshair_voxel.setter
    def crosshair_voxel(self, v):
        self.camera.crosshair_voxel = v

    @property
    def time_idx(self):
        return self.camera.time_idx

    @time_idx.setter
    def time_idx(self, v):
        self.camera.time_idx = v

    @property
    def show_axis(self):
        return self.camera.show_axis

    @show_axis.setter
    def show_axis(self, v):
        self.camera.show_axis = v

    @property
    def show_tracker(self):
        return self.camera.show_tracker

    @show_tracker.setter
    def show_tracker(self, v):
        self.camera.show_tracker = v

    @property
    def show_crosshair(self):
        return self.camera.show_crosshair

    @show_crosshair.setter
    def show_crosshair(self, v):
        self.camera.show_crosshair = v

    @property
    def show_scalebar(self):
        return self.camera.show_scalebar

    @show_scalebar.setter
    def show_scalebar(self, v):
        self.camera.show_scalebar = v

    @property
    def show_grid(self):
        return self.camera.show_grid

    @show_grid.setter
    def show_grid(self, v):
        self.camera.show_grid = v

    # --- Display Properties ---
    @property
    def ww(self):
        return self.display.ww

    @ww.setter
    def ww(self, v):
        self.display.ww = v

    @property
    def wl(self):
        return self.display.wl

    @wl.setter
    def wl(self, v):
        self.display.wl = v

    @property
    def colormap(self):
        return self.display.colormap

    @colormap.setter
    def colormap(self, v):
        self.display.colormap = v

    @property
    def base_threshold(self):
        return self.display.base_threshold

    @base_threshold.setter
    def base_threshold(self, v):
        self.display.base_threshold = v

    @property
    def interpolation_linear(self):
        return self.display.interpolation_linear

    @interpolation_linear.setter
    def interpolation_linear(self, v):
        self.display.interpolation_linear = v

    @property
    def show_legend(self):
        return self.camera.show_legend

    @show_legend.setter
    def show_legend(self, v):
        self.camera.show_legend = v

    @property
    def overlay_id(self):
        return self.display.overlay_id

    @overlay_id.setter
    def overlay_id(self, v):
        self.display.overlay_id = v

    @property
    def overlay_data(self):
        return self.display.overlay_data

    @overlay_data.setter
    def overlay_data(self, v):
        self.display.overlay_data = v

    @property
    def overlay_opacity(self):
        return self.display.overlay_opacity

    @overlay_opacity.setter
    def overlay_opacity(self, v):
        self.display.overlay_opacity = v

    @property
    def overlay_mode(self):
        return self.display.overlay_mode

    @overlay_mode.setter
    def overlay_mode(self, v):
        self.display.overlay_mode = v

    @property
    def overlay_threshold(self):
        return self.display.overlay_threshold

    @overlay_threshold.setter
    def overlay_threshold(self, v):
        self.display.overlay_threshold = v

    @property
    def overlay_checkerboard_size(self):
        return self.display.overlay_checkerboard_size

    @overlay_checkerboard_size.setter
    def overlay_checkerboard_size(self, v):
        self.display.overlay_checkerboard_size = v

    @property
    def overlay_checkerboard_swap(self):
        return self.display.overlay_checkerboard_swap

    @overlay_checkerboard_swap.setter
    def overlay_checkerboard_swap(self, v):
        self.display.overlay_checkerboard_swap = v

    # ==========================================

    def get_world_phys_coord(self, voxel_orig):
        """Strictly maps a RAW Original Voxel to World Physical Space."""
        phys = self.volume.voxel_coord_to_physic_coord(np.array(voxel_orig))
        if getattr(self, "transform_active", False) and getattr(
            self, "transform", None
        ):
            phys = self.transform.TransformPoint(phys.tolist())
        return np.array(phys)

    def get_voxel_from_world_phys(self, world_phys):
        """Strictly maps World Physical Space back to a RAW Original Voxel."""
        phys = np.array(world_phys)
        if getattr(self, "transform_active", False) and getattr(
            self, "transform", None
        ):
            phys = np.array(self.transform.GetInverse().TransformPoint(phys.tolist()))
        return self.volume.physic_coord_to_voxel_coord(phys)

    def get_world_phys_from_display_voxel(self, voxel_disp):
        """Maps the Visual Screen Voxel to World Space, respecting the Pan/Rotation illusions."""
        phys = self.volume.voxel_coord_to_physic_coord(np.array(voxel_disp))
        if getattr(self, "transform_active", False) and getattr(
            self, "transform", None
        ):
            if getattr(self, "base_display_data", None) is not None:
                # Buffer Space: Rotation is baked in. Only apply translation to find World.
                t = np.array(self.transform.GetTranslation())
                return phys + t
            else:
                # Fast Path (Camera Pan): Data hasn't moved, so apply the full transform.
                return np.array(self.transform.TransformPoint(phys.tolist()))
        return phys

    def get_display_voxel_from_world_phys(self, world_phys):
        """Maps World Space back to the Visual Screen Voxel to snap the crosshair correctly."""
        phys = np.array(world_phys)
        if getattr(self, "transform_active", False) and getattr(
            self, "transform", None
        ):
            if getattr(self, "base_display_data", None) is not None:
                # Buffer Space: Only reverse the translation.
                t = np.array(self.transform.GetTranslation())
                phys = phys - t
            else:
                # Fast Path (Camera Pan): Reverse the full transform.
                phys = np.array(
                    self.transform.GetInverse().TransformPoint(phys.tolist())
                )
        return self.volume.physic_coord_to_voxel_coord(phys)

    def is_ct_image(self, flat_data):
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
        self.crosshair_voxel = [
            self.slices[ViewMode.CORONAL],
            self.slices[ViewMode.SAGITTAL],
            self.slices[ViewMode.AXIAL],
            self.time_idx,
        ]
        self.crosshair_phys_coord = self.get_world_phys_from_display_voxel(
            np.array(self.crosshair_voxel[:3])
        )

        v = self.crosshair_voxel
        ix, iy, iz = int(v[0]), int(v[1]), int(v[2])
        display_data = (
            self.base_display_data
            if getattr(self, "base_display_data", None) is not None
            else self.volume.data
        )
        if self.volume.num_timepoints > 1:
            self.crosshair_value = display_data[self.time_idx, iz, iy, ix]
        else:
            self.crosshair_value = display_data[iz, iy, ix]

    def init_default_window_level(self):
        total_pixels = self.volume.data.size
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

            self.ww = p98 - p2
            self.wl = (p98 + p2) / 2

            # For extremely small values
            if self.ww <= 1e-20:
                self.ww = p99 - p1
                if self.ww <= 1e-20:
                    # If perfectly uniform, set width to 10% of the value
                    self.ww = max(abs(p1) * 0.1, 1e-20)
                    self.wl = (p99 + p1) / 2

    def update_crosshair_from_slice_scroll(self, new_slice_idx, orientation):
        vx, vy, vz = self.crosshair_voxel[:3]
        if orientation == ViewMode.AXIAL:
            vz = new_slice_idx
        elif orientation == ViewMode.SAGITTAL:
            vx = new_slice_idx
        elif orientation == ViewMode.CORONAL:
            vy = new_slice_idx

        new_v = [vx, vy, vz, self.time_idx]
        self.crosshair_voxel = new_v
        self.crosshair_phys_coord = self.get_world_phys_from_display_voxel(
            np.array(new_v[:3])
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
        display_data = (
            self.base_display_data
            if getattr(self, "base_display_data", None) is not None
            else self.volume.data
        )
        if self.volume.num_timepoints > 1:
            self.crosshair_value = display_data[self.time_idx, iz, iy, ix]
        else:
            self.crosshair_value = display_data[iz, iy, ix]

    def update_crosshair_from_2d(self, slice_x, slice_y, slice_idx, orientation):
        shape = self.get_slice_shape(orientation)
        v = slice_to_voxel(slice_x, slice_y, slice_idx, orientation, shape)

        self.crosshair_voxel = [v[0], v[1], v[2], self.time_idx]
        self.crosshair_phys_coord = self.get_world_phys_from_display_voxel(
            np.array(v[:3])
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
        display_data = (
            self.base_display_data
            if getattr(self, "base_display_data", None) is not None
            else self.volume.data
        )
        if self.volume.num_timepoints > 1:
            self.crosshair_value = display_data[self.time_idx, iz, iy, ix]
        else:
            self.crosshair_value = display_data[iz, iy, ix]

    def update_histogram(self):
        flat_data = self.volume.data.flatten()
        # Automatically determine 256 bins across the exact data range
        hist, bin_edges = np.histogram(flat_data, bins=256)
        self.hist_data_y = hist.astype(np.float32)
        self.hist_data_x = bin_edges[:-1].astype(np.float32)
        self.histogram_is_dirty = False

    def reset_view(self):
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
            ViewMode.AXIAL: self.volume.shape3d[0] // 2,
            ViewMode.SAGITTAL: self.volume.shape3d[2] // 2,
            ViewMode.CORONAL: self.volume.shape3d[1] // 2,
        }
        self.init_crosshair_to_slices()
        self.is_data_dirty = True

    def hard_reset(self):
        """Completely resets the image to its initial load state."""
        # 1. Reset Spatial properties (zoom, pan, slices)
        self.reset_view()

        # 2. Reset Camera UI toggles
        self.show_axis = True
        self.show_tracker = True
        self.show_crosshair = True
        self.show_scalebar = False
        self.show_grid = False
        self.show_legend = False

        # 3. Nuke the DisplayState (Drops overlays, resets colormap, etc.)
        self.display = DisplayState()

        # 4. Recalculate the optimal Window/Level from scratch
        self.init_default_window_level()

        self.is_data_dirty = True

    def apply_wl_preset(self, preset_name):
        if getattr(self.volume, "is_rgb", False) or preset_name == "Custom":
            return
        if "Optimal" in preset_name:
            stride = max(1, self.volume.data.size // 100000)
            sample_data = self.volume.data.flatten()[::stride]
            p2, p98 = np.percentile(sample_data, [2, 98])
            self.ww = max(1e-20, p98 - p2)
            self.wl = (p98 + p2) / 2
        elif "Min/Max" in preset_name:
            min_v = float(np.min(self.volume.data))
            max_v = float(np.max(self.volume.data))
            self.ww = max(1e-20, max_v - min_v)
            self.wl = (max_v + min_v) / 2
        elif preset_name in WL_PRESETS and WL_PRESETS[preset_name] is not None:
            self.ww = WL_PRESETS[preset_name]["ww"]
            self.wl = WL_PRESETS[preset_name]["wl"]

    def update_base_display_data(self):
        """Resamples the base image so the standalone viewer shows the transform visually.
        Optimized: ONLY applies Rotation. Translation is handled by 2D Camera Pan in the UI.
        """
        if (
            not getattr(self, "transform_active", False)
            or getattr(self, "transform", None) is None
        ):
            self.base_display_data = None
            return

        rx = self.transform.GetAngleX()
        ry = self.transform.GetAngleY()
        rz = self.transform.GetAngleZ()

        # FAST PATH: If purely translation, completely skip the heavy 3D resample!
        if abs(rx) < 1e-6 and abs(ry) < 1e-6 and abs(rz) < 1e-6:
            self.base_display_data = None
            return

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

        # HEAVY PATH: Create a Rotation-Only transform matching the true CoR
        rot_transform = sitk.Euler3DTransform()
        rot_transform.SetCenter(self.transform.GetCenter())
        rot_transform.SetRotation(rx, ry, rz)

        resampler.SetTransform(rot_transform.GetInverse())

        target_dim = self.volume.sitk_image.GetDimension()
        if target_dim == 3:
            resampled_img = resampler.Execute(self.volume.sitk_image)
            self.base_display_data = sitk.GetArrayFromImage(resampled_img)
        elif target_dim == 4:
            resampled_volumes = []
            for t in range(self.volume.num_timepoints):
                size = list(self.volume.sitk_image.GetSize())
                size[3] = 0
                index = [0, 0, 0, t]
                vol_3d = sitk.Extract(self.volume.sitk_image, size, index)
                resampled_volumes.append(resampler.Execute(vol_3d))
            self.base_display_data = sitk.GetArrayFromImage(
                sitk.JoinSeries(resampled_volumes)
            )

    def set_overlay(self, other_vs_id, other_vol, other_transform=None):
        if other_vs_id is None or other_vol is None:
            self.overlay_id = None
            self.overlay_data = None
            self.is_data_dirty = True
            return

        self.overlay_id = other_vs_id

        has_base_transform = (
            getattr(self, "transform_active", False)
            and getattr(self, "transform", None) is not None
        )
        has_overlay_transform = other_transform is not None

        # Do not early-exit if ANY transform is active!
        if (
            not has_base_transform
            and not has_overlay_transform
            and np.allclose(self.volume.spacing, other_vol.spacing, atol=1e-4)
            and np.allclose(self.volume.origin, other_vol.origin, atol=1e-4)
            and self.volume.shape3d == other_vol.shape3d
        ):
            self.overlay_data = other_vol.data
            self.is_data_dirty = True
            return

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
        resampler.SetInterpolator(sitk.sitkNearestNeighbor)

        min_val = float(np.min(other_vol.data))
        resampler.SetDefaultPixelValue(min_val)

        # --- THE WORLD ENGINE: Chain Base & Overlay Transforms ---
        if has_base_transform or has_overlay_transform:
            comp = sitk.CompositeTransform(3)
            if has_base_transform:
                comp.AddTransform(self.transform)
            if has_overlay_transform:
                comp.AddTransform(other_transform.GetInverse())
            resampler.SetTransform(comp)
        # ---------------------------------------------------------

        target_dim = other_vol.sitk_image.GetDimension()

        if target_dim == 3:
            resampled_img = resampler.Execute(other_vol.sitk_image)
            self.overlay_data = sitk.GetArrayFromImage(resampled_img)

        elif target_dim == 4:
            resampled_volumes = []
            for t in range(other_vol.num_timepoints):
                size = list(other_vol.sitk_image.GetSize())
                size[3] = 0
                index = [0, 0, 0, t]
                vol_3d = sitk.Extract(other_vol.sitk_image, size, index)

                res_3d = resampler.Execute(vol_3d)
                resampled_volumes.append(res_3d)

            resampled_4d = sitk.JoinSeries(resampled_volumes)
            self.overlay_data = sitk.GetArrayFromImage(resampled_4d)

        else:
            self.overlay_data = other_vol.data

        self.is_data_dirty = True

    def set_ct_window_level(self, flat_data):
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

        self.ww = preset["ww"]
        self.wl = preset["wl"]


class ROIState:
    def __init__(
        self, volume_id, name, color, source_mode="Ignore BG (val)", source_val=0.0
    ):
        self.volume_id = volume_id
        self.name = name
        self.color = color
        self.opacity = 0.5
        self.visible = True
        self.is_contour = False

        # We save the rules so history loads perfectly!
        self.source_mode = source_mode
        self.source_val = source_val

    def to_dict(self):
        return {
            "volume_id": self.volume_id,
            "name": self.name,
            "color": self.color,
            "opacity": self.opacity,
            "visible": self.visible,
            "is_contour": self.is_contour,
            "source_mode": self.source_mode,
            "source_val": self.source_val,
        }

    def from_dict(self, d):
        self.name = d.get("name", self.name)
        self.color = d.get("color", self.color)
        self.opacity = d.get("opacity", self.opacity)
        self.visible = d.get("visible", self.visible)
        self.is_contour = d.get("is_contour", self.is_contour)
        self.source_mode = d.get("source_mode", "Ignore BG (val)")
        self.source_val = d.get("source_val", 0.0)


class Controller:
    """The central manager."""

    def __init__(self):
        self.gui = None
        self.volumes = {}
        self.view_states = {}
        self.viewers = {}
        self.settings = SettingsManager()
        self.history = HistoryManager()
        self.use_history = True
        self._next_image_id = 0

    def get_next_image_id(self, current_id):
        if not self.view_states:
            return None
        keys = list(self.view_states.keys())
        if current_id not in keys:
            return keys[0]
        next_idx = (keys.index(current_id) + 1) % len(keys)
        return keys[next_idx]

    def link_all(self):
        if not self.view_states:
            return
        first_vs_id = next(iter(self.view_states))
        for vs in self.view_states.values():
            vs.sync_group = 1

        group_viewer_tags = [v.tag for v in self.viewers.values() if v.image_id]
        if group_viewer_tags:
            self.unify_ppm(group_viewer_tags)
            master_viewer = self.viewers[group_viewer_tags[0]]
            phys_center = master_viewer.get_center_physical_coord()
            if phys_center is not None:
                for tag in group_viewer_tags:
                    self.viewers[tag].center_on_physical_coord(phys_center)

        self.propagate_sync(first_vs_id)
        if self.gui:
            self.gui.refresh_sync_ui()
            self.gui.refresh_image_list_ui()

    def unlink_all(self):
        for vs in self.view_states.values():
            vs.sync_group = 0
        if self.gui:
            self.gui.refresh_sync_ui()
            self.gui.refresh_image_list_ui()

    def default_viewers_orientation(self):
        n = len(self.view_states)
        if n == 1:
            self.viewers["V1"].set_orientation(ViewMode.AXIAL)
            self.viewers["V2"].set_orientation(ViewMode.SAGITTAL)
            self.viewers["V3"].set_orientation(ViewMode.CORONAL)
            self.viewers["V4"].set_orientation(ViewMode.AXIAL)
        elif n == 2:
            self.viewers["V1"].set_orientation(ViewMode.AXIAL)
            self.viewers["V2"].set_orientation(ViewMode.SAGITTAL)
            self.viewers["V3"].set_orientation(ViewMode.AXIAL)
            self.viewers["V4"].set_orientation(ViewMode.SAGITTAL)
        elif n == 3:
            self.viewers["V1"].set_orientation(ViewMode.AXIAL)
            self.viewers["V2"].set_orientation(ViewMode.AXIAL)
            self.viewers["V3"].set_orientation(ViewMode.AXIAL)
            self.viewers["V4"].set_orientation(ViewMode.SAGITTAL)
        elif n >= 4:
            self.viewers["V1"].set_orientation(ViewMode.AXIAL)
            self.viewers["V2"].set_orientation(ViewMode.AXIAL)
            self.viewers["V3"].set_orientation(ViewMode.AXIAL)
            self.viewers["V4"].set_orientation(ViewMode.AXIAL)

    def load_image(self, path, is_auto_overlay=False):
        img_id = str(self._next_image_id)
        self._next_image_id += 1
        vol = VolumeData(path)
        vs = ViewState(vol)

        # History
        history_entry = self.history.get_image_state(vol) if self.use_history else None
        if history_entry:
            vs.camera.from_dict(history_entry["camera"])
            vs.display.from_dict(history_entry["display"])

            # Re-derive the crosshair_value based on restored voxel
            if vs.camera.crosshair_voxel is not None:
                ix, iy, iz = [int(v) for v in vs.camera.crosshair_voxel[:3]]
                if vol.num_timepoints > 1:
                    vs.crosshair_value = vol.data[vs.camera.time_idx, iz, iy, ix]
                else:
                    vs.crosshair_value = vol.data[iz, iy, ix]

            vs.is_data_dirty = True

        self.volumes[img_id] = vol
        self.view_states[img_id] = vs

        # Auto-load overlay
        # Prevent infinite recursion with is_auto_overlay flag
        if history_entry and history_entry.get("overlay_path") and not is_auto_overlay:
            op_path = resolve_history_path_key(history_entry["overlay_path"])
            if os.path.exists(op_path):
                # Load the overlay quietly in the background
                op_id = self.load_image(op_path, is_auto_overlay=True)
                op_vol = self.volumes[op_id]
                # Restore the link! (opacity, mode, threshold are already restored in from_dict)
                vs.set_overlay(op_id, op_vol)

        if not is_auto_overlay:
            self.add_recent_file(path)

        if self.gui:
            self.gui.refresh_image_list_ui()

        return img_id

    def load_label_map(self, base_id, filepath, start_color_idx):
        import json

        # 1. Attempt to find a JSON sidecar dictionary
        json_path = filepath.rsplit(".", 1)[0] + ".json"
        if filepath.endswith(".nii.gz"):
            json_path = filepath[:-7] + ".json"

        label_dict = {}
        if os.path.exists(json_path):
            try:
                with open(json_path, "r") as f:
                    raw_dict = json.load(f)
                    # Force integer keys in case JSON parsed them as strings
                    label_dict = {int(k): str(v) for k, v in raw_dict.items()}
            except Exception as e:
                print(f"Failed to load JSON {json_path}: {e}")

        # 2. Read the image quickly just to get the unique integer values
        temp_img = sitk.ReadImage(filepath)
        temp_data = sitk.GetArrayViewFromImage(temp_img)
        unique_vals = np.unique(temp_data)

        loaded_count = 0
        from vvv.config import ROI_COLORS

        base_name = os.path.basename(filepath)
        for ext in [
            ".nii.gz",
            ".nii",
            ".mhd",
            ".mha",
            ".nrrd",
            ".dcm",
            ".tif",
            ".png",
            ".jpg",
        ]:
            if base_name.lower().endswith(ext):
                base_name = base_name[: -len(ext)]
                break

        # 3. Process every non-zero label as a distinct ROI
        for val in unique_vals:
            if val == 0:
                continue  # 0 is strictly background in label maps

            color = ROI_COLORS[(start_color_idx + loaded_count) % len(ROI_COLORS)]
            roi_name = label_dict.get(int(val), f"{base_name} - Lbl {val}")

            self.load_binary_mask(
                base_id,
                filepath,
                name=roi_name,
                color=color,
                mode="Target FG (val)",
                target_val=float(val),
            )
            loaded_count += 1

        return loaded_count

    def load_binary_mask(
        self,
        base_id,
        filepath,
        name=None,
        color=[255, 50, 50],
        mode="Ignore BG (val)",
        target_val=0.0,
    ):
        base_vol = self.volumes[base_id]
        mask_vol = VolumeData(filepath)

        # Apply rule to raw data BEFORE any resampling or cropping!
        if mode == "Target FG (val)":
            mask_vol.data = (mask_vol.data == target_val).astype(np.uint8)
        else:
            mask_vol.data = (mask_vol.data != target_val).astype(np.uint8)

        # Update SITK image to ensure Resampler behaves correctly with the new binary data
        new_img = sitk.GetImageFromArray(mask_vol.data)
        new_img.SetSpacing(mask_vol.sitk_image.GetSpacing())
        new_img.SetOrigin(mask_vol.sitk_image.GetOrigin())
        new_img.SetDirection(mask_vol.sitk_image.GetDirection())
        mask_vol.sitk_image = new_img

        self.process_binary_mask(base_vol, mask_vol)

        # Safeguard warning
        if mask_vol.data.size == 0:
            raise ValueError("Outside the base image FOV (or completely empty).")

        mask_id = str(self._next_image_id)
        self._next_image_id += 1
        self.volumes[mask_id] = mask_vol

        if name is None:
            name = os.path.basename(filepath)
            for ext in [
                ".nii.gz",
                ".nii",
                ".mhd",
                ".mha",
                ".nrrd",
                ".dcm",
                ".tif",
                ".png",
                ".jpg",
            ]:
                if name.lower().endswith(ext):
                    name = name[: -len(ext)]
                    break

        roi_state = ROIState(
            mask_id, name, color, source_mode=mode, source_val=target_val
        )
        self.view_states[base_id].rois[mask_id] = roi_state
        self.view_states[base_id].is_data_dirty = True

        return mask_id

        # ==========================================
        # REGISTRATION & TRANSFORM MATH
        # ==========================================

    def load_transform(self, vs_id, filepath):
        if vs_id not in self.view_states:
            return False

        vs = self.view_states[vs_id]
        vol = self.volumes[vs_id]
        new_transform = sitk.Euler3DTransform()

        try:
            # 1. Try to parse as an Elastix Parameter File
            with open(filepath, "r") as f:
                content = f.read()

            if "TransformParameters" in content and "CenterOfRotationPoint" in content:
                import re

                params = (
                    re.search(r"\(TransformParameters(.*?)\)", content).group(1).split()
                )
                center = (
                    re.search(r"\(CenterOfRotationPoint(.*?)\)", content)
                    .group(1)
                    .split()
                )

                # Elastix Euler is [rx, ry, rz, tx, ty, tz] (angles in radians)
                new_transform.SetRotation(
                    float(params[0]), float(params[1]), float(params[2])
                )
                new_transform.SetTranslation(
                    (float(params[3]), float(params[4]), float(params[5]))
                )
                new_transform.SetCenter(
                    (float(center[0]), float(center[1]), float(center[2]))
                )
            else:
                # 2. Fallback to standard ITK Transform Reader
                generic_transform = sitk.ReadTransform(filepath)
                # Force it into an Euler3DTransform so our GUI sliders can interact with it
                if generic_transform.GetDimension() == 3:
                    new_transform.SetMatrix(generic_transform.GetMatrix())
                    new_transform.SetTranslation(generic_transform.GetTranslation())
                    if hasattr(generic_transform, "GetCenter"):
                        new_transform.SetCenter(generic_transform.GetCenter())

        except Exception as e:
            print(f"Error loading transform: {e}")
            return False

        # 3. Failsafe: If Center of Rotation is exactly 0,0,0, fix it!
        if np.allclose(new_transform.GetCenter(), [0, 0, 0]):
            new_transform.SetCenter(self._get_volume_physical_center(vol).tolist())

        vs.transform = new_transform
        vs.transform_file = os.path.basename(filepath)
        return True

    def save_transform(self, vs_id, filepath):
        vs = self.view_states.get(vs_id)
        if vs and vs.transform:
            sitk.WriteTransform(vs.transform, filepath)
            vs.transform_file = os.path.basename(filepath)

    def add_recent_file(self, path):
        """Adds a path to the recent files list in settings and caps it at 10."""
        if "behavior" not in self.settings.data:
            self.settings.data["behavior"] = {}

        recent = self.settings.data["behavior"].get("recent_files", [])

        # Convert list (DICOM series) to JSON string to make it hashable and storable
        path_str = json.dumps(path) if isinstance(path, list) else path

        if path_str in recent:
            recent.remove(path_str)
        recent.insert(0, path_str)

        # Cap at 10
        self.settings.data["behavior"]["recent_files"] = recent[:10]

    def scan_dicom_folder(self, folder_path, recursive=True):
        """Scans a folder for DICOM series and YIELDS progress updates."""
        import SimpleITK as sitk
        import os

        if not os.path.exists(folder_path):
            yield (1.0, "Done", [])
            return

        # Use a dictionary to group slices by Series UID across multiple folders!
        series_dict = {}
        search_dirs = (
            [x[0] for x in os.walk(folder_path, followlinks=True)]
            if recursive
            else [folder_path]
        )
        total_dirs = max(1, len(search_dirs))

        reader = sitk.ImageSeriesReader()
        file_reader = sitk.ImageFileReader()

        # Silence the C++ GDCM Warnings
        sitk.ProcessObject.SetGlobalWarningDisplay(False)

        try:
            for i, d in enumerate(search_dirs):
                # Yield progress to the UI Thread
                yield (i / total_dirs, os.path.basename(d))

                try:
                    series_ids = reader.GetGDCMSeriesIDs(d)
                    for sid in series_ids:
                        file_names = reader.GetGDCMSeriesFileNames(d, sid)
                        if not file_names:
                            continue

                        if sid in series_dict:
                            # Series is split across multiple folders -> just append the files!
                            series_dict[sid]["files"].extend(file_names)
                        else:
                            file_reader.SetFileName(file_names[0])
                            file_reader.ReadImageInformation()

                            def get_tag(tag, default=""):
                                return (
                                    file_reader.GetMetaData(tag).strip()
                                    if file_reader.HasMetaDataKey(tag)
                                    else default
                                )

                            # --- FORMAT DATE & TIME ---
                            d_str = get_tag("0008|0020")
                            t_str = get_tag("0008|0030")
                            fmt_date = d_str
                            if len(d_str) >= 8:
                                fmt_date = f"{d_str[0:4]}-{d_str[4:6]}-{d_str[6:8]}"
                                if len(t_str) >= 4:
                                    fmt_date += f" {t_str[0:2]}:{t_str[2:4]}"

                            # --- FUZZY SEARCH FOR INJECTED DOSE (Nested Sequences) ---
                            dose_str = ""
                            for k in file_reader.GetMetaDataKeys():
                                if "0018|1074" in k:  # Radionuclide Total Dose
                                    raw_dose = file_reader.GetMetaData(k).strip()
                                    try:
                                        dose_str = f"{float(raw_dose) / 1e6:.2f} MBq"
                                    except:
                                        dose_str = raw_dose
                                    break

                            size_tup = file_reader.GetSize()
                            x, y = size_tup[0], size_tup[1]
                            z = size_tup[2] if len(size_tup) > 2 else 1

                            series_info = {
                                "id": sid,
                                "dir": d,
                                "files": list(file_names),
                                "patient_name": get_tag("0010|0010", "Unknown"),
                                "study_desc": get_tag("0008|1030", "Unknown"),
                                "series_desc": get_tag("0008|103e", "Unknown"),
                                "modality": get_tag("0008|0060", "Unknown"),
                                "date": fmt_date if fmt_date else "Unknown",
                                "spacing": f"{file_reader.GetSpacing()[0]:.2f} x {file_reader.GetSpacing()[1]:.2f}",
                                "tags": [],
                                "_base_z": z,
                                "_base_x": x,
                                "_base_y": y,
                            }

                            # --- CURATED MASTER TAG LIST ---
                            target_tags = {
                                "0008|0008": "Image Type",
                                "0008|0020": "Study Date",
                                "0008|0030": "Study Time",
                                "0008|0060": "Modality",
                                "0008|0070": "Manufacturer",
                                "0008|1030": "Study Description",
                                "0008|103E": "Series Description",
                                "0010|0010": "Patient Name",
                                "0010|0020": "Patient ID",
                                "0010|0030": "Patient Birth Date",
                                "0010|0040": "Patient Sex",
                                "0018|0015": "Body Part Examined",
                                "0018|0050": "Slice Thickness",
                                "0018|1074": "Radionuclide Total Dose",
                                "0018|0031": "Radiopharmaceutical",
                                "0020|0011": "Series Number",
                                "0028|0010": "Rows",
                                "0028|0011": "Columns",
                            }

                            # Only append tags that actually contain data
                            for tag, name in target_tags.items():
                                val = dose_str if tag == "0018|1074" else get_tag(tag)

                                if val:
                                    # Format standalone dates/times cleanly
                                    if (
                                        tag in ("0008|0020", "0010|0030")
                                        and len(val) == 8
                                    ):
                                        val = f"{val[0:4]}-{val[4:6]}-{val[6:8]}"
                                    elif tag == "0008|0030" and len(val) >= 4:
                                        val = (
                                            f"{val[0:2]}:{val[2:4]}:{val[4:6]}"
                                            if len(val) >= 6
                                            else f"{val[0:2]}:{val[2:4]}"
                                        )

                                    series_info["tags"].append((tag, name, val))

                            series_dict[sid] = series_info
                except Exception as e:
                    pass
        finally:
            sitk.ProcessObject.SetGlobalWarningDisplay(True)

        # Final post-processing to flatten the dictionary and fix the Z-Size
        found_series = []
        for sid, s in series_dict.items():
            x, y, z_header = s.pop("_base_x"), s.pop("_base_y"), s.pop("_base_z")
            file_count = len(s["files"])

            # If there is only 1 file, trust the header Z size (Multi-frame DICOM).
            # Otherwise, use the total number of files found for this Series UID.
            z_dim = z_header if (z_header > 1 and file_count == 1) else file_count

            s["size"] = f"{x} x {y} x {z_dim}"
            found_series.append(s)

        yield (1.0, "Done", found_series)

    def process_binary_mask(self, base_vol, mask_vol):
        """Helper to resample and autocrop a binary mask."""
        if (
            mask_vol.shape3d != base_vol.shape3d
            or not np.allclose(mask_vol.spacing, base_vol.spacing, atol=1e-4)
            or not np.allclose(mask_vol.origin, base_vol.origin, atol=1e-4)
        ):

            resampler = sitk.ResampleImageFilter()
            resampler.SetReferenceImage(base_vol.sitk_image)
            resampler.SetInterpolator(sitk.sitkNearestNeighbor)
            resampler.SetDefaultPixelValue(0)

            mask_vol.sitk_image = resampler.Execute(mask_vol.sitk_image)
            mask_vol.data = sitk.GetArrayFromImage(mask_vol.sitk_image)
            mask_vol.shape3d = base_vol.shape3d
            mask_vol.spacing = base_vol.spacing
            mask_vol.origin = base_vol.origin

        # 3D Autocrop
        coords = np.argwhere(mask_vol.data > 0)
        if coords.size > 0:
            if mask_vol.data.ndim == 4:
                z0, y0, x0 = coords[:, 1:].min(axis=0)
                z1, y1, x1 = coords[:, 1:].max(axis=0) + 1
                mask_vol.data = mask_vol.data[:, z0:z1, y0:y1, x0:x1]
            else:
                z0, y0, x0 = coords.min(axis=0)
                z1, y1, x1 = coords.max(axis=0) + 1
                mask_vol.data = mask_vol.data[z0:z1, y0:y1, x0:x1]
            mask_vol.roi_bbox = (z0, z1, y0, y1, x0, x1)
        else:
            mask_vol.roi_bbox = (0, 0, 0, 0, 0, 0)
            if mask_vol.data.ndim == 4:
                mask_vol.data = np.zeros(
                    (mask_vol.data.shape[0], 0, 0, 0), dtype=mask_vol.data.dtype
                )
            else:
                mask_vol.data = np.zeros((0, 0, 0), dtype=mask_vol.data.dtype)

    def _get_volume_physical_center(self, vol):
        """Calculates the exact physical center of an image volume for the CoR."""
        cx = (vol.shape3d[2] - 1) / 2.0
        cy = (vol.shape3d[1] - 1) / 2.0
        cz = (vol.shape3d[0] - 1) / 2.0
        return vol.voxel_coord_to_physic_coord(np.array([cx, cy, cz]))

    def save_image(self, vs_id, filepath):
        """Exports the active volume to disk as a NIfTI, MHD, etc."""
        if vs_id not in self.volumes:
            return
        import SimpleITK as sitk

        vol = self.volumes[vs_id]
        sitk.WriteImage(vol.sitk_image, filepath)

    def center_on_roi(self, base_id, roi_id):
        if base_id not in self.view_states or roi_id not in self.volumes:
            return

        mask_vol = self.volumes[roi_id]
        if not hasattr(mask_vol, "roi_bbox"):
            return

        z0, z1, y0, y1, x0, x1 = mask_vol.roi_bbox
        if z0 == z1:  # Empty mask
            return

        cx = (x0 + x1 - 1) / 2.0
        cy = (y0 + y1 - 1) / 2.0
        cz = (z0 + z1 - 1) / 2.0

        vs = self.view_states[base_id]

        vs.crosshair_voxel = [cx, cy, cz, vs.time_idx]
        vs.crosshair_phys_coord = mask_vol.voxel_coord_to_physic_coord(
            np.array([cx, cy, cz])
        )

        self.propagate_sync(base_id)

        target_group = vs.sync_group
        for viewer in self.viewers.values():
            if viewer.image_id and viewer.view_state:
                if viewer.image_id == base_id or (
                    target_group != 0 and viewer.view_state.sync_group == target_group
                ):
                    viewer.needs_recenter = True
                    viewer.is_geometry_dirty = True

    def get_roi_stats(self, base_vs_id, roi_id, is_overlay=False):
        if base_vs_id not in self.view_states or roi_id not in self.volumes:
            return None

        vs = self.view_states[base_vs_id]
        roi_vol = self.volumes[roi_id]

        # 1. Calculate physical volume per voxel in cubic centimeters (cc)
        voxel_vol_mm3 = abs(np.prod(roi_vol.spacing))
        mask = roi_vol.data > 0
        voxel_count = np.count_nonzero(mask)
        vol_cc = (voxel_count * voxel_vol_mm3) / 1000.0

        if voxel_count == 0:
            return {
                "vol": 0.0,
                "mean": 0.0,
                "max": 0.0,
                "min": 0.0,
                "std": 0.0,
                "peak": 0.0,
                "mass": 0.0,
            }

        # 2. Extract the target data (Base vs Resampled Overlay)
        if is_overlay:
            if not vs.display.overlay_id or vs.display.overlay_data is None:
                return None
            target_data = vs.display.overlay_data
            ov_vol = self.volumes[vs.display.overlay_id]
            if ov_vol.num_timepoints > 1:
                t = min(vs.camera.time_idx, ov_vol.num_timepoints - 1)
                target_data = target_data[t]
        else:
            base_vol = self.volumes[base_vs_id]
            target_data = base_vol.data
            if base_vol.num_timepoints > 1:
                t = min(vs.camera.time_idx, base_vol.num_timepoints - 1)
                target_data = target_data[t]

        # 3. Crop the target image to match the ROI's bounding box
        if hasattr(roi_vol, "roi_bbox"):
            z0, z1, y0, y1, x0, x1 = roi_vol.roi_bbox
            if z0 != z1:
                target_data = target_data[z0:z1, y0:y1, x0:x1]

        pixels = target_data[mask]

        # 4. Compute advanced statistics
        mean_val = float(np.mean(pixels))
        peak_val = float(np.percentile(pixels, 95))  # Robust P95 Peak

        # Mass assumes CT Hounsfield Units (Water = 0 = 1g/cc, Air = -1000 = 0g/cc)
        density_g_cc = (mean_val / 1000.0) + 1.0
        mass_g = vol_cc * density_g_cc

        return {
            "vol": vol_cc,
            "mean": mean_val,
            "max": float(np.max(pixels)),
            "min": float(np.min(pixels)),
            "std": float(np.std(pixels)),
            "peak": peak_val,
            "mass": mass_g,
        }

    def get_pixel_values_at_voxel(self, vs_id, voxel_coord):
        """
        Calculates the Base value, Fused Target value, and intersecting ROIs for a specific voxel.
        Centralizes the math for both the floating mouse tracker and the sidebar crosshair!
        """
        vs = self.view_states.get(vs_id)
        if not vs:
            return None

        vol = self.volumes[vs_id]

        # 1. Extract and clamp integer base coordinates
        ix, iy, iz = [
            int(np.clip(np.floor(c + 0.5), 0, limit - 1))
            for c, limit in zip(
                voxel_coord[:3], [vol.shape3d[2], vol.shape3d[1], vol.shape3d[0]]
            )
        ]

        t_idx = int(voxel_coord[3]) if len(voxel_coord) > 3 else vs.time_idx

        # 2. Base Image Value
        base_val = None
        mz, my, mx = vol.shape3d
        if 0 <= ix < mx and 0 <= iy < my and 0 <= iz < mz:
            t = min(t_idx, vol.num_timepoints - 1) if vol.num_timepoints > 1 else 0

            # Read from the display buffer if active
            display_data = getattr(vs, "base_display_data", None)
            if display_data is not None:
                base_val = (
                    display_data[t, iz, iy, ix]
                    if vol.num_timepoints > 1
                    else display_data[iz, iy, ix]
                )
            else:
                base_val = (
                    vol.data[t, iz, iy, ix]
                    if vol.num_timepoints > 1
                    else vol.data[iz, iy, ix]
                )

        if base_val is None:
            return None  # Mouse is completely outside the image bounds

        # 3. Fused Target Overlay Value (Calculated via physical coordinate mapping)
        overlay_val = None
        if vs.overlay_id and vs.overlay_id in self.volumes:
            ov_vol = self.volumes[vs.overlay_id]
            ov_vs = self.view_states[vs.overlay_id]

            world_phys = vs.get_world_phys_from_display_voxel(np.array([ix, iy, iz]))
            ov_vox = ov_vs.get_voxel_from_world_phys(world_phys)

            ox, oy, oz = (
                int(np.floor(ov_vox[0] + 0.5)),
                int(np.floor(ov_vox[1] + 0.5)),
                int(np.floor(ov_vox[2] + 0.5)),
            )
            omz, omy, omx = ov_vol.shape3d

            if 0 <= ox < omx and 0 <= oy < omy and 0 <= oz < omz:
                ot = min(t_idx, ov_vol.num_timepoints - 1)
                overlay_val = (
                    ov_vol.data[ot, oz, oy, ox]
                    if ov_vol.num_timepoints > 1
                    else ov_vol.data[oz, oy, ox]
                )

        # 4. Intersecting ROIs (No visibility check! We want to see hidden ROIs)
        roi_names = []
        for r_id, r_state in vs.rois.items():
            r_vol = self.volumes.get(r_id)
            if r_vol:
                if hasattr(r_vol, "roi_bbox"):
                    rz0, rz1, ry0, ry1, rx0, rx1 = r_vol.roi_bbox
                    if rx0 <= ix < rx1 and ry0 <= iy < ry1 and rz0 <= iz < rz1:
                        rrx, rry, rrz = ix - rx0, iy - ry0, iz - rz0
                        rt = min(t_idx, r_vol.num_timepoints - 1)
                        r_val = (
                            r_vol.data[rt, rrz, rry, rrx]
                            if r_vol.num_timepoints > 1
                            else r_vol.data[rrz, rry, rrx]
                        )
                        if r_val > 0:
                            roi_names.append(r_state.name)
                else:
                    rmz, rmy, rmx = r_vol.shape3d
                    if 0 <= ix < rmx and 0 <= iy < rmy and 0 <= iz < rmz:
                        rt = min(t_idx, r_vol.num_timepoints - 1)
                        r_val = (
                            r_vol.data[rt, iz, iy, ix]
                            if r_vol.num_timepoints > 1
                            else r_vol.data[iz, iy, ix]
                        )
                        if r_val > 0:
                            roi_names.append(r_state.name)

        return {"base_val": base_val, "overlay_val": overlay_val, "rois": roi_names}

    def unify_ppm(self, target_viewer_tags):
        valid_viewers = [
            self.viewers[tag]
            for tag in target_viewer_tags
            if self.viewers[tag].view_state
        ]
        if not valid_viewers:
            return

        max_ppm = 0.0
        for viewer in valid_viewers:
            ppm = viewer.get_pixels_per_mm()
            if ppm > max_ppm:
                max_ppm = ppm

        if max_ppm > 0:
            for viewer in valid_viewers:
                viewer.set_pixels_per_mm(max_ppm)
                viewer.is_geometry_dirty = True

    def update_all_viewers_of_image(self, vs_id):
        for viewer in self.viewers.values():
            if viewer.image_id == vs_id:
                viewer.draw_crosshair()
                viewer.update_render()
                viewer.is_geometry_dirty = True

    def update_setting(self, keys, value):
        if not keys or keys[-1] is None:
            return

        d = self.settings.data
        for key in keys[:-1]:
            d = d[key]

        if keys[0] == "colors" and isinstance(value, (list, tuple)):
            if any(isinstance(x, float) for x in value):
                value = [int(x * 255) for x in value]
            else:
                value = [int(x) for x in value]

        d[keys[-1]] = value

        for viewer in self.viewers.values():
            viewer.update_render()
            viewer.is_geometry_dirty = True
            if viewer.image_id:
                viewer.draw_crosshair()

    def update_transform_manual(self, vs_id, tx, ty, tz, rx_deg, ry_deg, rz_deg):
        """Triggered by the GUI sliders to update the transform data model."""
        vs = self.view_states.get(vs_id)
        if not vs:
            return

        if not vs.transform:
            vs.transform = sitk.Euler3DTransform()
            vol = self.volumes[vs_id]
            vs.transform.SetCenter(self._get_volume_physical_center(vol).tolist())

        import math

        vs.transform.SetTranslation((float(tx), float(ty), float(tz)))
        vs.transform.SetRotation(
            math.radians(rx_deg), math.radians(ry_deg), math.radians(rz_deg)
        )

    def reset_settings(self):
        self.settings.reset()
        for viewer in self.viewers.values():
            viewer.update_render()
            if viewer.image_id:
                viewer.draw_crosshair()
                viewer.is_geometry_dirty = True

    def reset_image_view(self, vs_id, hard=False):
        """Resets the view and re-applies the boot-up synchronization logic."""
        if vs_id not in self.view_states:
            return

        vs = self.view_states[vs_id]

        if hard:
            vs.hard_reset()
        else:
            vs.reset_view()

        # Re-apply unifying math so it looks exactly like the initial load!
        same_viewers = [v.tag for v in self.viewers.values() if v.image_id == vs_id]
        if same_viewers:
            self.unify_ppm(same_viewers)

        # Force all linked viewers to perfectly re-center
        for tag in same_viewers:
            viewer = self.viewers[tag]
            if hasattr(viewer, "needs_recenter"):
                viewer.needs_recenter = True
            viewer.is_geometry_dirty = True

        if self.gui:
            self.gui.update_sidebar_info(self.gui.context_viewer)

    def reload_roi(self, base_id, roi_id):
        if base_id not in self.view_states or roi_id not in self.volumes:
            return

        mask_vol = self.volumes[roi_id]
        roi_state = self.view_states[base_id].rois[roi_id]
        was_reset = mask_vol.reload()

        # Re-apply binarization rule after reloading from disk!
        mode = getattr(roi_state, "source_mode", "Ignore BG (val)")
        target_val = getattr(roi_state, "source_val", 0.0)

        if mode == "Target FG (val)":
            mask_vol.data = (mask_vol.data == target_val).astype(np.uint8)
        else:
            mask_vol.data = (mask_vol.data != target_val).astype(np.uint8)

        new_img = sitk.GetImageFromArray(mask_vol.data)
        new_img.SetSpacing(mask_vol.sitk_image.GetSpacing())
        new_img.SetOrigin(mask_vol.sitk_image.GetOrigin())
        new_img.SetDirection(mask_vol.sitk_image.GetDirection())
        mask_vol.sitk_image = new_img

        base_vol = self.volumes[base_id]
        self.process_binary_mask(base_vol, mask_vol)

        self.view_states[base_id].is_data_dirty = True
        self.update_all_viewers_of_image(base_id)

        if self.gui:
            self.gui.refresh_rois_ui()
            self.gui.show_status_message(f"Reloaded: {roi_state.name}")

    def reload_settings(self):
        self.settings.reset()
        self.settings.load()
        for viewer in self.viewers.values():
            viewer.update_render()
            if viewer.image_id:
                viewer.draw_crosshair()
                viewer.is_geometry_dirty = True

    def reload_image(self, vs_id):
        if vs_id in self.view_states:
            vs = self.view_states[vs_id]
            vol = vs.volume
            was_reset = vol.reload()

            if was_reset:
                for viewer in self.viewers.values():
                    if viewer.image_id == vs_id:
                        viewer.set_image(vs_id)
            else:
                ix, iy, iz = [
                    int(np.clip(np.floor(c + 0.5), 0, limit - 1))
                    for c, limit in zip(
                        vs.crosshair_voxel[:3],
                        [vol.shape3d[2], vol.shape3d[1], vol.shape3d[0]],
                    )
                ]

                if vol.num_timepoints > 1:
                    vs.crosshair_value = vol.data[vs.time_idx, iz, iy, ix]
                else:
                    vs.crosshair_value = vol.data[iz, iy, ix]

                vs.histogram_is_dirty = True
                vs.is_data_dirty = True
                self.update_all_viewers_of_image(vs_id)

            for other_id, other_vs in self.view_states.items():
                if other_vs.overlay_id == vs_id:
                    other_vs.set_overlay(vs_id, vol)
                    self.update_all_viewers_of_image(other_id)

            if self.gui.context_viewer and self.gui.context_viewer.image_id == vs_id:
                self.gui.update_sidebar_info(self.gui.context_viewer)
                self.gui.update_sidebar_crosshair(self.gui.context_viewer)

            if self.gui:
                self.gui.show_status_message(f"Reloaded: {vol.name}")
                self.gui.refresh_image_list_ui()
                self.gui.refresh_rois_ui()

    def save_settings(self):
        return self.settings.save()

    def save_workspace(self, filepath):
        import shlex
        from vvv.utils import get_relative_path

        workspace_dir = os.path.dirname(filepath)
        data = {"volumes": {}, "viewers": {}}

        # 1. Save all open volumes and their states
        for vs_id, vs in self.view_states.items():
            vol = self.volumes[vs_id]

            # Handle 4D magic paths and DICOM list paths safely
            if isinstance(vol.path, list):
                safe_path = [get_relative_path(p, workspace_dir) for p in vol.path]
            elif isinstance(vol.path, str) and vol.path.startswith("4D:"):
                tokens = shlex.split(vol.path[3:].strip())
                rel_paths = [get_relative_path(p, workspace_dir) for p in tokens]
                safe_path = "4D:" + " ".join(f'"{p}"' for p in rel_paths)
            else:
                safe_path = get_relative_path(vol.path, workspace_dir)

            # Convert ROI paths to relative paths
            rois_data = []
            for roi_id, roi_state in vs.rois.items():
                if roi_id in self.volumes:
                    r_vol = self.volumes[roi_id]
                    if r_vol.file_paths:
                        r_path = get_relative_path(r_vol.file_paths[0], workspace_dir)
                        rois_data.append({"path": r_path, "state": roi_state.to_dict()})

            data["volumes"][vs_id] = {
                "path": safe_path,
                "sync_group": vs.sync_group,
                "overlay_id": vs.overlay_id,
                "camera": vs.camera.to_dict(),
                "display": vs.display.to_dict(),
            }

        # 2. Save which viewer is looking at what
        for v_tag, viewer in self.viewers.items():
            data["viewers"][v_tag] = {
                "image_id": viewer.image_id,
                "orientation": (
                    viewer.orientation.name if viewer.orientation else "AXIAL"
                ),
            }

        with open(filepath, "w") as f:
            json.dump(data, f, indent=4)

    def close_roi(self, base_id, roi_id):
        """Safely removes an ROI from the view state and frees the volume memory."""
        if base_id in self.view_states:
            vs = self.view_states[base_id]
            if roi_id in vs.rois:
                del vs.rois[roi_id]
                vs.is_data_dirty = True

        if roi_id in self.volumes:
            del self.volumes[roi_id]

        self.update_all_viewers_of_image(base_id)

    def close_image(self, vs_id):
        if vs_id in self.view_states:

            # History
            self.history.save_image_state(self, vs_id)

            for viewer in self.viewers.values():
                if viewer.image_id == vs_id:
                    viewer.drop_image()

            for other_id, other_vs in self.view_states.items():
                if other_vs.overlay_id == vs_id:
                    other_vs.set_overlay(None, None)
                    self.update_all_viewers_of_image(other_id)

            name = self.view_states[vs_id].volume.name

            # Delete ROIs from memory before deleting the view state ---
            for roi_id in list(self.view_states[vs_id].rois.keys()):
                if roi_id in self.volumes:
                    del self.volumes[roi_id]

            del self.view_states[vs_id]
            del self.volumes[vs_id]

            if self.view_states:
                first_vs_id = next(iter(self.view_states))
                for viewer in self.viewers.values():
                    if viewer.image_id is None:
                        viewer.set_image(first_vs_id)

            if self.gui:
                self.gui.refresh_image_list_ui()
                self.gui.refresh_rois_ui()
                if self.gui.context_viewer:
                    self.gui.update_sidebar_info(self.gui.context_viewer)
                self.gui.show_status_message(f"Closed: {name}")

    def on_visibility_toggle(self, sender, value, user_data):
        context_viewer = self.gui.context_viewer
        if not context_viewer or not context_viewer.view_state:
            return

        vs = context_viewer.view_state
        if user_data == "axis":
            vs.show_axis = value
        elif user_data == "grid":
            vs.show_grid = value
        elif user_data == "tracker":
            vs.show_tracker = value
        elif user_data == "crosshair":
            vs.show_crosshair = value
        elif user_data == "scalebar":
            vs.show_scalebar = value
        elif user_data == "legend":
            vs.show_legend = value

        self.update_all_viewers_of_image(context_viewer.image_id)

    def on_sync_group_change(self, sender, value, user_data):
        vs_id = user_data
        vs = self.view_states[vs_id]

        if value == "None":
            vs.sync_group = 0
            if self.gui:
                self.gui.refresh_image_list_ui()
            return

        new_group_id = int(value.split(" ")[1])
        vs.sync_group = new_group_id

        master_vs_id = None
        for other_id, other_vs in self.view_states.items():
            if other_id != vs_id and other_vs.sync_group == new_group_id:
                master_vs_id = other_id
                break

        group_viewer_tags = []
        for v in self.viewers.values():
            if v.view_state and v.view_state.sync_group == new_group_id:
                group_viewer_tags.append(v.tag)

        if not group_viewer_tags:
            return

        self.unify_ppm(group_viewer_tags)

        if master_vs_id:
            master_viewer = next(
                (v for v in self.viewers.values() if v.image_id == master_vs_id), None
            )
            if master_viewer:
                phys_center = master_viewer.get_center_physical_coord()
                if phys_center is not None:
                    for tag in group_viewer_tags:
                        self.viewers[tag].center_on_physical_coord(phys_center)
            self.propagate_sync(master_vs_id)

        self.update_all_viewers_of_image(vs_id)
        if self.gui:
            self.gui.refresh_image_list_ui()

    def tick(self):
        for viewer in self.viewers.values():
            did_update = viewer.tick()
            if did_update and self.gui and viewer == self.gui.context_viewer:
                self.gui.update_sidebar_crosshair(viewer)

        for vs in self.view_states.values():
            vs.is_data_dirty = False

        # Check if files changed on disk, update UI if needed
        outdated_changed = False
        for vol in self.volumes.values():
            if hasattr(vol, "is_outdated"):
                was_outdated = vol._is_outdated
                is_out = vol.is_outdated()
                if is_out != was_outdated:
                    outdated_changed = True

        if outdated_changed and self.gui:
            self.gui.refresh_image_list_ui()
            self.gui.refresh_rois_ui()

    def propagate_sync(self, source_vs_id):
        source_vs = self.view_states[source_vs_id]
        if source_vs.sync_group == 0:
            target_ids = [source_vs_id]
        else:
            target_ids = [
                tid
                for tid, vs in self.view_states.items()
                if vs.sync_group == source_vs.sync_group
            ]

        # Use the explicit display-aware method!
        world_phys = source_vs.get_world_phys_from_display_voxel(
            source_vs.crosshair_voxel[:3]
        )

        for target_id in target_ids:
            target_vs = self.view_states[target_id]

            if target_id == source_vs_id:
                source_vox = source_vs.crosshair_voxel
                target_vs.crosshair_voxel = source_vox.copy()
                target_vs.crosshair_phys_coord = (
                    target_vs.get_world_phys_from_display_voxel(source_vox[:3])
                )
                # ... [keep slices assignment]
                target_vs.slices[ViewMode.AXIAL] = int(source_vox[2])
                target_vs.slices[ViewMode.SAGITTAL] = int(source_vox[0])
                target_vs.slices[ViewMode.CORONAL] = int(source_vox[1])
            else:
                phys_pos = world_phys
                target_vol = target_vs.volume

                # Use the explicit display-aware mapping to find the new crosshair!
                target_vox = target_vs.get_display_voxel_from_world_phys(phys_pos)

                nt = target_vs.volume.num_timepoints
                target_vs.time_idx = min(source_vs.time_idx, nt - 1)

                target_vs.crosshair_voxel = [
                    target_vox[0],
                    target_vox[1],
                    target_vox[2],
                    target_vs.time_idx,
                ]
                target_vs.crosshair_phys_coord = phys_pos

                target_vs.slices[ViewMode.AXIAL] = int(
                    np.clip(np.floor(target_vox[2] + 0.5), 0, target_vol.shape3d[0] - 1)
                )
                target_vs.slices[ViewMode.SAGITTAL] = int(
                    np.clip(np.floor(target_vox[0] + 0.5), 0, target_vol.shape3d[2] - 1)
                )
                target_vs.slices[ViewMode.CORONAL] = int(
                    np.clip(np.floor(target_vox[1] + 0.5), 0, target_vol.shape3d[1] - 1)
                )

            ix, iy, iz = [
                int(np.clip(np.floor(c + 0.5), 0, limit - 1))
                for c, limit in zip(
                    target_vs.crosshair_voxel[:3],
                    [
                        target_vs.volume.shape3d[2],
                        target_vs.volume.shape3d[1],
                        target_vs.volume.shape3d[0],
                    ],
                )
            ]

            if target_vs.volume.num_timepoints > 1:
                target_vs.crosshair_value = target_vs.volume.data[
                    target_vs.time_idx, iz, iy, ix
                ]
            else:
                target_vs.crosshair_value = target_vs.volume.data[iz, iy, ix]

            target_vs.is_data_dirty = True

        for viewer in self.viewers.values():
            if viewer.image_id in target_ids:
                viewer.is_geometry_dirty = True

    def propagate_colormap(self, source_vs_id):
        source_vs = self.view_states[source_vs_id]
        import dearpygui.dearpygui as dpg

        sync_wl = False
        if dpg.does_item_exist("check_sync_wl"):
            sync_wl = dpg.get_value("check_sync_wl")

        target_group = source_vs.sync_group
        if sync_wl and target_group != 0:
            for target_id, vs in self.view_states.items():
                if vs.sync_group == target_group and not getattr(
                    vs.volume, "is_rgb", False
                ):
                    vs.colormap = source_vs.colormap
                    vs.is_data_dirty = True
        else:
            source_vs.is_data_dirty = True

        for viewer in self.viewers.values():
            if viewer.view_state:
                if (
                    viewer.image_id == source_vs_id
                    or (
                        sync_wl
                        and target_group != 0
                        and viewer.view_state.sync_group == target_group
                    )
                    or viewer.view_state.overlay_id == source_vs_id
                ):
                    viewer.update_render()
                    viewer.is_geometry_dirty = True

    def propagate_window_level(self, source_vs_id):
        source_vs = self.view_states[source_vs_id]
        import dearpygui.dearpygui as dpg

        sync_wl = False
        if dpg.does_item_exist("check_sync_wl"):
            sync_wl = dpg.get_value("check_sync_wl")

        dirty_ids = {source_vs_id}

        target_group = source_vs.sync_group
        if sync_wl and target_group != 0:
            for target_id, vs in self.view_states.items():
                if vs.sync_group == target_group and not getattr(
                    vs.volume, "is_rgb", False
                ):
                    vs.ww = source_vs.ww
                    vs.wl = source_vs.wl
                    vs.base_threshold = source_vs.base_threshold
                    dirty_ids.add(target_id)

        # Perform a single pass to sync Window/Level across the flat Base <-> Overlay hierarchy
        for tid in list(dirty_ids):
            t_vs = self.view_states[tid]

            # 1. Top-Down: If this image is a Base with a Registration overlay, push W/L down to the overlay
            if t_vs.overlay_id and t_vs.overlay_mode == "Registration":
                ovs = self.view_states.get(t_vs.overlay_id)
                if ovs and not getattr(ovs.volume, "is_rgb", False):
                    ovs.ww, ovs.wl = t_vs.ww, t_vs.wl
                    dirty_ids.add(t_vs.overlay_id)

            # 2. Bottom-Up: If this image is acting as an Overlay for a Base in Registration mode, push W/L up to the Base
            for base_id, base_vs in self.view_states.items():
                if base_vs.overlay_id == tid and base_vs.overlay_mode == "Registration":
                    if not getattr(base_vs.volume, "is_rgb", False):
                        base_vs.ww, base_vs.wl = t_vs.ww, t_vs.wl
                        dirty_ids.add(base_id)

        for tid in dirty_ids:
            self.view_states[tid].is_data_dirty = True

        for viewer in self.viewers.values():
            if viewer.view_state:
                if (
                    viewer.image_id in dirty_ids
                    or viewer.view_state.overlay_id in dirty_ids
                ):
                    viewer.update_render()
                    viewer.is_geometry_dirty = True

    def propagate_camera(self, source_viewer):
        if not source_viewer.view_state:
            return
        source_vs = source_viewer.view_state

        if source_vs.sync_group == 0:
            target_ids = [source_viewer.image_id]
        else:
            target_ids = [
                tid
                for tid, vs in self.view_states.items()
                if vs.sync_group == source_vs.sync_group
            ]

        phys_center = source_viewer.get_center_physical_coord()
        if phys_center is None:
            return

        target_ppm = source_viewer.get_pixels_per_mm()

        for viewer in self.viewers.values():
            if viewer.image_id in target_ids and viewer != source_viewer:
                viewer.set_pixels_per_mm(target_ppm)
                viewer.center_on_physical_coord(phys_center)

    def propagate_overlay_mode(self, source_vs_id):
        source_vs = self.view_states[source_vs_id]
        target_group = source_vs.sync_group

        if target_group != 0:
            for vs in self.view_states.values():
                if vs.sync_group == target_group:
                    vs.overlay_mode = source_vs.overlay_mode
                    vs.overlay_checkerboard_size = source_vs.overlay_checkerboard_size
                    vs.overlay_checkerboard_swap = source_vs.overlay_checkerboard_swap
                    vs.is_data_dirty = True
        else:
            source_vs.is_data_dirty = True

        for viewer in self.viewers.values():
            if viewer.view_state and (
                viewer.image_id == source_vs_id
                or viewer.view_state.sync_group == target_group
            ):
                viewer.update_render()
