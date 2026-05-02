import os
import glob
import shlex
import time
import numpy as np
import SimpleITK as sitk
from vvv.utils import ViewMode
from vvv.config import COLORMAPS
from dataclasses import dataclass
from vvv.utils import get_history_path_key
from vvv.maths.image_utils import straighten_image, extract_orientation_strings


@dataclass
class RenderLayer:
    """Bundles all necessary rendering parameters for a single image layer."""

    data: np.ndarray
    is_rgb: bool
    num_components: int
    ww: float
    wl: float
    cmap_name: str
    threshold: float | None
    time_idx: int
    spacing_2d: tuple
    # offset: used to move the image when associated matrix is modified
    offset_x: int = 0
    offset_y: int = 0
    offset_slice: int = 0


@dataclass
class ROILayer:
    """Bundles a 2D mask slice with its display properties for rendering."""

    data: np.ndarray  # The 2D slice of the mask
    color: list  # [R, G, B] (0-255)
    opacity: float  # 0.0 to 1.0
    is_contour: bool = False  # Placeholder for Phase 5.
    # Position on the screen
    offset_x: int = 0
    offset_y: int = 0


class SliceRenderer:
    """Pure utility to generate renderable RGBA arrays using a streamlined pipeline."""

    _AXIS_MAP = {
        ViewMode.AXIAL: (1, 2, 3),
        ViewMode.SAGITTAL: (3, 1, 2),
        ViewMode.CORONAL: (2, 1, 3),
    }

    @staticmethod
    def _blend_registration(
        base_rgba,
        base_norm,
        over_rgba,
        over_norm,
        base_is_rgb,
        over_is_rgb,
        opacity,
    ):
        base_reg = np.mean(base_norm[..., :3], axis=-1) if base_is_rgb else base_norm
        over_reg = np.mean(over_norm[..., :3], axis=-1) if over_is_rgb else over_norm

        # Extract threshold mask directly from the pre-computed alpha channel.
        W = over_rgba[..., 3] * opacity
        m1 = W <= 0.5

        # --- IN-PLACE OPTIMIZATION ---
        # Multiply W by 2.0 in-place. W is now equivalent to the old "W2" variable.
        np.multiply(W, 2.0, out=W)

        res_rgba = np.zeros((*base_reg.shape, 4), dtype=np.float32)

        # Red & Green channel math (using W which is now scaled by 2)
        res_rgba[..., 0] = np.where(
            m1, base_reg, base_reg * (2.0 - W) + over_reg * (W - 1.0)
        )
        res_rgba[..., 1] = np.where(m1, base_reg * (1.0 - W) + over_reg * W, over_reg)
        res_rgba[..., 2] = res_rgba[..., 0]
        res_rgba[..., 3] = 1.0

        # Apply base threshold directly (assigning a scalar 0.0 is highly optimized in NumPy)
        if not base_is_rgb:
            mask = base_rgba[..., 3] == 0.0
            res_rgba[mask] = 0.0

        return res_rgba

    @staticmethod
    def _blend_alpha(base_rgba, over_rgba, opacity):
        # Alpha channel of over_rgba already contains 0.0 where thresholded, and 1.0 otherwise.
        op_mask = over_rgba[..., 3:4] * opacity

        # --- THE IN-PLACE OPTIMIZATION ---
        # Instead of: base_rgba = base_rgba * (1.0 - op_mask) + over_rgba * op_mask

        # 1. Scale overlay image down (modifies over_rgba memory directly)
        np.multiply(over_rgba, op_mask, out=over_rgba)

        # 2. Convert op_mask to (1.0 - alpha) IN PLACE to prevent any hidden array allocations
        np.subtract(1.0, op_mask, out=op_mask)

        # 3. Scale base image down (modifies base_rgba memory directly)
        np.multiply(base_rgba, op_mask, out=base_rgba)

        # 4. Add them together (writes final result into base_rgba)
        np.add(base_rgba, over_rgba, out=base_rgba)

        return base_rgba

    @staticmethod
    def _blend_checkerboard(
        base_rgba,
        over_rgba,
        spacing_2d,
        chk_size,
        swap,
        is_base_rgb,
        is_over_rgb,
    ):
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

        # --- IN-PLACE OPTIMIZATION ---
        # 1. Allocate the canvas exactly ONCE (using the overlay as the base)
        res_rgba = np.copy(over_rgba)

        # 2. Paste the base image over it where the checkerboard mask is True
        np.copyto(res_rgba, base_rgba, where=mask_rgba)

        # 3. Apply Thresholds via in-place overwriting
        if not is_over_rgb:
            o_mask = over_rgba[..., 3:4] == 0.0
            np.copyto(res_rgba, base_rgba, where=(~mask_rgba & o_mask))

        if not is_base_rgb:
            # Drop the trailing dimension so the mask is purely 2D (H, W).
            # NumPy will now successfully apply it across all 4 RGBA channels!
            b_mask = base_rgba[..., 3] == 0.0
            res_rgba[mask & b_mask] = 0.0

        return res_rgba

    @staticmethod
    def _shift_2d_array(arr, dx, dy):
        """Rapidly translates a 2D NumPy array by pixel offsets without wrapping."""
        if dx == 0 and dy == 0:
            return arr

        h, w = arr.shape[:2]
        # Fill empty space with the minimum value (usually 0) so it doesn't create artifacts
        res = np.full_like(arr, np.min(arr))

        src_y0, src_y1 = max(0, -dy), min(h, h - dy)
        src_x0, src_x1 = max(0, -dx), min(w, w - dx)
        dst_y0, dst_y1 = max(0, dy), min(h, h + dy)
        dst_x0, dst_x1 = max(0, dx), min(w, w + dx)

        if src_y0 < src_y1 and src_x0 < src_x1:
            res[dst_y0:dst_y1, dst_x0:dst_x1] = arr[src_y0:src_y1, src_x0:src_x1]

        return res

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

            # Only do math on the specific patch where the organ lives.
            base_sub = base_rgba[dst_y0:dst_y1, dst_x0:dst_x1]

            base_sub[mask, 0] = base_sub[mask, 0] * inv_alpha + r * alpha
            base_sub[mask, 1] = base_sub[mask, 1] * inv_alpha + g * alpha
            base_sub[mask, 2] = base_sub[mask, 2] * inv_alpha + b * alpha

        return base_rgba

    @staticmethod
    def extract_slice(data, is_rgb, time_idx, slice_idx, orientation):
        try:
            if is_rgb:
                if data.ndim == 4:
                    data = data[np.newaxis, ...]
            else:
                if data.ndim == 3:
                    data = data[np.newaxis, ...]

            t = min(time_idx, data.shape[0] - 1)

            if orientation == ViewMode.AXIAL:
                return np.ascontiguousarray(data[t, slice_idx, ...])
            elif orientation == ViewMode.SAGITTAL:
                return np.ascontiguousarray(
                    np.flipud(np.fliplr(data[t, :, :, slice_idx, ...]))
                )
            elif orientation == ViewMode.CORONAL:
                return np.ascontiguousarray(np.flipud(data[t, :, slice_idx, ...]))
            return None
        except IndexError:
            return None  # Safe fallback if UI requests a slice out of bounds

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
        norm = slice_data.astype(np.float32)
        norm -= min_val
        norm /= ww

        # Clip and return as [0.0, 1.0] float for math, OR...
        np.clip(norm, 0.0, 1.0, out=norm)
        return norm

    @staticmethod
    def _extract_layer(
        layer_data,
        is_rgb,
        time_idx,
        slice_idx,
        orientation,
        max_s,
        offset_x=0,
        offset_y=0,
    ):
        """Safely pads dimensions, extracts the 2D slice, and applies 2D shifts."""
        if slice_idx < 0 or slice_idx >= max_s:
            return None

        # 1. Pad dimensions to ensure 4D (Time, Z, Y, X)
        if is_rgb and layer_data.ndim == 4:
            layer_data = layer_data[np.newaxis, ...]
        elif not is_rgb and layer_data.ndim == 3:
            layer_data = layer_data[np.newaxis, ...]

        # 2. Extract
        sliced = SliceRenderer.extract_slice(
            layer_data, is_rgb, time_idx, slice_idx, orientation
        )

        # 3. Apply optional 2D Pan/Shift
        if offset_x != 0 or offset_y != 0:
            sliced = SliceRenderer._shift_2d_array(sliced, offset_x, offset_y)

        return sliced

    @staticmethod
    def _colorize_layer(
        slice_data, is_rgb, num_components, ww, wl, cmap_name, threshold
    ):
        """Applies Window/Level, Colormaps, and Alpha channels."""
        if is_rgb:
            norm = np.clip(slice_data.astype(np.float32) / 255.0, 0.0, 1.0)
            if num_components == 3:
                alpha = np.ones((*norm.shape[:-1], 1), dtype=np.float32)
                rgba = np.concatenate([norm, alpha], axis=-1)
            else:
                rgba = norm
            return rgba, norm
        else:
            norm = SliceRenderer.normalize_wl(slice_data, ww, wl)
            lut = COLORMAPS.get(cmap_name, COLORMAPS["Grayscale"])
            rgba = lut[(norm * 255).astype(np.uint8)]

            if threshold is not None:
                rgba[slice_data <= threshold] = [0.0, 0.0, 0.0, 0.0]

            return rgba, norm

    @staticmethod
    def get_slice_rgba(
        base: RenderLayer,
        overlay: RenderLayer | None,
        overlay_opacity: float,
        overlay_mode: str,
        slice_idx: int,
        orientation: ViewMode,
        checkerboard_size: float = 20.0,
        checkerboard_swap: bool = False,
        rois=(),
    ):
        if orientation == ViewMode.HISTOGRAM:
            return np.array([0, 0, 0, 255], dtype=np.float32), (1, 1)

        if orientation not in SliceRenderer._AXIS_MAP:
            return np.zeros(4, dtype=np.float32), (1, 1)

        # Calculate max slices based on base image orientation
        s_ax, h_ax, w_ax = SliceRenderer._AXIS_MAP[orientation]

        # Account for RGB padding when calculating dimensions
        base_shape = base.data.shape
        if base.is_rgb and len(base_shape) == 4:
            base_shape = (1,) + base_shape
        elif not base.is_rgb and len(base_shape) == 3:
            base_shape = (1,) + base_shape

        max_s, h, w = base_shape[s_ax], base_shape[h_ax], base_shape[w_ax]

        # --- 1. BASE LAYER ---
        base_slice = SliceRenderer._extract_layer(
            base.data, base.is_rgb, base.time_idx, slice_idx, orientation, max_s
        )

        if base_slice is None:  # Out of bounds
            black_slice = np.zeros((h, w, 4), dtype=np.float32)
            black_slice[:, :, 3] = 1.0
            return black_slice.ravel(), (h, w)

        base_rgba, base_norm = SliceRenderer._colorize_layer(
            base_slice,
            base.is_rgb,
            base.num_components,
            base.ww,
            base.wl,
            base.cmap_name,
            base.threshold,
        )

        res_rgba = base_rgba

        # --- 2. OVERLAY LAYER ---
        if overlay is not None and overlay.data is not None and overlay_opacity > 0.0:
            target_slice = slice_idx - overlay.offset_slice

            over_slice = SliceRenderer._extract_layer(
                overlay.data,
                overlay.is_rgb,
                overlay.time_idx,
                target_slice,
                orientation,
                max_s,
                overlay.offset_x,
                overlay.offset_y,
            )

            if over_slice is None:
                # Overlay is out of bounds, but base is visible. Render transparent space.
                over_slice = np.zeros_like(base_slice)

            over_rgba, over_norm = SliceRenderer._colorize_layer(
                over_slice,
                overlay.is_rgb,
                overlay.num_components,
                overlay.ww,
                overlay.wl,
                overlay.cmap_name,
                overlay.threshold,
            )

            # --- Compositing Router ---
            if overlay_mode == "Registration":
                res_rgba = SliceRenderer._blend_registration(
                    base_rgba,
                    base_norm,
                    over_rgba,
                    over_norm,
                    base.is_rgb,
                    overlay.is_rgb,
                    overlay_opacity,
                )
            elif overlay_mode == "Alpha":
                res_rgba = SliceRenderer._blend_alpha(
                    base_rgba,
                    over_rgba,
                    overlay_opacity,
                )
            elif overlay_mode == "Checkerboard":
                res_rgba = SliceRenderer._blend_checkerboard(
                    base_rgba,
                    over_rgba,
                    base.spacing_2d,
                    checkerboard_size,
                    checkerboard_swap,
                    base.is_rgb,
                    overlay.is_rgb,
                )

        # --- 3. ROIs & FINAL EXPORT ---
        if rois:
            res_rgba = SliceRenderer._apply_rois(res_rgba, rois)

        return res_rgba.astype(np.float32, copy=False).ravel(), (h, w)


class VolumeData:
    """Stores the immutable medical image data and physical metadata."""

    SEQUENCE_PREFIXES = (
        "4D:",
        "4D",
        "3D:",
        "3D",
        "SEQ:",
        "SEQ",
        "SEQUENCE:",
        "SEQUENCE",
    )

    def __init__(
        self,
        path,
        is_roi=False,
        roi_mode="Ignore BG (val)",
        roi_target_val=0.0,
        preloaded_sitk=None,
    ):
        self.path = path
        self.file_paths = []

        if isinstance(path, list):
            self.file_paths = path
            # Use the folder name as the volume name
            self.name = os.path.basename(os.path.dirname(self.file_paths[0]))
        else:
            is_4d = False
            if isinstance(path, str) and path.upper().startswith(
                self.SEQUENCE_PREFIXES
            ):
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
                    # shlex.split strips backslashes by default (POSIX mode). Double escape them for Windows!
                    path_for_shlex = (
                        path.replace("\\", "\\\\") if os.name == "nt" else path
                    )
                    tokens = shlex.split(path_for_shlex)
                    valid_files = [f for f in tokens if os.path.isfile(f)]
                    if valid_files:
                        self.file_paths = sorted(valid_files)
                    else:
                        self.file_paths = [path]
            else:
                self.file_paths = [path]

            if not self.file_paths:
                raise FileNotFoundError(f"No files found for path: {self.path}")

            # path expansion
            self.file_paths = [os.path.expanduser(p) for p in self.file_paths]

        # Load, Straighten, then Extract
        if preloaded_sitk is not None:
            raw_sitk_image = preloaded_sitk
        else:
            raw_sitk_image = self.read_image_from_disk(self.file_paths)

        # Crop before straightening
        if is_roi:
            raw_sitk_image = self._crop_raw_sitk_image(
                raw_sitk_image, roi_mode, roi_target_val
            )

        self.matrix_display_str, self.matrix_tooltip_str = extract_orientation_strings(
            raw_sitk_image
        )

        self.sitk_image = straighten_image(
            raw_sitk_image, os.path.basename(self.file_paths[0]), is_label_map=is_roi
        )
        self.data = sitk.GetArrayViewFromImage(self.sitk_image)

        is_4d = self.sitk_image.GetDimension() == 4 and self.data.shape[0] > 1
        self.name = os.path.basename(self.file_paths[0])
        if is_4d and len(self.file_paths) > 1:
            self.name += f" ({len(self.file_paths)})"

        self.pixel_type = ""
        self.bytes_per_component = 1
        self.num_components = 1
        self.matrix = np.eye(3)
        self.inverse_matrix = np.eye(3)
        self.spacing = np.ones(3)
        self.origin = np.zeros(3)
        self.memory_mb = 0.0

        self.is_rgb = False
        self.is_dvf = False
        self.num_timepoints = 1
        self.shape3d = (1, 1, 1)

        self.read_image_metadata()

        # Modification tracking
        self.last_mtime = self._get_latest_mtime()
        self._last_check_time = 0
        self._is_outdated = False

    def read_image_from_disk(self, paths):
        """
        Master router for loading images. Handles standard ITK formats,
        synchrotron/detector formats via fabio, and a custom XDR fallback.
        """

        # --- 1. Fabio Format Router (Extensions we KNOW SimpleITK fails on) ---
        filename = os.path.basename(paths[0])
        ext = os.path.splitext(filename.lower())[1]

        if ext in (".edf", ".hst", ".cbf"):
            return self._read_via_fabio(paths)

        # --- 1. Custom HIS Router & Sequence Stacker ---
        if ext == ".his":
            if len(paths) == 1:
                return self._read_custom_his(paths[0])
            else:
                slices = []
            img = None
            for p in paths:
                img = self._read_custom_his(p)
                slices.append(sitk.GetArrayFromImage(img))

            # Stack the (1, Y, X) arrays into a (Z, Y, X) volume.
            stacked_vol = np.concatenate(slices, axis=0)

            final_img = sitk.GetImageFromArray(stacked_vol)
            if img is not None:
                final_img.SetSpacing(img.GetSpacing())
                final_img.SetOrigin(img.GetOrigin())
                return final_img

        # --- 2. Standard Load Logic ---
        if len(paths) == 1:
            # A. SINGLE FILE
            try:
                # 99% of images (NIfTI, DICOM, MHD) load perfectly here
                img = sitk.ReadImage(paths[0])
                if img.GetDimension() == 2:
                    img = sitk.JoinSeries([img])
                return img
            except RuntimeError as sitk_error:
                # ITK threw an error (likely "Could not create IO object")
                # Attempt to salvage the file using our pure Python AVS/XDR parser.
                try:
                    img = self._read_custom_avs_xdr(paths[0])
                    if img.GetDimension() == 2:
                        img = sitk.JoinSeries([img])
                    return img
                except Exception as xdr_error:
                    # If XDR also fails, it's truly a bad file. Surface the original ITK error.
                    raise RuntimeError(
                        f"ITK Failed: {sitk_error}\nFallback Failed: {xdr_error}"
                    )
        else:
            # B. MULTIPLE FILES (DICOM Folder or 4D Sequence)
            # SimpleITK has a dedicated reader for cleanly stacking multiple files
            try:
                reader = sitk.ImageSeriesReader()
                reader.SetFileNames(paths)
                reader.ForceOrthogonalDirectionOff()
                img = reader.Execute()
                if img.GetDimension() == 2:
                    img = sitk.JoinSeries([img])
                return img
            except RuntimeError as sitk_error:
                raise RuntimeError(f"Failed to load image series: {sitk_error}")

    def _read_via_fabio(self, paths):
        """
        Lazy-loads fabio to read synchrotron/detector formats,
        stacks the 2D slices, and rebuilds them as a 3D SimpleITK object.
        """
        # 1. Lazy Import (Only happens if a user actually loads an edf file)
        try:
            import fabio
        except ImportError:
            raise ImportError("fabio is required to read edf/cbf files.")

        # 2. Read and collect the raw NumPy arrays
        slices = []
        for path in paths:
            img = fabio.open(path)
            slices.append(img.data)

        # 3. Stack into a 3D numpy array.
        # Fabio data is typically 2D (Y, X).
        # Stacking them gives (Z, Y, X) which matches SimpleITK
        if len(slices) == 1:
            # If it's just one slice, pad it to 3D so VVV's spatial engine doesn't crash
            vol_array = np.expand_dims(slices[0], axis=0)
        else:
            vol_array = np.stack(slices, axis=0)

        # 4. Rebuild as a SimpleITK Image
        sitk_img = sitk.GetImageFromArray(vol_array)

        # Fabio headers are highly format-dependent (and often lack physical spacing).
        # We default to 1.0 spacing, but the raw pixel geometry is fully preserved.
        sitk_img.SetSpacing((1.0, 1.0, 1.0))
        sitk_img.SetOrigin((0.0, 0.0, 0.0))
        sitk_img.SetDirection(np.eye(3).flatten().tolist())

        return sitk_img

    def _read_custom_avs_xdr(self, path):
        """
        Pure Python parser for AVS Field / open-vv XDR files.
        Features Numba JIT, Endianness swapping, and binary Coordinate extraction.
        """
        import re

        with open(path, "rb") as f:
            chunk = f.read(4096)

        delim_idx = chunk.find(b"\x0c\x0c")
        if delim_idx == -1:
            raise ValueError("Missing AVS form-feed delimiter.")

        header = chunk[:delim_idx].decode("ascii", errors="ignore")

        if "ndim=" not in header:
            raise ValueError("Missing required AVS signature tags.")

        # 1. Extract Dimensions
        m1 = re.search(r"dim1\s*=\s*(\d+)", header)
        m2 = re.search(r"dim2\s*=\s*(\d+)", header)
        m3 = re.search(r"dim3\s*=\s*(\d+)", header)

        if not m1 or not m2 or not m3:
            raise ValueError("Missing dimension tags in AVS header.")

        dim1 = int(m1.group(1))
        dim2 = int(m2.group(1))
        dim3 = int(m3.group(1))
        expected_elements = dim1 * dim2 * dim3

        # 2. Extract Field Type & Binary Coordinates
        field_match = re.search(r"field\s*=\s*(\w+)", header, re.IGNORECASE)
        field_type = field_match.group(1).lower() if field_match else "uniform"

        coord_bytes = 0
        if field_type == "rectilinear":
            coord_bytes = (
                dim1 + dim2 + dim3
            ) * 4  # 32-bit float for every slice/row/col
        elif field_type == "uniform":
            coord_bytes = 6 * 4  # 3 dims * 2 floats (min/max)

        file_size = os.path.getsize(path)

        spacing = [1.0, 1.0, 1.0]
        origin = [0.0, 0.0, 0.0]

        # Sneak to the end of the file to grab the physical coordinates.
        if coord_bytes > 0 and file_size > coord_bytes:
            try:
                # XDR always uses Big-Endian floats (>f4)
                pts = np.fromfile(path, dtype=">f4", offset=file_size - coord_bytes)
                if field_type == "rectilinear" and len(pts) == (dim1 + dim2 + dim3):
                    p_x, p_y, p_z = (
                        pts[0:dim1],
                        pts[dim1 : dim1 + dim2],
                        pts[dim1 + dim2 :],
                    )
                    # AVS stores in cm. Multiply by 10 to convert to ITK's mm.
                    spacing[0] = 10.0 * (p_x[-1] - p_x[0]) / max(1, dim1 - 1)
                    spacing[1] = 10.0 * (p_y[-1] - p_y[0]) / max(1, dim2 - 1)
                    spacing[2] = 10.0 * (p_z[-1] - p_z[0]) / max(1, dim3 - 1)
                    origin = [10.0 * p_x[0], 10.0 * p_y[0], 10.0 * p_z[0]]
                elif field_type == "uniform" and len(pts) == 6:
                    spacing[0] = 10.0 * (pts[1] - pts[0]) / max(1, dim1 - 1)
                    spacing[1] = 10.0 * (pts[3] - pts[2]) / max(1, dim2 - 1)
                    spacing[2] = 10.0 * (pts[5] - pts[4]) / max(1, dim3 - 1)
                    origin = [10.0 * pts[0], 10.0 * pts[2], 10.0 * pts[4]]
            except Exception as e:
                print(f"Warning: Failed to parse AVS coordinates - {e}")

        # Override with explicit spacing if provided in comments (rare but possible)
        spacing_match = re.search(
            r"#.*spacing=\s*([\d\.]+)\s+([\d\.]+)\s+([\d\.]+)", header, re.IGNORECASE
        )
        if spacing_match:
            spacing = [float(spacing_match.group(i)) for i in (1, 2, 3)]

        # 3. Check for NKI Compression
        nki_compression = False
        nki_match = re.search(r"nki_compression\s*=\s*(\d+)", header)
        if nki_match and int(nki_match.group(1)) > 0:
            nki_compression = True

        data_offset = delim_idx + 2

        if nki_compression:
            import struct
            from vvv.maths.nki_decompress import nki_private_decompress

            raw_comp_array = np.fromfile(path, dtype=np.uint8, offset=data_offset)
            org_size, nki_mode = struct.unpack("<II", raw_comp_array[:8].tobytes())
            decompressed_1d = nki_private_decompress(raw_comp_array, org_size, nki_mode)

            if decompressed_1d.size < expected_elements:
                raise ValueError(
                    f"Decompression yielded {decompressed_1d.size} pixels, expected {expected_elements}"
                )
            vol_array = decompressed_1d[:expected_elements].reshape((dim3, dim2, dim1))
            dtype_str = "NKI Compressed (int16)"
        else:
            # Standard Uncompressed XDR Fallback
            # Subtract coord_bytes so our deduction math remains perfectly accurate.
            data_bytes = file_size - data_offset - coord_bytes

            if expected_elements > 0:
                actual_bytes_per_voxel = data_bytes // expected_elements

                if actual_bytes_per_voxel == 1:
                    dtype_str = ">u1"
                elif actual_bytes_per_voxel == 2:
                    dtype_str = ">i2"
                elif actual_bytes_per_voxel == 4:
                    dtype_str = ">i4" if "int" in header.lower() else ">f4"
                elif actual_bytes_per_voxel == 8:
                    dtype_str = ">f8"
                elif actual_bytes_per_voxel == 0:
                    raise ValueError(
                        f"File truncated! Expected {expected_elements} elements but only have {data_bytes} bytes."
                    )
                else:
                    dtype_str = ">i2"
            else:
                raise ValueError("Calculated dimensions are zero.")

            raw_array = np.fromfile(path, dtype=dtype_str, offset=data_offset)

            if raw_array.size < expected_elements:
                raise ValueError(
                    f"Array missing data! Expected {expected_elements}, got {raw_array.size}"
                )

            vol_array = raw_array[:expected_elements].reshape((dim3, dim2, dim1))

        # 4. Force Native Byte Order
        vol_array = vol_array.astype(vol_array.dtype.newbyteorder("="))

        # 5. Build the SimpleITK Image
        sitk_img = sitk.GetImageFromArray(vol_array)

        # Cast numpy.float32 to native Python float.
        sitk_img.SetSpacing([float(s) for s in spacing])
        sitk_img.SetOrigin([float(o) for o in origin])

        return sitk_img

    def _read_custom_his(self, path):
        """
        Pure Python parser for Heimann HIS format (Elekta).
        Instantly maps the 68-byte header and extracts the uncompressed payload.
        """
        import struct

        with open(path, "rb") as f:
            header = f.read(68)

        # 1. Check Magic Signature (0, 112, 68, 0)
        if len(header) < 68 or header[:4] != b"\x00\x70\x44\x00":
            raise ValueError(f"Not a valid Heimann HIS file: {os.path.basename(path)}")

        # 2. Extract Header Info (Strictly Little-Endian '<H' for unsigned short)
        extra_header_size = struct.unpack("<H", header[10:12])[0]

        ulx = struct.unpack("<H", header[12:14])[0]
        uly = struct.unpack("<H", header[14:16])[0]
        brx = struct.unpack("<H", header[16:18])[0]
        bry = struct.unpack("<H", header[18:20])[0]

        nrframes = struct.unpack("<H", header[20:22])[0]

        # ITK dimensions based on C++ source
        dim_x = bry - uly + 1
        dim_y = brx - ulx + 1

        # 3. Calculate Spacing
        spacing_x = 409.6 / dim_x
        spacing_y = 409.6 / dim_y

        # 4. Extract Binary Payload
        data_offset = 68 + extra_header_size
        raw_array = np.fromfile(
            path, dtype="<u2", offset=data_offset
        )  # <u2 = 16-bit uint

        # 5. Reshape and Pad to 3D
        if nrframes > 1:
            vol_array = raw_array.reshape((nrframes, dim_y, dim_x))
        else:
            vol_array = raw_array.reshape(
                (1, dim_y, dim_x)
            )  # Pad 2D projection to 3D for VVV

        # 6. Build SimpleITK Image
        sitk_img = sitk.GetImageFromArray(vol_array)
        sitk_img.SetSpacing((spacing_x, spacing_y, 1.0))

        origin_x = -0.5 * (dim_x - 1) * spacing_x
        origin_y = -0.5 * (dim_y - 1) * spacing_y
        sitk_img.SetOrigin((origin_x, origin_y, 0.0))

        return sitk_img

    def get_human_readable_file_path(self):
        raw_path = (
            self.file_paths[0]
            if isinstance(self.file_paths, list) and self.file_paths
            else str(self.path)
        )
        n = os.path.abspath(os.path.expanduser(raw_path))
        n = get_history_path_key(n)
        return n

    def _crop_raw_sitk_image(self, sitk_img, mode="Ignore BG (val)", target_val=0.0):
        """Uses ITK's C++ engine to instantly crop empty space before heavy resampling."""
        # 0. Guard against RGB/Vector images crashing the mathematical threshold filter
        if sitk_img.GetNumberOfComponentsPerPixel() > 1:
            return sitk_img

        # 1. Create a binary mask of the actual data
        if mode == "Target FG (val)":
            binary_mask = sitk_img == float(target_val)
        else:
            binary_mask = sitk_img != float(target_val)

        # 2. Find the bounding box in milliseconds
        stats = sitk.LabelShapeStatisticsImageFilter()
        stats.Execute(binary_mask)

        if stats.HasLabel(1):
            bbox = stats.GetBoundingBox(
                1
            )  # Returns (x_start, y_start, z_start, x_size, y_size, z_size)
            dim = sitk_img.GetDimension()

            # 3. Crop the raw image (this automatically recalculates the physical Origin).
            roi_filter = sitk.RegionOfInterestImageFilter()
            roi_filter.SetIndex(bbox[:dim])
            roi_filter.SetSize(bbox[dim:])
            return roi_filter.Execute(sitk_img)

        return sitk_img

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

        try:
            self.inverse_matrix = np.linalg.inv(self.matrix)
        except np.linalg.LinAlgError:
            print(
                f"Warning: Singular spatial matrix detected in {self.name}. Falling back to Identity."
            )
            self.matrix = np.eye(3)
            self.inverse_matrix = np.eye(3)

        self.spacing = np.array(self.sitk_image.GetSpacing()[:3])
        self.origin = np.array(self.sitk_image.GetOrigin()[:3])

        self.is_rgb = (
            self.num_components in [3, 4]
            and "float" not in self.pixel_type.lower()
            and "double" not in self.pixel_type.lower()
        )
        self.is_dvf = self.num_components > 1 and not self.is_rgb

        if self.is_dvf and self.data.ndim == 4:
            self.data = np.moveaxis(self.data, -1, 0)

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

    def _get_latest_mtime(self):
        try:
            if self.file_paths and os.path.exists(self.file_paths[0]):
                return os.path.getmtime(self.file_paths[0])
        except:
            pass
        return 0

    def is_outdated(self):
        now = time.time()
        # Throttled test (every 5 seconds) to guarantee 0 GUI lag.
        if now - self._last_check_time > 5.0:
            self._last_check_time = now
            current_mtime = self._get_latest_mtime()
            self._is_outdated = current_mtime > self.last_mtime
        return self._is_outdated

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
        from vvv.maths.image_utils import straighten_image

        try:
            new_sitk = self.read_image_from_disk(self.file_paths)
            new_sitk = straighten_image(new_sitk, os.path.basename(self.file_paths[0]))
        except Exception as e:
            print(f"Warning: Failed to reload {self.name}. Error: {e}")
            return False

        new_shape = new_sitk.GetSize()
        current_shape = self.sitk_image.GetSize() if self.sitk_image else None

        if current_shape and new_shape == current_shape:
            # Create the new view FIRST, then swap atomically
            new_data = sitk.GetArrayViewFromImage(new_sitk)

            # Keep a temporary reference to prevent instantaneous C++ free
            old_sitk = self.sitk_image

            self.sitk_image = new_sitk
            self.data = new_data
            self.read_image_metadata()

            self.last_mtime = self._get_latest_mtime()
            self._is_outdated = False

            # old_sitk safely drops out of scope here
            return False
        else:
            self.__init__(self.path)
            return True
