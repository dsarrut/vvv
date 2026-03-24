import os
import copy
import json
import numpy as np
import SimpleITK as sitk
from pathlib import Path
from vvv.roi_manager import ROIManager
from vvv.geometry import SpatialEngine
from vvv.file_manager import FileManager
from vvv.sync_manager import SyncManager
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
        self.space = SpatialEngine(volume)
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
        self.camera.crosshair_voxel = [
            self.camera.slices[ViewMode.CORONAL],
            self.camera.slices[ViewMode.SAGITTAL],
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
            self.crosshair_value = display_data[self.camera.time_idx, iz, iy, ix]
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

            self.display.ww = p98 - p2
            self.display.wl = (p98 + p2) / 2

            if self.display.ww <= 1e-20:
                self.display.ww = p99 - p1
                if self.display.ww <= 1e-20:
                    self.display.ww = max(abs(p1) * 0.1, 1e-20)
                    self.display.wl = (p99 + p1) / 2

    def update_crosshair_from_slice_scroll(self, new_slice_idx, orientation):
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
            self.crosshair_value = display_data[self.camera.time_idx, iz, iy, ix]
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
            self.crosshair_value = display_data[self.camera.time_idx, iz, iy, ix]
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
        # Cleanly reinitialize the sub-states!
        self.camera = CameraState(self.volume)
        self.display = DisplayState()
        self.init_default_window_level()
        self.is_data_dirty = True

    def apply_wl_preset(self, preset_name):
        if getattr(self.volume, "is_rgb", False) or preset_name == "Custom":
            return
        if "Optimal" in preset_name:
            stride = max(1, self.volume.data.size // 100000)
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
            self.display.overlay_id = None
            self.display.overlay_data = None
            self.is_data_dirty = True
            return

        self.display.overlay_id = other_vs_id
        has_base_transform = self.space.is_active and self.space.transform is not None
        has_overlay_transform = other_transform is not None

        if (
            not has_base_transform
            and not has_overlay_transform
            and np.allclose(self.volume.spacing, other_vol.spacing, atol=1e-4)
            and np.allclose(self.volume.origin, other_vol.origin, atol=1e-4)
            and self.volume.shape3d == other_vol.shape3d
        ):
            self.display.overlay_data = other_vol.data
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

        if has_base_transform or has_overlay_transform:
            comp = sitk.CompositeTransform(3)
            if has_base_transform:
                comp.AddTransform(self.space.transform)
            if has_overlay_transform:
                comp.AddTransform(other_transform.GetInverse())
            resampler.SetTransform(comp)

        target_dim = other_vol.sitk_image.GetDimension()
        if target_dim == 3:
            resampled_img = resampler.Execute(other_vol.sitk_image)
            self.display.overlay_data = sitk.GetArrayFromImage(resampled_img)
        elif target_dim == 4:
            resampled_volumes = []
            for t in range(other_vol.num_timepoints):
                size = list(other_vol.sitk_image.GetSize())
                size[3] = 0
                index = [0, 0, 0, t]
                vol_3d = sitk.Extract(other_vol.sitk_image, size, index)
                resampled_volumes.append(resampler.Execute(vol_3d))
            self.display.overlay_data = sitk.GetArrayFromImage(
                sitk.JoinSeries(resampled_volumes)
            )
        else:
            self.display.overlay_data = other_vol.data

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

        self.display.ww = preset["ww"]
        self.display.wl = preset["wl"]


class Controller:
    """The central manager."""

    def __init__(self):
        self.gui = None
        self.volumes = {}
        self.view_states = {}
        self.viewers = {}
        self.file = FileManager(self)
        self.sync = SyncManager(self)
        self.roi = ROIManager(self)
        self.settings = SettingsManager()
        self.history = HistoryManager()

        self.use_history = True
        self.next_image_id = 0

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
            self.sync.propagate_ppm(group_viewer_tags)
            master_viewer = self.viewers[group_viewer_tags[0]]
            phys_center = master_viewer.get_center_physical_coord()
            if phys_center is not None:
                for tag in group_viewer_tags:
                    self.viewers[tag].center_on_physical_coord(phys_center)

        self.sync.propagate_sync(first_vs_id)
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
            new_transform.SetCenter(vs.space.cor.tolist())

        vs.space.transform = new_transform
        vs.space.transform_file = os.path.basename(filepath)
        return True

    def save_transform(self, vs_id, filepath):
        vs = self.view_states.get(vs_id)
        if vs and vs.space.transform:
            sitk.WriteTransform(vs.space.transform, filepath)
            vs.space.transform_file = os.path.basename(filepath)

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

        t_idx = int(voxel_coord[3]) if len(voxel_coord) > 3 else vs.camera.time_idx

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
        if vs.display.overlay_id and vs.display.overlay_id in self.volumes:
            ov_vol = self.volumes[vs.display.overlay_id]
            ov_vs = self.view_states[vs.display.overlay_id]

            is_buf = vs.base_display_data is not None
            world_phys = vs.space.display_to_world(
                np.array([ix, iy, iz]), is_buffered=is_buf
            )

            is_ov_buf = ov_vs.base_display_data is not None
            ov_vox = ov_vs.space.world_to_display(world_phys, is_buffered=is_ov_buf)

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
        vs = self.view_states.get(vs_id)
        if not vs:
            return
        import math

        vs.space.set_manual_transform(
            tx, ty, tz, math.radians(rx_deg), math.radians(ry_deg), math.radians(rz_deg)
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
            self.sync.propagate_ppm(same_viewers)

        # Force all linked viewers to perfectly re-center
        for tag in same_viewers:
            viewer = self.viewers[tag]
            if hasattr(viewer, "needs_recenter"):
                viewer.needs_recenter = True
            viewer.is_geometry_dirty = True

        if self.gui:
            self.gui.update_sidebar_info(self.gui.context_viewer)

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
                        vs.camera.crosshair_voxel[:3],
                        [vol.shape3d[2], vol.shape3d[1], vol.shape3d[0]],
                    )
                ]

                if vol.num_timepoints > 1:
                    vs.crosshair_value = vol.data[vs.camera.time_idx, iz, iy, ix]
                else:
                    vs.crosshair_value = vol.data[iz, iy, ix]

                vs.histogram_is_dirty = True
                vs.is_data_dirty = True
                self.update_all_viewers_of_image(vs_id)

            for other_id, other_vs in self.view_states.items():
                if other_vs.display.overlay_id == vs_id:
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
