import pytest
import numpy as np
import SimpleITK as sitk
from vvv.maths.image import VolumeData
from vvv.maths.geometry import SpatialEngine


def test_load_2d_rgb_rgba_images(tmp_path):
    """Test that 2D PNG and JPG images (RGB and RGBA) load safely into 3D spaces without dimension mismatch."""

    # 1. Create a 2D RGB image
    data_rgb = np.zeros((20, 30, 3), dtype=np.uint8)
    data_rgb[:, :, 0] = 255  # Red channel
    img_rgb = sitk.GetImageFromArray(data_rgb, isVector=True)

    png_path = str(tmp_path / "test_rgb.png")
    jpg_path = str(tmp_path / "test_rgb.jpg")

    sitk.WriteImage(img_rgb, png_path)
    sitk.WriteImage(img_rgb, jpg_path)

    # Test PNG (RGB)
    vol_png = VolumeData(png_path)
    assert vol_png.is_rgb is True
    assert vol_png.num_components == 3
    assert vol_png.shape3d == (1, 20, 30)
    assert vol_png.data.shape == (1, 20, 30, 3)

    # Test JPG (RGB)
    vol_jpg = VolumeData(jpg_path)
    assert vol_jpg.is_rgb is True
    assert vol_jpg.num_components == 3
    assert vol_jpg.shape3d == (1, 20, 30)
    assert vol_jpg.data.shape == (1, 20, 30, 3)

    # 2. Create a 2D RGBA image
    data_rgba = np.zeros((20, 30, 4), dtype=np.uint8)
    data_rgba[:, :, 3] = 255  # Alpha channel
    img_rgba = sitk.GetImageFromArray(data_rgba, isVector=True)

    rgba_path = str(tmp_path / "test_rgba.png")
    sitk.WriteImage(img_rgba, rgba_path)

    # Test PNG (RGBA)
    vol_rgba = VolumeData(rgba_path)
    assert vol_rgba.is_rgb is True
    assert vol_rgba.num_components == 4
    assert vol_rgba.shape3d == (1, 20, 30)
    assert vol_rgba.data.shape == (1, 20, 30, 4)

    # 3. Verify Spatial Engine Dimension Safety
    # This explicitly tests the fix for the vector dimension mismatch exception
    engine = SpatialEngine(vol_png)
    phys = engine.raw_voxel_to_phys([5.0, 5.0, 0.0])
    assert len(phys) == 3

    vox = engine.phys_to_raw_voxel(phys)
    assert len(vox) == 3
