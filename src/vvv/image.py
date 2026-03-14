import SimpleITK as sitk
import numpy as np
import os
import glob
import shlex
from vvv.utils import ViewMode
from .config import COLORMAPS


class SliceRenderer:
    """Pure utility to generate renderable RGBA arrays using a streamlined pipeline."""

    @staticmethod
    def extract_slice(data, is_rgb, time_idx, slice_idx, orientation):
        if is_rgb:
            if data.ndim == 4:
                data = data[np.newaxis, ...]
        else:
            if data.ndim == 3:
                data = data[np.newaxis, ...]

        t = min(time_idx, data.shape[0] - 1)

        if orientation == ViewMode.AXIAL:
            return data[t, slice_idx, ...]
        elif orientation == ViewMode.SAGITTAL:
            return np.flipud(np.fliplr(data[t, :, :, slice_idx, ...]))
        elif orientation == ViewMode.CORONAL:
            return np.flipud(data[t, :, slice_idx, ...])
        return None

    @staticmethod
    def get_raw_slice(data, is_rgb, time_idx, slice_idx, orientation):
        if is_rgb:
            return np.zeros((1, 1))
        res = SliceRenderer.extract_slice(
            data, is_rgb, time_idx, slice_idx, orientation
        )
        return res if res is not None else np.zeros((1, 1))

    @staticmethod
    def normalize_wl(slice_data, ww, wl):
        if ww <= 0:
            return np.zeros_like(slice_data, dtype=np.float32)
        min_val = wl - ww / 2.0
        return np.clip((slice_data - min_val) / ww, 0.0, 1.0)

    @staticmethod
    def get_slice_rgba(
        base_data,
        base_is_rgb,
        base_num_components,
        base_ww,
        base_wl,
        base_cmap_name,
        base_threshold,
        base_time_idx,
        overlay_data,
        overlay_is_rgb,
        overlay_ww,
        overlay_wl,
        overlay_cmap_name,
        overlay_opacity,
        overlay_threshold,
        overlay_mode,
        overlay_time_idx,
        slice_idx,
        orientation,
    ):
        if orientation == ViewMode.HISTOGRAM:
            return np.array([0, 0, 0, 255], dtype=np.uint8), (1, 1)

        if base_is_rgb:
            if base_data.ndim == 4:
                base_data = base_data[np.newaxis, ...]
        else:
            if base_data.ndim == 3:
                base_data = base_data[np.newaxis, ...]

        axis_map = {
            ViewMode.AXIAL: (1, 2, 3),
            ViewMode.SAGITTAL: (3, 1, 2),
            ViewMode.CORONAL: (2, 1, 3),
        }

        if orientation not in axis_map:
            return np.zeros(4, dtype=np.float32), (1, 1)

        s_ax, h_ax, w_ax = axis_map[orientation]
        max_s, h, w = (
            base_data.shape[s_ax],
            base_data.shape[h_ax],
            base_data.shape[w_ax],
        )

        if slice_idx < 0 or slice_idx >= max_s:
            black_slice = np.zeros((h, w, 4), dtype=np.float32)
            black_slice[:, :, 3] = 1.0
            return black_slice.flatten(), (h, w)

        base_slice = SliceRenderer.extract_slice(
            base_data, base_is_rgb, base_time_idx, slice_idx, orientation
        )

        if base_is_rgb:
            base_norm = np.clip(base_slice.astype(np.float32) / 255.0, 0.0, 1.0)
            if base_num_components == 3:
                alpha = np.ones((*base_norm.shape[:-1], 1), dtype=np.float32)
                base_rgba = np.concatenate([base_norm, alpha], axis=-1)
            else:
                base_rgba = base_norm
        else:
            base_norm = SliceRenderer.normalize_wl(base_slice, base_ww, base_wl)
            lut = COLORMAPS.get(base_cmap_name, COLORMAPS["Grayscale"])
            base_rgba = lut[(base_norm * 255).astype(np.uint8)]

            if base_threshold > -1e8:
                mask = base_slice <= base_threshold
                base_rgba[mask] = [0.0, 0.0, 0.0, 0.0]

        if overlay_data is None or overlay_opacity <= 0.0:
            return base_rgba.flatten(), (h, w)

        if overlay_is_rgb:
            if overlay_data.ndim == 4:
                overlay_data = overlay_data[np.newaxis, ...]
        else:
            if overlay_data.ndim == 3:
                overlay_data = overlay_data[np.newaxis, ...]

        over_slice = SliceRenderer.extract_slice(
            overlay_data, overlay_is_rgb, overlay_time_idx, slice_idx, orientation
        )
        over_norm = SliceRenderer.normalize_wl(over_slice, overlay_ww, overlay_wl)

        if overlay_mode == "Registration":
            base_reg = (
                np.mean(base_norm[..., :3], axis=-1) if base_is_rgb else base_norm
            )
            over_reg = (
                np.mean(over_norm[..., :3], axis=-1) if overlay_is_rgb else over_norm
            )

            W = np.full(over_slice.shape, overlay_opacity, dtype=np.float32)
            W[over_slice < overlay_threshold] = 0.0

            res_rgba = np.zeros((*base_reg.shape, 4), dtype=np.float32)

            m1 = W <= 0.5
            W2 = W * 2.0

            res_rgba[..., 0] = np.where(
                m1, base_reg, base_reg * (2.0 - W2) + over_reg * (W2 - 1.0)
            )
            res_rgba[..., 1] = np.where(
                m1, base_reg * (1.0 - W2) + over_reg * W2, over_reg
            )
            res_rgba[..., 2] = res_rgba[..., 0]
            res_rgba[..., 3] = 1.0

            if base_threshold > -1e8 and not base_is_rgb:
                mask = base_slice <= base_threshold
                res_rgba[mask] = [0.0, 0.0, 0.0, 0.0]

        elif overlay_mode == "Alpha":
            over_lut = COLORMAPS.get(overlay_cmap_name, COLORMAPS["Hot"])
            over_rgba = over_lut[(over_norm * 255).astype(np.uint8)]

            op_mask = np.full(over_slice.shape, overlay_opacity, dtype=np.float32)
            op_mask[over_slice < overlay_threshold] = 0.0
            op_mask = op_mask[..., None]

            res_rgba = base_rgba * (1.0 - op_mask) + over_rgba * op_mask

        else:
            res_rgba = base_rgba

        res_rgba[..., 3] = 1.0
        return res_rgba.flatten(), (h, w)


class VolumeData:
    """Stores the immutable medical image data and physical metadata."""

    def __init__(self, path):
        self.path = path
        self.file_paths = []

        is_4d = False
        if isinstance(path, str) and path.startswith("4D:"):
            is_4d = True
            path = path[3:].strip()

        if is_4d:
            if os.path.isdir(path):
                valid_exts = (
                    ".mhd",
                    ".nii",
                    ".nii.gz",
                    ".nrrd",
                    ".dcm",
                    ".hdr",
                    ".img",
                )
                self.file_paths = sorted(
                    [
                        os.path.join(path, f)
                        for f in os.listdir(path)
                        if f.lower().endswith(valid_exts)
                    ]
                )
            elif "*" in path or "?" in path:
                self.file_paths = sorted(glob.glob(path))
            else:
                tokens = shlex.split(path)
                valid_files = [f for f in tokens if os.path.isfile(f)]
                if valid_files:
                    self.file_paths = sorted(valid_files)
                else:
                    self.file_paths = [path]
        else:
            self.file_paths = [path]

        if not self.file_paths:
            raise FileNotFoundError(f"No files found for path: {self.path}")

        self.sitk_image = self.read_image_from_disk(self.file_paths)
        self.data = sitk.GetArrayViewFromImage(self.sitk_image)

        is_4d = self.sitk_image.GetDimension() == 4 and self.data.shape[0] > 1
        self.name = os.path.basename(self.file_paths[0])
        if is_4d and len(self.file_paths) > 1:
            self.name += f" ({len(self.file_paths)})"

        self.pixel_type = None
        self.bytes_per_component = None
        self.num_components = None
        self.matrix = None
        self.spacing = None
        self.origin = None
        self.memory_mb = None

        self.is_rgb = False
        self.num_timepoints = 1
        self.shape3d = (1, 1, 1)

        self.read_image_metadata()

    def read_image_from_disk(self, paths):
        if len(paths) == 1:
            sitk_img = sitk.ReadImage(paths[0])
            dim = sitk_img.GetDimension()

            if dim == 2:
                sitk_img = sitk.JoinSeries([sitk_img])

            return sitk_img
        else:
            imgs = []
            base_size = None
            for p in paths:
                try:
                    img = sitk.ReadImage(p)
                    if base_size is None:
                        base_size = img.GetSize()
                        imgs.append(img)
                    elif img.GetSize() == base_size:
                        imgs.append(img)
                    else:
                        print(
                            f"Warning: Skipping {os.path.basename(p)} - Size {img.GetSize()} mismatches base {base_size}"
                        )
                except Exception as e:
                    print(f"Warning: Failed to read {os.path.basename(p)}")

            if not imgs:
                raise RuntimeError(
                    "No valid images could be read from the provided paths."
                )

            if len(imgs) == 1:
                return imgs[0]

            return sitk.JoinSeries(imgs)

    def read_image_metadata(self):
        self.pixel_type = self.sitk_image.GetPixelIDTypeAsString()
        self.bytes_per_component = self.sitk_image.GetSizeOfPixelComponent()
        self.num_components = self.sitk_image.GetNumberOfComponentsPerPixel()

        raw_matrix = self.sitk_image.GetDirection()
        if len(raw_matrix) == 9:
            self.matrix = np.array(raw_matrix).reshape((3, 3))
        elif len(raw_matrix) == 16:
            m = np.array(raw_matrix)
            self.matrix = np.array(
                [[m[0], m[1], m[2]], [m[4], m[5], m[6]], [m[8], m[9], m[10]]]
            )
        else:
            self.matrix = np.eye(3)

        self.inverse_matrix = np.linalg.inv(self.matrix)

        self.spacing = np.array(self.sitk_image.GetSpacing()[:3])
        self.origin = np.array(self.sitk_image.GetOrigin()[:3])

        self.is_rgb = self.num_components in [3, 4]
        shape = self.data.shape
        self.num_timepoints = 1

        if self.is_rgb:
            if len(shape) == 5:
                self.num_timepoints = shape[0]
                self.shape3d = shape[1:4]
            else:
                self.shape3d = shape[0:3]
        else:
            if len(shape) == 4:
                self.num_timepoints = shape[0]
                self.shape3d = shape[1:4]
            else:
                self.shape3d = shape[0:3]

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
        return self.origin + self.matrix @ (voxel * self.spacing)

    def physic_coord_to_voxel_coord(self, phys):
        return (self.inverse_matrix @ (phys - self.origin)) / self.spacing

    def reload(self):
        new_sitk = self.read_image_from_disk(self.file_paths)
        new_shape = new_sitk.GetSize()
        current_shape = self.sitk_image.GetSize()

        if new_shape == current_shape:
            self.sitk_image = new_sitk
            self.data = sitk.GetArrayViewFromImage(self.sitk_image)
            self.read_image_metadata()
            return False
        else:
            self.__init__(self.path)
            return True
