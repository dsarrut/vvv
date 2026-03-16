import SimpleITK as sitk
import numpy as np
import os
from pathlib import Path
import copy
import json
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

        self.data[key] = {
            "shape3d": list(vol.shape3d),
            "spacing": list(vol.spacing),
            "origin": list(vol.origin),  # ADDED: Physical origin
            "camera": vs.camera.to_dict(),
            "display": vs.display.to_dict(),
            "overlay_path": overlay_path,
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
        self.time_idx = 0  # for 4D images

        # Visibility toggles (these are spatially relevant)
        self.show_axis = True
        self.show_tracker = True
        self.show_crosshair = True
        self.show_scalebar = False
        self.show_grid = False
        self.show_legend = False

    def to_dict(self):
        return {
            # Use k.name to securely save "AXIAL", "SAGITTAL", etc.
            "zoom": {k.name: v for k, v in self.zoom.items()},
            "pan": {k.name: v for k, v in self.pan.items()},
            "slices": {k.name: v for k, v in self.slices.items()},
            "time_idx": self.time_idx,
            "show_axis": self.show_axis,
            "show_tracker": self.show_tracker,
            "show_crosshair": self.show_crosshair,
            "show_scalebar": self.show_scalebar,
            "show_grid": self.show_grid,
            "show_legend": self.show_legend,
            "crosshair_voxel": self.crosshair_voxel,
            "crosshair_phys_coord": (
                list(self.crosshair_phys_coord)
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
        # voxels with value below this threshold are not display (black)
        self.base_threshold = -1e8
        # FIXME : not really linear interpolation : draw squares pixels on large zoom
        self.interpolation_linear = False

        # Overlay parameters
        self.overlay_id = None
        self.overlay_data = None
        self.overlay_opacity = 0.5
        self.overlay_mode = "Alpha"  # Alpha, Registration, Checkboard, ...
        self.overlay_threshold = -1  # Not displayed if below this value
        self.overlay_checkerboard_size = 20.0  # in mm
        self.overlay_checkerboard_swap = False

    def to_dict(self):
        return {
            "ww": self.ww,
            "wl": self.wl,
            "colormap": self.colormap,
            "base_threshold": self.base_threshold,
            "interpolation_linear": self.interpolation_linear,
            "overlay_opacity": self.overlay_opacity,
            "overlay_mode": self.overlay_mode,
            "overlay_threshold": self.overlay_threshold,
            "overlay_checkerboard_size": self.overlay_checkerboard_size,
            "overlay_checkerboard_swap": self.overlay_checkerboard_swap,
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

        self.init_crosshair_to_slices()
        self.init_default_window_level()

    # ==========================================
    # THE PROPERTY BRIDGE
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
        self.crosshair_phys_coord = self.volume.voxel_coord_to_physic_coord(
            np.array(self.crosshair_voxel[:3])
        )

        v = self.crosshair_voxel
        ix, iy, iz = int(v[0]), int(v[1]), int(v[2])
        if self.volume.num_timepoints > 1:
            self.crosshair_value = self.volume.data[self.time_idx, iz, iy, ix]
        else:
            self.crosshair_value = self.volume.data[iz, iy, ix]

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
            if self.ww <= 0:
                self.ww = p99 - p1
                if self.ww <= 0:
                    self.ww = 1.0
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
        self.crosshair_phys_coord = self.volume.voxel_coord_to_physic_coord(
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
        if self.volume.num_timepoints > 1:
            self.crosshair_value = self.volume.data[self.time_idx, iz, iy, ix]
        else:
            self.crosshair_value = self.volume.data[iz, iy, ix]

    def update_crosshair_from_2d(self, slice_x, slice_y, slice_idx, orientation):
        shape = self.get_slice_shape(orientation)

        v = slice_to_voxel(slice_x, slice_y, slice_idx, orientation, shape)
        self.crosshair_voxel = [v[0], v[1], v[2], self.time_idx]
        self.crosshair_phys_coord = self.volume.voxel_coord_to_physic_coord(
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
        if self.volume.num_timepoints > 1:
            self.crosshair_value = self.volume.data[self.time_idx, iz, iy, ix]
        else:
            self.crosshair_value = self.volume.data[iz, iy, ix]

    def update_histogram(self):
        flat_data = self.volume.data.flatten()
        min_v, max_v = np.min(flat_data), np.max(flat_data)
        bins = np.arange(min_v, max_v + self.bin_width, self.bin_width)
        hist, bin_edges = np.histogram(flat_data, bins=bins)
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
            self.ww = max(1e-5, p98 - p2)
            self.wl = (p98 + p2) / 2
        elif "Min/Max" in preset_name:
            min_v = float(np.min(self.volume.data))
            max_v = float(np.max(self.volume.data))
            self.ww = max(1e-5, max_v - min_v)
            self.wl = (max_v + min_v) / 2
        elif preset_name in WL_PRESETS and WL_PRESETS[preset_name] is not None:
            self.ww = WL_PRESETS[preset_name]["ww"]
            self.wl = WL_PRESETS[preset_name]["wl"]

    def set_overlay(self, other_vs_id, other_vol):
        if other_vs_id is None or other_vol is None:
            self.overlay_id = None
            self.overlay_data = None
            self.is_data_dirty = True
            return

        self.overlay_id = other_vs_id

        if (
            np.allclose(self.volume.spacing, other_vol.spacing, atol=1e-4)
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
        resampler.SetDefaultPixelValue(0)

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
    def __init__(self, volume_id, name, color):
        self.volume_id = volume_id  # ID of the mask VolumeData in the controller
        self.name = name
        self.color = color  # [R, G, B]
        self.opacity = 0.5
        self.visible = True
        self.is_contour = False  # Default to fill for Phase 2

    def to_dict(self):
        return {
            "volume_id": self.volume_id,
            "name": self.name,
            "color": self.color,
            "opacity": self.opacity,
            "visible": self.visible,
            "is_contour": self.is_contour,
        }

    def from_dict(self, d):
        self.name = d.get("name", self.name)
        self.color = d.get("color", self.color)
        self.opacity = d.get("opacity", self.opacity)
        self.visible = d.get("visible", self.visible)
        self.is_contour = d.get("is_contour", self.is_contour)


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
        # ---------------------------

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

        if self.gui:
            self.gui.refresh_image_list_ui()

        return img_id

    def _process_binary_mask(self, base_vol, mask_vol):
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

    def load_binary_mask(self, base_id, filepath, name=None, color=[255, 50, 50]):
        base_vol = self.volumes[base_id]
        mask_vol = VolumeData(filepath)

        self._process_binary_mask(base_vol, mask_vol)

        mask_id = str(self._next_image_id)
        self._next_image_id += 1
        self.volumes[mask_id] = mask_vol

        if name is None:
            name = os.path.basename(filepath)

        roi_state = ROIState(mask_id, name, color)
        self.view_states[base_id].rois[mask_id] = roi_state
        self.view_states[base_id].is_data_dirty = True

        return mask_id

    def reload_roi(self, base_id, roi_id):
        if base_id not in self.view_states or roi_id not in self.volumes:
            return

        mask_vol = self.volumes[roi_id]
        was_reset = mask_vol.reload()

        # Re-apply resampling and autocropping to the fresh data
        base_vol = self.volumes[base_id]
        self._process_binary_mask(base_vol, mask_vol)

        self.view_states[base_id].is_data_dirty = True
        self.update_all_viewers_of_image(base_id)

    def center_on_roi(self, base_id, roi_id):
        if base_id not in self.view_states or roi_id not in self.volumes:
            return

        mask_vol = self.volumes[roi_id]
        if not hasattr(mask_vol, "roi_bbox"):
            return

        z0, z1, y0, y1, x0, x1 = mask_vol.roi_bbox
        if z0 == z1:  # Empty mask
            return

        # Calculate centroid in voxel space (relative to base image)
        cx = (x0 + x1 - 1) / 2.0
        cy = (y0 + y1 - 1) / 2.0
        cz = (z0 + z1 - 1) / 2.0

        vs = self.view_states[base_id]

        # Jump the crosshair precisely to the center of the bounding box
        vs.crosshair_voxel = [cx, cy, cz, vs.time_idx]
        vs.crosshair_phys_coord = mask_vol.voxel_coord_to_physic_coord(
            np.array([cx, cy, cz])
        )

        self.propagate_sync(base_id)

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

    def reset_settings(self):
        self.settings.reset()
        for viewer in self.viewers.values():
            viewer.update_render()
            if viewer.image_id:
                viewer.draw_crosshair()
                viewer.is_geometry_dirty = True

    def reload_settings(self):
        self.settings.reset()
        self.settings.load()
        for viewer in self.viewers.values():
            viewer.update_render()
            if viewer.image_id:
                viewer.draw_crosshair()
                viewer.is_geometry_dirty = True

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

            # Handle 4D magic paths safely
            if vol.path.startswith("4D:"):
                tokens = shlex.split(vol.path[3:].strip())
                rel_paths = [get_relative_path(p, workspace_dir) for p in tokens]
                safe_path = "4D:" + " ".join(f'"{p}"' for p in rel_paths)
            else:
                safe_path = get_relative_path(vol.path, workspace_dir)

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

    def close_image(self, vs_id):
        if vs_id in self.view_states:

            # history
            self.history.save_image_state(self, vs_id)

            for viewer in self.viewers.values():
                if viewer.image_id == vs_id:
                    viewer.drop_image()

            for other_id, other_vs in self.view_states.items():
                if other_vs.overlay_id == vs_id:
                    other_vs.set_overlay(None, None)
                    self.update_all_viewers_of_image(other_id)

            name = self.view_states[vs_id].volume.name
            del self.view_states[vs_id]
            del self.volumes[vs_id]

            if self.view_states:
                first_vs_id = next(iter(self.view_states))
                for viewer in self.viewers.values():
                    if viewer.image_id is None:
                        viewer.set_image(first_vs_id)

            if self.gui:
                self.gui.refresh_image_list_ui()
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

        for target_id in target_ids:
            target_vs = self.view_states[target_id]

            if target_id == source_vs_id:
                source_vox = source_vs.crosshair_voxel
                target_vs.crosshair_voxel = source_vox.copy()
                target_vs.crosshair_phys_coord = (
                    target_vs.volume.voxel_coord_to_physic_coord(source_vox[:3])
                )

                target_vs.slices[ViewMode.AXIAL] = int(source_vox[2])
                target_vs.slices[ViewMode.SAGITTAL] = int(source_vox[0])
                target_vs.slices[ViewMode.CORONAL] = int(source_vox[1])
            else:
                phys_pos = source_vs.crosshair_phys_coord
                target_vol = target_vs.volume

                target_vox = target_vol.physic_coord_to_voxel_coord(phys_pos)

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
