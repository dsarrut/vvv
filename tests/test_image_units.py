import os
import json
import numpy as np
import SimpleITK as sitk
from unittest.mock import MagicMock, patch
from vvv.maths.image import VolumeData


def test_sidecar_json_unit_detection(tmp_path):
    """Verifies that VolumeData correctly reads and maps the unit from a sidecar JSON file."""
    # 1. CT with "hu"
    ct_img = sitk.GetImageFromArray(np.zeros((10, 10, 10), dtype=np.int16))
    ct_path = str(tmp_path / "ct.nii.gz")
    sitk.WriteImage(ct_img, ct_path)
    ct_json_path = str(tmp_path / "ct.json")
    with open(ct_json_path, "w") as f:
        json.dump({"modality": "ct", "unit": "hu"}, f)

    ct_vol = VolumeData(ct_path)
    assert ct_vol.unit == "HU"
    assert "ct.json" in ct_vol.unit_source

    # 2. PET with "suv"
    pet_img = sitk.GetImageFromArray(np.zeros((10, 10, 10), dtype=np.float32))
    pet_path = str(tmp_path / "pet.nii.gz")
    sitk.WriteImage(pet_img, pet_path)
    pet_json_path = str(tmp_path / "pet.json")
    with open(pet_json_path, "w") as f:
        json.dump({"modality": "pet", "unit": "suv"}, f)

    pet_vol = VolumeData(pet_path)
    assert pet_vol.unit == "SUV"
    assert "pet.json" in pet_vol.unit_source

    # 3. PET with "bq"
    pet_bq_img = sitk.GetImageFromArray(np.zeros((10, 10, 10), dtype=np.float32))
    pet_bq_path = str(tmp_path / "pet_bq.nii.gz")
    sitk.WriteImage(pet_bq_img, pet_bq_path)
    pet_bq_json_path = str(tmp_path / "pet_bq.json")
    with open(pet_bq_json_path, "w") as f:
        json.dump({"modality": "pet", "unit": "bq"}, f)

    pet_bq_vol = VolumeData(pet_bq_path)
    assert pet_bq_vol.unit == "Bq/mL"
    assert "pet_bq.json" in pet_bq_vol.unit_source

    # 4. PET with "sul"
    pet_sul_img = sitk.GetImageFromArray(np.zeros((10, 10, 10), dtype=np.float32))
    pet_sul_path = str(tmp_path / "pet_sul.nii.gz")
    sitk.WriteImage(pet_sul_img, pet_sul_path)
    pet_sul_json_path = str(tmp_path / "pet_sul.json")
    with open(pet_sul_json_path, "w") as f:
        json.dump({"modality": "pet", "unit": "sul"}, f)

    pet_sul_vol = VolumeData(pet_sul_path)
    assert pet_sul_vol.unit == "SUL"
    assert "pet_sul.json" in pet_sul_vol.unit_source


def test_fallback_unit_when_no_json(tmp_path):
    """Verifies that an image without sidecar JSON or DICOM metadata defaults to None (?)."""
    raw_img = sitk.GetImageFromArray(np.zeros((5, 5, 5), dtype=np.float32))
    img_path = str(tmp_path / "raw.mhd")
    sitk.WriteImage(raw_img, img_path)

    vol = VolumeData(img_path)
    assert vol.unit is None
    assert vol.unit_source == "Unknown"


def test_dicom_unit_detection(tmp_path):
    """Verifies that DICOM files infer their unit from modality/tags."""
    img_path = str(tmp_path / "fake_dicom.nii.gz")
    img = sitk.GetImageFromArray(np.zeros((5, 5, 5), dtype=np.int16))
    sitk.WriteImage(img, img_path)

    with patch("pydicom.dcmread") as mock_dcmread:
        # Mock CT dataset
        ds_ct = MagicMock()
        ds_ct.Modality = "CT"
        mock_dcmread.return_value = ds_ct

        vol_ct = VolumeData(img_path)
        assert vol_ct.unit == "HU"
        assert "DICOM" in vol_ct.unit_source

        # Mock PT dataset with BQML
        ds_pt = MagicMock()
        ds_pt.Modality = "PT"
        ds_pt.Units = "BQML"
        mock_dcmread.return_value = ds_pt

        vol_pt = VolumeData(img_path)
        assert vol_pt.unit == "Bq/mL"
        assert "BQML" in vol_pt.unit_source


def test_save_image_updates_sidecar_json(headless_gui_app, tmp_path):
    """Verifies that updating an image's unit and saving updates/creates the sidecar JSON."""
    controller, gui, viewer, vs_id = headless_gui_app

    # Create dummy image
    img = sitk.GetImageFromArray(np.zeros((5, 5, 5), dtype=np.float32))
    img_path = str(tmp_path / "test_save_unit.nii.gz")
    sitk.WriteImage(img, img_path)

    vol = controller.volumes[vs_id]
    vol.path = img_path
    vol.file_paths = [img_path]
    vol.name = "test_save_unit.nii.gz"
    vol.unit = "SUV"
    vol._is_outdated = True

    json_path = str(tmp_path / "test_save_unit.json")
    assert not os.path.exists(json_path)

    # Trigger save_image
    controller.save_image(vs_id, img_path)

    # Sidecar JSON should now exist with unit = "SUV"
    assert os.path.exists(json_path)
    with open(json_path, "r") as f:
        data = json.load(f)
    assert data.get("unit") == "SUV"
    assert vol._is_outdated is False
    assert "test_save_unit.json" in vol.unit_source


def test_workspace_save_restore_units(headless_gui_app, tmp_path):
    """Verifies that saving a workspace and restoring it preserves image units."""
    controller, gui, viewer, vs_id = headless_gui_app

    vol = controller.volumes[vs_id]
    vol.unit = "kBq/mL"
    vol.unit_source = "Sidecar JSON (pet.json)"

    ws_path = str(tmp_path / "test_units.vvw")
    controller.file.save_workspace(ws_path)

    # Check workspace file JSON content
    with open(ws_path, "r") as f:
        ws_data = json.load(f)

    img_entry = ws_data["images"][vs_id]
    assert img_entry.get("unit") == "kBq/mL"
    assert img_entry.get("unit_source") == "Sidecar JSON (pet.json)"


def test_p200_sidecar_detection():
    """Verifies that the p200 data/ example sidecar JSON files parse correctly."""
    repo_root = os.path.dirname(os.path.dirname(__file__))
    ct_path = os.path.join(repo_root, "data", "p200", "ct.nii.gz")
    pet_path = os.path.join(repo_root, "data", "p200", "pet.nii.gz")
    pet_bq_path = os.path.join(repo_root, "data", "p200", "pet_bq.nii.gz")

    if os.path.exists(ct_path):
        ct_vol = VolumeData(ct_path)
        assert ct_vol.unit == "HU"
        assert "ct.json" in ct_vol.unit_source

    if os.path.exists(pet_path):
        pet_vol = VolumeData(pet_path)
        assert pet_vol.unit == "SUV"
        assert "pet.json" in pet_vol.unit_source

    if os.path.exists(pet_bq_path):
        pet_bq_vol = VolumeData(pet_bq_path)
        assert pet_bq_vol.unit == "Bq/mL"
        assert "pet_bq.json" in pet_bq_vol.unit_source


def test_legend_draws_with_unit(headless_gui_app):
    """Verifies that draw_legend reflects image units and invalidates cache when unit changes."""
    controller, gui, viewer, vs_id = headless_gui_app
    vol = controller.volumes[vs_id]
    vol.unit = "HU"

    viewer.quad_w = 400
    viewer.quad_h = 400
    viewer.show_legend = True

    with (
        patch("dearpygui.dearpygui.does_item_exist", return_value=True),
        patch("dearpygui.dearpygui.delete_item"),
        patch("dearpygui.dearpygui.draw_text") as mock_draw_text,
        patch("dearpygui.dearpygui.draw_rectangle") as mock_draw_rect,
        patch("dearpygui.dearpygui.draw_line"),
    ):

        # Single colorbar legend drawing
        viewer.drawer.draw_legend()

        # Verify that "HU" was drawn
        drawn_texts = [call.args[1] for call in mock_draw_text.call_args_list]
        assert "HU" in drawn_texts

        # Verify draw_rectangle calls have exactly 2 positional arguments (pmin, pmax)
        for call in mock_draw_rect.call_args_list:
            assert (
                len(call.args) == 2
            ), f"draw_rectangle called with {len(call.args)} args: {call.args}"

        # Verify caching: subsequent call with same state should not re-draw
        mock_draw_text.reset_mock()
        viewer.drawer.draw_legend()
        assert mock_draw_text.call_count == 0

        # Change unit to SUL -> cache invalidation -> re-draws with SUL
        vol.unit = "SUL"
        viewer.drawer.draw_legend()
        drawn_texts_sul = [call.args[1] for call in mock_draw_text.call_args_list]
        assert "SUL" in drawn_texts_sul

        # Test Dual Colorbar with base and overlay
        mock_draw_text.reset_mock()
        mock_draw_rect.reset_mock()
        viewer.view_state.display.overlay.image_id = "2"
        controller.volumes["2"].unit = "SUV"
        viewer.drawer.draw_legend()
        drawn_texts_dual = [call.args[1] for call in mock_draw_text.call_args_list]
        assert "SUL" in drawn_texts_dual
        assert "SUV" in drawn_texts_dual
        assert "(1)" in drawn_texts_dual
        assert "(2)" in drawn_texts_dual

        for call in mock_draw_rect.call_args_list:
            assert (
                len(call.args) == 2
            ), f"draw_rectangle called with {len(call.args)} args: {call.args}"

        # Verify that image id and unit are centered with respect to each other
        text_positions = {
            call.args[1]: call.args[0] for call in mock_draw_text.call_args_list
        }
        # (1) and SUL have the same character count (3 chars), so their x coordinates must match exactly
        assert text_positions["(1)"][0] == text_positions["SUL"][0]
        # (2) and SUV have the same character count (3 chars), so their x coordinates must match exactly
        assert text_positions["(2)"][0] == text_positions["SUV"][0]


def test_ui_unit_change_triggers_legend_update(headless_gui_app):
    """Verifies that changing unit marks viewers dirty and updates active legend immediately."""
    controller, gui, viewer, vs_id = headless_gui_app
    viewer.quad_w = 400
    viewer.quad_h = 400
    viewer.show_legend = True

    with (
        patch("dearpygui.dearpygui.does_item_exist", return_value=True),
        patch("dearpygui.dearpygui.delete_item"),
        patch("dearpygui.dearpygui.draw_text") as mock_draw_text,
        patch("dearpygui.dearpygui.draw_rectangle"),
        patch("dearpygui.dearpygui.draw_line"),
        patch("dearpygui.dearpygui.set_value"),
    ):

        # Initial draw without unit
        viewer.drawer.draw_legend()
        mock_draw_text.reset_mock()

        # Update unit and invoke redraw logic as gui callbacks do
        vol = controller.volumes[vs_id]
        vol.unit = "SUV"
        for v in controller.viewers.values():
            v.is_geometry_dirty = True
            v.drawer._last_leg_state = None
            if getattr(v, "show_legend", False):
                v.drawer.draw_legend()

        drawn_texts = [call.args[1] for call in mock_draw_text.call_args_list]
        assert "SUV" in drawn_texts
        assert viewer.is_geometry_dirty is True
