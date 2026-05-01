import pytest
import numpy as np
import SimpleITK as sitk
from vvv.core.controller import Controller
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
# 4. SYNC PROTECTION
# ==========================================


def test_dvf_cannot_join_sync_group(dvf_app, tmp_path):
    """A DVF image cannot be added to a sync group containing a regular 3D image."""
    controller, _, vs_id_dvf = dvf_app

    arr = np.ones((5, 5, 5), dtype=np.float32)
    img = sitk.GetImageFromArray(arr)
    path = str(tmp_path / "regular.nrrd")
    sitk.WriteImage(img, path)
    vs_id_3d = controller.file.load_image(path)

    # Put the 3D image in group 1 first
    controller.set_sync_group(vs_id_3d, 1)
    assert controller.view_states[vs_id_3d].sync_group == 1
    assert controller.view_states[vs_id_3d].sync_group == 1 # type: ignore

    # DVF must be silently rejected
    controller.set_sync_group(vs_id_dvf, 1)
    assert controller.view_states[vs_id_dvf].sync_group == 0


def test_regular_image_cannot_join_dvf_sync_group(dvf_app, tmp_path):
    """A regular 3D image cannot join a group that already contains a DVF."""
    controller, _, vs_id_dvf = dvf_app

    arr = np.ones((5, 5, 5), dtype=np.float32)
    img = sitk.GetImageFromArray(arr)
    path = str(tmp_path / "regular2.nrrd")
    sitk.WriteImage(img, path)
    vs_id_3d = controller.file.load_image(path)

    # Put the DVF in group 2 first
    controller.set_sync_group(vs_id_dvf, 2)
    assert controller.view_states[vs_id_dvf].sync_group == 2
    assert controller.view_states[vs_id_dvf].sync_group == 0 # DVF should be forced to group 0

    # Regular image must be silently rejected
    controller.set_sync_group(vs_id_3d, 2)
    assert controller.view_states[vs_id_3d].sync_group == 0
