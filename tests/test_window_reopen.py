"""A window closed with its close button is only hidden by DearPyGui; its
on_close callback deletes it. If that callback did not run, opening it again
must still show it (it did nothing for the DICOM browser, colleague on Intel
macOS)."""

import dearpygui.dearpygui as dpg


def test_help_window_reopens_after_a_close_without_callback(headless_gui_app):
    controller, gui, viewer, vs_id = headless_gui_app
    gui.show_help_window()
    assert dpg.is_item_shown("help_window")

    dpg.configure_item("help_window", show=False)  # closed, on_close not run
    gui.show_help_window()
    assert dpg.does_item_exist("help_window") and dpg.is_item_shown("help_window")

    gui.show_help_window()  # toggle: a shown window is closed
    assert not dpg.does_item_exist("help_window")
