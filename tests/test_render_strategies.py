import os
import sys
import subprocess
import pytest
from vvv.ui.render_strategy import NNMode, GL_NEAREST_SUPPORTED, select_nn_mode, should_use_lazy_lin


def test_bench_fusion_modes_smoke():
    """Runs the fusion benchmark in very-quick mode to ensure it doesn't crash."""
    script_path = os.path.join(os.path.dirname(__file__), "bench_fusion_modes.py")
    result = subprocess.run(
        [sys.executable, script_path, "--very-quick"], capture_output=True, text=True
    )
    assert result.returncode == 0, f"Benchmark script failed:\n{result.stderr}\n{result.stdout}"


def test_all_nn_modes_execute_without_crashing(headless_gui_app):
    """Iterates through all rendering strategies to ensure the math doesn't throw exceptions."""
    controller, gui, viewer, base_id = headless_gui_app

    # 1. Mount an overlay to properly test Dual and Single-Tex fusion modes
    # The headless_gui_app fixture already loads two synthetic volumes
    vs2_id = list(controller.view_states.keys())[1]
    viewer.view_state.set_overlay(vs2_id, controller.volumes[vs2_id], controller)
    viewer.view_state.display.overlay_mode = "Alpha"

    # 2. Turn on pixelated zoom so the NN paths actually trigger
    viewer.view_state.display.pixelated_zoom = True
    viewer.resize(800, 600)  # Force a realistic canvas size

    # 3. Test every mode
    for mode in NNMode:
        controller.settings.data["rendering"] = {
            "gl_nearest": mode == NNMode.HW_GL_NEAREST,
            "single_texture": mode in (NNMode.SW_SINGLE_MERGED, NNMode.SW_SINGLE_NATIVE),
            "native_voxel": mode in (NNMode.SW_DUAL_NATIVE, NNMode.SW_SINGLE_NATIVE),
            "lazy_lin": False
        }
        viewer.is_geometry_dirty = True

        try:
            viewer.update_render(force_reblend=True)
        except Exception as e:
            pytest.fail(f"Rendering failed on mode {mode.name}: {e}")

        assert viewer.last_rgba_flat is not None


# --- Pure function tests (no GUI fixture needed) ---

class TestSelectNnMode:
    def test_no_fusion_macos_gives_dual_native(self):
        if GL_NEAREST_SUPPORTED:
            pytest.skip("GL_NEAREST_SUPPORTED platform — HW path takes over")
        cfg = {"gl_nearest": False, "single_texture": "Auto", "native_voxel": "Auto"}
        assert select_nn_mode(cfg, has_fusion=False) == NNMode.SW_DUAL_NATIVE

    def test_fusion_macos_gives_single_native(self):
        if GL_NEAREST_SUPPORTED:
            pytest.skip("GL_NEAREST_SUPPORTED platform — HW path takes over")
        cfg = {"gl_nearest": False, "single_texture": "Auto", "native_voxel": "Auto"}
        assert select_nn_mode(cfg, has_fusion=True) == NNMode.SW_SINGLE_NATIVE

    def test_gl_nearest_wins_when_supported(self):
        cfg = {"gl_nearest": True}
        mode = select_nn_mode(cfg, has_fusion=True)
        if GL_NEAREST_SUPPORTED:
            assert mode == NNMode.HW_GL_NEAREST
        else:
            assert mode != NNMode.HW_GL_NEAREST

    def test_explicit_single_merged(self):
        cfg = {"gl_nearest": False, "single_texture": "Single", "native_voxel": "Resampled"}
        assert select_nn_mode(cfg, has_fusion=True) == NNMode.SW_SINGLE_MERGED

    def test_explicit_dual_resampled(self):
        cfg = {"gl_nearest": False, "single_texture": "Dual", "native_voxel": "Resampled"}
        assert select_nn_mode(cfg, has_fusion=False) == NNMode.SW_DUAL_RESAMPLED


class TestShouldUseLazyLin:
    def test_auto_no_fusion_is_false(self):
        assert should_use_lazy_lin({"lazy_lin": "Auto"}, has_fusion=False, is_hw=False) is False

    def test_auto_fusion_no_hw_is_true(self):
        assert should_use_lazy_lin({"lazy_lin": "Auto"}, has_fusion=True, is_hw=False) is True

    def test_auto_fusion_numba_disables_lazy(self):
        assert should_use_lazy_lin({"lazy_lin": "Auto"}, has_fusion=True, is_hw=False, use_numba=True) is False

    def test_explicit_on_overrides_numba(self):
        assert should_use_lazy_lin({"lazy_lin": "On"}, has_fusion=True, is_hw=False, use_numba=True) is True

    def test_auto_fusion_hw_is_false(self):
        assert should_use_lazy_lin({"lazy_lin": "Auto"}, has_fusion=True, is_hw=True) is False

    def test_explicit_on_no_hw(self):
        assert should_use_lazy_lin({"lazy_lin": "On"}, has_fusion=False, is_hw=False) is True

    def test_explicit_on_with_hw_is_false(self):
        assert should_use_lazy_lin({"lazy_lin": "On"}, has_fusion=False, is_hw=True) is False

    def test_explicit_off(self):
        assert should_use_lazy_lin({"lazy_lin": False}, has_fusion=True, is_hw=False) is False