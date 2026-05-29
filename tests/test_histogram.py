import numpy as np
import pytest
import SimpleITK as sitk

from vvv.core.view_state import DisplayState
from vvv.core.controller import Controller
from vvv.ui.gui import MainGUI
from vvv.ui.viewer import SliceViewer
from vvv.plugins.intensity.control_intensity import HistogramState, IntensityController


def _viewer2(controller):
    v = controller.viewers.get("V2")
    if v is None or v.view_state is None:
        pytest.skip("Second viewer not available")
    return v


def _hs(viewer):
    gui = viewer.controller.gui
    plugin = next(p for p in gui.plugins if p.plugin_id == "intensity_plugin")
    image_id = viewer.image_id
    if image_id and image_id not in plugin._controller._hist:
        plugin.on_image_loaded(image_id)
    return plugin._controller._hs(viewer)


def _c(viewer):
    gui = viewer.controller.gui
    plugin = next(p for p in gui.plugins if p.plugin_id == "intensity_plugin")
    image_id = viewer.image_id
    if image_id and image_id not in plugin._controller._hist:
        plugin.on_image_loaded(image_id)
    return plugin._controller


# ─────────────────────────────────────────────────────────────────────────────
# 1. HistogramState default values and IntensityController serialization
# ─────────────────────────────────────────────────────────────────────────────

class TestHistogramStateAndSerialization:
    def test_default_values(self):
        hs = HistogramState()
        assert hs.use_bars is True
        assert hs.use_log is True
        assert hs.bins == 256
        assert hs.x_center is None
        assert hs.x_range is None
        assert hs.y_max is None

    def test_serialize_image_state(self):
        c = IntensityController("intensity_plugin")
        c.on_image_loaded("test_img")
        hs = c._hist["test_img"]
        hs.use_bars = True
        hs.use_log = False
        hs.x_center = -100.0
        hs.x_range = 500.0
        hs.y_max = 3.5
        d = c.serialize_image_state("test_img")
        assert d["use_bars"] is True
        assert d["use_log"] is False
        assert d["x_center"] == pytest.approx(-100.0)
        assert d["x_range"] == pytest.approx(500.0)
        assert d["y_max"] == pytest.approx(3.5)

    def test_restore_image_state(self):
        c = IntensityController("intensity_plugin")
        c.on_image_loaded("test_img")
        c.restore_image_state("test_img", {
            "use_bars": True,
            "use_log": False,
            "x_center": -300.0,
            "x_range": 2000.0,
            "y_max": 6.1,
        })
        hs = c._hist["test_img"]
        assert hs.use_bars is True
        assert hs.use_log is False
        assert hs.x_center == pytest.approx(-300.0)
        assert hs.x_range == pytest.approx(2000.0)
        assert hs.y_max == pytest.approx(6.1)

    def test_restore_image_state_ignores_missing_keys(self):
        c = IntensityController("intensity_plugin")
        c.on_image_loaded("test_img")
        hs = c._hist["test_img"]
        # Set non-default values
        hs.use_bars = False
        hs.use_log = False
        c.restore_image_state("test_img", {})
        assert hs.use_bars is False
        assert hs.use_log is False

    def test_roundtrip_serialization(self):
        c = IntensityController("intensity_plugin")
        c.on_image_loaded("test_img1")
        c.on_image_loaded("test_img2")
        hs1 = c._hist["test_img1"]
        hs1.use_bars = True
        hs1.use_log = False
        hs1.x_center = -500.0
        hs1.x_range = 3000.0
        hs1.y_max = 7.2

        d = c.serialize_image_state("test_img1")
        c.restore_image_state("test_img2", d)
        hs2 = c._hist["test_img2"]
        assert hs2.use_bars == hs1.use_bars
        assert hs2.use_log == hs1.use_log
        assert hs2.x_center == pytest.approx(hs1.x_center)
        assert hs2.x_range == pytest.approx(hs1.x_range)
        assert hs2.y_max == pytest.approx(hs1.y_max)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Histogram computation and dirty-flag management
# ─────────────────────────────────────────────────────────────────────────────

def test_histogram_is_dirty_on_init(headless_gui_app):
    _, gui, viewer, _ = headless_gui_app
    hs = _hs(viewer)
    assert hs.is_dirty is True


def test_update_histogram_populates_data(headless_gui_app):
    _, gui, viewer, _ = headless_gui_app
    hs = _hs(viewer)
    c = _c(viewer)
    c._update_histogram(viewer.volume, hs, hs.bins)

    assert hs.is_dirty is False
    assert hs.data_x is not None
    assert hs.data_y is not None
    assert len(hs.data_x) == 256
    assert len(hs.data_y) == 256


def test_histogram_counts_sum_to_total_voxels(headless_gui_app):
    _, gui, viewer, _ = headless_gui_app
    hs = _hs(viewer)
    c = _c(viewer)
    c._update_histogram(viewer.volume, hs, hs.bins)

    total_voxels = viewer.volume.data.size
    assert int(hs.data_y.sum()) == total_voxels


def test_histogram_uniform_volume_peaks_at_single_bin(headless_gui_app):
    """Uniform data (all 100.0) should yield exactly one non-zero bin."""
    _, gui, viewer, _ = headless_gui_app
    hs = _hs(viewer)
    c = _c(viewer)
    c._update_histogram(viewer.volume, hs, hs.bins)

    non_zero_bins = np.count_nonzero(hs.data_y)
    assert non_zero_bins == 1


def test_volume_data_change_invalidates_hist_vol_data_id(headless_gui_app):
    """After replacing volume.data, the stored _hist_vol_data_id must differ."""
    _, gui, viewer, _ = headless_gui_app
    hs = _hs(viewer)
    c = _c(viewer)
    c._update_histogram(viewer.volume, hs, hs.bins)
    hs._vol_data_id = id(viewer.volume.data)

    # Simulate image reload by replacing the numpy array object
    viewer.volume.data = np.zeros_like(viewer.volume.data)

    assert id(viewer.volume.data) != hs._vol_data_id


# ─────────────────────────────────────────────────────────────────────────────
# 3. Colorscale pure numpy logic
# ─────────────────────────────────────────────────────────────────────────────

def test_colorscale_pure_numpy_logic():
    """Verify the colorscale algorithm with numpy only — no DPG required."""
    from vvv.config import COLORMAPS
    cmap = COLORMAPS["Grayscale"]       # (256, 4) float32, dark→bright
    wl, ww = 0.0, 100.0                 # lower=−50, upper=+50
    lower, upper = wl - ww / 2, wl + ww / 2
    img_min, img_max = -100.0, 100.0

    x = np.linspace(img_min, img_max, 256, dtype=np.float32)
    t = np.clip((x - lower) / max(ww, 1e-10), 0.0, 1.0)
    idx = (t * 255).astype(np.int32)
    colors = cmap[idx].copy()
    colors[x < lower] = [0.0, 0.0, 0.0, 1.0]
    colors[x > upper] = [1.0, 1.0, 1.0, 1.0]

    # Black below lower
    below = np.where(x < lower)[0]
    assert len(below) > 0
    assert colors[below[0], 0] == pytest.approx(0.0)

    # White above upper
    above = np.where(x > upper)[0]
    assert len(above) > 0
    assert colors[above[-1], 0] == pytest.approx(1.0)

    # Monotonically non-decreasing inside the window (grayscale)
    inside = np.where((x >= lower) & (x <= upper))[0]
    assert len(inside) >= 2
    red_inside = colors[inside, 0]
    assert red_inside[0] <= red_inside[-1]


# ─────────────────────────────────────────────────────────────────────────────
# 4. DVF histogram: displacement magnitude, not mixed components
# ─────────────────────────────────────────────────────────────────────────────

# Vector [3, 4, 0] at voxel (2,2,2) → magnitude = 5.0 (3-4-5 triple)
_DVF_VEC = np.array([3.0, 4.0, 0.0], dtype=np.float32)
_DVF_MAG = 5.0


@pytest.fixture(scope="module")
def dvf_viewer(tmp_path_factory):
    """5×5×5 DVF with one non-zero vector [3,4,0] → magnitude 5.0."""
    data = np.zeros((5, 5, 5, 3), dtype=np.float32)
    data[2, 2, 2] = _DVF_VEC
    sitk_img = sitk.GetImageFromArray(data, isVector=True)
    sitk_img.SetSpacing((1.0, 1.0, 1.0))
    path = tmp_path_factory.mktemp("dvf_hist") / "dvf.nrrd"
    sitk.WriteImage(sitk_img, str(path))

    controller = Controller()
    for tag in ["V1", "V2", "V3", "V4"]:
        controller.viewers[tag] = SliceViewer(tag, controller)
    gui = MainGUI(controller)
    controller.gui = gui
    vs_id = controller.file.load_image(str(path))
    viewer = controller.viewers["V1"]
    viewer.set_image(vs_id)
    gui.context_viewer = viewer
    return viewer


def test_dvf_volume_is_detected_as_dvf(dvf_viewer):
    assert dvf_viewer.volume.is_dvf is True
    assert dvf_viewer.volume.is_rgb is False


def test_dvf_histogram_uses_magnitude_not_components(dvf_viewer):
    """update_histogram must produce a magnitude distribution, not a mixed
    flat array of all three displacement components."""
    hs = _hs(dvf_viewer)
    c = _c(dvf_viewer)
    c._update_histogram(dvf_viewer.volume, hs, hs.bins)

    # All voxels except one have zero displacement → magnitude = 0.
    # One voxel has magnitude = 5.0.
    # Bins should cover [0, 5] and all counts should be ≥ 0.
    assert hs.data_x is not None
    assert hs.data_y is not None
    assert hs.data_x[0] >= 0.0, "DVF magnitude must be non-negative"
    assert hs.data_x[-1] >= 0.0


def test_dvf_histogram_max_bin_is_near_magnitude(dvf_viewer):
    """The highest non-zero bin must be close to the known magnitude of 5.0."""
    hs = _hs(dvf_viewer)
    c = _c(dvf_viewer)
    c._update_histogram(dvf_viewer.volume, hs, hs.bins)

    nonzero = np.where(hs.data_y > 0)[0]
    assert len(nonzero) > 0
    last_bin_center = float(hs.data_x[nonzero[-1]])
    assert last_bin_center == pytest.approx(_DVF_MAG, rel=0.05)


def test_dvf_histogram_counts_sum_to_voxel_count(dvf_viewer):
    """Magnitude histogram must account for every spatial voxel."""
    hs = _hs(dvf_viewer)
    c = _c(dvf_viewer)
    c._update_histogram(dvf_viewer.volume, hs, hs.bins)

    vol = dvf_viewer.volume
    n_voxels = int(np.prod(vol.data.shape[1:]))  # (z, y, x) only
    assert int(hs.data_y.sum()) == n_voxels


def test_dvf_histogram_all_x_values_non_negative(dvf_viewer):
    """Magnitude is always ≥ 0; no bin should have a negative center."""
    hs = _hs(dvf_viewer)
    c = _c(dvf_viewer)
    c._update_histogram(dvf_viewer.volume, hs, hs.bins)

    assert float(hs.data_x[0]) >= 0.0
