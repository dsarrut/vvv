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


def test_pet_aqara_presets():
    """Verifies AQARA PET presets exist and apply ww/wl and min_threshold=0.0."""
    from vvv.config import WL_PRESETS
    from vvv.core.view_state import ViewState

    # Presets exist in config
    assert "PET: [0 - 10]" in WL_PRESETS
    assert WL_PRESETS["PET: [0 - 10]"]["ww"] == 10.0
    assert WL_PRESETS["PET: [0 - 10]"]["wl"] == 5.0
    assert WL_PRESETS["PET: [0 - 10]"]["min_threshold"] == 0.0

    assert "PET: [0 - 5]" in WL_PRESETS
    assert WL_PRESETS["PET: [0 - 5]"]["min_threshold"] == 0.0

    mock_vol = MagicMock()
    mock_vol.data = np.ones((10, 10, 10), dtype=np.float32)
    mock_vol.is_rgb = False
    mock_vol.shape3d = (10, 10, 10)
    mock_vol.num_timepoints = 1

    vs = ViewState(mock_vol)
    vs.apply_wl_preset("PET: [0 - 10]")
    assert vs.display.ww == 10.0
    assert vs.display.wl == 5.0
    assert vs.display.min_threshold == 0.0

    # Switching to CT clears min_threshold
    vs.apply_wl_preset("CT: Soft Tissue")
    assert vs.display.min_threshold is None


def test_pet_image_auto_defaults_to_aqara_preset(tmp_path):
    """Verifies that an image with unit SUV or SUL auto-initializes with PET: [0 - 10] and min_threshold=0.0."""
    from vvv.core.view_state import ViewState

    # Save a dummy PET image with sidecar pet.json
    pet_img = sitk.GetImageFromArray(np.full((10, 10, 10), 3.0, dtype=np.float32))
    pet_path = str(tmp_path / "aqara_pet.nii.gz")
    sitk.WriteImage(pet_img, pet_path)
    with open(str(tmp_path / "aqara_pet.json"), "w") as f:
        json.dump({"unit": "SUV"}, f)

    vol = VolumeData(pet_path)
    assert vol.unit == "SUV"

    vs = ViewState(vol)
    vs.init_default_window_level()
    assert vs.display.ww == 10.0
    assert vs.display.wl == 5.0
    assert vs.display.min_threshold == 0.0


def test_compute_legend_ticks():
    """Verifies that compute_legend_ticks produces clean round ticks for clinical and general ranges."""
    from vvv.ui.drawing import compute_legend_ticks

    # Standard PET: [0 - 10]
    ticks_10 = compute_legend_ticks(0.0, 10.0)
    assert ticks_10 == [0.0, 2.0, 4.0, 6.0, 8.0, 10.0]

    # PET: [0 - 5]
    ticks_5 = compute_legend_ticks(0.0, 5.0)
    assert ticks_5 == [0.0, 1.0, 2.0, 3.0, 4.0, 5.0]

    # PET: [0 - 20]
    ticks_20 = compute_legend_ticks(0.0, 20.0)
    assert ticks_20 == [0.0, 5.0, 10.0, 15.0, 20.0]

    # General range
    ticks_ct = compute_legend_ticks(-1000.0, 1000.0)
    assert -1000.0 in ticks_ct and 1000.0 in ticks_ct and 0.0 in ticks_ct


def test_legend_toggle_cycling_and_status(headless_gui_app):
    """Tests cycling through off -> mode 1 -> mode 2 (AQARA) -> off."""
    controller, gui, viewer, _ = headless_gui_app
    viewer.view_state.camera.show_legend = 0

    viewer.action_toggle_legend()
    assert viewer.show_legend == 1
    assert "mode 1" in controller.status_message

    viewer.action_toggle_legend()
    assert viewer.show_legend == 2
    assert "AQARA" in controller.status_message

    viewer.action_toggle_legend()
    assert viewer.show_legend == 0
    assert "off" in controller.status_message


def test_legend_mode2_aqara_draws_ticks_without_indicator(headless_gui_app):
    """Verifies Mode 2 draws tick lines and values, but suppresses crosshair needle/triangles."""
    controller, gui, viewer, vs_id = headless_gui_app
    viewer.quad_w = 400
    viewer.quad_h = 400
    viewer.view_state.display.ww = 10.0
    viewer.view_state.display.wl = 5.0
    viewer.view_state.crosshair_value = 4.2

    # Mode 1: draws triangle indicator for crosshair
    viewer.show_legend = 1
    with (
        patch("dearpygui.dearpygui.does_item_exist", return_value=True),
        patch("dearpygui.dearpygui.delete_item"),
        patch("dearpygui.dearpygui.draw_text") as mock_text_m1,
        patch("dearpygui.dearpygui.draw_rectangle"),
        patch("dearpygui.dearpygui.draw_line") as mock_line_m1,
        patch("dearpygui.dearpygui.draw_triangle") as mock_tri_m1,
    ):
        viewer.drawer.draw_legend()
        assert mock_tri_m1.called is True
        texts_m1 = [call.args[1] for call in mock_text_m1.call_args_list]
        assert "10" in texts_m1
        assert "5" in texts_m1
        assert "0" in texts_m1

    # Mode 2: AQARA with ticks, NO triangle indicator
    viewer.show_legend = 2
    with (
        patch("dearpygui.dearpygui.does_item_exist", return_value=True),
        patch("dearpygui.dearpygui.delete_item"),
        patch("dearpygui.dearpygui.draw_text") as mock_text_m2,
        patch("dearpygui.dearpygui.draw_rectangle"),
        patch("dearpygui.dearpygui.draw_line") as mock_line_m2,
        patch("dearpygui.dearpygui.draw_triangle") as mock_tri_m2,
    ):
        viewer.drawer.draw_legend()
        assert mock_tri_m2.called is False  # No indicator triangle!
        texts_m2 = [call.args[1] for call in mock_text_m2.call_args_list]
        # Should have ticks: 0, 2, 4, 6, 8, 10
        for expected_tick in ["0", "2", "4", "6", "8", "10"]:
            assert expected_tick in texts_m2


def test_legend_mode2_dual_colorbar(headless_gui_app):
    """Verifies Mode 2 with fusion overlay draws ticks for both base and overlay without needle triangles."""
    controller, gui, viewer, vs_id = headless_gui_app
    viewer.quad_w = 500
    viewer.quad_h = 500
    viewer.show_legend = 2

    # Set up overlay
    vs = viewer.view_state
    overlay_vs = controller.view_states["2"]
    vs.display.overlay.image_id = "2"
    vs.display.ww = 10.0
    vs.display.wl = 5.0
    overlay_vs.display.ww = 20.0
    overlay_vs.display.wl = 10.0
    vs.crosshair_value = 3.0

    with (
        patch("dearpygui.dearpygui.does_item_exist", return_value=True),
        patch("dearpygui.dearpygui.delete_item"),
        patch("dearpygui.dearpygui.draw_text") as mock_text,
        patch("dearpygui.dearpygui.draw_rectangle"),
        patch("dearpygui.dearpygui.draw_line") as mock_line,
        patch("dearpygui.dearpygui.draw_triangle") as mock_tri,
    ):
        viewer.drawer.draw_legend()
        assert mock_tri.called is False  # No indicator triangles in Mode 2!
        texts = [call.args[1] for call in mock_text.call_args_list]
        # Base ticks [0, 2, 4, 6, 8, 10]
        assert "0" in texts and "10" in texts
        # Overlay ticks [0, 5, 10, 15, 20]
        assert "20" in texts and "15" in texts


def test_legend_min_threshold_indicator(headless_gui_app):
    """Verifies that min_threshold draws an amber cutoff line and dims sub-threshold colorbar values."""
    controller, gui, viewer, vs_id = headless_gui_app
    viewer.quad_w = 400
    viewer.quad_h = 400
    viewer.show_legend = 1

    vs = viewer.view_state
    vs.display.ww = 10.0
    vs.display.wl = 5.0
    # Range is [0.0 - 10.0], set threshold at 2.0
    vs.display.min_threshold = 2.0

    drawn_lines = []

    def mock_draw_line_func(*args, **kwargs):
        drawn_lines.append((args, kwargs))

    with (
        patch("dearpygui.dearpygui.does_item_exist", return_value=True),
        patch("dearpygui.dearpygui.delete_item"),
        patch("dearpygui.dearpygui.draw_text"),
        patch("dearpygui.dearpygui.draw_rectangle"),
        patch("dearpygui.dearpygui.draw_line", side_effect=mock_draw_line_func),
        patch("dearpygui.dearpygui.draw_triangle"),
    ):
        viewer.drawer.draw_legend()

        # Find cutoff line: color [255, 180, 50, 230], thickness 2
        cutoff_lines = [
            kw
            for (args, kw) in drawn_lines
            if kw.get("color") == [255, 180, 50, 230] and kw.get("thickness") == 2
        ]
        assert len(cutoff_lines) == 1

        # Check that gradient lines below threshold are dimmed
        # For Grayscale: raw white is [255, 255, 255], black is [0, 0, 0]
        # At i > 0 but val_i <= 2.0 (i <= 51), color should be dimmed
        gradient_lines = [
            (args, kw)
            for (args, kw) in drawn_lines
            if kw.get("color") != [255, 180, 50, 230] and kw.get("thickness") == 2
        ]
        assert len(gradient_lines) == 256

        # Test cache invalidation on min_threshold change
        drawn_lines.clear()
        vs.display.min_threshold = 4.0
        viewer.drawer.draw_legend()
        new_cutoff_lines = [
            kw for (args, kw) in drawn_lines if kw.get("color") == [255, 180, 50, 230]
        ]
        assert len(new_cutoff_lines) == 1


def test_legend_min_threshold_dual_colorbar(headless_gui_app):
    """Verifies that cutoff lines are drawn for both base and overlay when min_threshold is set."""
    controller, gui, viewer, vs_id = headless_gui_app
    viewer.quad_w = 500
    viewer.quad_h = 500
    viewer.show_legend = 2

    vs = viewer.view_state
    overlay_vs = controller.view_states["2"]
    vs.display.overlay.image_id = "2"
    vs.display.ww = 10.0
    vs.display.wl = 5.0
    vs.display.min_threshold = 1.0

    overlay_vs.display.ww = 20.0
    overlay_vs.display.wl = 10.0
    overlay_vs.display.min_threshold = 5.0

    drawn_lines = []

    def mock_draw_line_func(*args, **kwargs):
        drawn_lines.append((args, kwargs))

    with (
        patch("dearpygui.dearpygui.does_item_exist", return_value=True),
        patch("dearpygui.dearpygui.delete_item"),
        patch("dearpygui.dearpygui.draw_text"),
        patch("dearpygui.dearpygui.draw_rectangle"),
        patch("dearpygui.dearpygui.draw_line", side_effect=mock_draw_line_func),
        patch("dearpygui.dearpygui.draw_triangle"),
    ):
        viewer.drawer.draw_legend()

        cutoff_lines = [
            kw
            for (args, kw) in drawn_lines
            if kw.get("color") == [255, 180, 50, 230] and kw.get("thickness") == 2
        ]
        # Both base and overlay should have a cutoff line
        assert len(cutoff_lines) == 2


def test_legend_sub_min_threshold_option_a(headless_gui_app):
    """Verifies that when min_threshold < val_min, a downward triangle and thr: <value> label are drawn below the bar."""
    controller, gui, viewer, vs_id = headless_gui_app
    viewer.quad_w = 400
    viewer.quad_h = 400
    viewer.show_legend = 2  # Mode 2 AQARA

    vs = viewer.view_state
    # WW = 8.0, WL = 6.0 => [2.0 - 10.0]
    vs.display.ww = 8.0
    vs.display.wl = 6.0
    # Threshold at 0.0, strictly below val_min (2.0)
    vs.display.min_threshold = 0.0

    drawn_texts = []
    drawn_triangles = []
    drawn_rects = []
    drawn_lines = []

    with (
        patch("dearpygui.dearpygui.does_item_exist", return_value=True),
        patch("dearpygui.dearpygui.delete_item"),
        patch(
            "dearpygui.dearpygui.draw_text",
            side_effect=lambda *a, **kw: drawn_texts.append((a, kw)),
        ),
        patch(
            "dearpygui.dearpygui.draw_rectangle",
            side_effect=lambda *a, **kw: drawn_rects.append((a, kw)),
        ),
        patch(
            "dearpygui.dearpygui.draw_line",
            side_effect=lambda *a, **kw: drawn_lines.append((a, kw)),
        ),
        patch(
            "dearpygui.dearpygui.draw_triangle",
            side_effect=lambda *a, **kw: drawn_triangles.append((a, kw)),
        ),
    ):
        viewer.drawer.draw_legend()

        # Cutoff line inside the bar should NOT be drawn because 0.0 < 2.0
        cutoff_lines = [
            kw
            for (args, kw) in drawn_lines
            if kw.get("color") == [255, 180, 50, 230] and kw.get("thickness") == 2
        ]
        assert len(cutoff_lines) == 0

        # Downward triangle below bar should be drawn
        thr_triangles = [
            kw
            for (args, kw) in drawn_triangles
            if kw.get("color") == [255, 180, 50, 230]
        ]
        assert len(thr_triangles) == 1

        # Text "thr: 0" should be drawn below the bar in amber
        thr_texts = [
            args[1]
            for (args, kw) in drawn_texts
            if kw.get("color") == [255, 180, 50, 230]
        ]
        assert "thr: 0" in thr_texts

        # Panel bottom should be extended (y_start + cb_height + 32)
        cb_height = int(400 * 0.4)  # 160
        y_start = (400 - cb_height) // 2  # 120
        expected_bottom_y = y_start + cb_height + 32
        panel_rect = drawn_rects[0][0]  # first drawn rectangle is background panel
        assert panel_rect[1][1] == expected_bottom_y
