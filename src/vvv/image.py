import SimpleITK as sitk
import numpy as np
import os
import glob
import shlex
from dataclasses import dataclass
from vvv.utils import ViewMode
from .config import COLORMAPS


@dataclass
class RenderLayer:
    """Bundles all necessary rendering parameters for a single image layer."""

    data: np.ndarray
    is_rgb: bool
    num_components: int
    ww: float
    wl: float
    cmap_name: str
    threshold: float
    time_idx: int
    spacing_2d: tuple  # <--- ADDED: Physical pixel dimensions (width_mm, height_mm)


@dataclass
class ROILayer:
    """Bundles a 2D mask slice with its display properties for rendering."""

    data: np.ndarray  # The 2D slice of the mask
    color: list  # [R, G, B] (0-255)
    opacity: float  # 0.0 to 1.0
    is_contour: bool = False  # FIXME Placeholder for Phase 5!
    # position on the screen
    offset_x: int = 0
    offset_y: int = 0


class SliceRenderer:
    """Pure utility to generate renderable RGBA arrays using a streamlined pipeline."""

    @staticmethod
    def _blend_registration(
        base_rgba,
        base_norm,
        over_slice,
        over_norm,
        base_is_rgb,
        over_is_rgb,
        opacity,
        threshold,
        base_threshold,
        base_slice,
    ):
        """Handles grayscale/RGB structural mixing for Registration mode."""
        base_reg = np.mean(base_norm[..., :3], axis=-1) if base_is_rgb else base_norm
        over_reg = np.mean(over_norm[..., :3], axis=-1) if over_is_rgb else over_norm

        W = np.full(over_slice.shape, opacity, dtype=np.float32)
        W[over_slice < threshold] = 0.0

        res_rgba = np.zeros((*base_reg.shape, 4), dtype=np.float32)
        m1 = W <= 0.5
        W2 = W * 2.0

        res_rgba[..., 0] = np.where(
            m1, base_reg, base_reg * (2.0 - W2) + over_reg * (W2 - 1.0)
        )
        res_rgba[..., 1] = np.where(m1, base_reg * (1.0 - W2) + over_reg * W2, over_reg)
        res_rgba[..., 2] = res_rgba[..., 0]
        res_rgba[..., 3] = 1.0

        if base_threshold > -1e8 and not base_is_rgb:
            mask = base_slice <= base_threshold
            res_rgba[mask] = [0.0, 0.0, 0.0, 0.0]

        return res_rgba

    @staticmethod
    def _blend_alpha(base_rgba, over_slice, over_norm, cmap_name, opacity, threshold):
        """Handles standard opacity-based colormap overlays."""
        over_lut = COLORMAPS.get(cmap_name, COLORMAPS["Hot"])
        over_rgba = over_lut[(over_norm * 255).astype(np.uint8)]

        op_mask = np.full(over_slice.shape, opacity, dtype=np.float32)
        op_mask[over_slice < threshold] = 0.0
        op_mask = op_mask[..., None]

        return base_rgba * (1.0 - op_mask) + over_rgba * op_mask

    @staticmethod
    def _blend_checkerboard(
        base_rgba,
        over_rgba,
        over_slice,
        base_slice,
        overlay_threshold,
        base_threshold,
        spacing_2d,
        chk_size,
        swap,
        is_base_rgb,
        is_over_rgb,
    ):
        """Handles spatial grid swapping between base and overlay."""
        h, w = base_rgba.shape[:2]
        grid_y, grid_x = np.ogrid[:h, :w]
        space_w, space_h = spacing_2d

        chk_size = max(0.1, float(chk_size))
        chk_y = ((grid_y * space_h) / chk_size).astype(np.int32)
        chk_x = ((grid_x * space_w) / chk_size).astype(np.int32)

        mask = (chk_y + chk_x) % 2 == 0
        if swap:
            mask = ~mask
        mask_rgba = mask[..., None]

        res_rgba = np.where(mask_rgba, base_rgba, over_rgba)

        if overlay_threshold > -1e8 and not is_over_rgb:
            o_mask = (over_slice < overlay_threshold)[..., None]
            res_rgba = np.where(~mask_rgba & o_mask, base_rgba, res_rgba)

        if base_threshold > -1e8 and not is_base_rgb:
            b_mask = (base_slice <= base_threshold)[..., None]
            res_rgba = np.where(mask_rgba & b_mask, [0.0, 0.0, 0.0, 0.0], res_rgba)

        return res_rgba

    @staticmethod
    def _apply_rois(base_rgba, rois):
        """Rapidly composites binary ROI masks using 2D Bounding Boxes."""
        bh, bw = base_rgba.shape[:2]

        for roi in rois:
            if roi.opacity <= 0.0 or roi.data.size == 0:
                continue

            h, w = roi.data.shape
            x0, y0 = roi.offset_x, roi.offset_y
            x1, y1 = x0 + w, y0 + h

            # Skip if completely out of bounds (safety check)
            if x0 >= bw or y0 >= bh or x1 <= 0 or y1 <= 0:
                continue

            # Calculate intersection bounds
            src_x0, src_y0 = max(0, -x0), max(0, -y0)
            src_x1, src_y1 = min(w, bw - x0), min(h, bh - y0)

            dst_x0, dst_y0 = max(0, x0), max(0, y0)
            dst_x1, dst_y1 = min(bw, x1), min(bh, y1)

            # Crop mask and apply to sub-region of the screen
            roi_data_cropped = roi.data[src_y0:src_y1, src_x0:src_x1]
            mask = roi_data_cropped > 0

            if not np.any(mask):
                continue

            alpha = roi.opacity
            inv_alpha = 1.0 - alpha
            r = roi.color[0] / 255.0
            g = roi.color[1] / 255.0
            b = roi.color[2] / 255.0

            # Only do math on the specific patch where the organ lives!
            base_sub = base_rgba[dst_y0:dst_y1, dst_x0:dst_x1]

            base_sub[mask, 0] = base_sub[mask, 0] * inv_alpha + r * alpha
            base_sub[mask, 1] = base_sub[mask, 1] * inv_alpha + g * alpha
            base_sub[mask, 2] = base_sub[mask, 2] * inv_alpha + b * alpha

        return base_rgba

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
        base: RenderLayer,
        overlay: RenderLayer,  # Can be None if no overlay is active
        overlay_opacity: float,
        overlay_mode: str,
        slice_idx: int,
        orientation: int,
        checkerboard_size: float = 20.0,
        checkerboard_swap: bool = False,
        rois=(),
    ):
        # --- Unpack the base layer safely ---
        base_data, base_is_rgb, base_num_components = (
            base.data,
            base.is_rgb,
            base.num_components,
        )
        base_ww, base_wl, base_cmap_name = base.ww, base.wl, base.cmap_name
        base_threshold, base_time_idx = base.threshold, base.time_idx

        # --- Unpack the overlay layer safely ---
        if overlay is not None and overlay.data is not None:
            overlay_data, overlay_is_rgb = overlay.data, overlay.is_rgb
            overlay_ww, overlay_wl, overlay_cmap_name = (
                overlay.ww,
                overlay.wl,
                overlay.cmap_name,
            )
            overlay_threshold, overlay_time_idx = overlay.threshold, overlay.time_idx
        else:
            overlay_data = None
            overlay_opacity = 0.0  # Force skip

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

        # --- THE FIX: We no longer return early here! ---
        res_rgba = base_rgba

        if overlay_data is not None and overlay_opacity > 0.0:
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
                res_rgba = SliceRenderer._blend_registration(
                    base_rgba,
                    base_norm,
                    over_slice,
                    over_norm,
                    base_is_rgb,
                    overlay_is_rgb,
                    overlay_opacity,
                    overlay_threshold,
                    base_threshold,
                    base_slice,
                )

            elif overlay_mode == "Alpha":
                res_rgba = SliceRenderer._blend_alpha(
                    base_rgba,
                    over_slice,
                    over_norm,
                    overlay_cmap_name,
                    overlay_opacity,
                    overlay_threshold,
                )

            elif overlay_mode == "Checkerboard":
                if overlay_is_rgb:
                    over_rgba = over_norm
                    if over_rgba.shape[-1] == 3:
                        alpha = np.ones((*over_rgba.shape[:-1], 1), dtype=np.float32)
                        over_rgba = np.concatenate([over_rgba, alpha], axis=-1)
                else:
                    over_lut = COLORMAPS.get(overlay_cmap_name, COLORMAPS["Hot"])
                    over_rgba = over_lut[(over_norm * 255).astype(np.uint8)]

                res_rgba = SliceRenderer._blend_checkerboard(
                    base_rgba,
                    over_rgba,
                    over_slice,
                    base_slice,
                    overlay_threshold,
                    base_threshold,
                    base.spacing_2d,
                    checkerboard_size,
                    checkerboard_swap,
                    base_is_rgb,
                    overlay_is_rgb,
                )

        # ROI management
        if rois:
            res_rgba = SliceRenderer._apply_rois(res_rgba, rois)

        # Ensure absolute Float32 strictness before sending to the DPG GPU texture buffer!
        return res_rgba.astype(np.float32).flatten(), (h, w)


class VolumeData:
    """Stores the immutable medical image data and physical metadata."""

    def __init__(self, path):
        self.path = path
        self.file_paths = []

        if isinstance(path, list):
            self.file_paths = path
            # Use the folder name as the volume name
            self.name = os.path.basename(os.path.dirname(self.file_paths[0]))
        else:
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
            # --- Try fast GDCM loading first ---
            reader = sitk.ImageSeriesReader()
            reader.SetFileNames(paths)
            try:
                return reader.Execute()
            except Exception as e:
                # Fallback to the old loop for 4D NIfTI/MHD sequences
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
                                f"Warning: Skipping {os.path.basename(p)} - Size mismatch"
                            )
                    except Exception as inner_e:
                        print(f"Warning: Failed to read {os.path.basename(p)}")

                if not imgs:
                    raise RuntimeError(
                        "No valid images could be read from the provided paths."
                    )

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
