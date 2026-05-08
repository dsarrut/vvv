import numpy as np
from vvv.maths.image import SliceRenderer
from vvv.config import COLORMAPS
from vvv.utils import ViewMode

import platform as _platform
GL_NEAREST_SUPPORTED = _platform.system() in ("Linux", "Windows")
_gl_nearest_fn = None

def try_set_gl_nearest():
    """Call glTexParameteri(GL_NEAREST) on the currently-bound 2D texture.

    DPG leaves its new texture bound after add_dynamic_texture(), so calling
    this immediately after that creates a GL_NEAREST texture at no extra cost.
    Silently does nothing if GL is unavailable (headless tests, bad context…).
    """
    global _gl_nearest_fn
    if _gl_nearest_fn is None:
        import ctypes, ctypes.util, platform
        try:
            sys = platform.system()
            if sys == "Linux":
                lib = ctypes.CDLL(ctypes.util.find_library("GL") or "libGL.so.1")
            elif sys == "Windows":
                lib = ctypes.windll.opengl32  # type: ignore[attr-defined]
            else:
                # macOS uses Metal via DearPyGui — raw GL calls crash with no context
                _gl_nearest_fn = False
                return
            _GL_TEXTURE_2D        = 0x0DE1
            _GL_TEXTURE_MIN_FILTER = 0x2801
            _GL_TEXTURE_MAG_FILTER = 0x2800
            _GL_NEAREST            = 0x2600

            def _set():
                try:
                    lib.glTexParameteri(_GL_TEXTURE_2D, _GL_TEXTURE_MIN_FILTER, _GL_NEAREST)
                    lib.glTexParameteri(_GL_TEXTURE_2D, _GL_TEXTURE_MAG_FILTER, _GL_NEAREST)
                except Exception:
                    pass

            _gl_nearest_fn = _set
        except Exception:
            _gl_nearest_fn = False

    if callable(_gl_nearest_fn):
        _gl_nearest_fn()

def blend_slices_cpu(base_2d, ov_2d, opacity, shift_x, shift_y):
    """Alpha blends an overlay slice onto a base slice on the CPU."""
    h, w = base_2d.shape[:2]
    oh, ow = ov_2d.shape[:2]

    sx = int(round(shift_x))
    sy = int(round(shift_y))

    out = base_2d.copy()

    x0_base = max(0, sx)
    x1_base = min(w, sx + ow)
    y0_base = max(0, sy)
    y1_base = min(h, sy + oh)

    x0_ov = max(0, -sx)
    x1_ov = min(ow, w - sx)
    y0_ov = max(0, -sy)
    y1_ov = min(oh, h - sy)

    if x0_base >= x1_base or y0_base >= y1_base:
        return out

    b_roi = base_2d[y0_base:y1_base, x0_base:x1_base]
    o_roi = ov_2d[y0_ov:y1_ov, x0_ov:x1_ov]

    alpha_ov = o_roi[..., 3:4] * opacity
    out[y0_base:y1_base, x0_base:x1_base, :3] = o_roi[..., :3] * alpha_ov + b_roi[..., :3] * (1.0 - alpha_ov)
    out[y0_base:y1_base, x0_base:x1_base, 3:4] = alpha_ov + b_roi[..., 3:4] * (1.0 - alpha_ov)

    return out


def compute_software_nearest_neighbor(
    rgba_img, pmin, pmax, canvas_w, canvas_h, out_buffer=None, last_crop=None
):
    """Extracts the exact viewport region and upscales using pure Nearest Neighbor math."""
    h, w = rgba_img.shape[:2]

    disp_w = max(1e-5, pmax[0] - pmin[0])
    disp_h = max(1e-5, pmax[1] - pmin[1])

    # 1D index arrays only (cheap: O(canvas_w + canvas_h)).
    # +0.5 samples the center of each screen pixel; +1e-5 prevents float64
    # boundary jitter (e.g. 3.9999999 flooring to 3 instead of 4).
    ix_full = np.floor(
        (np.arange(canvas_w, dtype=np.float32) + 0.5 - pmin[0]) * (w / disp_w)
        + 1e-5
    ).astype(np.int32)
    iy_full = np.floor(
        (np.arange(canvas_h, dtype=np.float32) + 0.5 - pmin[1]) * (h / disp_h)
        + 1e-5
    ).astype(np.int32)

    valid_x = (ix_full >= 0) & (ix_full < w)
    valid_y = (iy_full >= 0) & (iy_full < h)

    if not valid_x.any() or not valid_y.any():
        if out_buffer is None:
            return np.zeros((canvas_h, canvas_w, 4), dtype=rgba_img.dtype)
        if last_crop:
            oy0, oy1, ox0, ox1 = last_crop
            out_buffer[oy0:oy1, ox0:ox1] = 0.0
        return out_buffer, None

    all_valid = bool(valid_x.all()) and bool(valid_y.all())

    if all_valid:
        # Identity mapping: canvas == image AND ix/iy are exactly [0..w-1]/[0..h-1].
        # Guard with endpoint check (O(1)) to reject zoom-in on same-size image.
        if (
            canvas_w == w
            and canvas_h == h
            and int(ix_full[0]) == 0
            and int(ix_full[-1]) == w - 1
            and int(iy_full[0]) == 0
            and int(iy_full[-1]) == h - 1
        ):
            if out_buffer is None:
                return rgba_img
            if last_crop:
                oy0, oy1, ox0, ox1 = last_crop
                out_buffer[oy0:oy1, ox0:ox1] = 0.0
            return rgba_img, None
        ix, iy = ix_full, iy_full
        x0 = y0 = 0
        x1, y1 = canvas_w, canvas_h
    else:
        # Restrict to the valid sub-rectangle [x0:x1) × [y0:y1).
        # This eliminates the black-border region from all heavy work.
        x0 = int(np.argmax(valid_x))
        x1 = canvas_w - int(np.argmax(valid_x[::-1]))
        y0 = int(np.argmax(valid_y))
        y1 = canvas_h - int(np.argmax(valid_y[::-1]))
        ix = ix_full[x0:x1]
        iy = iy_full[y0:y1]

    vw, vh = x1 - x0, y1 - y0

    # Fast path when every image pixel covers ≥1 screen pixel in both axes
    # (any zoom level where NN looks different from linear).
    # ix/iy are then monotone non-decreasing with many repeated values.
    # Extract the small visible ROI once and tile with np.repeat
    # (sequential SIMD copies) instead of scatter-gather fancy indexing.
    if vw >= w and vh >= h:
        ix_new = np.empty(vw, dtype=bool)
        iy_new = np.empty(vh, dtype=bool)
        ix_new[0] = iy_new[0] = True
        ix_new[1:] = ix[1:] != ix[:-1]
        iy_new[1:] = iy[1:] != iy[:-1]
        unique_ix = ix[ix_new]
        unique_iy = iy[iy_new]
        ix_cnt = np.diff(np.where(np.append(ix_new, True))[0])
        iy_cnt = np.diff(np.where(np.append(iy_new, True))[0])
        if len(unique_iy) == h and len(unique_ix) == w:
            # Fill case: all source rows/cols present — skip 2D fancy-index copy.
            # np.repeat directly on rgba_img saves one full-image allocation.
            tile = np.repeat(np.repeat(rgba_img, iy_cnt, axis=0), ix_cnt, axis=1)
        else:
            roi = rgba_img[unique_iy[:, None], unique_ix[None, :]]
            tile = np.repeat(np.repeat(roi, iy_cnt, axis=0), ix_cnt, axis=1)
    else:
        # Zoomed out past 1:1 — NN and linear look identical; fancy-index the subregion.
        tile = rgba_img[iy[:, None], ix[None, :]]

    if out_buffer is None:
        if all_valid:
            return tile
        out = np.zeros((canvas_h, canvas_w, 4), dtype=rgba_img.dtype)
        out[y0:y1, x0:x1] = tile
        return out

    if all_valid:
        if last_crop:
            oy0, oy1, ox0, ox1 = last_crop
            out_buffer[oy0:oy1, ox0:ox1] = 0.0
        out_buffer[:, :] = tile
        return out_buffer, None

    if last_crop is None:
        # Previous frame was all_valid (entire buffer was filled) — zero it now
        # so the border region outside the new crop doesn't show stale image data.
        out_buffer[:] = 0.0
    elif last_crop != (y0, y1, x0, x1):
        oy0, oy1, ox0, ox1 = last_crop
        out_buffer[oy0:oy1, ox0:ox1] = 0.0

    out_buffer[y0:y1, x0:x1] = tile
    return out_buffer, (y0, y1, x0, x1)


def compute_native_voxel_overlay(viewer, pmin, pmax, canvas_w, canvas_h, target_buffer=None, opacity=1.0):
    """Render the overlay at its native voxel resolution in NN pixelated mode.

    Instead of NN-mapping the pre-resampled overlay (at CT resolution), this maps
    canvas pixels directly to the overlay's original voxel space — producing blocks
    that match the true physical voxel size of the overlay (e.g. 4.7 mm SPECT pixels).
    Registration transforms are applied analytically via numpy matrix math.
    """
    vs = viewer.view_state
    if not vs or not vs.display.overlay_id:
        return None
    if vs.display.overlay_id not in viewer.controller.view_states:
        return None

    ovs = viewer.controller.view_states[vs.display.overlay_id]
    base_vol = viewer.volume
    ov_vol = viewer.controller.volumes.get(vs.display.overlay_id)
    if not base_vol or not ov_vol or ov_vol.data is None:
        return None

    disp_w = pmax[0] - pmin[0]
    disp_h = pmax[1] - pmin[1]
    if disp_w <= 0 or disp_h <= 0:
        return None

    # --- 1. Extract composite transform as numpy affine ---
    def _affine_np(transform):
        if transform is None:
            return np.eye(3, dtype=np.float64), np.zeros(3, dtype=np.float64)
        try:
            R = np.array(transform.GetMatrix(), dtype=np.float64).reshape(3, 3)
            t = np.array(transform.GetTranslation(), dtype=np.float64)
            fp = transform.GetFixedParameters()
            c = np.array(fp[:3], dtype=np.float64) if len(fp) >= 3 else np.zeros(3)
            return R, t + c - R @ c
        except Exception:
            return np.eye(3, dtype=np.float64), np.zeros(3, dtype=np.float64)

    ov_xfm = ovs.space.transform.GetInverse() if (ovs.space.transform and ovs.space.is_active) else None
    base_xfm = vs.space.transform if (vs.space.transform and vs.space.is_active) else None
    R1, t1 = _affine_np(ov_xfm)
    R2, t2 = _affine_np(base_xfm)
    R_comp = R2 @ R1
    t_comp = R2 @ t1 + t2

    # --- 2 & 3. Analytic Composition ---
    M_base = base_vol.matrix * base_vol.spacing[np.newaxis, :]  # (3, 3)
    M_inv_ov = ov_vol.inverse_matrix / ov_vol.spacing[:, None]  # (3, 3)

    A_total = M_inv_ov @ R_comp @ M_base
    b_total = M_inv_ov @ (R_comp @ base_vol.origin + t_comp - ov_vol.origin)

    slice_h, slice_w = viewer.get_slice_shape()
    depth = float(viewer.slice_idx)

    time_idx = min(vs.camera.time_idx, ov_vol.num_timepoints - 1)
    ov_data = ov_vol.data[time_idx] if ov_vol.num_timepoints > 1 else ov_vol.data
    ov_D, ov_H, ov_W = ov_data.shape

    # --- SCREEN CROP OPTIMIZATION ---
    c_x0, c_x1, c_y0, c_y1 = 0, canvas_w, 0, canvas_h
    try:
        A_inv = np.linalg.inv(A_total)
        corners_ov = np.array([
            [0, 0, 0], [ov_W, 0, 0], [0, ov_H, 0], [ov_W, ov_H, 0],
            [0, 0, ov_D], [ov_W, 0, ov_D], [0, ov_H, ov_D], [ov_W, ov_H, ov_D],
        ])
        base_corners = (A_inv @ (corners_ov - b_total).T).T

        if viewer.orientation == ViewMode.AXIAL:
            ix_disp_corners = base_corners[:, 0] + 0.5
            iy_disp_corners = base_corners[:, 1] + 0.5
        elif viewer.orientation == ViewMode.SAGITTAL:
            ix_disp_corners = slice_w - base_corners[:, 1] - 0.5
            iy_disp_corners = slice_h - base_corners[:, 2] - 0.5
        else:  # CORONAL
            ix_disp_corners = base_corners[:, 0] + 0.5
            iy_disp_corners = slice_h - base_corners[:, 2] - 0.5

        x_screen = (ix_disp_corners * disp_w / slice_w) + pmin[0] - 0.5
        y_screen = (iy_disp_corners * disp_h / slice_h) + pmin[1] - 0.5

        b_x0, b_x1 = int(np.floor(x_screen.min())), int(np.ceil(x_screen.max())) + 1
        b_y0, b_y1 = int(np.floor(y_screen.min())), int(np.ceil(y_screen.max())) + 1

        c_x0, c_x1 = max(0, min(canvas_w, b_x0)), max(0, min(canvas_w, b_x1))
        c_y0, c_y1 = max(0, min(canvas_h, b_y0)), max(0, min(canvas_h, b_y1))
    except np.linalg.LinAlgError:
        pass

    if target_buffer is None:
        if not hasattr(viewer, "_native_ov_buf") or viewer._native_ov_buf.shape[:2] != (canvas_h, canvas_w):
            viewer._native_ov_buf = np.zeros((canvas_h, canvas_w, 4), dtype=np.float32)
            viewer._last_native_ov_crop = None

        rgba = viewer._native_ov_buf
        if getattr(viewer, "_last_native_ov_crop", None):
            oy0, oy1, ox0, ox1 = viewer._last_native_ov_crop
            rgba[oy0:oy1, ox0:ox1] = 0.0

        viewer._last_native_ov_crop = (c_y0, c_y1, c_x0, c_x1)
    else:
        rgba = target_buffer

    if c_x0 >= c_x1 or c_y0 >= c_y1:
        return rgba.ravel() if target_buffer is None else None

    A_total = A_total.astype(np.float32)
    b_total = b_total.astype(np.float32)
    C0, C1, C2 = A_total[:, 0], A_total[:, 1], A_total[:, 2]
    B_eff = b_total + 0.5  

    ix_disp = (np.arange(c_x0, c_x1, dtype=np.float32) + 0.5 - pmin[0]) * (slice_w / disp_w)
    iy_disp = (np.arange(c_y0, c_y1, dtype=np.float32) + 0.5 - pmin[1]) * (slice_h / disp_h)

    if viewer.orientation == ViewMode.AXIAL:
        itk_x, itk_y = ix_disp - 0.5, iy_disp - 0.5
        B_eff += C2 * depth
        vec_w, vec_h = C0[:, None] * itk_x, C1[:, None] * itk_y
    elif viewer.orientation == ViewMode.SAGITTAL:
        itk_y, itk_z = slice_w - ix_disp - 0.5, slice_h - iy_disp - 0.5
        B_eff += C0 * depth
        vec_w, vec_h = C1[:, None] * itk_y, C2[:, None] * itk_z
    else:  # CORONAL
        itk_x, itk_z = ix_disp - 0.5, slice_h - iy_disp - 0.5
        B_eff += C1 * depth
        vec_w, vec_h = C0[:, None] * itk_x, C2[:, None] * itk_z

    s_x = B_eff[0] + vec_h[0][:, None] + vec_w[0]
    s_y = B_eff[1] + vec_h[1][:, None] + vec_w[1]
    s_z = B_eff[2] + vec_h[2][:, None] + vec_w[2]

    in_bounds = ((s_x >= 0) & (s_x < ov_W) & (s_y >= 0) & (s_y < ov_H) & (s_z >= 0) & (s_z < ov_D))

    if in_bounds.any():
        x_nn, y_nn, z_nn = s_x[in_bounds].astype(np.int32), s_y[in_bounds].astype(np.int32), s_z[in_bounds].astype(np.int32)
        x_min, x_max = x_nn.min(), x_nn.max()
        y_min, y_max = y_nn.min(), y_nn.max()
        z_min, z_max = z_nn.min(), z_nn.max()

        box_size = (z_max - z_min + 1) * (y_max - y_min + 1) * (x_max - x_min + 1)
        if box_size < 2_000_000:
            cropped_ov = ov_data[z_min : z_max + 1, y_min : y_max + 1, x_min : x_max + 1]
            x_nn, y_nn, z_nn = x_nn - x_min, y_nn - y_min, z_nn - z_min
            c_H, c_W = cropped_ov.shape[1], cropped_ov.shape[2]
            flat_idx = z_nn * (c_H * c_W) + y_nn * c_W + x_nn
            valid_vals = cropped_ov.flatten()[flat_idx].astype(np.float32)
        else:
            flat_idx = z_nn * (ov_H * ov_W) + y_nn * ov_W + x_nn
            valid_vals = ov_data.ravel()[flat_idx].astype(np.float32)

        threshold = ovs.display.base_threshold
        if threshold is not None:
            thr_mask = valid_vals > threshold
            valid_vals, in_bounds[in_bounds] = valid_vals[thr_mask], thr_mask

        if in_bounds.any():
            norm = SliceRenderer.normalize_wl(valid_vals, ovs.display.ww, ovs.display.wl)
            lut = COLORMAPS.get(ovs.display.colormap, COLORMAPS["Grayscale"])
            new_colors = lut[(norm * 255).astype(np.uint8)]
            rgba_crop = rgba[c_y0:c_y1, c_x0:c_x1]
            
            if target_buffer is not None:
                # CPU Pre-compositing: Alpha Blend directly into the base image array
                alpha = new_colors[:, 3:4] * opacity
                dst_colors = rgba_crop[in_bounds]
                rgba_crop[in_bounds, :3] = new_colors[:, :3] * alpha + dst_colors[:, :3] * (1.0 - alpha)
                rgba_crop[in_bounds, 3:4] = alpha + dst_colors[:, 3:4] * (1.0 - alpha)
            else:
                rgba_crop[in_bounds] = new_colors

    return rgba.ravel() if target_buffer is None else None