"""
Pure ITK resampling for base and overlay images.

Both functions have no side effects: they take volumes and transforms,
run ResampleImageFilter (which releases the GIL), and return the result.
They run in background jobs (Controller.resample_image); the results are
applied on the main thread by the caller.
"""

from __future__ import annotations

import numpy as np
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from vvv.maths.image import VolumeData


def _outside_value(vol) -> float:
    """Value for voxels outside the resampled image: its minimum (background),
    or 0 for a displacement field (no displacement, not a fake vector)."""
    if getattr(vol, "is_dvf", False):
        return 0.0
    return float(vol.get_data_range()[0])  # cached: no full scan per resample


class CroppedOverlay:
    """An overlay resampled on a box of the base grid only, seen as the whole
    grid: indexing returns what the full array would (the fill value outside
    the box), so the slice, ROI and isodose readers are unchanged. A 64^3 PET
    on a 512x512x2926 CT is ~0.5 GB instead of 3 GB. 3D scalar overlays only;
    np.asarray() builds the full array (MIP)."""

    ndim = 3

    def __init__(self, crop, shape, start, fill, owner=None):
        self.crop = crop
        self._owner = owner  # the ITK image crop is a view of: kept alive
        self.shape = tuple(int(n) for n in shape)
        self.start = tuple(int(i) for i in start)
        self.fill = fill
        self.dtype = crop.dtype

    @property
    def nbytes(self):
        return self.crop.nbytes

    def __array__(self, dtype=None, copy=None):
        out = np.full(self.shape, self.fill, dtype=self.dtype)
        (z0, y0, x0), (dz, dy, dx) = self.start, self.crop.shape
        out[z0 : z0 + dz, y0 : y0 + dy, x0 : x0 + dx] = self.crop
        return out if dtype is None else out.astype(dtype)

    def __getitem__(self, key):
        if isinstance(key, np.ndarray):  # a boolean mask of the full grid
            return np.asarray(self)[key]
        key = key if isinstance(key, tuple) else (key,)
        if any(k is Ellipsis for k in key):
            i = next(i for i, k in enumerate(key) if k is Ellipsis)
            key = key[:i] + (slice(None),) * (3 - len(key) + 1) + key[i + 1 :]
        key = key + (slice(None),) * (3 - len(key))
        # Per axis: the output run that falls in the box, and the matching crop
        # slice (an index or a slice of the grid maps to a regular progression)
        shape, keep, out_sl, crop_sl = [], [], [], []
        for k, n, s0, m in zip(key, self.shape, self.start, self.crop.shape):
            full = np.arange(n)[k]  # IndexError out of the grid, as an array
            keep.append(np.ndim(full) > 0)
            local = np.atleast_1d(full) - s0
            shape.append(len(local))
            inside = np.flatnonzero((local >= 0) & (local < m))
            if inside.size == 0:
                crop_sl = None
                continue
            lo, hi = int(inside[0]), int(inside[-1]) + 1
            step = int(local[lo + 1] - local[lo]) if hi - lo > 1 else 1
            stop = int(local[hi - 1]) + step
            out_sl.append(slice(lo, hi))
            if crop_sl is not None:
                crop_sl.append(slice(int(local[lo]), stop if stop >= 0 else None, step))
        out = np.full(shape, self.fill, dtype=self.dtype)
        if crop_sl is not None:
            out[tuple(out_sl)] = self.crop[tuple(crop_sl)]
        return out.reshape([n for n, k in zip(shape, keep) if k])


def _grid_box(base_vol, img, to_base):
    """(start, size) in x, y, z of the base grid box that covers img, its
    corners mapped by to_base (img physical -> base physical), +1 voxel."""
    n = img.GetSize()
    corners = [
        to_base.TransformPoint(img.TransformContinuousIndexToPhysicalPoint(
            [(-0.5, n[d] - 0.5)[(c >> d) & 1] for d in range(3)]))
        for c in range(8)
    ]
    rel = np.asarray(corners) - base_vol.origin
    idx = rel @ base_vol.matrix / base_vol.spacing  # continuous index, x y z
    full = np.array(base_vol.shape3d[::-1])
    start = np.clip(np.floor(idx.min(axis=0)).astype(int) - 1, 0, full - 1)
    end = np.clip(np.ceil(idx.max(axis=0)).astype(int) + 2, start + 1, full)
    return start.tolist(), (end - start).tolist()


def _overlay_box(base_vol, overlay_vol, composite):
    """(start, size) in x, y, z of the base grid box that covers the overlay
    (+1 voxel for the linear interpolation), or None for the whole grid (no
    gain, or a transform that cannot be inverted)."""
    try:
        to_base = composite.GetInverse()
    except Exception:
        return None
    start, size = _grid_box(base_vol, overlay_vol.sitk_image, to_base)
    if np.prod(size) > 0.5 * np.prod(base_vol.shape3d):
        return None
    return start, size


def resample_roi(base_vol, data, bbox, rotation_transform):
    """An ROI mask (3D, cropped to bbox of the base grid) as displayed while
    its image is shown rotated (resample_base): rotated the same way, nearest
    neighbour, on the box of the base grid it covers. Returns (data, bbox)."""
    import SimpleITK as sitk

    z0, z1, y0, y1, x0, x1 = bbox
    src = data.view(np.uint8) if data.dtype == bool else data
    img = sitk.GetImageFromArray(np.ascontiguousarray(src))
    img.SetSpacing(base_vol.spacing.tolist())
    img.SetDirection(base_vol.matrix.flatten().tolist())
    img.SetOrigin((base_vol.origin + base_vol.matrix @ (np.array([x0, y0, z0]) * base_vol.spacing)).tolist())
    start, size = _grid_box(base_vol, img, rotation_transform)  # read -> displayed

    resampler = sitk.ResampleImageFilter()
    resampler.SetSize(size)
    resampler.SetOutputSpacing(base_vol.spacing.tolist())
    resampler.SetOutputOrigin(
        (base_vol.origin + base_vol.matrix @ (np.array(start) * base_vol.spacing)).tolist()
    )
    resampler.SetOutputDirection(base_vol.matrix.flatten().tolist())
    resampler.SetInterpolator(sitk.sitkNearestNeighbor)
    resampler.SetDefaultPixelValue(0)
    resampler.SetTransform(rotation_transform.GetInverse())  # as resample_base
    out = sitk.GetArrayFromImage(resampler.Execute(img))
    if data.dtype == bool:
        out = out.astype(bool)
    (sx, sy, sz), (nx, ny, nz) = start, size
    return out, (sz, sz + nz, sy, sy + ny, sx, sx + nx)


def resample_overlay(
    base_vol: "VolumeData",
    overlay_vol: "VolumeData",
    base_transform,    # sitk.Transform | None  (None when transform is inactive)
    overlay_transform, # sitk.Transform | None  (None when transform is inactive)
) -> tuple:
    """
    Resample overlay_vol onto the physical grid of base_vol.

    Pure: safe in a worker thread (ResampleImageFilter.Execute releases the GIL).

    Returns:
        (sitk_cache, overlay_data, baked_translation)
        - sitk_cache: ITK image object; must be kept alive as long as overlay_data
          is in use, since overlay_data is a numpy view into it (or None for 2D).
        - overlay_data: numpy array of shape matching base_vol's 3D grid
          (or (C, Z, Y, X) for DVF).
        - baked_translation: (tx, ty, tz) delta translation baked into the
          resample; used later by compute_overlay_pixel_shift() to compute
          the residual live-alignment shift.
    """
    import SimpleITK as sitk

    # The output grid is base_vol's physical grid (always 3D, even for 4D
    # volumes, to prevent ITK dimension mismatch), set without allocating a
    # reference image of the base size
    resampler = sitk.ResampleImageFilter()
    resampler.SetSize([int(n) for n in base_vol.shape3d[::-1]])
    resampler.SetOutputSpacing(base_vol.spacing.tolist())
    resampler.SetOutputOrigin(base_vol.origin.tolist())
    resampler.SetOutputDirection(base_vol.matrix.flatten().tolist())
    resampler.SetInterpolator(sitk.sitkLinear)
    resampler.SetDefaultPixelValue(_outside_value(overlay_vol))

    # Map from base physical space → overlay physical space via composite transform.
    composite = sitk.CompositeTransform(3)
    if overlay_transform is not None:
        composite.AddTransform(overlay_transform.GetInverse())
    if base_transform is not None:
        base_tx_transform = sitk.TranslationTransform(3)
        base_tx_transform.SetOffset(base_transform.GetTranslation())
        composite.AddTransform(base_tx_transform)
    resampler.SetTransform(composite)

    target_dim = overlay_vol.sitk_image.GetDimension()

    box = None
    if target_dim == 3 and overlay_vol.num_components == 1 and not overlay_vol.is_rgb:
        box = _overlay_box(base_vol, overlay_vol, composite)
    if box is not None:  # only the box of the base grid that the overlay covers
        start, size = box
        resampler.SetSize(size)
        resampler.SetOutputOrigin(
            (base_vol.origin + base_vol.matrix @ (np.array(start) * base_vol.spacing)).tolist()
        )
        resampled_img = resampler.Execute(overlay_vol.sitk_image)  # GIL released
        overlay_data = CroppedOverlay(
            sitk.GetArrayViewFromImage(resampled_img),
            base_vol.shape3d,
            start[::-1],
            resampler.GetDefaultPixelValue(),
            owner=resampled_img,
        )
        sitk_cache = resampled_img

    elif target_dim == 3:
        resampled_img = resampler.Execute(overlay_vol.sitk_image)  # GIL released
        overlay_data = sitk.GetArrayViewFromImage(resampled_img)
        if getattr(overlay_vol, "is_dvf", False) and overlay_data.ndim == 4:
            overlay_data = np.moveaxis(overlay_data, -1, 0)
        sitk_cache = resampled_img

    elif target_dim == 4:
        resampled_volumes = []
        for t in range(overlay_vol.num_timepoints):
            size = list(overlay_vol.sitk_image.GetSize())
            size[3] = 0
            vol_3d = sitk.Extract(overlay_vol.sitk_image, size, [0, 0, 0, t])
            resampled_volumes.append(resampler.Execute(vol_3d))  # GIL released
        joined_img = sitk.JoinSeries(resampled_volumes)
        sitk_cache = joined_img
        overlay_data = sitk.GetArrayViewFromImage(joined_img)

    else:
        # 2D or unsupported dimension: fall back to raw data (no resampling)
        sitk_cache = None
        overlay_data = overlay_vol.data

    # The baked translation is the transform delta that was folded into the
    # resample grid. compute_overlay_pixel_shift() subtracts this from the
    # current live transform to get the residual pixel offset.
    ov_tx, ov_ty, ov_tz = (
        overlay_transform.GetTranslation() if overlay_transform is not None
        else (0.0, 0.0, 0.0)
    )
    base_tx, base_ty, base_tz = (
        base_transform.GetTranslation() if base_transform is not None
        else (0.0, 0.0, 0.0)
    )
    baked_translation = (
        ov_tx - base_tx,
        ov_ty - base_ty,
        ov_tz - base_tz,
    )

    return sitk_cache, overlay_data, baked_translation


def resample_base(vol: "VolumeData", rotation_transform) -> tuple:
    """
    Resample vol onto its own grid after applying a rotation-only transform.
    Used when the base image has an active rotation (registration preview).

    Pure: safe in a worker thread (ResampleImageFilter.Execute releases the GIL).

    Returns:
        (sitk_cache, base_display_data)
        - sitk_cache: ITK image object kept alive so base_display_data
          (a numpy view into it) stays valid. None for unsupported dims.
        - base_display_data: numpy array, or None for unsupported dims.
    """
    import SimpleITK as sitk

    ref_img = sitk.Image(
        vol.shape3d[2],
        vol.shape3d[1],
        vol.shape3d[0],
        sitk.sitkUInt8,
    )
    ref_img.SetSpacing(vol.spacing.tolist())
    ref_img.SetOrigin(vol.origin.tolist())
    ref_img.SetDirection(vol.matrix.flatten().tolist())

    resampler = sitk.ResampleImageFilter()
    resampler.SetReferenceImage(ref_img)
    resampler.SetInterpolator(sitk.sitkLinear)
    resampler.SetDefaultPixelValue(_outside_value(vol))
    resampler.SetTransform(rotation_transform.GetInverse())

    target_dim = vol.sitk_image.GetDimension()

    if target_dim == 3:
        resampled_img = resampler.Execute(vol.sitk_image)  # GIL released
        base_data = sitk.GetArrayViewFromImage(resampled_img)
        if getattr(vol, "is_dvf", False) and base_data.ndim == 4:
            base_data = np.moveaxis(base_data, -1, 0)
        return resampled_img, base_data

    elif target_dim == 4:
        resampled_volumes = []
        for t in range(vol.num_timepoints):
            size = list(vol.sitk_image.GetSize())
            size[3] = 0
            vol_3d = sitk.Extract(vol.sitk_image, size, [0, 0, 0, t])
            resampled_volumes.append(resampler.Execute(vol_3d))  # GIL released
        joined_img = sitk.JoinSeries(resampled_volumes)
        return joined_img, sitk.GetArrayViewFromImage(joined_img)

    else:
        return None, None
