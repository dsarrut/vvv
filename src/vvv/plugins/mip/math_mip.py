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


def compute_mip_projection(
    data: np.ndarray, axis: str, depth_cueing: bool, depth_cueing_strength: float = 0.5
) -> np.ndarray:
    """Helper to dispatch to the correct function based on selected axis."""
    strength = depth_cueing_strength if depth_cueing else 0.0
    axis_upper = axis.upper()
    if axis_upper == "Z":
        return project_mip_z(data, strength)
    elif axis_upper == "Y":
        return project_mip_y(data, strength)
    elif axis_upper == "X":
        return project_mip_x(data, strength)
    else:
        raise ValueError(f"Invalid projection axis: {axis}")
