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


def test_load_workspace_relative_path_resolution(tmp_path):
    """Test that workspaces successfully resolve relative paths when absolute paths do not exist."""
    import os
    import json
    from unittest.mock import MagicMock
    from vvv.ui.ui_sequences import load_workspace_sequence

    # 1. Create a dummy image at a relative subpath
    img_dir = tmp_path / "a" / "b" / "c"
    img_dir.mkdir(parents=True, exist_ok=True)
    img_path = img_dir / "titi.mha"
    
    # Create simple dummy image file
    img = sitk.GetImageFromArray(np.zeros((3, 3, 3), dtype=np.uint8))
    sitk.WriteImage(img, str(img_path))

    # 2. Write a workspace JSON file pointing to a non-existent absolute path
    # originally saved at /home/dsarrut/a/b/toto.vvw
    # with image path /home/dsarrut/a/b/c/titi.mha
    ws_data = {
        "version": 1.0,
        "workspace_path": "/home/dsarrut/a/b/toto.vvw",
        "viewers": {},
        "images": {
            "img_1": {
                "path": "/home/dsarrut/a/b/c/titi.mha",
                "display": {},
                "camera": {},
                "extraction": {},
                "dvf": {},
                "rois": [],
                "profiles": []
            }
        }
    }
    
    ws_path = tmp_path / "a" / "b" / "toto.vvw"
    with open(ws_path, "w") as f:
        json.dump(ws_data, f)

    # 3. Call load_workspace_sequence and verify it loads the resolved path
    gui = MagicMock()
    controller = MagicMock()
    # Mock file load to return a dummy volume ID
    controller.file.load_image.return_value = "img_1_loaded"
    controller.volumes = {"img_1_loaded": MagicMock()}
    controller.view_states = MagicMock()

    # Load generator
    generator = load_workspace_sequence(gui, controller, str(ws_path))
    list(generator)  # Consume the generator

    # Check that it called load_image with the resolved local path!
    expected_local_path = str(img_path)
    controller.file.load_image.assert_called_once_with(expected_local_path, ignore_history=True)


def test_load_workspace_roi_json_filtering(tmp_path):
    """Test that ROI paths containing a .json file are filtered when loaded by SimpleITK."""
    import os
    import json
    from unittest.mock import MagicMock
    from vvv.ui.ui_sequences import load_workspace_sequence

    # 1. Create a dummy image at a relative subpath
    img_dir = tmp_path / "a" / "b" / "c"
    img_dir.mkdir(parents=True, exist_ok=True)
    img_path = img_dir / "titi.mha"
    
    # Create simple dummy image file
    img = sitk.GetImageFromArray(np.zeros((3, 3, 3), dtype=np.uint8))
    sitk.WriteImage(img, str(img_path))

    # Create dummy label map files
    labels_nii = img_dir / "labels.nii.gz"
    sitk.WriteImage(img, str(labels_nii))
    labels_json = img_dir / "labels.json"
    with open(labels_json, "w") as f:
        json.dump({"test": 123}, f)

    ws_data = {
        "version": 1.0,
        "workspace_path": "/home/dsarrut/a/b/toto.vvw",
        "viewers": {},
        "images": {
            "img_1": {
                "path": "/home/dsarrut/a/b/c/titi.mha",
                "display": {},
                "camera": {},
                "extraction": {},
                "dvf": {},
                "rois": [
                    {
                        "path": [
                            "/home/dsarrut/a/b/c/labels.nii.gz",
                            "/home/dsarrut/a/b/c/labels.json"
                        ],
                        "state": {
                            "volume_id": "1",
                            "name": "Tumor",
                            "color": [255, 0, 0],
                            "opacity": 0.5,
                            "visible": True,
                            "is_contour": False,
                            "source_mode": "Target FG (val)",
                            "source_val": 1.0,
                            "source_type": "Label Map"
                        }
                    }
                ],
                "profiles": []
            }
        }
    }
    
    ws_path = tmp_path / "a" / "b" / "toto.vvw"
    with open(ws_path, "w") as f:
        json.dump(ws_data, f)

    # 3. Call load_workspace_sequence and verify it loads the resolved path
    gui = MagicMock()
    controller = MagicMock()
    controller.file.load_image.return_value = "img_1_loaded"
    controller.volumes = {"img_1_loaded": MagicMock()}
    controller.view_states = MagicMock()

    # Consume the generator
    generator = load_workspace_sequence(gui, controller, str(ws_path))
    list(generator)

    # Check that the ROI load did not trigger a DICOM or file load failure warning
    controller.roi.extract_label_from_image.assert_called_once()


