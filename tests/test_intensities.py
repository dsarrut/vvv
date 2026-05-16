"""
Tests for the WL histogram panel:
  - DisplayState histogram fields (defaults, serialization, no-rerender)
  - ViewState.use_log_y property delegation
  - Histogram computation and dirty-flag management
  - IntensitiesUI callbacks (log, bar, center, drag, auto-center)
  - Per-image independence of histogram settings
  - WL drag-line callbacks (lower / upper / level)
  - Colorscale texture pixel generation
"""

import numpy as np
import pytest
import dearpygui.dearpygui as dpg

from vvv.config import COLORMAPS
from vvv.core.view_state import DisplayState


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _ensure_colorscale_tex():
    """Create the colorscale dynamic texture if it does not already exist."""
    if not dpg.does_item_exist("wl_colorscale_tex"):
        dpg.add_dynamic_texture(
            width=256, height=1,
            default_value=[0.5] * (256 * 4),
            tag="wl_colorscale_tex",
            parent="global_texture_registry",
        )


def _viewer2(controller):
    v = controller.viewers.get("V2")
    if v is None or v.view_state is None:
        pytest.skip("Second viewer not available")
    return v


# ─────────────────────────────────────────────────────────────────────────────
# 1. DisplayState histogram fields — pure unit tests (no DPG / no GUI)
# ─────────────────────────────────────────────────────────────────────────────

class TestDisplayStateHistogramFields:
    def test_default_values(self):
        dsp = DisplayState()
        assert dsp.hist_use_bars is False
        assert dsp.hist_use_log is True
        assert dsp.hist_auto_center is False
        assert dsp.hist_x_center is None
        assert dsp.hist_x_range is None
        assert dsp.hist_y_max is None

    def test_to_dict_includes_all_hist_fields(self):
        dsp = DisplayState()
        dsp.hist_use_bars = True
        dsp.hist_use_log = False
        dsp.hist_auto_center = True
        dsp.hist_x_center = -100.0
        dsp.hist_x_range = 500.0
        dsp.hist_y_max = 3.5
        d = dsp.to_dict()
        assert d["hist_use_bars"] is True
        assert d["hist_use_log"] is False
        assert d["hist_auto_center"] is True
        assert d["hist_x_center"] == pytest.approx(-100.0)
        assert d["hist_x_range"] == pytest.approx(500.0)
        assert d["hist_y_max"] == pytest.approx(3.5)

    def test_from_dict_restores_all_hist_fields(self):
        dsp = DisplayState()
        dsp.from_dict({
            "hist_use_bars": True,
            "hist_use_log": False,
            "hist_auto_center": True,
            "hist_x_center": -300.0,
            "hist_x_range": 2000.0,
            "hist_y_max": 6.1,
        })
        assert dsp.hist_use_bars is True
        assert dsp.hist_use_log is False
        assert dsp.hist_auto_center is True
        assert dsp.hist_x_center == pytest.approx(-300.0)
        assert dsp.hist_x_range == pytest.approx(2000.0)
        assert dsp.hist_y_max == pytest.approx(6.1)

    def test_from_dict_applies_defaults_for_missing_keys(self):
        dsp = DisplayState()
        dsp.from_dict({})
        assert dsp.hist_use_bars is False
        assert dsp.hist_use_log is True
        assert dsp.hist_auto_center is False
        assert dsp.hist_x_center is None
        assert dsp.hist_x_range is None
        assert dsp.hist_y_max is None

    def test_hist_fields_not_in_data_fields_no_rerender(self):
        """Changing histogram preferences must NOT set is_data_dirty."""
        class FakeVS:
            is_data_dirty = False

        dsp = DisplayState()
        dsp._parent = FakeVS()
        dsp.hist_use_bars = True
        dsp.hist_use_log = False
        dsp.hist_x_center = 100.0
        dsp.hist_x_range = 400.0
        dsp.hist_y_max = 5.0
        assert dsp._parent.is_data_dirty is False

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
# 4. Log / bar toggle callbacks
# ─────────────────────────────────────────────────────────────────────────────

def test_log_toggle_flips_hist_use_log(headless_gui_app):
    _, gui, viewer, _ = headless_gui_app
    vs = viewer.view_state

    assert vs.display.hist_use_log is True
    gui.intensities_ui.on_hist_log_toggle(None, None, None)
    assert vs.display.hist_use_log is False
    gui.intensities_ui.on_hist_log_toggle(None, None, None)
    assert vs.display.hist_use_log is True


def test_log_toggle_marks_histogram_dirty(headless_gui_app):
    _, gui, viewer, _ = headless_gui_app
    vs = viewer.view_state
    vs.update_histogram()
    assert vs.histogram_is_dirty is False

    gui.intensities_ui.on_hist_log_toggle(None, None, None)
    assert vs.histogram_is_dirty is True


def test_bar_toggle_flips_hist_use_bars(headless_gui_app):
    _, gui, viewer, _ = headless_gui_app
    vs = viewer.view_state

    assert vs.display.hist_use_bars is False
    gui.intensities_ui.on_hist_bar_toggle(None, None, None)
    assert vs.display.hist_use_bars is True
    gui.intensities_ui.on_hist_bar_toggle(None, None, None)
    assert vs.display.hist_use_bars is False


def test_bar_toggle_marks_histogram_dirty(headless_gui_app):
    _, gui, viewer, _ = headless_gui_app
    vs = viewer.view_state
    vs.update_histogram()
    assert vs.histogram_is_dirty is False

    gui.intensities_ui.on_hist_bar_toggle(None, None, None)
    assert vs.histogram_is_dirty is True


# ─────────────────────────────────────────────────────────────────────────────
# 5. Axis range callbacks (Center, Width, YMax, Auto-center)
# ─────────────────────────────────────────────────────────────────────────────

def test_hist_center_button_sets_x_center_to_wl(headless_gui_app):
    _, gui, viewer, _ = headless_gui_app
    vs = viewer.view_state

    gui.intensities_ui.on_hist_center(None, None, None)

    assert vs.display.hist_x_center == pytest.approx(vs.display.wl)
    assert vs.display.hist_x_range == pytest.approx(vs.display.ww * 4.0 / 3.0)


def test_hist_xcenter_drag_updates_hist_x_center(headless_gui_app):
    _, gui, viewer, _ = headless_gui_app
    vs = viewer.view_state
    vs.display.hist_x_range = 400.0  # ensure range is initialised

    gui.intensities_ui.on_hist_xcenter_drag(None, 50.0, None)

    assert vs.display.hist_x_center == pytest.approx(50.0)


def test_hist_xwidth_drag_updates_hist_x_range(headless_gui_app):
    _, gui, viewer, _ = headless_gui_app
    vs = viewer.view_state
    vs.display.hist_x_center = 0.0

    gui.intensities_ui.on_hist_xwidth_drag(None, 300.0, None)

    assert vs.display.hist_x_range == pytest.approx(300.0)


def test_hist_xwidth_drag_clamps_to_positive(headless_gui_app):
    _, gui, viewer, _ = headless_gui_app
    vs = viewer.view_state
    vs.display.hist_x_center = 0.0

    gui.intensities_ui.on_hist_xwidth_drag(None, -10.0, None)

    assert vs.display.hist_x_range >= 1e-5


def test_hist_ymax_drag_updates_hist_y_max(headless_gui_app):
    _, gui, viewer, _ = headless_gui_app
    vs = viewer.view_state

    gui.intensities_ui.on_hist_ymax_drag(None, 5.0, None)

    assert vs.display.hist_y_max == pytest.approx(5.0)


def test_hist_ymax_drag_clamps_to_positive(headless_gui_app):
    _, gui, viewer, _ = headless_gui_app
    vs = viewer.view_state

    gui.intensities_ui.on_hist_ymax_drag(None, -3.0, None)

    assert vs.display.hist_y_max >= 1e-5


def test_hist_auto_center_toggles_flag(headless_gui_app):
    _, gui, viewer, _ = headless_gui_app
    vs = viewer.view_state

    assert vs.display.hist_auto_center is False
    gui.intensities_ui.on_hist_auto_center(None, None, None)
    assert vs.display.hist_auto_center is True
    gui.intensities_ui.on_hist_auto_center(None, None, None)
    assert vs.display.hist_auto_center is False


def test_callbacks_ignore_none_app_data_without_raising(headless_gui_app):
    _, gui, _, _ = headless_gui_app
    # These should silently no-op, not raise
    gui.intensities_ui.on_hist_xcenter_drag(None, None, None)
    gui.intensities_ui.on_hist_xwidth_drag(None, None, None)
    gui.intensities_ui.on_hist_ymax_drag(None, None, None)


# ─────────────────────────────────────────────────────────────────────────────
# 6. WL drag-line callbacks (histogram bars → WL state)
# ─────────────────────────────────────────────────────────────────────────────

def test_drag_lower_adjusts_ww_symmetrically(headless_gui_app):
    """Moving lower bar to wl−100 must yield ww=200 with wl unchanged."""
    _, gui, viewer, _ = headless_gui_app
    vs = viewer.view_state
    vs.display.wl = 0.0

    gui.intensities_ui.on_hist_drag_lower(None, -100.0, None)

    assert vs.display.ww == pytest.approx(200.0)
    assert vs.display.wl == pytest.approx(0.0)


def test_drag_upper_adjusts_ww_symmetrically(headless_gui_app):
    """Moving upper bar to wl+150 must yield ww=300 with wl unchanged."""
    _, gui, viewer, _ = headless_gui_app
    vs = viewer.view_state
    vs.display.wl = 0.0

    gui.intensities_ui.on_hist_drag_upper(None, 150.0, None)

    assert vs.display.ww == pytest.approx(300.0)
    assert vs.display.wl == pytest.approx(0.0)


def test_drag_level_moves_wl_keeping_ww(headless_gui_app):
    _, gui, viewer, _ = headless_gui_app
    vs = viewer.view_state
    original_ww = vs.display.ww

    gui.intensities_ui.on_hist_drag_level(None, 50.0, None)

    assert vs.display.wl == pytest.approx(50.0)
    assert vs.display.ww == pytest.approx(original_ww)


def test_drag_lower_does_not_change_wl(headless_gui_app):
    _, gui, viewer, _ = headless_gui_app
    vs = viewer.view_state
    vs.display.wl = 10.0
    original_wl = vs.display.wl

    gui.intensities_ui.on_hist_drag_lower(None, 10.0 - 50.0, None)

    assert vs.display.wl == pytest.approx(original_wl)


def test_drag_upper_does_not_change_wl(headless_gui_app):
    _, gui, viewer, _ = headless_gui_app
    vs = viewer.view_state
    vs.display.wl = 10.0
    original_wl = vs.display.wl

    gui.intensities_ui.on_hist_drag_upper(None, 10.0 + 50.0, None)

    assert vs.display.wl == pytest.approx(original_wl)


def test_drag_lower_ww_minimum_is_positive(headless_gui_app):
    """Dragging lower beyond the level must not produce a negative ww."""
    _, gui, viewer, _ = headless_gui_app
    vs = viewer.view_state
    vs.display.wl = 0.0

    # Drag lower to a position ABOVE the level (invalid direction)
    gui.intensities_ui.on_hist_drag_lower(None, 100.0, None)

    assert vs.display.ww >= 1e-5


# ─────────────────────────────────────────────────────────────────────────────
# 7. Per-image independence of histogram settings
# ─────────────────────────────────────────────────────────────────────────────

def test_bar_type_is_independent_per_viewer(headless_gui_app):
    controller, gui, viewer1, _ = headless_gui_app
    viewer2 = _viewer2(controller)

    gui.context_viewer = viewer1
    gui.intensities_ui.on_hist_bar_toggle(None, None, None)

    assert viewer1.view_state.display.hist_use_bars is True
    assert viewer2.view_state.display.hist_use_bars is False


def test_log_mode_is_independent_per_viewer(headless_gui_app):
    controller, gui, viewer1, _ = headless_gui_app
    viewer2 = _viewer2(controller)

    gui.context_viewer = viewer1
    gui.intensities_ui.on_hist_log_toggle(None, None, None)

    assert viewer1.view_state.display.hist_use_log is False
    assert viewer2.view_state.display.hist_use_log is True


def test_x_range_is_independent_per_viewer(headless_gui_app):
    controller, gui, viewer1, _ = headless_gui_app
    viewer2 = _viewer2(controller)

    viewer1.view_state.display.hist_x_center = 100.0
    viewer1.view_state.display.hist_x_range = 800.0

    assert viewer2.view_state.display.hist_x_center is None
    assert viewer2.view_state.display.hist_x_range is None


def test_switching_viewer_preserves_each_image_bar_type(headless_gui_app):
    """Toggling bar on V1, switching to V2 and back must keep each setting."""
    controller, gui, viewer1, _ = headless_gui_app
    viewer2 = _viewer2(controller)

    # Set V1 to bars, V2 stays lines
    gui.context_viewer = viewer1
    gui.intensities_ui.on_hist_bar_toggle(None, None, None)

    gui.context_viewer = viewer2
    assert viewer2.view_state.display.hist_use_bars is False

    gui.context_viewer = viewer1
    assert viewer1.view_state.display.hist_use_bars is True


# ─────────────────────────────────────────────────────────────────────────────
# 8. Colorscale texture pixel generation
# ─────────────────────────────────────────────────────────────────────────────

def _colorscale_pixels(gui, vs):
    """Helper: generate colorscale array and update texture; return pixel list."""
    _ensure_colorscale_tex()
    gui.intensities_ui._update_colorscale_texture(vs)
    return dpg.get_value("wl_colorscale_tex")


def test_colorscale_pixels_below_window_are_black(headless_gui_app):
    _, gui, viewer, _ = headless_gui_app
    vs = viewer.view_state

    vs.display.wl = 0.0
    vs.display.ww = 100.0               # window: [−50, +50]
    vs.display.hist_x_center = 0.0
    vs.display.hist_x_range = 200.0     # view:   [−100, +100]

    pixels = _colorscale_pixels(gui, vs)
    if pixels is None:
        pytest.skip("DPG get_value not supported for texture in headless mode")

    # First pixel corresponds to x ≈ −100, which is below lower (−50) → black
    r0, g0, b0 = pixels[0], pixels[1], pixels[2]
    assert r0 == pytest.approx(0.0, abs=0.02)
    assert g0 == pytest.approx(0.0, abs=0.02)
    assert b0 == pytest.approx(0.0, abs=0.02)


def test_colorscale_pixels_above_window_are_white(headless_gui_app):
    _, gui, viewer, _ = headless_gui_app
    vs = viewer.view_state

    vs.display.wl = 0.0
    vs.display.ww = 100.0               # window: [−50, +50]
    vs.display.hist_x_center = 0.0
    vs.display.hist_x_range = 200.0     # view:   [−100, +100]

    pixels = _colorscale_pixels(gui, vs)
    if pixels is None:
        pytest.skip("DPG get_value not supported for texture in headless mode")

    # Last pixel corresponds to x ≈ +100, which is above upper (+50) → white
    r, g, b = pixels[-4], pixels[-3], pixels[-2]
    assert r == pytest.approx(1.0, abs=0.02)
    assert g == pytest.approx(1.0, abs=0.02)
    assert b == pytest.approx(1.0, abs=0.02)


def test_colorscale_grayscale_gradient_inside_window(headless_gui_app):
    """Within the WL window the grayscale ramp must be monotonically increasing."""
    _, gui, viewer, _ = headless_gui_app
    vs = viewer.view_state

    vs.display.colormap = "Grayscale"
    vs.display.wl = 0.0
    vs.display.ww = 200.0               # window fills the entire view
    vs.display.hist_x_center = 0.0
    vs.display.hist_x_range = 200.0

    pixels = _colorscale_pixels(gui, vs)
    if pixels is None:
        pytest.skip("DPG get_value not supported for texture in headless mode")

    # Extract red channel (= luminance for grayscale)
    red = [pixels[i * 4] for i in range(256)]
    # Left half should be darker than right half
    assert red[32] < red[224]


def test_colorscale_pure_numpy_logic():
    """Verify the colorscale algorithm with numpy only — no DPG required."""
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
