"""The status bar tells the user while the fast colormap kernel compiles."""

import dearpygui.dearpygui as dpg

import vvv.ui.gui as gui_mod


def test_notice_while_compiling_then_ready(headless_gui_app, monkeypatch):
    _, gui, _, _ = headless_gui_app
    state = {"t": None}
    monkeypatch.setattr(gui_mod, "fast_colorize_compiling_for", lambda: state["t"])
    shown = []
    monkeypatch.setattr(gui, "show_status_message", lambda m, **k: shown.append(m))

    state["t"] = 0.1  # short compile (cached run): no message
    gui._update_fast_render_notice()
    assert shown == []

    state["t"] = 0.5
    gui._update_fast_render_notice()
    gui._update_fast_render_notice()  # shown once
    assert len(shown) == 1 and "Preparing fast rendering" in shown[0]

    state["t"] = None  # done
    gui._update_fast_render_notice()
    assert shown[-1] == "Fast rendering ready"
