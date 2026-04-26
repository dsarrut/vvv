import pytest
import numpy as np
import SimpleITK as sitk
from vvv.maths.image import VolumeData
from vvv.maths.geometry import SpatialEngine


@pytest.mark.parametrize("ext", [".nii", ".nii.gz", ".mha", ".mhd", ".nrrd"])
def test_load_standard_3d_formats(tmp_path, ext):
    """Test that all standard ITK 3D formats can be written and successfully loaded."""
    data = np.zeros((5, 10, 15), dtype=np.float32)
    data.fill(100.0)
    img = sitk.GetImageFromArray(data)
    img.SetSpacing((1.5, 1.5, 2.0))

    path = str(tmp_path / f"test_3d{ext}")
    sitk.WriteImage(img, path)

    vol = VolumeData(path)
    assert vol.shape3d == (5, 10, 15)
    assert np.allclose(vol.spacing, (1.5, 1.5, 2.0))
    assert vol.data[2, 5, 7] == 100.0


@pytest.mark.parametrize("ext", [".png", ".jpg"])
def test_load_standard_2d_formats(tmp_path, ext):
    """Test that standard 2D formats are loaded and safely padded to 3D."""
    data = np.zeros((10, 15), dtype=np.uint8)
    data.fill(50)
    img = sitk.GetImageFromArray(data)
    img.SetSpacing((1.2, 1.2))

    path = str(tmp_path / f"test_2d{ext}")
    sitk.WriteImage(img, path)

    vol = VolumeData(path)
    # 2D images are dynamically padded to 3D with Z=1
    assert vol.shape3d == (1, 10, 15)
    assert vol.data[0, 5, 7] == 50


def test_load_custom_his_format(tmp_path):
    """Test the pure Python Heimann HIS (Elekta) parser with a mock binary payload."""
    import struct

    path = str(tmp_path / "test.his")
    width, height, frames = 15, 10, 3

    header = bytearray(68)
    header[0:4] = b"\x00\x70\x44\x00"
    struct.pack_into("<H", header, 10, 0)  # extra_header_size
    struct.pack_into("<H", header, 12, 0)  # ulx
    struct.pack_into("<H", header, 14, 0)  # uly
    struct.pack_into("<H", header, 16, height - 1)  # brx (Sets ITK dim_y)
    struct.pack_into("<H", header, 18, width - 1)  # bry (Sets ITK dim_x)
    struct.pack_into("<H", header, 20, frames)  # nrframes

    with open(path, "wb") as f:
        f.write(header)
        data = (np.ones((frames, height, width), dtype=np.uint16) * 42).astype("<u2")
        f.write(data.tobytes())

    vol = VolumeData(path)
    assert vol.shape3d == (3, 10, 15)
    assert vol.data[1, 5, 7] == 42


def test_load_custom_avs_xdr_format(tmp_path):
    """Test the fallback AVS Field / open-vv XDR pure Python parser with a mock binary payload."""
    path = str(tmp_path / "test.fld")
    dim1, dim2, dim3 = 15, 10, 5

    header = f"ndim=3\ndim1={dim1}\ndim2={dim2}\ndim3={dim3}\nfield=uniform\n\x0c\x0c"
    with open(path, "wb") as f:
        f.write(header.encode("ascii"))
        data = (np.ones((dim3, dim2, dim1), dtype=np.int16) * 84).astype(">i2")
        f.write(data.tobytes())
        coords = np.array([0, 1, 0, 1, 0, 1], dtype=np.float32).astype(">f4")
        f.write(coords.tobytes())

    # sitk.ReadImage will purposely fail on a .fld file, triggering our custom fallback!
    vol = VolumeData(path)
    assert vol.shape3d == (5, 10, 15)
    assert vol.data[2, 5, 7] == 84


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
