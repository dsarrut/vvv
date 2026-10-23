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



def test_name_matches_rule():
    from vvv.ui.ui_components import name_matches

    assert name_matches("Lung_L", "lung")
    assert name_matches("Lung_L", "  LUNG ")  # stripped, case-insensitive
    assert not name_matches("Liver", "lung")
    assert name_matches("Liver", "lung", invert=True)
    assert not name_matches("Lung_L", "lung", invert=True)
    # an empty filter keeps everything, inverted or not
    assert name_matches("Liver", "") and name_matches("Liver", "  ", invert=True)
    assert name_matches(None, "") and not name_matches(None, "x")


def test_tooltip_delays_and_components():
    import dearpygui.dearpygui as dpg
    from types import SimpleNamespace
    from vvv.ui.ui_components import (
        get_tooltip_delay,
        build_tooltip,
        build_beginner_tooltip,
        build_icon_button,
    )

    # 1. Test get_tooltip_delay logic
    mock_gui = SimpleNamespace(
        is_beginner_mode=False,
        controller=SimpleNamespace(
            settings=SimpleNamespace(
                data={
                    "interaction": {
                        "tooltip_delay": 0.8,
                        "tooltip_delay_beginner": 0.2,
                    }
                }
            )
        ),
        icon_tooltip_tags=[],
        beginner_tags=[],
    )

    # In normal mode: always_on=True should return 0.8, always_on=False should return 0.2
    assert get_tooltip_delay(mock_gui, always_on=True) == 0.8
    assert get_tooltip_delay(mock_gui, always_on=False) == 0.2

    # In beginner mode: both return 0.2
    mock_gui.is_beginner_mode = True
    assert get_tooltip_delay(mock_gui, always_on=True) == 0.2
    assert get_tooltip_delay(mock_gui, always_on=False) == 0.2

    # 2. Test DPG tooltip creation and registration
    created_ctx = False
    try:
        dpg.get_active_window()
    except Exception:
        dpg.create_context()
        created_ctx = True

    try:
        mock_gui.is_beginner_mode = False
        with dpg.window(label="TestTT") as win:
            btn1 = dpg.add_button(label="IconBtn")
            tt1 = build_tooltip(btn1, "Save file", mock_gui, always_on=True)
            assert tt1 in mock_gui.icon_tooltip_tags
            cfg1 = dpg.get_item_configuration(tt1)
            assert cfg1["show"] is True
            assert cfg1["delay"] == pytest.approx(0.8)

            btn2 = dpg.add_button(label="TextBtn")
            tt2 = build_beginner_tooltip(btn2, "Educational text", mock_gui)
            assert tt2 in mock_gui.beginner_tags
            cfg2 = dpg.get_item_configuration(tt2)
            assert cfg2["show"] is False
            assert cfg2["delay"] == pytest.approx(0.2)

            # Test build_icon_button
            btn3 = build_icon_button(
                icon="X",
                callback=lambda: None,
                tooltip="Delete Item",
                gui=mock_gui,
                width=20,
            )
            assert dpg.does_item_exist(btn3)
            assert dpg.get_item_configuration(btn3)["width"] == 20

            # Test hidden button tooltip visibility synchronization
            from vvv.ui.ui_components import set_item_show

            btn4 = dpg.add_button(label="HiddenBtn", show=False)
            tt4 = build_tooltip(btn4, "Hidden Action", mock_gui, always_on=True)
            # Tooltip on hidden button should start hidden
            assert dpg.get_item_configuration(tt4)["show"] is False

            set_item_show(btn4, True, mock_gui)
            assert dpg.get_item_configuration(btn4)["show"] is True
            assert dpg.get_item_configuration(tt4)["show"] is True

            set_item_show(btn4, False, mock_gui)
            assert dpg.get_item_configuration(btn4)["show"] is False
            assert dpg.get_item_configuration(tt4)["show"] is False

            # Test build_name_filter_bar with sort button
            from vvv.ui.ui_components import build_name_filter_bar

            build_name_filter_bar(
                group_tag="test_filter_group",
                input_tag="test_filter_input",
                btn_clear_tag="test_filter_clear",
                on_filter_changed=lambda a: None,
                on_clear_clicked=lambda: None,
                btn_invert_tag="test_filter_invert",
                on_invert_clicked=lambda: None,
                btn_sort_tag="test_filter_sort",
                on_sort_clicked=lambda: None,
                count_tag="test_filter_count",
            )
            assert dpg.does_item_exist("test_filter_group")
            assert dpg.does_item_exist("test_filter_input")
            assert dpg.does_item_exist("test_filter_sort")
            assert dpg.does_item_exist("test_filter_invert")
            assert dpg.does_item_exist("test_filter_clear")
            assert dpg.does_item_exist("test_filter_count")
    finally:
        if created_ctx:
            dpg.destroy_context()



def test_sort_helpers():
    from types import SimpleNamespace as N
    from vvv.ui.ui_components import next_sort_order, sort_by_name

    assert [next_sort_order(o) for o in (0, 1, -1)] == [1, -1, 0]
    items = [N(name="b"), N(name="A"), N(name="c")]
    assert [x.name for x in sort_by_name(items, 0)] == ["b", "A", "c"]
    assert [x.name for x in sort_by_name(items, 1)] == ["A", "b", "c"]
    assert [x.name for x in sort_by_name(items, -1)] == ["c", "b", "A"]
    pairs = [("k1", N(name="z")), ("k2", N(name="y"))]
    assert [k for k, _ in sort_by_name(pairs, 1, name=lambda p: p[1].name)] == ["k2", "k1"]


def test_batch_action_toolbar_uses_icon_buttons():
    import dearpygui.dearpygui as dpg
    from vvv.ui.ui_components import build_batch_action_toolbar

    created_ctx = False
    try:
        dpg.get_active_window()
    except Exception:
        dpg.create_context()
        created_ctx = True
    try:
        for t in ("icon_button_theme", "delete_button_theme"):
            if not dpg.does_item_exist(t):
                with dpg.theme(tag=t):
                    pass
        calls = []
        with dpg.window():
            build_batch_action_toolbar(
                "t",
                on_reset_colors=lambda: calls.append("reset"),
                on_toggle_visible=lambda: calls.append("vis"),
                on_delete_clicked=lambda: calls.append("del"),
            )
        kids = dpg.get_item_children("t_batch_toolbar", 1)
        assert [dpg.get_item_alias(k) for k in kids[:2]] == ["t_batch_reset_colors", "t_batch_toggle_visible"]
        assert dpg.get_item_theme("t_batch_reset_colors") == "icon_button_theme"
        assert dpg.get_item_theme(kids[-1]) == "delete_button_theme"  # delete last
        dpg.get_item_callback("t_batch_toggle_visible")("s", None, None)
        assert calls == ["vis"]
    finally:
        if created_ctx:
            dpg.destroy_context()


def test_dialog_footer_order_widths_and_keys():
    import dearpygui.dearpygui as dpg
    from vvv.ui.ui_components import build_dialog_footer, DIALOG_BTN_W

    created_ctx = False
    try:
        dpg.get_active_window()
    except Exception:
        dpg.create_context()
        created_ctx = True
    try:
        calls = []
        with dpg.window(tag="dlg_test"):
            build_dialog_footer(
                [("Cancel", lambda: calls.append("cancel")), ("Save", lambda: calls.append("save"))],
                keys_for="dlg_test",
            )
        table = dpg.get_item_children("dlg_test", 1)[-1]
        row = dpg.get_item_children(table, 1)[0]
        cells = dpg.get_item_children(row, 1)
        buttons = [c for c in cells if dpg.get_item_type(c).endswith("mvButton")]
        assert [dpg.get_item_label(b) for b in buttons] == ["Cancel", "Save"]  # main action last
        assert {dpg.get_item_width(b) for b in buttons} == {DIALOG_BTN_W}
        dpg.get_item_callback(buttons[-1])("s", None, None)
        assert calls == ["save"]
        assert dpg.does_item_exist("dlg_test_footer_keys")
    finally:
        if dpg.does_item_exist("dlg_test_footer_keys"):
            dpg.delete_item("dlg_test_footer_keys")
        if dpg.does_item_exist("dlg_test"):
            dpg.delete_item("dlg_test")
        if created_ctx:
            dpg.destroy_context()
