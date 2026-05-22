import numpy as np
import pytest
import SimpleITK as sitk

from vvv.core.view_state import DisplayState
from vvv.core.controller import Controller
from vvv.ui.gui import MainGUI
from vvv.ui.viewer import SliceViewer


def _viewer2(controller):
    v = controller.viewers.get("V2")
    if v is None or v.view_state is None:
        pytest.skip("Second viewer not available")
    return v


# ─────────────────────────────────────────────────────────────────────────────
# 1. DisplayState histogram fields — pure unit tests
# ─────────────────────────────────────────────────────────────────────────────

class TestDisplayStateHistogramFields:
    def test_default_values(self):
        dsp = DisplayState()
        assert dsp.hist_use_bars is True
        assert dsp.hist_use_log is True
        assert dsp.hist_x_center is None
        assert dsp.hist_x_range is None
        assert dsp.hist_y_max is None

    def test_to_dict_includes_all_hist_fields(self):
        dsp = DisplayState()
        dsp.hist_use_bars = True
        dsp.hist_use_log = False
        dsp.hist_x_center = -100.0
        dsp.hist_x_range = 500.0
        dsp.hist_y_max = 3.5
        d = dsp.to_dict()
        assert d["hist_use_bars"] is True
        assert d["hist_use_log"] is False
        assert d["hist_x_center"] == pytest.approx(-100.0)
        assert d["hist_x_range"] == pytest.approx(500.0)
        assert d["hist_y_max"] == pytest.approx(3.5)

    def test_from_dict_restores_all_hist_fields(self):
        dsp = DisplayState()
        dsp.from_dict({
            "hist_use_bars": True,
            "hist_use_log": False,
            "hist_x_center": -300.0,
            "hist_x_range": 2000.0,
            "hist_y_max": 6.1,
        })
        assert dsp.hist_use_bars is True
        assert dsp.hist_use_log is False
        assert dsp.hist_x_center == pytest.approx(-300.0)
        assert dsp.hist_x_range == pytest.approx(2000.0)
        assert dsp.hist_y_max == pytest.approx(6.1)

    def test_from_dict_applies_defaults_for_missing_keys(self):
        dsp = DisplayState()
        dsp.from_dict({})
        assert dsp.hist_use_bars is True
        assert dsp.hist_use_log is True
        assert dsp.hist_x_center is None
        assert dsp.hist_x_range is None
        assert dsp.hist_y_max is None

    def test_hist_fields_not_in_data_fields_no_rerender(self):
        """Changing histogram preferences must NOT set is_data_dirty."""
        class FakeVS:
            is_data_dirty = False

        fake_vs = FakeVS()
        dsp = DisplayState()
        object.__setattr__(dsp, "_parent", fake_vs)
        dsp.hist_use_bars = True
        dsp.hist_use_log = False
        dsp.hist_x_center = 100.0
        dsp.hist_x_range = 400.0
        dsp.hist_y_max = 5.0
        assert fake_vs.is_data_dirty is False

    def test_roundtrip_serialization(self):
        dsp1 = DisplayState()
        dsp1.hist_use_bars = True
        dsp1.hist_use_log = False
        dsp1.hist_x_center = -500.0
        dsp1.hist_x_range = 3000.0
        dsp1.hist_y_max = 7.2

        dsp2 = DisplayState()
        dsp2.from_dict(dsp1.to_dict())

        assert dsp2.hist_use_bars == dsp1.hist_use_bars
        assert dsp2.hist_use_log == dsp1.hist_use_log
        assert dsp2.hist_x_center == pytest.approx(dsp1.hist_x_center)
        assert dsp2.hist_x_range == pytest.approx(dsp1.hist_x_range)
        assert dsp2.hist_y_max == pytest.approx(dsp1.hist_y_max)


# ─────────────────────────────────────────────────────────────────────────────
# 2. ViewState.use_log_y — property delegation to display.hist_use_log
# ─────────────────────────────────────────────────────────────────────────────

def test_use_log_y_reads_from_display(headless_gui_app):
    _, _, viewer, _ = headless_gui_app
    vs = viewer.view_state
    assert vs.use_log_y is True
    assert vs.display.hist_use_log is True


def test_use_log_y_setter_propagates_to_display(headless_gui_app):
    _, _, viewer, _ = headless_gui_app
    vs = viewer.view_state
    vs.use_log_y = False
    assert vs.display.hist_use_log is False


def test_use_log_y_getter_reflects_display_change(headless_gui_app):
    _, _, viewer, _ = headless_gui_app
    vs = viewer.view_state
    vs.display.hist_use_log = False
    assert vs.use_log_y is False
    vs.display.hist_use_log = True
    assert vs.use_log_y is True


# ─────────────────────────────────────────────────────────────────────────────
# 3. Histogram computation and dirty-flag management
# ─────────────────────────────────────────────────────────────────────────────

def test_histogram_is_dirty_on_init(headless_gui_app):
    _, _, viewer, _ = headless_gui_app
    assert viewer.view_state.histogram_is_dirty is True


def test_update_histogram_populates_data(headless_gui_app):
    _, _, viewer, _ = headless_gui_app
    vs = viewer.view_state
    vs.update_histogram()

    assert vs.histogram_is_dirty is False
    assert vs.hist_data_x is not None
    assert vs.hist_data_y is not None
    assert len(vs.hist_data_x) == 256
    assert len(vs.hist_data_y) == 256


def test_histogram_counts_sum_to_total_voxels(headless_gui_app):
    _, _, viewer, _ = headless_gui_app
    vs = viewer.view_state
    vs.update_histogram()

    total_voxels = viewer.volume.data.size
    assert int(vs.hist_data_y.sum()) == total_voxels


def test_histogram_uniform_volume_peaks_at_single_bin(headless_gui_app):
    """Uniform data (all 100.0) should yield exactly one non-zero bin."""
    _, _, viewer, _ = headless_gui_app
    vs = viewer.view_state
    vs.update_histogram()

    non_zero_bins = np.count_nonzero(vs.hist_data_y)
    assert non_zero_bins == 1


def test_volume_data_change_invalidates_hist_vol_data_id(headless_gui_app):
    """After replacing volume.data, the stored _hist_vol_data_id must differ."""
    _, _, viewer, _ = headless_gui_app
    vs = viewer.view_state
    vs.update_histogram()
    vs._hist_vol_data_id = id(viewer.volume.data)  # simulate what _refresh does

    # Simulate image reload by replacing the numpy array object
    viewer.volume.data = np.zeros_like(viewer.volume.data)

    assert id(viewer.volume.data) != vs._hist_vol_data_id


# ─────────────────────────────────────────────────────────────────────────────
# 4. Colorscale pure numpy logic
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
# 5. DVF histogram: displacement magnitude, not mixed components
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
    vs = dvf_viewer.view_state
    vs.update_histogram()

    # All voxels except one have zero displacement → magnitude = 0.
    # One voxel has magnitude = 5.0.
    # Bins should cover [0, 5] and all counts should be ≥ 0.
    assert vs.hist_data_x is not None
    assert vs.hist_data_y is not None
    assert vs.hist_data_x[0] >= 0.0, "DVF magnitude must be non-negative"
    assert vs.hist_data_x[-1] >= 0.0


def test_dvf_histogram_max_bin_is_near_magnitude(dvf_viewer):
    """The highest non-zero bin must be close to the known magnitude of 5.0."""
    vs = dvf_viewer.view_state
    vs.update_histogram()

    nonzero = np.where(vs.hist_data_y > 0)[0]
    assert len(nonzero) > 0
    last_bin_center = float(vs.hist_data_x[nonzero[-1]])
    assert last_bin_center == pytest.approx(_DVF_MAG, rel=0.05)


def test_dvf_histogram_counts_sum_to_voxel_count(dvf_viewer):
    """Magnitude histogram must account for every spatial voxel."""
    vs = dvf_viewer.view_state
    vs.update_histogram()

    vol = dvf_viewer.volume
    n_voxels = int(np.prod(vol.data.shape[1:]))  # (z, y, x) only
    assert int(vs.hist_data_y.sum()) == n_voxels


def test_dvf_histogram_all_x_values_non_negative(dvf_viewer):
    """Magnitude is always ≥ 0; no bin should have a negative center."""
    vs = dvf_viewer.view_state
    vs.update_histogram()

    assert float(vs.hist_data_x[0]) >= 0.0
