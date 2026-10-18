import itertools
import numpy as np
import logging

logger = logging.getLogger(__name__)


def extract_orientation_strings(raw_img):
    """Extracts the original matrix and formats it for the GUI. Handles 3D and 4D."""
    raw_dir = raw_img.GetDirection()

    # Safely extract the 3x3 spatial component regardless of 3D (9) or 4D (16)
    if len(raw_dir) == 16:
        m = np.array(raw_dir)
        orig_mat = np.array(
            [[m[0], m[1], m[2]], [m[4], m[5], m[6]], [m[8], m[9], m[10]]]
        )
    elif len(raw_dir) == 9:
        orig_mat = np.array(raw_dir).reshape(3, 3)
    else:
        orig_mat = np.eye(3)

    # 1. Generate the exact 3x3 tooltip string
    tooltip_str = (
        f"{orig_mat[0,0]:.6g}  {orig_mat[0,1]:.6g}  {orig_mat[0,2]:.6g}\n"
        f"{orig_mat[1,0]:.6g}  {orig_mat[1,1]:.6g}  {orig_mat[1,2]:.6g}\n"
        f"{orig_mat[2,0]:.6g}  {orig_mat[2,1]:.6g}  {orig_mat[2,2]:.6g}"
    )

    # 2. Generate the compact sidebar string
    if np.allclose(orig_mat, np.eye(3), atol=1e-4):
        display_str = "ID"
    elif np.allclose(np.abs(orig_mat).sum(axis=0), 1.0, atol=1e-4) and np.allclose(
        np.abs(orig_mat).sum(axis=1), 1.0, atol=1e-4
    ):

        def fmt_val(v):
            return "1" if v > 0.5 else "-1" if v < -0.5 else "0"

        rows = [" ".join(fmt_val(x) for x in row) for row in orig_mat]
        display_str = " ; ".join(rows)
    else:
        display_str = "Oblique"

    return display_str, tooltip_str


def _is_signed_permutation(m, atol=1e-4):
    """True if the direction matrix only flips and/or swaps axes (entries 0 or ±1)."""
    p = np.round(m)
    return (
        np.allclose(m, p, atol=atol)
        and np.all(np.abs(p).sum(axis=0) == 1)
        and np.all(np.abs(p).sum(axis=1) == 1)
    )


def straighten_image(img, filename="image", is_label_map=False):
    """
    Intercepts oblique/rotated images and warps them into a perfectly
    straight bounding box aligned with the physical axes.
    """
    import SimpleITK as sitk
    dim = img.GetDimension()

    if dim == 4:
        return img

    identity_dir = np.eye(dim).flatten()
    current_dir = np.array(img.GetDirection())

    # If the image is already perfectly aligned, do nothing.
    if np.allclose(current_dir, identity_dir, atol=1e-4):
        return img

    # Axis flips/permutations only (e.g. RAS NIfTI, sagittal acquisitions):
    # reorder the voxels exactly instead of resampling.
    if dim == 3 and _is_signed_permutation(current_dir.reshape(3, 3)):
        out = sitk.DICOMOrient(img, "LPS")
        if np.allclose(out.GetDirection(), identity_dir, atol=1e-4):
            out.SetDirection(identity_dir.tolist())
            return out

    logger.warning(
        f"Oblique orientation detected in {filename}. Straightening to physical grid..."
    )
    return _resample_axis_aligned(img, is_label_map)


def _resample_axis_aligned(img, is_label_map=False):
    """Linearly resample img onto an identity-direction grid covering all its voxel centres.

    Each output (physical) axis takes the spacing of the index axis that maps
    mostly onto it, so a pure flip/permutation would give back the original grid.
    """
    import SimpleITK as sitk

    dim = img.GetDimension()
    identity_dir = np.eye(dim).flatten()

    # Bounding box of the voxel centres (last index is size - 1)
    size = img.GetSize()
    corners = list(itertools.product(*[(0, s - 1) for s in size]))
    phys_corners = np.array([img.TransformIndexToPhysicalPoint(c) for c in corners])
    min_phys = np.min(phys_corners, axis=0)
    max_phys = np.max(phys_corners, axis=0)

    m = np.array(img.GetDirection()).reshape(dim, dim)
    spacing = np.array(img.GetSpacing())[np.argmax(np.abs(m), axis=1)]
    new_size = np.ceil((max_phys - min_phys) / spacing - 1e-6).astype(int) + 1

    resampler = sitk.ResampleImageFilter()
    resampler.SetOutputDirection(identity_dir.tolist())
    resampler.SetOutputOrigin(min_phys.tolist())
    resampler.SetOutputSpacing(spacing.tolist())
    resampler.SetSize(new_size.tolist())
    if is_label_map:
        resampler.SetInterpolator(sitk.sitkNearestNeighbor)
    else:
        resampler.SetInterpolator(sitk.sitkLinear)

    try:
        bg_val = float(sitk.GetArrayViewFromImage(img).min())
    except Exception:
        bg_val = 0.0
    resampler.SetDefaultPixelValue(bg_val)

    return resampler.Execute(img)


def compute_colorscale_gradient(
    wl: float, ww: float, cmap_name: str, img_min: float, img_max: float
) -> list[float]:
    """Computes a 256-step RGBA gradient list for visualising a colormap colorscale

    under window/level settings. Values below lower bound are mapped to black,
    and values above upper bound are mapped to white.
    """
    from vvv.config import COLORMAPS

    cmap = COLORMAPS.get(cmap_name, COLORMAPS["Grayscale"])
    lower, upper = wl - ww / 2.0, wl + ww / 2.0
    x = np.linspace(img_min, img_max, 256, dtype=np.float32)
    t = np.clip((x - lower) / max(ww, 1e-10), 0.0, 1.0)
    idx = (t * 255).astype(np.int32)
    colors = cmap[idx].copy()
    colors[x < lower] = [0.0, 0.0, 0.0, 1.0]
    colors[x > upper] = [1.0, 1.0, 1.0, 1.0]
    return colors.flatten().tolist()

