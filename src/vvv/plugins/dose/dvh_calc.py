from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Any
import numpy as np


@dataclass
class ROI_DVH_Curve:
    roi_id: str
    roi_name: str
    color: List[int]            # [R, G, B, A]
    volume_cc: float            # Total volume in cm³ (cc)
    doses: np.ndarray           # X values (Gy)
    volume_percent: np.ndarray  # Y values (0 to 100%)
    volume_absolute: np.ndarray # Y values in cm³
    diff_volume_percent: np.ndarray # Differential Y values (%)
    diff_volume_absolute: np.ndarray# Differential Y values (cm³)
    min_dose: float
    mean_dose: float
    median_dose: float          # D50%
    max_dose: float
    d98: float                  # Near-min dose (dose to >=98% volume)
    d95: float                  # Dose to >=95% volume
    d2: float                   # Near-max dose (dose to >=2% volume)
    enabled: bool = True


def compute_roi_dvh(
    dose_vol: Any,
    roi_vol: Any,
    roi_name: str,
    color: List[int],
    num_bins: int = 200,
    max_eval_dose: Optional[float] = None,
) -> Optional[ROI_DVH_Curve]:
    """
    Computes cumulative and differential DVH for a single ROI against a 3D dose volume.
    Handles differing spatial resolution/orientation between dose and ROI grids
    using SimpleITK linear interpolation within the ROI.
    """
    import SimpleITK as sitk  # lazy: not needed to start vvv

    if not hasattr(roi_vol, "sitk_image") or roi_vol.sitk_image is None:
        return None
    if not hasattr(dose_vol, "sitk_image") or dose_vol.sitk_image is None:
        return None

    r_sitk = roi_vol.sitk_image
    r_arr = roi_vol.data[0] if getattr(roi_vol.data, "ndim", 3) == 4 else roi_vol.data
    mask = r_arr > 0
    if not np.any(mask):
        return None

    # Voxel volume of the ROI in cm³ (1 cm³ = 1000 mm³)
    sp = r_sitk.GetSpacing()
    voxel_vol_cc = (abs(sp[0] * sp[1] * sp[2])) / 1000.0
    total_voxels = int(np.count_nonzero(mask))
    total_vol_cc = total_voxels * voxel_vol_cc

    # Sample dose into ROI geometry using SimpleITK linear interpolation
    try:
        dose_in_roi = sitk.Resample(
            dose_vol.sitk_image,
            r_sitk,
            sitk.Transform(),
            sitk.sitkLinear,
            0.0,
            sitk.sitkFloat32,
        )
        dose_arr = sitk.GetArrayFromImage(dose_in_roi)
    except Exception:
        # Fallback if resample fails: direct array if shapes match
        if dose_vol.data.shape == r_arr.shape:
            dose_arr = dose_vol.data[0] if dose_vol.data.ndim == 4 else dose_vol.data
        else:
            return None

    vox_doses = dose_arr[mask].astype(np.float64)
    if len(vox_doses) == 0:
        return None

    sorted_doses = np.sort(vox_doses)
    min_dose = float(sorted_doses[0])
    max_dose = float(sorted_doses[-1])
    mean_dose = float(np.mean(sorted_doses))
    median_dose = float(np.median(sorted_doses))

    # Dosimetric percentiles
    # D98 = dose received by at least 98% of volume (2nd percentile of sorted doses)
    d98 = float(np.percentile(sorted_doses, 2.0))
    d95 = float(np.percentile(sorted_doses, 5.0))
    d2 = float(np.percentile(sorted_doses, 98.0))

    # Evaluation dose bins for plotting
    upper_limit = max_eval_dose if max_eval_dose is not None else max(max_dose * 1.05, 1.0)
    d_eval = np.linspace(0.0, upper_limit, num_bins)

    # Fast cumulative calculation using searchsorted:
    # count of voxels with dose >= d is (total_voxels - insertion_index)
    idx = np.searchsorted(sorted_doses, d_eval, side="left")
    counts_ge = total_voxels - idx
    vol_pct = (counts_ge / total_voxels) * 100.0
    vol_abs = counts_ge * voxel_vol_cc

    # Differential DVH (histogram)
    hist_counts, _ = np.histogram(sorted_doses, bins=len(d_eval) - 1, range=(0.0, upper_limit))
    diff_pct = np.zeros_like(d_eval)
    diff_abs = np.zeros_like(d_eval)
    diff_pct[:-1] = (hist_counts / total_voxels) * 100.0
    diff_abs[:-1] = hist_counts * voxel_vol_cc
    diff_pct[-1] = 0.0
    diff_abs[-1] = 0.0

    return ROI_DVH_Curve(
        roi_id=str(getattr(roi_vol, "name", "roi")),
        roi_name=roi_name,
        color=list(color),
        volume_cc=total_vol_cc,
        doses=d_eval,
        volume_percent=vol_pct,
        volume_absolute=vol_abs,
        diff_volume_percent=diff_pct,
        diff_volume_absolute=diff_abs,
        min_dose=min_dose,
        mean_dose=mean_dose,
        median_dose=median_dose,
        max_dose=max_dose,
        d98=d98,
        d95=d95,
        d2=d2,
        enabled=True,
    )

