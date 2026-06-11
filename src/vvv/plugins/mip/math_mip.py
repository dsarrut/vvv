import numpy as np

from typing import Any

numba: Any
try:
    import numba as _numba
    numba = _numba
    _NUMBA_AVAILABLE = True
except ImportError:
    class _Dummy:
        def njit(self, *args, **kwargs):
            return lambda f: f
        def prange(self, *args):
            return range(*args)
    numba = _Dummy()
    _NUMBA_AVAILABLE = False


if _NUMBA_AVAILABLE:
    @numba.njit(parallel=True, cache=True, fastmath=True)
    def project_mip_z(data: np.ndarray, depth_cueing_strength: float) -> np.ndarray:
        """Compute MIP along the Z (depth) axis using Numba. Output shape is (H, W)."""
        D, H, W = data.shape
        out = np.zeros((H, W), dtype=data.dtype)
        for y in numba.prange(H):  # type: ignore
            for x in range(W):
                max_val = data[0, y, x]
                for z in range(D):
                    val = data[z, y, x]
                    if depth_cueing_strength > 0.0:
                        factor = 1.0 - depth_cueing_strength * (z / max(1.0, D - 1))
                        val = val * factor
                    if val > max_val:
                        max_val = val
                out[y, x] = max_val
        return out


    @numba.njit(parallel=True, cache=True, fastmath=True)
    def project_mip_y(data: np.ndarray, depth_cueing_strength: float) -> np.ndarray:
        """Compute MIP along the Y (depth) axis using Numba. Output shape is (D, W)."""
        D, H, W = data.shape
        out = np.zeros((D, W), dtype=data.dtype)
        for z in numba.prange(D):  # type: ignore
            for x in range(W):
                max_val = data[z, 0, x]
                for y in range(H):
                    val = data[z, y, x]
                    if depth_cueing_strength > 0.0:
                        factor = 1.0 - depth_cueing_strength * (y / max(1.0, H - 1))
                        val = val * factor
                    if val > max_val:
                        max_val = val
                out[z, x] = max_val
        return out


    @numba.njit(parallel=True, cache=True, fastmath=True)
    def project_mip_x(data: np.ndarray, depth_cueing_strength: float) -> np.ndarray:
        """Compute MIP along the X (depth) axis using Numba. Output shape is (D, H)."""
        D, H, W = data.shape
        out = np.zeros((D, H), dtype=data.dtype)
        for z in numba.prange(D):  # type: ignore
            for y in range(H):
                max_val = data[z, y, 0]
                for x in range(W):
                    val = data[z, y, x]
                    if depth_cueing_strength > 0.0:
                        factor = 1.0 - depth_cueing_strength * (x / max(1.0, W - 1))
                        val = val * factor
                    if val > max_val:
                        max_val = val
                out[z, y] = max_val
        return out


    @numba.njit(parallel=True, cache=True, fastmath=True)
    def project_mip_z_rotated(data: np.ndarray, theta: float, depth_cueing_strength: float) -> np.ndarray:
        """Compute rotated MIP along Z (rotation around Y). Output shape is (H, W)."""
        D, H, W = data.shape
        diag = int(np.ceil(np.sqrt(D**2 + W**2)))
        out = np.zeros((H, W), dtype=data.dtype)
        
        cz = (D - 1) / 2.0
        cx = (W - 1) / 2.0
        cos_t = np.cos(theta)
        sin_t = np.sin(theta)
        
        # Precompute coordinates and bounds
        r_start = np.zeros(W, dtype=np.int32)
        r_end = np.zeros(W, dtype=np.int32)
        x_indices = np.zeros((W, diag), dtype=np.int32)
        z_indices = np.zeros((W, diag), dtype=np.int32)
        
        for x_out in range(W):
            v = x_out - cx
            first_valid = -1
            last_valid = -1
            for r in range(diag):
                u = r - (diag - 1) / 2.0
                x_rot = cx + v * cos_t - u * sin_t
                z_rot = cz + v * sin_t + u * cos_t
                xi = int(np.round(x_rot))
                zi = int(np.round(z_rot))
                if 0 <= xi < W and 0 <= zi < D:
                    if first_valid == -1:
                        first_valid = r
                    last_valid = r
                    x_indices[x_out, r] = xi
                    z_indices[x_out, r] = zi
            r_start[x_out] = first_valid
            r_end[x_out] = last_valid + 1 if last_valid != -1 else -1
        
        for y in numba.prange(H):  # type: ignore
            for x_out in range(W):
                rs = r_start[x_out]
                re = r_end[x_out]
                if rs != -1:
                    val0 = data[z_indices[x_out, rs], y, x_indices[x_out, rs]]
                    if depth_cueing_strength > 0.0:
                        factor = 1.0 - depth_cueing_strength * (rs / max(1.0, diag - 1))
                        val0 = val0 * factor
                    max_val = val0
                    
                    for r in range(rs + 1, re):
                        xi = x_indices[x_out, r]
                        zi = z_indices[x_out, r]
                        val = data[zi, y, xi]
                        if depth_cueing_strength > 0.0:
                            factor = 1.0 - depth_cueing_strength * (r / max(1.0, diag - 1))
                            val = val * factor
                        if val > max_val:
                            max_val = val
                    out[y, x_out] = max_val
        return out


    @numba.njit(parallel=True, cache=True, fastmath=True)
    def project_mip_y_rotated(data: np.ndarray, theta: float, depth_cueing_strength: float) -> np.ndarray:
        """Compute rotated MIP along Y (rotation around Z). Output shape is (D, W)."""
        D, H, W = data.shape
        diag = int(np.ceil(np.sqrt(H**2 + W**2)))
        out = np.zeros((D, W), dtype=data.dtype)
        
        cy = (H - 1) / 2.0
        cx = (W - 1) / 2.0
        cos_t = np.cos(theta)
        sin_t = np.sin(theta)
        
        # Precompute coordinates and bounds
        r_start = np.zeros(W, dtype=np.int32)
        r_end = np.zeros(W, dtype=np.int32)
        x_indices = np.zeros((W, diag), dtype=np.int32)
        y_indices = np.zeros((W, diag), dtype=np.int32)
        
        for x_out in range(W):
            v = x_out - cx
            first_valid = -1
            last_valid = -1
            for r in range(diag):
                u = r - (diag - 1) / 2.0
                x_rot = cx + v * cos_t - u * sin_t
                y_rot = cy + v * sin_t + u * cos_t
                xi = int(np.round(x_rot))
                yi = int(np.round(y_rot))
                if 0 <= xi < W and 0 <= yi < H:
                    if first_valid == -1:
                        first_valid = r
                    last_valid = r
                    x_indices[x_out, r] = xi
                    y_indices[x_out, r] = yi
            r_start[x_out] = first_valid
            r_end[x_out] = last_valid + 1 if last_valid != -1 else -1
                    
        for z in numba.prange(D):  # type: ignore
            for x_out in range(W):
                rs = r_start[x_out]
                re = r_end[x_out]
                if rs != -1:
                    val0 = data[z, y_indices[x_out, rs], x_indices[x_out, rs]]
                    if depth_cueing_strength > 0.0:
                        factor = 1.0 - depth_cueing_strength * (rs / max(1.0, diag - 1))
                        val0 = val0 * factor
                    max_val = val0
                    
                    for r in range(rs + 1, re):
                        xi = x_indices[x_out, r]
                        yi = y_indices[x_out, r]
                        val = data[z, yi, xi]
                        if depth_cueing_strength > 0.0:
                            factor = 1.0 - depth_cueing_strength * (r / max(1.0, diag - 1))
                            val = val * factor
                        if val > max_val:
                            max_val = val
                    out[z, x_out] = max_val
        return out


    @numba.njit(parallel=True, cache=True, fastmath=True)
    def project_mip_x_rotated(data: np.ndarray, theta: float, depth_cueing_strength: float) -> np.ndarray:
        """Compute rotated MIP along X (rotation around Z). Output shape is (D, H)."""
        D, H, W = data.shape
        diag = int(np.ceil(np.sqrt(W**2 + H**2)))
        out = np.zeros((D, H), dtype=data.dtype)
        
        cx = (W - 1) / 2.0
        cy = (H - 1) / 2.0
        cos_t = np.cos(theta)
        sin_t = np.sin(theta)
        
        # Precompute coordinates and bounds
        r_start = np.zeros(H, dtype=np.int32)
        r_end = np.zeros(H, dtype=np.int32)
        y_indices = np.zeros((H, diag), dtype=np.int32)
        x_indices = np.zeros((H, diag), dtype=np.int32)
        
        for y_out in range(H):
            v = y_out - cy
            first_valid = -1
            last_valid = -1
            for r in range(diag):
                u = r - (diag - 1) / 2.0
                y_rot = cy + v * cos_t - u * sin_t
                x_rot = cx + v * sin_t + u * cos_t
                yi = int(np.round(y_rot))
                xi = int(np.round(x_rot))
                if 0 <= xi < W and 0 <= yi < H:
                    if first_valid == -1:
                        first_valid = r
                    last_valid = r
                    y_indices[y_out, r] = yi
                    x_indices[y_out, r] = xi
            r_start[y_out] = first_valid
            r_end[y_out] = last_valid + 1 if last_valid != -1 else -1
                    
        for z in numba.prange(D):  # type: ignore
            for y_out in range(H):
                rs = r_start[y_out]
                re = r_end[y_out]
                if rs != -1:
                    val0 = data[z, y_indices[y_out, rs], x_indices[y_out, rs]]
                    if depth_cueing_strength > 0.0:
                        factor = 1.0 - depth_cueing_strength * (rs / max(1.0, diag - 1))
                        val0 = val0 * factor
                    max_val = val0
                    
                    for r in range(rs + 1, re):
                        yi = y_indices[y_out, r]
                        xi = x_indices[y_out, r]
                        val = data[z, yi, xi]
                        if depth_cueing_strength > 0.0:
                            factor = 1.0 - depth_cueing_strength * (r / max(1.0, diag - 1))
                            val = val * factor
                        if val > max_val:
                            max_val = val
                    out[z, y_out] = max_val
        return out
else:
    def project_mip_z(data: np.ndarray, depth_cueing_strength: float) -> np.ndarray:
        """Compute MIP along the Z (depth) axis using NumPy. Output shape is (H, W)."""
        D, H, W = data.shape
        if depth_cueing_strength <= 0.0:
            return np.max(data, axis=0)
        factors = 1.0 - depth_cueing_strength * (np.arange(D, dtype=np.float32) / max(1.0, D - 1))
        # Add dimensions for broadcasting: shape (D, 1, 1)
        factors = factors[:, np.newaxis, np.newaxis]
        attenuated = data * factors
        return np.max(attenuated, axis=0)


    def project_mip_y(data: np.ndarray, depth_cueing_strength: float) -> np.ndarray:
        """Compute MIP along the Y (depth) axis using NumPy. Output shape is (D, W)."""
        D, H, W = data.shape
        if depth_cueing_strength <= 0.0:
            return np.max(data, axis=1)
        factors = 1.0 - depth_cueing_strength * (np.arange(H, dtype=np.float32) / max(1.0, H - 1))
        # Add dimensions for broadcasting: shape (1, H, 1)
        factors = factors[np.newaxis, :, np.newaxis]
        attenuated = data * factors
        return np.max(attenuated, axis=1)


    def project_mip_x(data: np.ndarray, depth_cueing_strength: float) -> np.ndarray:
        """Compute MIP along the X (depth) axis using NumPy. Output shape is (D, H)."""
        D, H, W = data.shape
        if depth_cueing_strength <= 0.0:
            return np.max(data, axis=2)
        factors = 1.0 - depth_cueing_strength * (np.arange(W, dtype=np.float32) / max(1.0, W - 1))
        # Add dimensions for broadcasting: shape (1, 1, W)
        factors = factors[np.newaxis, np.newaxis, :]
        attenuated = data * factors
        return np.max(attenuated, axis=2)


    def project_mip_z_rotated(data: np.ndarray, theta: float, depth_cueing_strength: float) -> np.ndarray:
        """Compute rotated MIP along Z using NumPy. Output shape is (H, W)."""
        D, H, W = data.shape
        diag = int(np.ceil(np.sqrt(D**2 + W**2)))
        
        cz = (D - 1) / 2.0
        cx = (W - 1) / 2.0
        cos_t = np.cos(theta)
        sin_t = np.sin(theta)
        
        u = np.arange(diag, dtype=np.float32) - (diag - 1) / 2.0
        
        x_out = np.arange(W)[:, np.newaxis]
        v = x_out - cx
        
        xr = np.round(cx + v * cos_t - u * sin_t).astype(np.int32)
        zr = np.round(cz + v * sin_t + u * cos_t).astype(np.int32)
        
        mask = (xr >= 0) & (xr < W) & (zr >= 0) & (zr < D)
        
        xr_clipped = np.clip(xr, 0, W - 1)
        zr_clipped = np.clip(zr, 0, D - 1)
        
        vals = data[zr_clipped[:, np.newaxis, :], np.arange(H)[np.newaxis, :, np.newaxis], xr_clipped[:, np.newaxis, :]]
        
        if depth_cueing_strength > 0.0:
            factors = 1.0 - depth_cueing_strength * (np.arange(diag, dtype=np.float32) / max(1.0, diag - 1))[np.newaxis, np.newaxis, :]
            vals = vals * factors
            
        fill_value = np.iinfo(data.dtype).min if np.issubdtype(data.dtype, np.integer) else -np.inf
        vals = np.where(mask[:, np.newaxis, :], vals, fill_value)
        
        return np.max(vals, axis=2).T.astype(data.dtype)


    def project_mip_y_rotated(data: np.ndarray, theta: float, depth_cueing_strength: float) -> np.ndarray:
        """Compute rotated MIP along Y using NumPy. Output shape is (D, W)."""
        D, H, W = data.shape
        diag = int(np.ceil(np.sqrt(H**2 + W**2)))
        
        cy = (H - 1) / 2.0
        cx = (W - 1) / 2.0
        cos_t = np.cos(theta)
        sin_t = np.sin(theta)
        
        u = np.arange(diag, dtype=np.float32) - (diag - 1) / 2.0
        
        x_out = np.arange(W)[:, np.newaxis]
        v = x_out - cx
        
        xr = np.round(cx + v * cos_t - u * sin_t).astype(np.int32)
        yr = np.round(cy + v * sin_t + u * cos_t).astype(np.int32)
        
        mask = (xr >= 0) & (xr < W) & (yr >= 0) & (yr < H)
        
        xr_clipped = np.clip(xr, 0, W - 1)
        yr_clipped = np.clip(yr, 0, H - 1)
        
        vals = data[np.arange(D)[np.newaxis, :, np.newaxis], yr_clipped[:, np.newaxis, :], xr_clipped[:, np.newaxis, :]]
        
        if depth_cueing_strength > 0.0:
            factors = 1.0 - depth_cueing_strength * (np.arange(diag, dtype=np.float32) / max(1.0, diag - 1))[np.newaxis, np.newaxis, :]
            vals = vals * factors
            
        fill_value = np.iinfo(data.dtype).min if np.issubdtype(data.dtype, np.integer) else -np.inf
        vals = np.where(mask[:, np.newaxis, :], vals, fill_value)
        
        return np.max(vals, axis=2).T.astype(data.dtype)


    def project_mip_x_rotated(data: np.ndarray, theta: float, depth_cueing_strength: float) -> np.ndarray:
        """Compute rotated MIP along X using NumPy. Output shape is (D, H)."""
        D, H, W = data.shape
        diag = int(np.ceil(np.sqrt(W**2 + H**2)))
        
        cx = (W - 1) / 2.0
        cy = (H - 1) / 2.0
        cos_t = np.cos(theta)
        sin_t = np.sin(theta)
        
        u = np.arange(diag, dtype=np.float32) - (diag - 1) / 2.0
        
        y_out = np.arange(H)[:, np.newaxis]
        v = y_out - cy
        
        yr = np.round(cy + v * cos_t - u * sin_t).astype(np.int32)
        xr = np.round(cx + v * sin_t + u * cos_t).astype(np.int32)
        
        mask = (xr >= 0) & (xr < W) & (yr >= 0) & (yr < H)
        
        xr_clipped = np.clip(xr, 0, W - 1)
        yr_clipped = np.clip(yr, 0, H - 1)
        
        vals = data[np.arange(D)[np.newaxis, :, np.newaxis], yr_clipped[:, np.newaxis, :], xr_clipped[:, np.newaxis, :]]
        
        if depth_cueing_strength > 0.0:
            factors = 1.0 - depth_cueing_strength * (np.arange(diag, dtype=np.float32) / max(1.0, diag - 1))[np.newaxis, np.newaxis, :]
            vals = vals * factors
            
        fill_value = np.iinfo(data.dtype).min if np.issubdtype(data.dtype, np.integer) else -np.inf
        vals = np.where(mask[:, np.newaxis, :], vals, fill_value)
        
        return np.max(vals, axis=2).T.astype(data.dtype)


def compute_mip_projection(
    data: np.ndarray,
    axis: str,
    depth_cueing: bool,
    depth_cueing_strength: float = 0.5,
    rotation_angle: float = 0.0,
) -> np.ndarray:
    """Helper to dispatch to the correct function based on selected axis and rotation angle (in degrees)."""
    strength = depth_cueing_strength if depth_cueing else 0.0
    axis_upper = axis.upper()
    theta = np.deg2rad(rotation_angle)
    
    use_rotation = abs(theta) > 1e-5
    
    if axis_upper == "Z":
        return project_mip_z_rotated(data, theta, strength) if use_rotation else project_mip_z(data, strength)
    elif axis_upper == "Y":
        return project_mip_y_rotated(data, theta, strength) if use_rotation else project_mip_y(data, strength)
    elif axis_upper == "X":
        return project_mip_x_rotated(data, theta, strength) if use_rotation else project_mip_x(data, strength)
    else:
        raise ValueError(f"Invalid projection axis: {axis}")
