import SimpleITK as sitk
import numpy as np
import os
from pathlib import Path
import copy
import json

from vvv.utils import ViewMode, slice_to_voxel

# Re-exporting these so that existing files (like gui.py and viewer.py)
# don't have to change their `from .core import XYZ` statements!
from .config import DEFAULT_SETTINGS, WL_PRESETS, COLORMAPS
from .image import VolumeData, SliceRenderer, RenderLayer


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
        self.time_idx = 0

        # Visibility toggles (these are spatially relevant)
        self.show_axis = True
        self.show_tracker = True
        self.show_crosshair = True
        self.show_scalebar = False
        self.grid_mode = False


class DisplayState:
    """Stores all radiometric and rendering properties."""

    def __init__(self):
        self.ww = 2000.0
        self.wl = 270.0
        self.colormap = "Grayscale"
        self.base_threshold = -1e8
        self.interpolation_linear = False
        self.show_legend = False

        # Overlay parameters
        self.overlay_id = None
        self.overlay_data = None
        self.overlay_opacity = 0.5
        self.overlay_mode = "Alpha"
        self.overlay_threshold = -1
        self.overlay_checkerboard_size = 20.0
        self.overlay_checkerboard_swap = False


class ViewState:
    """Stores all transient UI and camera parameters."""

    def __init__(self, volume):
        self.volume = volume
        self.is_data_dirty = True
        self.sync_group = 0

        # The Split
        self.camera = CameraState(volume)
        self.display = DisplayState()

        # Derived value based on camera coords and display data
        self.crosshair_value = None

        self.init_crosshair_to_slices()
        self.init_default_window_level()

    # ==========================================
    # THE PROPERTY BRIDGE
    # Safely routes top-level requests to the new sub-states
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
    def grid_mode(self):
        return self.camera.grid_mode

    @grid_mode.setter
    def grid_mode(self, v):
        self.camera.grid_mode = v

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
        return self.display.show_legend

    @show_legend.setter
    def show_legend(self, v):
        self.display.show_legend = v

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

    def update_histogram(self):
        flat_data = self.volume.data.flatten()
        min_v, max_v = np.min(flat_data), np.max(flat_data)
        bins = np.arange(min_v, max_v + self.bin_width, self.bin_width)
        hist, bin_edges = np.histogram(flat_data, bins=bins)
        self.hist_data_y = hist.astype(np.float32)
        self.hist_data_x = bin_edges[:-1].astype(np.float32)
        self.histogram_is_dirty = False

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


class Controller:
    """The central manager."""

    def __init__(self):
        self.gui = None
        self.volumes = {}
        self.view_states = {}
        self.viewers = {}
        self.settings = SettingsManager()
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

    def load_image(self, path):
        img_id = str(self._next_image_id)
        self._next_image_id += 1
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
                viewer.is_geometry_dirty = True

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
            vs.grid_mode = value
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
                self.gui.update_sidebar_window_level(viewer)

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
