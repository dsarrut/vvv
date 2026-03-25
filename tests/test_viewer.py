import pytest
import numpy as np
import SimpleITK as sitk
from vvv.ui.gui import MainGUI
import dearpygui.dearpygui as dpg
from vvv.ui.viewer import SliceViewer
from vvv.core.controller import Controller
from vvv.math.image import RenderLayer, SliceRenderer
from vvv.ui.ui_sequences import load_workspace_sequence
from vvv.utils import ViewMode, slice_to_voxel, voxel_to_slice


@pytest.fixture(scope="session")
def synthetic_image_path(tmp_path_factory):
    """Generates a 5x5x5 checkerboard image."""
    indices = np.indices((5, 5, 5))
    checkerboard = (indices[0] + indices[1] + indices[2]) % 2
    checkerboard = (checkerboard * 100).astype(np.float32)
    sitk_img = sitk.GetImageFromArray(checkerboard)
    sitk_img.SetSpacing((1.0, 1.0, 1.0))
    sitk_img.SetOrigin((10.0, 20.0, 50.0))
    img_path = tmp_path_factory.mktemp("data") / "checkerboard_5x5x5.nrrd"
    sitk.WriteImage(sitk_img, str(img_path))
    return str(img_path)


@pytest.fixture(scope="session")
def synthetic_overlay_path(tmp_path_factory):
    """Generates a 3x3x3 image with DIFFERENT spacing (2.0) and predictable values."""
    indices = np.indices((3, 3, 3))
    data = (indices[0] * 100 + indices[1] * 10 + indices[2]).astype(np.float32)
    sitk_img = sitk.GetImageFromArray(data)
    sitk_img.SetSpacing((2.0, 2.0, 2.0))
    sitk_img.SetOrigin((10.0, 20.0, 50.0))
    img_path = tmp_path_factory.mktemp("data") / "overlay_3x3x3.nrrd"
    sitk.WriteImage(sitk_img, str(img_path))
    return str(img_path)


@pytest.fixture(scope="session")
def synthetic_4d_path(tmp_path_factory):
    """Generates a 4D sequence (3 timepoints of a 5x5x5 volume)."""
    data = np.zeros((3, 5, 5, 5), dtype=np.float32)
    for t in range(3):
        data[t] = t * 100.0  # Time 0 is 0, Time 1 is 100, Time 2 is 200
    sitk_img = sitk.GetImageFromArray(data)
    img_path = tmp_path_factory.mktemp("data") / "sequence_4d.nrrd"
    sitk.WriteImage(sitk_img, str(img_path))
    return str(img_path)


@pytest.fixture
def headless_app(synthetic_image_path):
    """Sets up the real application architecture without launching the render loop."""
    controller = Controller()
    for tag in ["V1", "V2", "V3", "V4"]:
        controller.viewers[tag] = SliceViewer(tag, controller)
    gui = MainGUI(controller)
    controller.gui = gui
    vs_id = controller.file.load_image(synthetic_image_path)
    viewer = controller.viewers["V1"]
    viewer.set_image(vs_id)
    gui.context_viewer = viewer
    gui.on_window_resize()
    return controller, viewer, vs_id


# ==========================================
# 2. ORIGINAL TESTS (Interaction & Coords)
# ==========================================


def test_utils_coordinate_conversions():
    shape = (10, 20)  # h, w -> real_h, real_w
    v = slice_to_voxel(5.5, 3.5, 7.0, ViewMode.AXIAL, shape)
    assert np.allclose(v, [5.0, 3.0, 7.0])
    s_x, s_y = voxel_to_slice(5.0, 3.0, 7.0, ViewMode.AXIAL, shape)
    assert s_x == 5.5
    assert s_y == 3.5
    v_sag = slice_to_voxel(5.5, 3.5, 7.0, ViewMode.SAGITTAL, shape)
    assert np.allclose(v_sag, [7.0, 14.0, 6.0])


def test_exact_coordinate_and_value_mapping(headless_app):
    controller, viewer, vs_id = headless_app
    vs = controller.view_states[vs_id]
    viewer.set_orientation(ViewMode.AXIAL)
    viewer.update_crosshair_data(pix_x=1.5, pix_y=3.5)
    assert vs.camera.crosshair_voxel == [1.0, 3.0, 2.0, 0]
    assert vs.camera.crosshair_phys_coord.tolist() == [11.0, 23.0, 52.0]
    assert vs.crosshair_value == 0.0
    viewer.update_crosshair_data(pix_x=2.5, pix_y=3.5)
    assert vs.crosshair_value == 100.0


def test_overlay_fusion_resampling_accuracy(headless_app, synthetic_overlay_path):
    controller, viewer, vs_id_base = headless_app
    vs_base = controller.view_states[vs_id_base]
    vs_id_overlay = controller.file.load_image(synthetic_overlay_path)
    vol_overlay = controller.volumes[vs_id_overlay]
    vs_base.set_overlay(vs_id_overlay, vol_overlay)

    assert vs_base.display.overlay_data.shape == (5, 5, 5)
    assert vs_base.display.overlay_data[2, 2, 2] == 111.0
    assert vs_base.display.overlay_data[4, 4, 4] == 222.0


def test_sync_correspondence_between_different_geometries(
    headless_app, synthetic_overlay_path
):
    controller, viewer1, vs_id1 = headless_app
    vs_id2 = controller.file.load_image(synthetic_overlay_path)
    viewer2 = controller.viewers["V2"]
    viewer2.set_image(vs_id2)

    controller.gui.on_sync_group_change(None, "Group 1", vs_id1)
    controller.gui.on_sync_group_change(None, "Group 1", vs_id2)
    viewer1.set_orientation(ViewMode.AXIAL)
    viewer2.set_orientation(ViewMode.AXIAL)

    viewer1.update_crosshair_data(pix_x=2.5, pix_y=2.5)
    controller.sync.propagate_sync(vs_id1)

    vs1 = controller.view_states[vs_id1]
    vs2 = controller.view_states[vs_id2]
    assert vs1.camera.crosshair_voxel == [2.0, 2.0, 2.0, 0]
    assert np.allclose(vs2.camera.crosshair_phys_coord, vs1.camera.crosshair_phys_coord)
    assert vs2.camera.crosshair_voxel == [1.0, 1.0, 1.0, 0.0]


def test_auto_window_level(headless_app):
    controller, viewer, vs_id = headless_app
    vs = controller.view_states[vs_id]
    viewer.update_window_level(ww=10.0, wl=500.0)
    controller.settings.data["physics"]["auto_window_fov"] = 0.80
    viewer.get_mouse_slice_coords = lambda ignore_hover=False, allow_outside=False: (
        2.5,
        2.5,
    )
    viewer.on_key_press(dpg.mvKey_W)
    assert vs.display.ww >= 95.0
    assert vs.display.wl == pytest.approx(50.0, abs=5.0)


def test_zoom_interaction(headless_app, monkeypatch):
    controller, viewer, vs_id = headless_app
    monkeypatch.setattr(dpg, "get_drawing_mouse_pos", lambda: (250, 250))
    initial_zoom = viewer.zoom
    viewer.on_zoom("in")
    zoomed_in = viewer.zoom
    assert zoomed_in > initial_zoom
    viewer.on_zoom("out")
    assert viewer.zoom == pytest.approx(
        zoomed_in * (1.0 / controller.settings.data["interaction"]["zoom_speed"])
    )


def test_pan_interaction_via_drag(headless_app, monkeypatch):
    controller, viewer, vs_id = headless_app
    initial_pan = viewer.pan_offset.copy()

    monkeypatch.setattr(
        dpg, "is_mouse_button_down", lambda btn: btn == dpg.mvMouseButton_Left
    )
    monkeypatch.setattr(
        dpg, "is_key_down", lambda key: key in [dpg.mvKey_LControl, dpg.mvKey_RControl]
    )
    monkeypatch.setattr(dpg, "get_mouse_pos", lambda local=False: [115, 125])

    viewer.drag_start_mouse = [100, 100]
    viewer.drag_start_pan = initial_pan.copy()
    viewer.on_drag(None)

    assert viewer.pan_offset[0] == initial_pan[0] + 15
    assert viewer.pan_offset[1] == initial_pan[1] + 25


def test_reset_view(headless_app):
    controller, viewer, vs_id = headless_app
    viewer.zoom = 5.0
    viewer.pan_offset = [100, -50]
    viewer.slice_idx = 0
    viewer.on_key_press(dpg.mvKey_R)
    assert viewer.zoom == 1.0
    assert viewer.pan_offset == [0, 0]
    assert viewer.slice_idx == 2


# ==========================================
# 3. PURE MATH & LOGIC ISOLATION
# ==========================================


def test_roi_statistics_math(headless_app, tmp_path):
    """Test mathematically isolated ROI physical statistics (Volume, Mass, Mean)."""
    controller, viewer, vs_id = headless_app

    # 1. Create a 3x3x3 ROI Mask where ONLY the exact center voxel is 1
    roi_data = np.zeros((3, 3, 3), dtype=np.uint8)
    roi_data[1, 1, 1] = 1

    sitk_img = sitk.GetImageFromArray(roi_data)
    sitk_img.SetSpacing((2.0, 2.0, 2.0))  # 2x2x2 = 8 mm^3 volume!
    sitk_img.SetOrigin(controller.volumes[vs_id].origin.tolist())

    mask_path = tmp_path / "mask.nrrd"
    sitk.WriteImage(sitk_img, str(mask_path))

    # 2. Overwrite the Base Image center voxel to EXACTLY 1000 HU (Hounsfield)
    controller.volumes[vs_id].data[1, 1, 1] = 1000.0

    # 3. Load ROI and run stats
    roi_id = controller.roi.load_binary_mask(
        vs_id, str(mask_path), mode="Target FG (val)", target_val=1.0
    )
    stats = controller.roi.get_roi_stats(vs_id, roi_id, is_overlay=False)

    # 4. Verify pure math
    assert stats["vol"] == 0.008  # 8 mm^3 / 1000 = 0.008 cc
    assert stats["mean"] == 1000.0
    assert stats["max"] == 1000.0

    # Mass = Vol * Density. 1000 HU = 2.0 g/cc. Mass = 0.008 * 2.0 = 0.016 g
    assert stats["mass"] == pytest.approx(0.016)


def test_roi_binarization_rules(headless_app, tmp_path):
    """Test that loading a label map strictly obeys the binarization rules before rendering."""
    controller, viewer, vs_id = headless_app

    # Create a synthetic discrete label map
    label_map = np.array([[[0, 1, 2, 3]]], dtype=np.uint8)
    sitk_img = sitk.GetImageFromArray(label_map)
    sitk_img.SetSpacing((1.0, 1.0, 1.0))
    sitk_img.SetOrigin((0.0, 0.0, 0.0))

    mask_path = tmp_path / "labels.nrrd"
    sitk.WriteImage(sitk_img, str(mask_path))

    # Apply the math rule during load
    roi_id = controller.roi.load_binary_mask(
        vs_id, str(mask_path), mode="Target FG (val)", target_val=2.0
    )
    roi_data = controller.volumes[roi_id].data

    # Only the pixel that was '2' should be 1. Everything else MUST be 0.
    assert roi_data[0, 0, 2] == 1
    assert np.count_nonzero(roi_data) == 1


# ==========================================
# 4. DATA-IN / DATA-OUT (Serialization)
# ==========================================


def test_history_lru_cache(headless_app):
    """Test that the Auto-History JSON caps at 100 items and evicts the oldest entries."""
    controller, viewer, vs_id = headless_app

    # Isolate from the real user's ~/.config/vvv/history.json
    controller.history.data.clear()

    for i in range(105):
        controller.history.data[f"fake_file_path_{i}.nii"] = {"shape3d": [5, 5, 5]}

    controller.history.save_image_state(controller, vs_id)

    assert len(controller.history.data) == 100
    assert "fake_file_path_0.nii" not in controller.history.data


# ==========================================
# 5. HEADLESS STATE VERIFICATION
# ==========================================


def test_window_level_sync_propagation(
    headless_app, synthetic_overlay_path, monkeypatch
):
    """Test that changing W/L on one image cascades to grouped images without UI clicking."""
    controller, viewer, vs1_id = headless_app
    vs2_id = controller.file.load_image(synthetic_overlay_path)

    # Put both in Group 1
    vs1 = controller.view_states[vs1_id]
    vs2 = controller.view_states[vs2_id]
    vs1.sync_group = 1
    vs2.sync_group = 1

    # Mock the UI Checkbox existing and being checked
    monkeypatch.setattr(dpg, "does_item_exist", lambda t: t == "check_sync_wl")
    monkeypatch.setattr(
        dpg, "get_value", lambda t: True if t == "check_sync_wl" else None
    )

    # Change Base W/L and Propagate
    vs1.display.ww = 142.5
    controller.sync.propagate_window_level(vs1_id)

    # Verify Target adopted the value via the Controller logic alone
    assert vs2.display.ww == 142.5


def test_4d_time_scrolling(headless_app, synthetic_4d_path):
    """Test that 4D images correctly loop time frames and update crosshair values."""
    controller, viewer, _ = headless_app
    vs_id_4d = controller.file.load_image(synthetic_4d_path)
    vs = controller.view_states[vs_id_4d]
    viewer.set_image(vs_id_4d)

    assert vs.camera.time_idx == 0
    viewer.update_crosshair_data(pix_x=2.5, pix_y=2.5)
    assert vs.crosshair_value == 0.0  # Timepoint 0 = 0

    # Scroll forward 1 tick
    viewer.on_time_scroll(1)
    assert vs.camera.time_idx == 1
    assert vs.crosshair_value == 100.0  # Timepoint 1 = 100

    # Scroll backward 2 ticks (Loops past 0 to the end of the array!)
    viewer.on_time_scroll(-2)
    assert vs.camera.time_idx == 2
    assert vs.crosshair_value == 200.0


def test_mpr_orientation_switch(headless_app, tmp_path):
    """Test that switching orientations recalibrates slice depths and axis limits."""
    controller, viewer, vs_id = headless_app

    # Z=10, Y=20, X=20 (Square X/Y plane bypasses the harmless boot-up axis swap)
    data = np.zeros((10, 20, 20), dtype=np.float32)
    sitk_img = sitk.GetImageFromArray(data)
    img_path = tmp_path / "square.nrrd"
    sitk.WriteImage(sitk_img, str(img_path))

    square_id = controller.file.load_image(str(img_path))
    viewer.set_image(square_id)

    viewer.set_orientation(ViewMode.AXIAL)
    assert viewer.slice_idx == 5

    viewer.set_orientation(ViewMode.CORONAL)
    assert viewer.slice_idx == 10

    viewer.set_orientation(ViewMode.SAGITTAL)
    assert viewer.slice_idx == 10


# ==========================================
# 6. VISUAL REGRESSION (Renderer Isolation)
# ==========================================


def test_renderer_checkerboard_math():
    """Test the physical checkerboard swapping algorithm directly on the raw RGBA arrays."""
    # Base = Pure White
    base_data = np.ones((50, 50, 4), dtype=np.float32)
    base_layer = RenderLayer(
        data=base_data,
        is_rgb=True,
        num_components=4,
        ww=0,
        wl=0,
        cmap_name="Grayscale",
        threshold=-1e9,
        time_idx=0,
        spacing_2d=(1.0, 1.0),
    )

    # Overlay = Pure Red
    over_data = np.ones((50, 50, 4), dtype=np.float32)
    over_data[..., 1:3] = 0.0  # Zero out Green/Blue
    over_layer = RenderLayer(
        data=over_data,
        is_rgb=True,
        num_components=4,
        ww=0,
        wl=0,
        cmap_name="Grayscale",
        threshold=-1e9,
        time_idx=0,
        spacing_2d=(1.0, 1.0),
    )

    # Trigger checkerboard with 10mm squares
    flat_rgba, (h, w) = SliceRenderer.get_slice_rgba(
        base=base_layer,
        overlay=over_layer,
        overlay_opacity=1.0,
        overlay_mode="Checkerboard",
        slice_idx=0,
        orientation=ViewMode.AXIAL,
        checkerboard_size=10.0,
        checkerboard_swap=False,
        rois=(),
    )
    res_img = flat_rgba.reshape((h, w, 4))

    # Voxel (0,0) should be Base (White)
    assert np.allclose(res_img[0, 0], [1.0, 1.0, 1.0, 1.0])

    # Voxel (0,11) crosses the 10mm checker boundary -> should be Overlay (Red)
    assert np.allclose(res_img[0, 11], [1.0, 0.0, 0.0, 1.0])


def test_renderer_registration_blending():
    """Test the Registration structural blending (50/50 mix of Base Gray and Overlay Gray)."""

    # Base: Value = 0.2 (Dark Gray)
    base_slice = np.full((10, 10), 0.2, dtype=np.float32)
    base_layer = RenderLayer(
        data=base_slice,
        is_rgb=False,
        num_components=1,
        ww=1.0,
        wl=0.5,
        cmap_name="Grayscale",
        threshold=-1e9,
        time_idx=0,
        spacing_2d=(1.0, 1.0),
    )

    # Overlay: Value = 0.8 (Light Gray)
    over_slice = np.full((10, 10), 0.8, dtype=np.float32)
    over_layer = RenderLayer(
        data=over_slice,
        is_rgb=False,
        num_components=1,
        ww=1.0,
        wl=0.5,
        cmap_name="Grayscale",
        threshold=-1e9,
        time_idx=0,
        spacing_2d=(1.0, 1.0),
    )

    # Blend at exactly 50% opacity
    flat_rgba, (h, w) = SliceRenderer.get_slice_rgba(
        base=base_layer,
        overlay=over_layer,
        overlay_opacity=0.5,
        overlay_mode="Registration",
        slice_idx=0,
        orientation=ViewMode.AXIAL,
        checkerboard_size=20.0,
        checkerboard_swap=False,
        rois=(),
    )
    res_img = flat_rgba.reshape((h, w, 4))

    # The math for Registration Mode at 0.5 opacity is a direct average.
    # Base Normalized (0.2) + Over Normalized (0.8) / 2 = 0.5
    assert res_img[5, 5, 0] == pytest.approx(0.5, abs=0.01)  # Red Channel
    assert res_img[5, 5, 1] == pytest.approx(0.5, abs=0.01)  # Green Channel
    assert res_img[5, 5, 2] == pytest.approx(0.5, abs=0.01)  # Blue Channel
    assert res_img[5, 5, 3] == 1.0  # Alpha must remain opaque


# ==========================================
# 3. PURE MATH & LOGIC ISOLATION
# ==========================================


def test_roi_statistics_math(headless_app, tmp_path):
    """Test mathematically isolated ROI physical statistics (Volume, Mass, Mean)."""
    controller, viewer, _ = headless_app

    # 1. Create an isolated 3x3x3 Base Image where center voxel is exactly 1000 HU
    base_data = np.zeros((3, 3, 3), dtype=np.float32)
    base_data[1, 1, 1] = 1000.0
    base_img = sitk.GetImageFromArray(base_data)
    base_img.SetSpacing((2.0, 2.0, 2.0))
    base_img.SetOrigin((0.0, 0.0, 0.0))
    base_path = tmp_path / "base.nrrd"
    sitk.WriteImage(base_img, str(base_path))

    base_id = controller.file.load_image(str(base_path))

    # 2. Create a 3x3x3 ROI Mask where ONLY the exact center voxel is 1
    roi_data = np.zeros((3, 3, 3), dtype=np.uint8)
    roi_data[1, 1, 1] = 1
    mask_img = sitk.GetImageFromArray(roi_data)
    mask_img.SetSpacing((2.0, 2.0, 2.0))  # 2x2x2 = 8 mm^3 volume!
    mask_img.SetOrigin((0.0, 0.0, 0.0))
    mask_path = tmp_path / "mask.nrrd"
    sitk.WriteImage(mask_img, str(mask_path))

    # 3. Load ROI and run stats
    roi_id = controller.roi.load_binary_mask(
        base_id, str(mask_path), mode="Target FG (val)", target_val=1.0
    )
    stats = controller.roi.get_roi_stats(base_id, roi_id, is_overlay=False)

    # 4. Verify pure math
    assert stats["vol"] == 0.008  # 8 mm^3 / 1000 = 0.008 cc
    assert stats["mean"] == 1000.0
    assert stats["max"] == 1000.0

    # Mass = Vol * Density. 1000 HU = 2.0 g/cc. Mass = 0.008 * 2.0 = 0.016 g
    assert stats["mass"] == pytest.approx(0.016)


def test_roi_binarization_rules(headless_app, tmp_path):
    """Test that loading a label map strictly obeys the binarization rules before rendering."""
    controller, viewer, vs_id = headless_app
    base_vol = controller.volumes[vs_id]

    label_map = np.array([[[0, 1, 2, 3]]], dtype=np.uint8)
    sitk_img = sitk.GetImageFromArray(label_map)
    sitk_img.SetSpacing(base_vol.spacing.tolist())
    sitk_img.SetOrigin(base_vol.origin.tolist())  # Match physical space!

    mask_path = tmp_path / "labels.nrrd"
    sitk.WriteImage(sitk_img, str(mask_path))

    roi_id = controller.roi.load_binary_mask(
        vs_id, str(mask_path), mode="Target FG (val)", target_val=2.0
    )
    roi_vol = controller.volumes[roi_id]

    assert np.count_nonzero(roi_vol.data) == 1
    assert roi_vol.data[0, 0, 0] == 1


# ... (Keep Data-In/Data-Out and Headless State Verification tests exactly the same) ...

# ==========================================
# 6. VISUAL REGRESSION (Renderer Isolation)
# ==========================================


def test_renderer_checkerboard_math():
    """Test the physical checkerboard swapping algorithm directly on the raw RGBA arrays."""
    # Arrays must be 255.0 because the renderer divides RGB by 255.0!
    base_data = np.full((1, 50, 50, 4), 255.0, dtype=np.float32)
    base_layer = RenderLayer(
        data=base_data,
        is_rgb=True,
        num_components=4,
        ww=0,
        wl=0,
        cmap_name="Grayscale",
        threshold=-1e9,
        time_idx=0,
        spacing_2d=(1.0, 1.0),
    )

    over_data = np.full((1, 50, 50, 4), 255.0, dtype=np.float32)
    over_data[..., 1:3] = 0.0
    over_layer = RenderLayer(
        data=over_data,
        is_rgb=True,
        num_components=4,
        ww=0,
        wl=0,
        cmap_name="Grayscale",
        threshold=-1e9,
        time_idx=0,
        spacing_2d=(1.0, 1.0),
    )

    flat_rgba, (h, w) = SliceRenderer.get_slice_rgba(
        base=base_layer,
        overlay=over_layer,
        overlay_opacity=1.0,
        overlay_mode="Checkerboard",
        slice_idx=0,
        orientation=ViewMode.AXIAL,
        checkerboard_size=10.0,
        checkerboard_swap=False,
        rois=(),
    )
    res_img = flat_rgba.reshape((h, w, 4))

    assert np.allclose(res_img[0, 0], [1.0, 1.0, 1.0, 1.0])
    assert np.allclose(res_img[0, 11], [1.0, 0.0, 0.0, 1.0])


def test_renderer_registration_blending():
    """Test the Registration blending (Base -> Red, Overlay -> Green)."""
    base_slice = np.full((1, 10, 10), 0.2, dtype=np.float32)
    base_layer = RenderLayer(
        data=base_slice,
        is_rgb=False,
        num_components=1,
        ww=1.0,
        wl=0.5,
        cmap_name="Grayscale",
        threshold=-1e9,
        time_idx=0,
        spacing_2d=(1.0, 1.0),
    )

    over_slice = np.full((1, 10, 10), 0.8, dtype=np.float32)
    over_layer = RenderLayer(
        data=over_slice,
        is_rgb=False,
        num_components=1,
        ww=1.0,
        wl=0.5,
        cmap_name="Grayscale",
        threshold=-1e9,
        time_idx=0,
        spacing_2d=(1.0, 1.0),
    )

    flat_rgba, (h, w) = SliceRenderer.get_slice_rgba(
        base=base_layer,
        overlay=over_layer,
        overlay_opacity=0.5,
        overlay_mode="Registration",
        slice_idx=0,
        orientation=ViewMode.AXIAL,
        checkerboard_size=20.0,
        checkerboard_swap=False,
        rois=(),
    )
    res_img = flat_rgba.reshape((h, w, 4))

    # Registration Mode puts Base in Red, Overlay in Green!
    assert res_img[5, 5, 0] == pytest.approx(0.2, abs=0.01)  # Red
    assert res_img[5, 5, 1] == pytest.approx(0.8, abs=0.01)  # Green
    assert res_img[5, 5, 2] == pytest.approx(0.2, abs=0.01)  # Blue
    assert res_img[5, 5, 3] == 1.0


# ===============
def test_history_is_pure_and_restores_physics(headless_app):
    """
    Proves that HistoryManager ONLY saves physical/radiometric state,
    and intentionally ignores Overlays and ROIs to prevent missing-file crashes.
    """
    controller, viewer, vs_id = headless_app
    vs = controller.view_states[vs_id]

    # 1. Simulate user zooming in and changing Window/Level
    viewer.set_orientation(ViewMode.AXIAL)
    vs.camera.zoom[ViewMode.AXIAL] = 3.5
    vs.display.ww = 800.0

    # 2. Simulate user adding an ROI (which history should IGNORE)
    vs.rois["fake_roi_id"] = "I am a fake ROI state"

    # 3. Save History
    controller.history.save_image_state(controller, vs_id)

    # 4. Read the raw history file directly
    history_entry = controller.history.get_image_state(controller.volumes[vs_id])

    # ASSERTIONS
    assert history_entry is not None
    assert history_entry["camera"]["zoom"]["AXIAL"] == 3.5  # Zoom was saved
    assert history_entry["display"]["ww"] == 800.0  # W/L was saved
    assert "rois" not in history_entry  # ROIs were safely ignored
    assert "overlay_path" not in history_entry  # Overlays were safely ignored


def test_workspace_strict_hierarchy_load(headless_app, synthetic_image_path, tmp_path):
    """
    Proves that the Workspace JSON saves everything (including ROIs) and
    that the load sequence uses ID Mapping to prevent ID collisions.
    """
    controller, viewer, vs_id = headless_app

    # Create a tiny Mock GUI to absorb the UI refresh calls without needing a real window
    # Create a tiny Mock GUI to absorb the UI refresh calls without needing a real window
    class MockGUI:
        def __init__(self):
            # Provide the dummy layout dictionary the viewer expects!
            self.ui_cfg = {"layout": {"window_padding": 4}}

        def show_status_message(self, msg):
            pass

        def refresh_image_list_ui(self):
            pass

        def refresh_rois_ui(self):
            pass

        def refresh_sync_ui(self):
            pass

        def on_window_resize(self):
            pass

        def set_context_viewer(self, v):
            pass

    controller.gui = MockGUI()

    # 1. Setup a complex workspace state
    viewer.zoom = 4.0
    viewer.pan_offset = [10, 20]

    # Add a mock ROI to the base image
    fake_roi_id = "99"
    controller.volumes[fake_roi_id] = type(
        "MockVol", (), {"file_paths": [synthetic_image_path]}
    )()
    controller.view_states[vs_id].rois[fake_roi_id] = type(
        "MockROI", (), {"to_dict": lambda self: {"name": "Test ROI"}}
    )()
    # 2. Save the Workspace
    ws_path = tmp_path / "test_workspace.json"
    controller.file.save_workspace(str(ws_path))

    # 3. WIPE THE CONTROLLER COMPLETELY (Simulate a fresh boot)
    controller.viewers["V1"].drop_image()
    controller.view_states.clear()
    controller.volumes.clear()
    controller.next_image_id = (
        100  # Force a completely different ID generation to test mapping!
    )

    # 4. Run the load sequence generator
    generator = load_workspace_sequence(controller.gui, controller, str(ws_path))
    for _ in generator:
        pass  # Exhaust the generator

    # ASSERTIONS
    new_vs_id = list(controller.view_states.keys())[0]  # Should be '100', not '0'
    assert new_vs_id != vs_id  # Proves ID mapping worked!

    # Did the Viewer reconnect to the new ID?
    assert controller.viewers["V1"].image_id == new_vs_id
    assert controller.viewers["V1"].zoom == 4.0
    assert controller.viewers["V1"].pan_offset == [10, 20]

    # Did the ROI get queued for loading in the JSON?
    import json

    with open(ws_path, "r") as f:
        saved_ws = json.load(f)
    assert len(saved_ws["images"][vs_id]["rois"]) == 1
    assert saved_ws["images"][vs_id]["rois"][0]["state"]["name"] == "Test ROI"
