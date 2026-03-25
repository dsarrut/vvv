import numpy as np
import SimpleITK as sitk
from vvv.config import WL_PRESETS
from vvv.math.geometry import SpatialEngine
from vvv.utils import ViewMode, slice_to_voxel


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

        if "crosshair_voxel" in d:
            self.crosshair_voxel = d["crosshair_voxel"]
        if "crosshair_phys_coord" in d and d["crosshair_phys_coord"] is not None:
            self.crosshair_phys_coord = np.array(d["crosshair_phys_coord"])


class DisplayState:
    """Stores all radiometric and rendering properties."""

    def __init__(self):
        self.ww = 2000.0
        self.wl = 270.0
        self.colormap = "Grayscale"
        self.base_threshold = -1e8
        self.interpolation_linear = False

        self.overlay_id = None
        self.overlay_data = None
        self.overlay_opacity = 0.5
        self.overlay_mode = "Alpha"
        self.overlay_threshold = -1
        self.overlay_checkerboard_size = 20.0
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

        self.camera = CameraState(volume)
        self.display = DisplayState()
        self.rois = {}

        self.crosshair_value = None
        self.space = SpatialEngine(volume)
        self.base_display_data = None

        self.hist_data_x = None
        self.hist_data_y = None
        self.histogram_is_dirty = True
        self.use_log_y = True

        self.init_crosshair_to_slices()
        self.init_default_window_level()

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
