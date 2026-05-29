"""
Pure ITK resampling for overlay fusion.

resample_overlay() has no side effects: it takes volumes and transforms,
runs ResampleImageFilter (which releases the GIL), and returns the result.
Thread-safety (tombstone pattern) and job-id staleness checks are the
caller's responsibility — see Controller._apply_overlay_resample().
"""

from __future__ import annotations

import numpy as np
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from vvv.maths.image import VolumeData


def resample_overlay(
    base_vol: "VolumeData",
    overlay_vol: "VolumeData",
    base_transform,    # sitk.Transform | None  (None when transform is inactive)
    overlay_transform, # sitk.Transform | None  (None when transform is inactive)
) -> tuple:
    """
    Resample overlay_vol onto the physical grid of base_vol.

    [ASYNC_BOUNDARY] SimpleITK ResampleImageFilter.Execute() releases the GIL.
    The caller must keep the previous _sitk_overlay_cache alive as a local
    variable throughout this call (tombstone pattern) so the 60fps render
    thread never reads a freed numpy view.

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

    # Build a 3D reference image that matches base_vol's physical grid.
    # Always 3D even when volumes are 4D to prevent ITK dimension mismatch.
    ref_img = sitk.Image(
        base_vol.shape3d[2],
        base_vol.shape3d[1],
        base_vol.shape3d[0],
        sitk.sitkUInt8,
    )
    ref_img.SetSpacing(base_vol.spacing.tolist())
    ref_img.SetOrigin(base_vol.origin.tolist())
    ref_img.SetDirection(base_vol.matrix.flatten().tolist())

    resampler = sitk.ResampleImageFilter()
    resampler.SetReferenceImage(ref_img)
    resampler.SetInterpolator(sitk.sitkLinear)
    resampler.SetDefaultPixelValue(np.min(overlay_vol.data).item())

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

    if target_dim == 3:
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
