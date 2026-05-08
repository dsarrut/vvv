import os
import sys
import subprocess
import pytest
from vvv.ui.render_strategy import NNMode


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
        viewer.nn_mode = mode
        viewer.is_geometry_dirty = True

        try:
            viewer.update_render(force_reblend=True)
        except Exception as e:
            pytest.fail(f"Rendering failed on mode {mode.name}: {e}")

        assert viewer.last_rgba_flat is not None