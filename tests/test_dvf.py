import pytest
import numpy as np
import SimpleITK as sitk
from vvv.core.controller import Controller
from vvv.core.view_state import DVFState
from vvv.maths.image import SliceRenderer
from vvv.ui.gui import MainGUI
from vvv.ui.viewer import SliceViewer
from vvv.utils import ViewMode


# Center voxel carries vector [3, 4, 0] → magnitude = 5.0 (3-4-5 triple)
_DVF_VEC = np.array([3.0, 4.0, 0.0], dtype=np.float32)
_DVF_MAG = 5.0


@pytest.fixture(scope="session")
def synthetic_dvf_path(tmp_path_factory):
    """5x5x5 DVF: center voxel (2,2,2) has vector [3,4,0], all others zero."""
    data = np.zeros((5, 5, 5, 3), dtype=np.float32)
    data[2, 2, 2] = _DVF_VEC
    sitk_img = sitk.GetImageFromArray(data, isVector=True)
    sitk_img.SetSpacing((1.0, 1.0, 1.0))
    sitk_img.SetOrigin((0.0, 0.0, 0.0))
    img_path = tmp_path_factory.mktemp("data") / "synthetic_dvf.nrrd"
    sitk.WriteImage(sitk_img, str(img_path))
    return str(img_path)


@pytest.fixture
def dvf_app(synthetic_dvf_path):
    controller = Controller()
    for tag in ["V1", "V2", "V3", "V4"]:
        controller.viewers[tag] = SliceViewer(tag, controller)
    gui = MainGUI(controller)
    controller.gui = gui
    vs_id = controller.file.load_image(synthetic_dvf_path)
    viewer = controller.viewers["V1"]
    viewer.set_image(vs_id)
    gui.context_viewer = viewer
    gui.on_window_resize()
    return controller, viewer, vs_id


# ==========================================
# 1. LOADING & METADATA
# ==========================================


def test_dvf_detection(dvf_app):
    """Vector image is detected as DVF, not as RGB or a regular 4D sequence."""
    controller, _, vs_id = dvf_app
    vol = controller.volumes[vs_id]

    assert vol.is_dvf is True
    assert getattr(vol, "is_rgb", False) is False
    assert vol.num_components == 3


def test_dvf_data_layout(dvf_app):
    """After loading, components are axis 0: shape is (3, Z, Y, X)."""
    controller, _, vs_id = dvf_app
    vol = controller.volumes[vs_id]

    assert vol.data.shape == (3, 5, 5, 5)
    assert vol.shape3d == (5, 5, 5)
    # num_timepoints == 3 because the (3,Z,Y,X) array looks like a 4D sequence
    assert vol.num_timepoints == 3


def test_dvf_known_vector_in_array(dvf_app):
    """Center voxel stores the expected displacement vector per component."""
    controller, _, vs_id = dvf_app
    vol = controller.volumes[vs_id]

    assert vol.data[0, 2, 2, 2] == pytest.approx(3.0)  # dx
    assert vol.data[1, 2, 2, 2] == pytest.approx(4.0)  # dy
    assert vol.data[2, 2, 2, 2] == pytest.approx(0.0)  # dz


def test_dvf_zero_voxels(dvf_app):
    """Non-displaced voxels store zero vectors."""
    controller, _, vs_id = dvf_app
    vol = controller.volumes[vs_id]

    assert np.all(vol.data[:, 0, 0, 0] == 0.0)
    assert np.all(vol.data[:, 4, 4, 4] == 0.0)


# ==========================================
# 2. COMPONENT DISPLAY (4D-LIKE SCROLLING)
# ==========================================


def test_dvf_crosshair_per_component(dvf_app):
    """time_idx selects a single displacement component at the crosshair voxel."""
    controller, viewer, vs_id = dvf_app
    vs = controller.view_states[vs_id]
    viewer.set_orientation(ViewMode.AXIAL)

    # Place crosshair at center voxel (ix=2, iy=2, iz=2)
    viewer.update_crosshair_data(pix_x=2.5, pix_y=2.5)

    vs.camera.time_idx = 0
    vs.init_crosshair_to_slices()
    assert vs.crosshair_value == pytest.approx(3.0)  # dx

    vs.camera.time_idx = 1
    vs.init_crosshair_to_slices()
    assert vs.crosshair_value == pytest.approx(4.0)  # dy

    vs.camera.time_idx = 2
    vs.init_crosshair_to_slices()
    assert vs.crosshair_value == pytest.approx(0.0)  # dz


def test_dvf_component_scroll(dvf_app):
    """on_time_scroll cycles through the three displacement components."""
    controller, viewer, vs_id = dvf_app
    vs = controller.view_states[vs_id]
    viewer.set_image(vs_id)
    viewer.set_orientation(ViewMode.AXIAL)
    viewer.update_crosshair_data(pix_x=2.5, pix_y=2.5)

    assert vs.camera.time_idx == 0
    viewer.on_time_scroll(1)
    assert vs.camera.time_idx == 1
    viewer.on_time_scroll(1)
    assert vs.camera.time_idx == 2
    # Wraps back to 0
    viewer.on_time_scroll(1)
    assert vs.camera.time_idx == 0


# ==========================================
# 3. FULL VECTOR & MAGNITUDE
# ==========================================


def test_dvf_tracker_full_vector(dvf_app):
    """Controller tracker returns all 3 displacement components for DVF voxels."""
    controller, viewer, vs_id = dvf_app
    vs = controller.view_states[vs_id]
    viewer.set_orientation(ViewMode.AXIAL)
    viewer.update_crosshair_data(pix_x=2.5, pix_y=2.5)

    phys = vs.camera.crosshair_phys_coord
    result = controller.get_pixel_values_at_phys(vs_id, phys, time_idx=0)

    assert result is not None
    base_val = result["base_val"]
    assert base_val is not None
    assert len(base_val) == 3
    assert np.allclose(base_val, _DVF_VEC)


def test_dvf_magnitude(dvf_app):
    """L2 norm of the center voxel vector equals 5.0 (3-4-5 triple)."""
    controller, _, vs_id = dvf_app
    vol = controller.volumes[vs_id]

    vec = vol.data[:, 2, 2, 2]
    assert np.linalg.norm(vec) == pytest.approx(_DVF_MAG)


def test_dvf_zero_magnitude_at_background(dvf_app):
    """Undisplaced voxels have zero magnitude."""
    controller, _, vs_id = dvf_app
    vol = controller.volumes[vs_id]

    assert np.linalg.norm(vol.data[:, 0, 0, 0]) == pytest.approx(0.0)


def test_dvf_tracker_zero_at_background(dvf_app):
    """Tracker returns zero vector at a non-displaced voxel."""
    controller, viewer, vs_id = dvf_app
    vs = controller.view_states[vs_id]

    # Corner voxel (0,0,0) — slice_idx=0 in axial, click at pixel 0.5, 0.5
    viewer.set_orientation(ViewMode.AXIAL)
    vs.camera.slices[ViewMode.AXIAL] = 0
    viewer.update_crosshair_data(pix_x=0.5, pix_y=0.5)

    phys = vs.camera.crosshair_phys_coord
    result = controller.get_pixel_values_at_phys(vs_id, phys, time_idx=0)

    assert result is not None
    assert np.allclose(result["base_val"], [0.0, 0.0, 0.0])


# ==========================================
# 4. SYNC INTEGRATION
# ==========================================


def test_dvf_can_join_sync_group_and_sync_components(dvf_app, tmp_path):
    """A DVF image can join a sync group and syncs its component index (time_idx) like a 4D image."""
    controller, viewer, vs_id_dvf = dvf_app

    # 4D sequence with 3 frames
    vols = [sitk.GetImageFromArray(np.zeros((5, 5, 5), dtype=np.float32)) for _ in range(3)]
    img = sitk.JoinSeries(vols)
    path = str(tmp_path / "seq.nrrd")
    sitk.WriteImage(img, path)
    vs_id_4d = controller.file.load_image(path)

    controller.set_sync_group(vs_id_4d, 1)
    controller.set_sync_group(vs_id_dvf, 1)

    assert controller.view_states[vs_id_4d].sync_group == 1
    assert controller.view_states[vs_id_dvf].sync_group == 1

    viewer.set_image(vs_id_4d)
    viewer.on_time_scroll(2)

    # Both should now be on time_idx 2 (Frame 2 for 4D, Dz for DVF)
    assert controller.view_states[vs_id_4d].camera.time_idx == 2
    assert controller.view_states[vs_id_dvf].camera.time_idx == 2


# ==========================================
# 5. DVF STATE (VECTOR DISPLAY SETTINGS)
# ==========================================


def test_dvf_state_defaults():
    """DVFState initializes with the correct default values for vector arrow rendering."""
    state = DVFState()
    assert state.display_mode == "Vector Field"
    assert state.vector_sampling == 5
    assert state.vector_scale == pytest.approx(1.0)
    assert state.vector_thickness == pytest.approx(1.0)
    assert state.vector_color_min == [0, 255, 255, 255]
    assert state.vector_color_max == [255, 0, 0, 255]
    assert state.vector_color_max_mag == pytest.approx(10.0)
    assert state.vector_min_length_arrow == pytest.approx(3.0)
    assert state.vector_min_length_draw == pytest.approx(0.0)
    assert state.vector_precision == 2


def test_dvf_state_serialization_roundtrip():
    """to_dict / from_dict preserves all DVFState fields unchanged."""
    original = DVFState()
    original.display_mode = "Component"
    original.vector_sampling = 10
    original.vector_scale = 2.5
    original.vector_thickness = 3.0
    original.vector_color_min = [0, 255, 0, 200]
    original.vector_color_max = [255, 0, 255, 128]
    original.vector_color_max_mag = 25.0
    original.vector_min_length_arrow = 0.5
    original.vector_min_length_draw = 0.3
    original.vector_precision = 4

    restored = DVFState()
    restored.from_dict(original.to_dict())

    assert restored.display_mode == "Component"
    assert restored.vector_sampling == 10
    assert restored.vector_scale == pytest.approx(2.5)
    assert restored.vector_thickness == pytest.approx(3.0)
    assert restored.vector_color_min == [0, 255, 0, 200]
    assert restored.vector_color_max == [255, 0, 255, 128]
    assert restored.vector_color_max_mag == pytest.approx(25.0)
    assert restored.vector_min_length_arrow == pytest.approx(0.5)
    assert restored.vector_min_length_draw == pytest.approx(0.3)
    assert restored.vector_precision == 4


def test_dvf_state_dirty_flag(dvf_app):
    """Changing a DVFState field marks the parent ViewState geometry and data as dirty."""
    controller, _, vs_id = dvf_app
    vs = controller.view_states[vs_id]

    vs.is_geometry_dirty = False
    vs.is_data_dirty = False

    vs.dvf.display_mode = "Component"

    assert vs.is_geometry_dirty is True
    assert vs.is_data_dirty is True


def test_dvf_state_no_dirty_on_same_value(dvf_app):
    """Setting a DVFState field to its current value does not trigger dirty flags."""
    controller, _, vs_id = dvf_app
    vs = controller.view_states[vs_id]

    vs.dvf.vector_sampling = 5  # ensure it is at the default
    vs.is_geometry_dirty = False
    vs.is_data_dirty = False

    vs.dvf.vector_sampling = 5  # no-op: same value

    assert vs.is_geometry_dirty is False
    assert vs.is_data_dirty is False


# ==========================================
# 6. VECTOR FIELD SLICE EXTRACTION & AXIS MAPPING
# ==========================================


def test_dvf_axial_vector_component_mapping(dvf_app):
    """
    Axial slice at z=2: h_comp=vx, v_comp=vy, d_comp=vz — no sign flips.
    Center voxel (2,2) must expose the full [dx, dy, dz] = [3, 4, 0] triple.
    """
    controller, _, vs_id = dvf_app
    data = controller.volumes[vs_id].data  # (3, 5, 5, 5)

    vx = SliceRenderer.get_raw_slice(data, False, 0, 2, ViewMode.AXIAL)
    vy = SliceRenderer.get_raw_slice(data, False, 1, 2, ViewMode.AXIAL)
    vz = SliceRenderer.get_raw_slice(data, False, 2, 2, ViewMode.AXIAL)

    assert vx[2, 2] == pytest.approx(3.0)  # h_comp
    assert vy[2, 2] == pytest.approx(4.0)  # v_comp
    assert vz[2, 2] == pytest.approx(0.0)  # d_comp


def test_dvf_sagittal_vector_component_mapping(dvf_app):
    """
    Sagittal slice at x=2: h_comp=-vy, v_comp=-vz, d_comp=vx.
    extract_slice applies flipud+fliplr; on a 5×5 grid the center stays at [2,2].
    """
    controller, _, vs_id = dvf_app
    data = controller.volumes[vs_id].data  # (3, 5, 5, 5)

    vx = SliceRenderer.get_raw_slice(data, False, 0, 2, ViewMode.SAGITTAL)
    vy = SliceRenderer.get_raw_slice(data, False, 1, 2, ViewMode.SAGITTAL)
    vz = SliceRenderer.get_raw_slice(data, False, 2, 2, ViewMode.SAGITTAL)

    assert (-vy)[2, 2] == pytest.approx(-4.0)  # h_comp
    assert (-vz)[2, 2] == pytest.approx(0.0)   # v_comp
    assert vx[2, 2] == pytest.approx(3.0)       # d_comp


def test_dvf_coronal_vector_component_mapping(dvf_app):
    """
    Coronal slice at y=2: h_comp=vx, v_comp=-vz, d_comp=vy.
    extract_slice applies flipud only; center row stays at index 2 in a 5×5 grid.
    """
    controller, _, vs_id = dvf_app
    data = controller.volumes[vs_id].data  # (3, 5, 5, 5)

    vx = SliceRenderer.get_raw_slice(data, False, 0, 2, ViewMode.CORONAL)
    vy = SliceRenderer.get_raw_slice(data, False, 1, 2, ViewMode.CORONAL)
    vz = SliceRenderer.get_raw_slice(data, False, 2, 2, ViewMode.CORONAL)

    assert vx[2, 2] == pytest.approx(3.0)    # h_comp
    assert (-vz)[2, 2] == pytest.approx(0.0) # v_comp
    assert vy[2, 2] == pytest.approx(4.0)    # d_comp


# ==========================================
# 7. COLOR INTERPOLATION FOR MAGNITUDE
# ==========================================


def _interpolate_color(mag_3d, c_min, c_max, t_min, t_max):
    """Replicate the color interpolation formula used in draw_vector_field."""
    t_col = min(1.0, max(0.0, (mag_3d - t_min) / (t_max - t_min)))
    c = np.array(c_min, dtype=np.float32) + t_col * (
        np.array(c_max, dtype=np.float32) - np.array(c_min, dtype=np.float32)
    )
    return [int(c[0]), int(c[1]), int(c[2]), int(c[3])]


def test_dvf_color_at_zero_magnitude():
    """Magnitude at the minimum threshold maps to vector_color_min (cyan by default)."""
    state = DVFState()
    color = _interpolate_color(
        0.0, state.vector_color_min, state.vector_color_max,
        state.vector_min_length_draw, state.vector_color_max_mag,
    )
    assert color == [0, 255, 255, 255]


def test_dvf_color_at_half_max_magnitude():
    """Magnitude at half of vector_color_max_mag maps to the midpoint color."""
    state = DVFState()
    # Default max_mag=10.0, c_min=[0,255,255,255], c_max=[255,0,0,255]
    # At mag=5.0: t=0.5 → [127, 127, 127, 255]
    color = _interpolate_color(
        5.0, state.vector_color_min, state.vector_color_max,
        state.vector_min_length_draw, state.vector_color_max_mag,
    )
    assert color == [127, 127, 127, 255]


def test_dvf_color_clamped_above_max_magnitude():
    """Magnitude beyond vector_color_max_mag is clamped to vector_color_max (red by default)."""
    state = DVFState()
    color = _interpolate_color(
        999.0, state.vector_color_min, state.vector_color_max,
        state.vector_min_length_draw, state.vector_color_max_mag,
    )
    assert color == [255, 0, 0, 255]
