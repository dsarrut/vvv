import SimpleITK as sitk
import numpy as np
import os
from pathlib import Path
import copy
import json
from vvv.utils import ViewMode, slice_to_voxel

DEFAULT_SETTINGS = {
    "colors": {
        "crosshair": [0, 246, 7, 180],
        "tracker_text": [0, 246, 7, 255],
        "x": [255, 80, 80, 230],
        "y": [80, 255, 80, 230],
        "z": [80, 80, 255, 230],
        "grid": [255, 255, 255, 40],
        "viewer": [10, 246, 7, 60],
    },
    "physics": {"auto_window_fov": 0.20, "voxel_strip_threshold": 1500},
    "shortcuts": {
        "open_file": "O",
        "next_image": "N",
        "auto_window": "W",
        "auto_window_overlay": "X",
        "scroll_up": "Up",
        "scroll_down": "Down",
        "fast_scroll_up": 517,  # page up
        "fast_scroll_down": 518,  # page down
        "zoom_in": "I",
        "zoom_out": "O",
        "reset_view": "R",
        "center_view": "C",
        "view_axial": "F1",
        "view_sagittal": "F2",
        "view_coronal": "F3",
        "view_histogram": "F4",
        "toggle_interp": "L",
        "toggle_grid": "G",
        "hide_all": "H",
    },
    "interaction": {
        "zoom_speed": 1.1,
        "fast_scroll_steps": 10,
        "wl_drag_sensitivity": 2.0,
    },
    "layout": {"window_width": 1200, "window_height": 1000, "side_panel_width": 300},
}


WL_PRESETS = {
    "Optimal": None,
    "Min/Max": None,
    "Binary Mask": {"ww": 1.0, "wl": 0.5},
    "CT: Soft Tissue": {"ww": 400.0, "wl": 50.0},
    "CT: Bone": {"ww": 2000.0, "wl": 400.0},
    "CT: Lung": {"ww": 1500.0, "wl": -600.0},
    "CT: Brain": {"ww": 80.0, "wl": 40.0},
}


def generate_colormaps():
    """Generates standard mathematical LUTs (Look-Up Tables) to avoid heavy dependencies."""
    cmaps = {}
    x = np.linspace(0, 1, 256)
    ones = np.ones(256)

    # 1. Grayscale
    cmaps["Grayscale"] = np.column_stack([x, x, x, ones]).astype(np.float32)

    # 2. Hot (Black -> Red -> Yellow -> White)
    r = np.clip(3 * x, 0, 1)
    g = np.clip(3 * x - 1, 0, 1)
    b = np.clip(3 * x - 2, 0, 1)
    cmaps["Hot"] = np.column_stack([r, g, b, ones]).astype(np.float32)

    # 3. Cold (Black -> Blue -> Cyan -> White)
    cmaps["Cold"] = np.column_stack([b, g, r, ones]).astype(np.float32)

    # 4. Jet / Rainbow
    r = np.clip(1.5 - np.abs(4 * x - 3), 0, 1)
    g = np.clip(1.5 - np.abs(4 * x - 2), 0, 1)
    b = np.clip(1.5 - np.abs(4 * x - 1), 0, 1)
    cmaps["Jet"] = np.column_stack([r, g, b, ones]).astype(np.float32)

    # 5. Dosimetry (Blue -> Green -> Red wash)
    r = np.clip(4 * x - 1.5, 0, 1)
    g = np.clip(2 - np.abs(4 * x - 2), 0, 1)
    b = np.clip(2.5 - 4 * x, 0, 1)
    cmaps["Dosimetry"] = np.column_stack([r, g, b, ones]).astype(np.float32)

    # 6. Segmentation (Random high-contrast colors, Black background)
    np.random.seed(42)  # Fixed seed so colors stay consistent between sessions
    seg_r = np.random.rand(256)
    seg_g = np.random.rand(256)
    seg_b = np.random.rand(256)
    seg_r[0], seg_g[0], seg_b[0] = 0, 0, 0  # 0 is always transparent black
    cmaps["Segmentation"] = np.column_stack([seg_r, seg_g, seg_b, ones]).astype(
        np.float32
    )

    return cmaps


COLORMAPS = generate_colormaps()


class SettingsManager:
    def __init__(self):
        # Platform-specific path
        if os.name == "nt":
            self.config_dir = Path(os.getenv("APPDATA")) / "VVV"
        else:
            self.config_dir = Path.home() / ".config" / "vvv"

        self.config_path = self.config_dir / ".vv_settings"
        self.data = copy.deepcopy(DEFAULT_SETTINGS)
        self.load()

    def _deep_update(self, default_dict, user_dict):
        """Recursively merges user settings into defaults, preserving new keys."""
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
                    # 1. Load the JSON from the file into the variable
                    user_settings = json.load(f)

                    # 2. Recursively merge it into the default data
                    self._deep_update(self.data, user_settings)
            except Exception as e:
                print(f"Error loading settings: {e}")

    def reset(self):
        """Restores the data dictionary to default values."""
        self.data = copy.deepcopy(DEFAULT_SETTINGS)

    def save(self):
        self.config_dir.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, "w") as f:
            json.dump(self.data, f, indent=4)
        return str(self.config_path)  # Return the path for the UI hint


class ViewState:
    """Stores all transient UI and camera parameters."""

    def __init__(self, volume):
        self.volume = volume  # Immutable physical data
        self.is_data_dirty = True

        self.ww = 2000.0
        self.wl = 270.0

        self.zoom = {ViewMode.AXIAL: 1.0, ViewMode.SAGITTAL: 1.0, ViewMode.CORONAL: 1.0}
        self.pan = {
            ViewMode.AXIAL: [0, 0],
            ViewMode.SAGITTAL: [0, 0],
            ViewMode.CORONAL: [0, 0],
        }

        self.slices = {
            ViewMode.AXIAL: self.volume.data.shape[0] // 2,
            ViewMode.SAGITTAL: self.volume.data.shape[1] // 2,
            ViewMode.CORONAL: self.volume.data.shape[2] // 2,
        }

        self.crosshair_phys_coord = None
        self.crosshair_voxel = None
        self.crosshair_value = None

        self.interpolation_linear = False
        self.grid_mode = False
        self.show_axis = True
        self.show_tracker = True
        self.show_crosshair = True
        self.show_scalebar = False
        self.colormap = "Grayscale"

        # Overlay / Fusion Data
        self.overlay_id = None
        self.overlay_data = None
        self.overlay_opacity = 0.5
        self.overlay_mode = "Alpha"
        self.overlay_threshold = -1

        # Histogram
        self.hist_data_x = []
        self.hist_data_y = []
        self.bin_width = 10.0
        self.use_log_y = False
        self.histogram_is_dirty = True

        # Syncing
        self.sync_group = 0

        self.init_crosshair_to_slices()
        self.init_default_window_level()

    def get_slice_shape(self, orientation):
        """Returns the 2D shape (h, w) of the current slice without extracting pixel data."""
        data = self.volume.data
        if orientation == ViewMode.AXIAL:
            return data.shape[1], data.shape[2]
        elif orientation == ViewMode.SAGITTAL:
            return data.shape[0], data.shape[1]
        elif orientation == ViewMode.CORONAL:
            return data.shape[0], data.shape[2]
        return 1, 1

    def init_crosshair_to_slices(self):
        self.crosshair_voxel = [
            self.slices[ViewMode.CORONAL],
            self.slices[ViewMode.SAGITTAL],
            self.slices[ViewMode.AXIAL],
        ]
        self.crosshair_phys_coord = self.volume.voxel_coord_to_physic_coord(
            self.crosshair_voxel
        )
        ix, iy, iz = self.crosshair_voxel
        self.crosshair_value = self.volume.data[iz, iy, ix]

    def update_crosshair_from_slice_scroll(self, new_slice_idx, orientation):
        vx, vy, vz = self.crosshair_voxel
        if orientation == ViewMode.AXIAL:
            vz = new_slice_idx
        elif orientation == ViewMode.SAGITTAL:
            vx = new_slice_idx
        elif orientation == ViewMode.CORONAL:
            vy = new_slice_idx

        new_v = [vx, vy, vz]
        self.crosshair_voxel = new_v
        self.crosshair_phys_coord = self.volume.voxel_coord_to_physic_coord(
            np.array(new_v)
        )
        ix, iy, iz = [
            int(np.clip(c + 1e-5, 0, limit - 1))
            for c, limit in zip(
                new_v,
                [
                    self.volume.data.shape[2],
                    self.volume.data.shape[1],
                    self.volume.data.shape[0],
                ],
            )
        ]
        self.crosshair_value = self.volume.data[iz, iy, ix]

    def update_crosshair_from_2d(self, slice_x, slice_y, slice_idx, orientation):
        shape = self.get_slice_shape(orientation)

        v = slice_to_voxel(slice_x, slice_y, slice_idx, orientation, shape)
        self.crosshair_voxel = list(v)
        self.crosshair_phys_coord = self.volume.voxel_coord_to_physic_coord(np.array(v))

        ix, iy, iz = [
            int(np.clip(c + 1e-5, 0, limit - 1))
            for c, limit in zip(
                v,
                [
                    self.volume.data.shape[2],
                    self.volume.data.shape[1],
                    self.volume.data.shape[0],
                ],
            )
        ]
        self.crosshair_value = self.volume.data[iz, iy, ix]

    def reset_view(self):
        self.zoom = {ViewMode.AXIAL: 1.0, ViewMode.SAGITTAL: 1.0, ViewMode.CORONAL: 1.0}
        self.pan = {
            ViewMode.AXIAL: [0, 0],
            ViewMode.SAGITTAL: [0, 0],
            ViewMode.CORONAL: [0, 0],
        }
        self.slices = {
            ViewMode.AXIAL: self.volume.data.shape[0] // 2,
            ViewMode.SAGITTAL: self.volume.data.shape[1] // 2,
            ViewMode.CORONAL: self.volume.data.shape[2] // 2,
        }
        self.init_crosshair_to_slices()
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
            # Cast to float to prevent int16 overflow on medical images!
            min_v = float(np.min(self.volume.data))
            max_v = float(np.max(self.volume.data))
            self.ww = max(1e-5, max_v - min_v)
            self.wl = (max_v + min_v) / 2
        elif preset_name in WL_PRESETS and WL_PRESETS[preset_name] is not None:
            self.ww = WL_PRESETS[preset_name]["ww"]
            self.wl = WL_PRESETS[preset_name]["wl"]

    def update_histogram(self):
        flat_data = self.volume.data.flatten()
        min_v, max_v = np.min(flat_data), np.max(flat_data)
        bins = np.arange(min_v, max_v + self.bin_width, self.bin_width)
        hist, bin_edges = np.histogram(flat_data, bins=bins)
        self.hist_data_y = hist.astype(np.float32)
        self.hist_data_x = bin_edges[:-1].astype(np.float32)
        self.histogram_is_dirty = False

    def set_overlay(self, other_vs_id, other_vol):
        """
        Resamples a secondary VolumeData onto this ViewState's exact physical grid using SimpleITK.
        """
        if other_vs_id is None or other_vol is None:
            self.overlay_id = None
            self.overlay_data = None
            self.is_data_dirty = True
            return

        self.overlay_id = other_vs_id

        # Fast path: If the physical grids are exactly identical, just copy the numpy array reference
        if (
            np.array_equal(self.volume.spacing, other_vol.spacing)
            and np.array_equal(self.volume.origin, other_vol.origin)
            and self.volume.sitk_image.GetSize() == other_vol.sitk_image.GetSize()
        ):
            self.overlay_data = other_vol.data
            self.is_data_dirty = True
            return

        # Slow path: Resample the moving image onto the fixed image's physical grid
        # Use linear for smooth medical overlays?
        resampler = sitk.ResampleImageFilter()
        resampler.SetReferenceImage(self.volume.sitk_image)
        # resampler.SetInterpolator(sitk.sitkLinear)
        # keep NN resampling NN to avoid interpolated pixel intensities
        resampler.SetInterpolator(sitk.sitkNearestNeighbor)
        resampler.SetDefaultPixelValue(0)  # Warning, wrong for CT # how to deal ?

        # Execute resampling (need a *copy* not GetArrayViewFromImage)
        resampled_img = resampler.Execute(other_vol.sitk_image)
        self.overlay_data = sitk.GetArrayFromImage(resampled_img)
        self.is_data_dirty = True

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

    def set_ct_window_level(self, flat_data):
        p5, p95 = np.percentile(flat_data, [5, 95])
        data_range = p95 - p5
        image_shape = self.volume.data.shape

        if len(image_shape) == 3 and image_shape[0] > 300:
            preset = {"ww": 600, "wl": 0}  # Special internal fallback for whole body
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

    def get_raw_slice(self, slice_idx, orientation=ViewMode.AXIAL):
        return SliceRenderer.get_raw_slice(
            self.volume.data,
            getattr(self.volume, "is_rgb", False),
            slice_idx,
            orientation,
        )

    def get_slice_rgba(self, slice_idx, orientation=ViewMode.AXIAL):
        return SliceRenderer.get_slice_rgba(
            self.volume.data,
            getattr(self.volume, "is_rgb", False),
            self.volume.num_components,
            self.ww,
            self.wl,
            self.colormap,
            slice_idx,
            orientation,
        )


class VolumeData:
    """Stores the immutable medical image data and physical metadata."""

    def __init__(self, path):
        self.path = path
        self.name = os.path.basename(path)

        # Physical data
        self.sitk_image = self.read_image_from_disk(path)
        self.data = sitk.GetArrayViewFromImage(self.sitk_image)

        # Metadata
        self.pixel_type = None
        self.bytes_per_component = None
        self.num_components = None
        self.matrix = None
        self.spacing = None
        self.origin = None
        self.memory_mb = None
        self.read_image_metadata()
        self.is_rgb = self.num_components in [3, 4]

    def read_image_from_disk(self, path):
        sitk_img = sitk.ReadImage(path)
        dim = sitk_img.GetDimension()

        if dim == 2:
            sitk_img = sitk.JoinSeries([sitk_img])
        elif dim == 4:
            print(f"4D not supported yet: {path}")
            pass

        return sitk_img

    def read_image_metadata(self):
        self.pixel_type = self.sitk_image.GetPixelIDTypeAsString()
        self.bytes_per_component = self.sitk_image.GetSizeOfPixelComponent()
        self.num_components = self.sitk_image.GetNumberOfComponentsPerPixel()
        self.matrix = self.sitk_image.GetDirection()
        self.spacing = np.array(self.sitk_image.GetSpacing())
        self.origin = np.array(self.sitk_image.GetOrigin())
        bytes_per_pixel = self.bytes_per_component * self.num_components
        self.memory_mb = (
            self.sitk_image.GetNumberOfPixels() * bytes_per_pixel / (1024 * 1024)
        )

    def get_physical_aspect_ratio(self, orientation):
        dx, dy, dz = self.spacing
        if orientation == ViewMode.AXIAL:
            return dx, dy
        elif orientation == ViewMode.SAGITTAL:
            return dy, dz
        else:
            return dx, dz

    def voxel_coord_to_physic_coord(self, voxel):
        return (voxel * self.spacing) + self.origin - self.spacing / 2

    def reload(self):
        """Re-reads data from the disk while preserving state if dimensions match."""
        new_sitk = self.read_image_from_disk(self.path)
        new_shape = new_sitk.GetSize()
        current_shape = self.sitk_image.GetSize()

        if new_shape == current_shape:
            # DIMENSIONS MATCH: Soft update
            self.sitk_image = new_sitk
            self.data = sitk.GetArrayViewFromImage(self.sitk_image)
            self.read_image_metadata()
            return False
        else:
            # DIMENSIONS CHANGED: Full reset
            self.__init__(self.path)
            return True


class Controller:
    """The central manager."""

    def __init__(self):
        self.gui = None

        # Completely Decoupled Contexts
        self.volumes = {}
        self.view_states = {}

        self.viewers = {}
        self.settings = SettingsManager()

        self._next_image_id = 0

    def get_next_image_id(self, current_id):
        """Returns the ID of the next image in the global list, looping back to the start."""
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

    def load_image(self, path):
        img_id = str(self._next_image_id)
        self._next_image_id += 1

        # Instantiate physical data, then map a view state to it
        vol = VolumeData(path)
        self.volumes[img_id] = vol
        self.view_states[img_id] = ViewState(vol)

        if self.gui:
            self.gui.refresh_image_list_ui()

        return img_id

    def update_all_viewers_of_image(self, vs_id):
        for viewer in self.viewers.values():
            if viewer.image_id == vs_id:
                viewer.draw_crosshair()
                viewer.update_render()

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
            if viewer.image_id:
                viewer.draw_crosshair()

    def unify_ppm_max_NOT_USED(self, target_viewer_tags):
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

    def unify_ppm(self, target_viewer_tags):
        valid_viewers = [
            self.viewers[tag]
            for tag in target_viewer_tags
            if self.viewers[tag].view_state
        ]
        if not valid_viewers:
            return

        min_ppm = 1e9
        for viewer in valid_viewers:
            ppm = viewer.get_pixels_per_mm()
            if ppm < min_ppm:
                min_ppm = ppm

        if min_ppm > 0:
            for viewer in valid_viewers:
                viewer.set_pixels_per_mm(min_ppm)
                viewer.is_geometry_dirty = True

    def reset_settings(self):
        self.settings.reset()
        for viewer in self.viewers.values():
            viewer.update_render()

    def save_settings(self):
        return self.settings.save()

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
                vs.histogram_is_dirty = True
                self.update_all_viewers_of_image(vs_id)

            if self.gui.context_viewer and self.gui.context_viewer.image_id == vs_id:
                self.gui.update_sidebar_info(self.gui.context_viewer)

            if self.gui:
                self.gui.show_status_message(f"Reloaded: {vol.name}")

    def close_image(self, vs_id):
        if vs_id in self.view_states:
            # 1. Unload from any viewer actively displaying it
            for viewer in self.viewers.values():
                if viewer.image_id == vs_id:
                    viewer.drop_image()

            # 2. Detach it from any other image using it as an overlay
            for other_id, other_vs in self.view_states.items():
                if other_vs.overlay_id == vs_id:
                    other_vs.set_overlay(None, None)
                    self.update_all_viewers_of_image(other_id)

            # 3. Delete the data from memory
            name = self.view_states[vs_id].volume.name
            del self.view_states[vs_id]
            del self.volumes[vs_id]

            # 4. Reassign empty viewers
            if self.view_states:
                first_vs_id = next(iter(self.view_states))
                for viewer in self.viewers.values():
                    if viewer.image_id is None:
                        viewer.set_image(first_vs_id)

            # 5. Update UI
            if self.gui:
                self.gui.refresh_image_list_ui()
                if self.gui.context_viewer:
                    # Force the sidebar to refresh so the Fusion dropdown reverts to "None"
                    self.gui.update_sidebar_info(self.gui.context_viewer)
                self.gui.show_status_message(f"Closed: {name}")

    def close_image_OLD(self, vs_id):
        if vs_id in self.view_states:
            for viewer in self.viewers.values():
                if viewer.image_id == vs_id:
                    viewer.drop_image()

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
                self.gui.show_status_message(f"Closed: {name}")

    def on_visibility_toggle(self, sender, value, user_data):
        context_viewer = self.gui.context_viewer
        if not context_viewer or not context_viewer.view_state:
            return

        vs = context_viewer.view_state
        if user_data == "axis":
            vs.show_axis = value
        elif user_data == "grid":
            vs.grid_mode = value
        elif user_data == "tracker":
            vs.show_tracker = value
        elif user_data == "crosshair":
            vs.show_crosshair = value
        elif user_data == "scalebar":
            vs.show_scalebar = value

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
        """Called every frame by the main loop to orchestrate updates."""
        # 1. Tell every viewer to update if needed
        for viewer in self.viewers.values():
            did_update = viewer.tick()

            # If the currently active viewer updated, tell the GUI to refresh the sidebar
            if did_update and self.gui and viewer == self.gui.context_viewer:
                self.gui.update_sidebar_crosshair(viewer)
                self.gui.update_sidebar_window_level(viewer)

        # 2. Safely reset the global data flags AFTER all viewers have seen them
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
                    target_vs.volume.voxel_coord_to_physic_coord(source_vox)
                )

                target_vs.slices[ViewMode.AXIAL] = int(source_vox[2])
                target_vs.slices[ViewMode.SAGITTAL] = int(source_vox[0])
                target_vs.slices[ViewMode.CORONAL] = int(source_vox[1])
            else:
                phys_pos = source_vs.crosshair_phys_coord
                target_vol = target_vs.volume
                target_vox = (
                    phys_pos - target_vol.origin + target_vol.spacing / 2
                ) / target_vol.spacing
                target_vs.crosshair_voxel = list(target_vox)
                target_vs.crosshair_phys_coord = phys_pos

                # Use identical clipping math to the value extractor so the rendered slice
                # matches the data slice
                target_vs.slices[ViewMode.AXIAL] = int(
                    np.clip(target_vox[2] + 1e-5, 0, target_vol.data.shape[0] - 1)
                )
                target_vs.slices[ViewMode.SAGITTAL] = int(
                    np.clip(target_vox[0] + 1e-5, 0, target_vol.data.shape[2] - 1)
                )
                target_vs.slices[ViewMode.CORONAL] = int(
                    np.clip(target_vox[1] + 1e-5, 0, target_vol.data.shape[1] - 1)
                )

            # Ensure the target ViewState updates its cached intensity value right now!
            ix, iy, iz = [
                int(np.clip(c + 1e-5, 0, limit - 1))
                for c, limit in zip(
                    target_vs.crosshair_voxel,
                    [
                        target_vs.volume.data.shape[2],
                        target_vs.volume.data.shape[1],
                        target_vs.volume.data.shape[0],
                    ],
                )
            ]
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

    def propagate_window_level(self, source_vs_id):
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
                    vs.ww = source_vs.ww
                    vs.wl = source_vs.wl
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


class SliceRenderer:
    """Pure utility to generate renderable RGBA arrays using a streamlined pipeline."""

    @staticmethod
    def extract_slice(data, slice_idx, orientation):
        """Step 1: Universal 3D extraction. The ellipsis (...) handles both Grayscale and RGB natively."""
        if orientation == ViewMode.AXIAL:
            return data[slice_idx, ...]
        elif orientation == ViewMode.SAGITTAL:
            return np.flipud(np.fliplr(data[:, :, slice_idx, ...]))
        elif orientation == ViewMode.CORONAL:
            return np.flipud(data[:, slice_idx, ...])
        return None

    @staticmethod
    def get_raw_slice(data, is_rgb, slice_idx, orientation):
        """Legacy helper for logic that strictly requires a 2D float array (like Auto Window/Level)."""
        if is_rgb:
            return np.zeros((1, 1))
        res = SliceRenderer.extract_slice(data, slice_idx, orientation)
        return res if res is not None else np.zeros((1, 1))

    @staticmethod
    def get_slice_rgba(
        base_data,
        base_is_rgb,
        base_num_components,
        base_ww,
        base_wl,
        base_cmap_name,
        overlay_data,
        overlay_ww,
        overlay_wl,
        overlay_cmap_name,
        overlay_opacity,
        overlay_threshold,
        slice_idx,
        orientation,
    ):
        if orientation == ViewMode.HISTOGRAM:
            return np.array([0, 0, 0, 255], dtype=np.uint8), (1, 1)

        # 1. Determine bounds securely from the BASE image
        if orientation == ViewMode.AXIAL:
            max_s, h, w = base_data.shape[0], base_data.shape[1], base_data.shape[2]
        elif orientation == ViewMode.SAGITTAL:
            max_s, h, w = base_data.shape[2], base_data.shape[0], base_data.shape[1]
        elif orientation == ViewMode.CORONAL:
            max_s, h, w = base_data.shape[1], base_data.shape[0], base_data.shape[2]
        else:
            return np.zeros(4, dtype=np.float32), (1, 1)

        # Handle out-of-bounds slicing securely
        if slice_idx < 0 or slice_idx >= max_s:
            black_slice = np.zeros((h, w, 4), dtype=np.float32)
            black_slice[:, :, 3] = 1.0
            return black_slice.flatten(), (h, w)

        # 2. Extract Base Slice
        base_slice = SliceRenderer.extract_slice(base_data, slice_idx, orientation)

        # 3. Colorize Base Slice
        if base_is_rgb:
            norm_img = np.clip(base_slice.astype(np.float32) / 255.0, 0.0, 1.0)
            if base_num_components == 3:
                alpha = np.ones((*norm_img.shape[:-1], 1), dtype=np.float32)
                base_rgba = np.concatenate([norm_img, alpha], axis=-1)
            else:
                base_rgba = norm_img
        else:
            min_val = base_wl - base_ww / 2
            norm_img = (
                np.zeros_like(base_slice, dtype=np.float32)
                if base_ww <= 0
                else np.clip((base_slice - min_val) / base_ww, 0.0, 1.0)
            )
            lut = COLORMAPS.get(base_cmap_name, COLORMAPS["Grayscale"])
            base_rgba = lut[(norm_img * 255).astype(np.uint8)]

        # 4. Handle Overlay Fusion (If an overlay exists)
        if overlay_data is not None and overlay_opacity > 0.0:
            over_slice = SliceRenderer.extract_slice(
                overlay_data, slice_idx, orientation
            )

            # Normalize overlay
            over_min = overlay_wl - overlay_ww / 2
            over_norm = (
                np.zeros_like(over_slice, dtype=np.float32)
                if overlay_ww <= 0
                else np.clip((over_slice - over_min) / overlay_ww, 0.0, 1.0)
            )

            # Apply overlay LUT
            over_lut = COLORMAPS.get(overlay_cmap_name, COLORMAPS["Hot"])
            over_rgba = over_lut[(over_norm * 255).astype(np.uint8)]

            # Create a dynamic opacity mask to strip out values below the threshold
            op_mask = np.full(over_slice.shape, overlay_opacity, dtype=np.float32)
            op_mask[over_slice < overlay_threshold] = 0.0
            op_mask = op_mask[
                ..., None
            ]  # Broadcast to (H, W, 1) so it multiplies RGBA correctly

            # Alpha Blend: Base * (1 - Op_Mask) + Overlay * Op_Mask
            final_rgba = base_rgba * (1.0 - op_mask) + over_rgba * op_mask
            final_rgba[..., 3] = 1.0
            return final_rgba.flatten(), (h, w)

        # If no overlay, just return the base image
        return base_rgba.flatten(), (h, w)

    @staticmethod
    def get_slice_rgba_OK_colormap(
        data, is_rgb, num_components, ww, wl, cmap_name, slice_idx, orientation
    ):
        if orientation == ViewMode.HISTOGRAM:
            return np.array([0, 0, 0, 255], dtype=np.uint8), (1, 1)

        # Determine bounds securely
        if orientation == ViewMode.AXIAL:
            max_s, h, w = data.shape[0], data.shape[1], data.shape[2]
        elif orientation == ViewMode.SAGITTAL:
            max_s, h, w = data.shape[2], data.shape[0], data.shape[1]
        elif orientation == ViewMode.CORONAL:
            max_s, h, w = data.shape[1], data.shape[0], data.shape[2]
        else:
            return np.zeros(4, dtype=np.float32), (1, 1)

        # Handle out-of-bounds slicing securely
        if slice_idx < 0 or slice_idx >= max_s:
            black_slice = np.zeros((h, w, 4), dtype=np.float32)
            black_slice[:, :, 3] = 1.0
            return black_slice.flatten(), (h, w)

        # Step 1: Extract (One single call handles everything)
        slice_data = SliceRenderer.extract_slice(data, slice_idx, orientation)

        # Step 2 & 3: Normalize and apply LUT (Look-Up Table)
        if is_rgb:
            norm_img = np.clip(slice_data.astype(np.float32) / 255.0, 0.0, 1.0)
            if num_components == 3:
                alpha = np.ones((*norm_img.shape[:-1], 1), dtype=np.float32)
                rgba = np.concatenate([norm_img, alpha], axis=-1)
            else:
                rgba = norm_img
        else:
            min_val = wl - ww / 2
            norm_img = (
                np.zeros_like(slice_data, dtype=np.float32)
                if ww <= 0
                else np.clip((slice_data - min_val) / ww, 0.0, 1.0)
            )

            # Map normalized [0..1] values directly into the Colormap LUT
            lut = COLORMAPS.get(cmap_name, COLORMAPS["Grayscale"])
            indices = (norm_img * 255).astype(np.uint8)
            rgba = lut[indices]

        return rgba.flatten(), (h, w)

    @staticmethod
    def get_slice_rgba_OLD(
        data, is_rgb, num_components, ww, wl, slice_idx, orientation
    ):
        if orientation == ViewMode.HISTOGRAM:
            return np.array([0, 0, 0, 255], dtype=np.uint8), (1, 1)

        # Determine bounds securely
        if orientation == ViewMode.AXIAL:
            max_s, h, w = data.shape[0], data.shape[1], data.shape[2]
        elif orientation == ViewMode.SAGITTAL:
            max_s, h, w = data.shape[2], data.shape[0], data.shape[1]
        elif orientation == ViewMode.CORONAL:
            max_s, h, w = data.shape[1], data.shape[0], data.shape[2]
        else:
            return np.zeros(4, dtype=np.float32), (1, 1)

        # Handle out-of-bounds slicing securely
        if slice_idx < 0 or slice_idx >= max_s:
            black_slice = np.zeros((h, w, 4), dtype=np.float32)
            black_slice[:, :, 3] = 1.0
            return black_slice.flatten(), (h, w)

        # Step 1: Extract (One single call handles everything)
        slice_data = SliceRenderer.extract_slice(data, slice_idx, orientation)

        # Step 2 & 3: Normalize and Colorize
        if is_rgb:
            norm_img = np.clip(slice_data.astype(np.float32) / 255.0, 0.0, 1.0)
            if num_components == 3:
                alpha = np.ones((*norm_img.shape[:-1], 1), dtype=np.float32)
                rgba = np.concatenate([norm_img, alpha], axis=-1)
            else:
                rgba = norm_img
        else:
            min_val = wl - ww / 2
            norm_img = (
                np.zeros_like(slice_data, dtype=np.float32)
                if ww <= 0
                else np.clip((slice_data - min_val) / ww, 0.0, 1.0)
            )
            rgba = np.stack(
                [norm_img, norm_img, norm_img, np.ones_like(norm_img)], axis=-1
            )

        return rgba.flatten(), (h, w)
