import numpy as np
import SimpleITK as sitk

def extract_orientation_strings(raw_img):
    """Extracts the original matrix and formats it for the GUI."""
    orig_mat = np.array(raw_img.GetDirection()).reshape(3, 3)

    # 1. Generate the exact 3x3 tooltip string
    tooltip_str = (
        f"{orig_mat[0,0]:.6g}  {orig_mat[0,1]:.6g}  {orig_mat[0,2]:.6g}\n"
        f"{orig_mat[1,0]:.6g}  {orig_mat[1,1]:.6g}  {orig_mat[1,2]:.6g}\n"
        f"{orig_mat[2,0]:.6g}  {orig_mat[2,1]:.6g}  {orig_mat[2,2]:.6g}"
    )

    # 2. Generate the compact sidebar string
    if np.allclose(orig_mat, np.eye(3), atol=1e-4):
        display_str = "ID"
    elif np.allclose(np.abs(orig_mat).sum(axis=0), 1.0, atol=1e-4) and \
            np.allclose(np.abs(orig_mat).sum(axis=1), 1.0, atol=1e-4):
        def fmt_val(v): return "1" if v > 0.5 else "-1" if v < -0.5 else "0"
        rows = [" ".join(fmt_val(x) for x in row) for row in orig_mat]
        display_str = " ; ".join(rows)
    else:
        display_str = "Oblique"

    return display_str, tooltip_str


def straighten_image(img, filename="image"):
    """
    Intercepts oblique/rotated images and warps them into a perfectly
    straight bounding box aligned with the physical axes.
    """
    dim = img.GetDimension()
    identity_dir = np.eye(dim).flatten()
    current_dir = np.array(img.GetDirection())

    # If the image is already perfectly aligned, do nothing!
    if np.allclose(current_dir, identity_dir, atol=1e-4):
        return img

    import itertools
    print(f"Oblique orientation detected in {filename}. Straightening to physical grid...")

    size = img.GetSize()
    corners = list(itertools.product(*[(0, s) for s in size]))
    phys_corners = np.array([img.TransformIndexToPhysicalPoint(c) for c in corners])

    min_phys = np.min(phys_corners, axis=0)
    max_phys = np.max(phys_corners, axis=0)

    spacing = np.array(img.GetSpacing())
    new_size = np.ceil((max_phys - min_phys) / spacing).astype(int)

    resampler = sitk.ResampleImageFilter()
    resampler.SetOutputDirection(identity_dir.tolist())
    resampler.SetOutputOrigin(min_phys.tolist())
    resampler.SetOutputSpacing(spacing.tolist())
    resampler.SetSize(new_size.tolist())
    resampler.SetInterpolator(sitk.sitkLinear)

    try:
        bg_val = float(sitk.GetArrayViewFromImage(img).min())
    except Exception:
        bg_val = 0.0
    resampler.SetDefaultPixelValue(bg_val)

    return resampler.Execute(img)