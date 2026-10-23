from vvv.ui.ui_screen import start_window_geometry

DEFAULT = (1400, 1000)


def test_default_size_grows_with_the_screen_and_is_centered():
    assert start_window_geometry(1400, 1000, DEFAULT, (2560, 1440)) == (2176, 1224, 192, 108)


def test_default_size_clamped_to_a_small_screen():
    w, h, x, y = start_window_geometry(1400, 1000, DEFAULT, (1366, 768))
    assert (w, h) == (1326, 688) and x >= 0 and y >= 25


def test_user_size_kept_but_clamped():
    assert start_window_geometry(1200, 700, DEFAULT, (2560, 1440))[:2] == (1200, 700)
    assert start_window_geometry(1200, 700, DEFAULT, (1366, 768))[:2] == (1200, 688)


def test_unknown_screen_keeps_the_settings():
    assert start_window_geometry(1400, 1000, DEFAULT, None) == (1400, 1000, None, None)


def test_auto_fold_follows_the_window_height(headless_gui_app):
    controller, gui, _, _ = headless_gui_app
    layout = controller.settings.data.setdefault("layout", {})
    layout["folded_panels"] = []  # a choice was saved once: not folded at start
    gui._window_short = None
    gui.auto_fold_panels(700, relayout=False)
    assert "ch" not in gui.folded_panels
    gui.auto_fold_panels(1000, relayout=False)  # taller, then shorter: folds
    gui.auto_fold_panels(700, relayout=False)
    assert "ch" in gui.folded_panels
    gui.auto_fold_panels(1000, relayout=False)  # taller again: unfolds
    assert "ch" not in gui.folded_panels

    gui.auto_fold_panels(700, relayout=False)
    gui._ch_auto_folded = False  # unfolded by hand while short (as the toggle,
    gui.set_panel_folded("ch", False, save=False)  # without writing the settings)...
    gui.auto_fold_panels(1000, relayout=False)
    gui.auto_fold_panels(750, relayout=False)  # ...then shorter again: folds
    assert "ch" in gui.folded_panels


def test_auto_fold_at_start_without_a_saved_choice(headless_gui_app):
    controller, gui, _, _ = headless_gui_app
    controller.settings.data.setdefault("layout", {}).pop("folded_panels", None)
    gui.folded_panels.discard("ch")
    gui._window_short = None
    gui.auto_fold_panels(700, relayout=False)
    assert "ch" in gui.folded_panels
