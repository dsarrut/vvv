import pytest
from vvv.ui.ui_components import normalize_rgba_to_int


def test_normalize_rgba_to_int_floats():
    assert normalize_rgba_to_int([1.0, 0.5, 0.0, 1.0]) == [255, 127, 0, 255]
    assert normalize_rgba_to_int([0.0, 0.0, 0.0, 1.0]) == [0, 0, 0, 255]


def test_normalize_rgba_to_int_integers():
    assert normalize_rgba_to_int([255, 128, 0, 255]) == [255, 128, 0, 255]
    assert normalize_rgba_to_int([0, 1, 0, 1]) == [0, 1, 0, 1]


def test_normalize_rgba_to_int_rgb_3_channels():
    assert normalize_rgba_to_int([255, 100, 50]) == [255, 100, 50, 255]
    assert normalize_rgba_to_int([1.0, 0.0, 0.0]) == [255, 0, 0, 255]


def test_normalize_rgba_to_int_empty_fallback():
    assert normalize_rgba_to_int([]) == [0, 0, 0, 255]


def test_build_horizontal_separator_and_section_title():
    import dearpygui.dearpygui as dpg
    from vvv.ui.ui_components import build_horizontal_separator, build_section_title

    created_ctx = False
    try:
        dpg.get_active_window()
    except Exception:
        dpg.create_context()
        created_ctx = True

    try:
        with dpg.window(label="TestWindow") as win:
            sep = build_horizontal_separator(width=-8, space_below=4)
            assert dpg.does_item_exist(sep)
            assert dpg.get_item_type(sep) == "mvAppItemType::mvTable"
            assert dpg.get_item_configuration(sep)["width"] == -8
            assert dpg.does_item_exist("clean_separator_theme")

            # Check that a spacer was added after the table
            children = dpg.get_item_children(win, 1)
            assert len(children) >= 2
            assert dpg.get_item_type(children[-1]) == "mvAppItemType::mvSpacer"
            assert dpg.get_item_configuration(children[-1])["height"] == 4

            title_sep = build_section_title("Section Title", [255, 255, 255])
            assert dpg.does_item_exist(title_sep)
            assert dpg.get_item_type(title_sep) == "mvAppItemType::mvTable"
            assert dpg.get_item_configuration(title_sep)["width"] == -8
    finally:
        if created_ctx:
            dpg.destroy_context()

