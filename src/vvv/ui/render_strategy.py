import numpy as np
from vvv.maths.image import SliceRenderer
from vvv.config import COLORMAPS
from vvv.utils import ViewMode
from enum import IntEnum

import platform as _platform
GL_NEAREST_SUPPORTED = _platform.system() in ("Linux", "Windows")
_gl_nearest_fn = None

try:
    import os as _os
    _os.environ.setdefault("KMP_WARNINGS", "0")  # suppress OMP nested-parallelism info message
    import numba
    _NUMBA_AVAILABLE = True
except ImportError:
    import typing as _typing
    numba: _typing.Any = None
    _NUMBA_AVAILABLE = False

if _NUMBA_AVAILABLE:
    @numba.njit(parallel=True, cache=True, fastmath=True)
    def _native_ov_kernel_nb(
        ov_data,      # (D, H, W) any numeric dtype
        rgba,         # (canvas_h, canvas_w, 4) float32 — written in-place
        B_eff,        # (3,) float32 — affine offset incl. depth contribution
        C_col,        # (3,) float32 — per-row axis column vector
        C_row,        # (3,) float32 — per-col axis column vector
        iy_adj,       # (crop_h,) float32 — orientation-adjusted row coords
        ix_adj,       # (crop_w,) float32 — orientation-adjusted col coords
        lut,          # (256, 4) float32, values 0-1
        wl_min,       # float32
        wl_scale,     # float32 = 1/ww
        threshold,    # float32 — use -inf for "no threshold"
        opacity,      # float32
        c_y0,         # int — crop row offset into rgba
        c_x0,         # int — crop col offset into rgba
        ov_D,         # int
        ov_H,         # int
        ov_W,         # int
        precomposite, # bool — True: alpha-blend into base; False: write standalone
    ):
        crop_h = len(iy_adj)
        crop_w = len(ix_adj)
        for cy in numba.prange(crop_h):
            iy = iy_adj[cy]
            # Hoist row contribution out of inner loop
            Bx = B_eff[0] + C_col[0] * iy
            By = B_eff[1] + C_col[1] * iy
            Bz = B_eff[2] + C_col[2] * iy
            for cx in range(crop_w):
                ix = ix_adj[cx]
                sx = Bx + C_row[0] * ix
                sy = By + C_row[1] * ix
                sz = Bz + C_row[2] * ix
                xi = int(sx)
                yi = int(sy)
                zi = int(sz)
                if xi < 0 or xi >= ov_W or yi < 0 or yi >= ov_H or zi < 0 or zi >= ov_D:
                    continue
                val = numba.float32(ov_data[zi, yi, xi])
                if val <= threshold:
                    continue
                norm = (val - wl_min) * wl_scale
                if norm < 0.0:
                    norm = 0.0
                if norm > 1.0:
                    norm = 1.0
                lut_idx = int(norm * 255.0)
                r = lut[lut_idx, 0]
                g = lut[lut_idx, 1]
                b = lut[lut_idx, 2]
                a = lut[lut_idx, 3] * opacity
                ry = cy + c_y0
                rx = cx + c_x0
                if precomposite:
                    inv_a = 1.0 - a
                    rgba[ry, rx, 0] = r * a + rgba[ry, rx, 0] * inv_a
                    rgba[ry, rx, 1] = g * a + rgba[ry, rx, 1] * inv_a
                    rgba[ry, rx, 2] = b * a + rgba[ry, rx, 2] * inv_a
                    rgba[ry, rx, 3] = a + rgba[ry, rx, 3] * inv_a
                else:
                    rgba[ry, rx, 0] = r
                    rgba[ry, rx, 1] = g
                    rgba[ry, rx, 2] = b
                    rgba[ry, rx, 3] = a


class NNMode(IntEnum):
    HW_GL_NEAREST     = 0  # GPU GL_NEAREST filter — Linux/Windows only
    SW_DUAL_NATIVE    = 1  # 2 textures; overlay at true voxel resolution via affine math
    SW_DUAL_RESAMPLED = 2  # 2 textures; overlay NN-scaled from ITK-resampled grid
    SW_SINGLE_MERGED  = 3  # 1 texture; CPU alpha-blend base+overlay then NN scale
    SW_SINGLE_NATIVE  = 4  # 1 texture; NN base + native-voxel overlay painted in


DEFAULT_NN_MODE: NNMode = NNMode.HW_GL_NEAREST if GL_NEAREST_SUPPORTED else NNMode.SW_DUAL_NATIVE


def select_nn_mode(cfg: dict, has_fusion: bool) -> NNMode:
    """Derive the active NNMode from rendering config and fusion state."""
    if GL_NEAREST_SUPPORTED and cfg.get("gl_nearest", True):
        return NNMode.HW_GL_NEAREST

    st_cfg = cfg.get("single_texture", "Auto")
    is_single = has_fusion if st_cfg == "Auto" else (st_cfg is True or st_cfg == "Single")

    nv_cfg = cfg.get("native_voxel", "Auto")
    is_native = True if nv_cfg == "Auto" else (nv_cfg is True or nv_cfg == "Native")

    if is_single and is_native:
        return NNMode.SW_SINGLE_NATIVE
    if is_single:
        return NNMode.SW_SINGLE_MERGED
    if is_native:
        return NNMode.SW_DUAL_NATIVE
    return NNMode.SW_DUAL_RESAMPLED


def should_use_lazy_lin(cfg: dict, has_fusion: bool, is_hw: bool, use_numba: bool = False) -> bool:
    """Return True if lazy-lin (bilinear-during-drag) should be active.

    Auto mode enables lazy-lin only when: fusion is active, HW path is not used,
    AND Numba is not available (Numba makes the SW render fast enough to skip lazy-lin).
    Explicit On/Off overrides always win regardless of Numba.
    """
    if is_hw:
        return False
    ll_cfg = cfg.get("lazy_lin", "Auto")
    if ll_cfg == "Auto":
        return has_fusion and not use_numba
    return ll_cfg is True or ll_cfg == "On"


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
    inv_alpha = 1.0 - alpha_ov
    out[y0_base:y1_base, x0_base:x1_base, :3] = o_roi[..., :3] * alpha_ov + b_roi[..., :3] * inv_alpha
    out[y0_base:y1_base, x0_base:x1_base, 3:4] = alpha_ov + b_roi[..., 3:4] * inv_alpha

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


def _affine_np(transform):
    """Extract rotation matrix R and effective translation t from a SimpleITK transform.

    Returns (R, t) such that the transform maps p → R @ p + t.
    Returns (identity, zeros) for None or on error.
    """
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

    base_xfm = vs.space.transform if (vs.space.transform and vs.space.is_active) else None
    ov_xfm = ovs.space.transform if (ovs.space.transform and ovs.space.is_active) else None

    t_user_A = np.zeros(3, dtype=np.float64)
    if base_xfm is not None:
        t_user_A = np.array(base_xfm.GetTranslation(), dtype=np.float64)

    R_B, t_B = _affine_np(ov_xfm)
    try:
        R_B_inv = np.linalg.inv(R_B)
    except np.linalg.LinAlgError:
        R_B_inv = np.eye(3)
        
    R_comp = R_B_inv
    t_comp = R_B_inv @ (t_user_A - t_B)

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
        C_col, C_row = C1, C0
        iy_adj, ix_adj = itk_y, itk_x
        vec_w, vec_h = C0[:, None] * itk_x, C1[:, None] * itk_y
    elif viewer.orientation == ViewMode.SAGITTAL:
        itk_y, itk_z = slice_w - ix_disp - 0.5, slice_h - iy_disp - 0.5
        B_eff += C0 * depth
        C_col, C_row = C2, C1
        iy_adj, ix_adj = itk_z, itk_y
        vec_w, vec_h = C1[:, None] * itk_y, C2[:, None] * itk_z
    else:  # CORONAL
        itk_x, itk_z = ix_disp - 0.5, slice_h - iy_disp - 0.5
        B_eff += C1 * depth
        C_col, C_row = C2, C0
        iy_adj, ix_adj = itk_z, itk_x
        vec_w, vec_h = C0[:, None] * itk_x, C2[:, None] * itk_z

    lut = COLORMAPS.get(ovs.display.colormap, COLORMAPS["Grayscale"])
    thr_val = ovs.display.base_threshold

    use_numba = _NUMBA_AVAILABLE and viewer.controller.settings.data.get("rendering", {}).get("numba", True)

    if use_numba:
        thr_nb = np.float32(thr_val if thr_val is not None else -np.inf)
        wl_min = np.float32(ovs.display.wl - ovs.display.ww * 0.5)
        wl_scale = np.float32(1.0 / max(ovs.display.ww, 1e-20))
        ov_arr = np.ascontiguousarray(ov_data)
        if target_buffer is None:
            rgba[c_y0:c_y1, c_x0:c_x1] = 0.0
        _native_ov_kernel_nb(
            ov_arr, rgba,
            B_eff.astype(np.float32),
            C_col.astype(np.float32), C_row.astype(np.float32),
            iy_adj.astype(np.float32), ix_adj.astype(np.float32),
            lut, wl_min, wl_scale, thr_nb, np.float32(opacity),
            c_y0, c_x0, ov_D, ov_H, ov_W,
            target_buffer is not None,
        )
        return rgba.ravel() if target_buffer is None else None

    # --- NumPy fallback (no numba) ---
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

        if thr_val is not None:
            thr_mask = valid_vals > thr_val
            valid_vals, in_bounds[in_bounds] = valid_vals[thr_mask], thr_mask

        if in_bounds.any():
            norm = SliceRenderer.normalize_wl(valid_vals, ovs.display.ww, ovs.display.wl)
            new_colors = lut[(norm * 255).astype(np.uint8)]
            rgba_crop = rgba[c_y0:c_y1, c_x0:c_x1]

            if target_buffer is not None:
                alpha = new_colors[:, 3:4] * opacity
                inv_alpha = 1.0 - alpha
                dst_colors = rgba_crop[in_bounds]
                rgba_crop[in_bounds, :3] = new_colors[:, :3] * alpha + dst_colors[:, :3] * inv_alpha
                rgba_crop[in_bounds, 3:4] = alpha + dst_colors[:, 3:4] * inv_alpha
            else:
                rgba_crop[in_bounds] = new_colors

    return rgba.ravel() if target_buffer is None else None


def compute_preview_2d_affine(vol, orientation, slice_idx, R, center, time_idx):
    """Fast per-slice preview via inverse rotation sampling on the raw volume (nearest-neighbor)."""
    shape = vol.shape3d  # (Z, Y, X) numpy
    spacing = vol.spacing
    if orientation == ViewMode.AXIAL:
        rows, cols = np.meshgrid(np.arange(shape[1]), np.arange(shape[2]), indexing="ij")
        vox_N = np.column_stack([cols.ravel(), rows.ravel(), np.full(rows.size, slice_idx, dtype=np.float64)])
    elif orientation == ViewMode.SAGITTAL:
        rows, cols = np.meshgrid(np.arange(shape[0]), np.arange(shape[1]), indexing="ij")
        vox_N = np.column_stack([
            np.full(rows.size, slice_idx, dtype=np.float64),
            (shape[1] - 1 - cols).ravel().astype(np.float64),
            (shape[0] - 1 - rows).ravel().astype(np.float64),
        ])
    else:  # CORONAL
        rows, cols = np.meshgrid(np.arange(shape[0]), np.arange(shape[2]), indexing="ij")
        vox_N = np.column_stack([
            cols.ravel().astype(np.float64),
            np.full(rows.size, slice_idx, dtype=np.float64),
            (shape[0] - 1 - rows).ravel().astype(np.float64),
        ])

    phys_N = vol.origin + (vox_N * spacing) @ vol.matrix.T
    phys_in_N = (phys_N - center) @ R + center  # apply R^T per row (inverse rotation)
    vox_in_N = ((phys_in_N - vol.origin) @ vol.inverse_matrix.T) / spacing

    x_in = np.clip(np.round(vox_in_N[:, 0]).astype(np.intp), 0, shape[2] - 1)
    y_in = np.clip(np.round(vox_in_N[:, 1]).astype(np.intp), 0, shape[1] - 1)
    z_in = np.clip(np.round(vox_in_N[:, 2]).astype(np.intp), 0, shape[0] - 1)

    data = vol.data
    if data.ndim == 4:
        data = data[min(time_idx, data.shape[0] - 1)]

    return np.ascontiguousarray(data[z_in, y_in, x_in].reshape(rows.shape))