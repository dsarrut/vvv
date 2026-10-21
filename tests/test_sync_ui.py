import dearpygui.dearpygui as dpg
import pytest
from vvv.ui.ui_sync import (
    _toggle_sync_all,
    _toggle_sync_all_wl,
    refresh_sync_ui,
    handle_sync_group_change,
    handle_wl_group_change,
)


def test_sync_ui_layout_and_beginner_mode(headless_gui_app):
    """Verifies that the two link buttons share a single-row table and adjust width on beginner mode."""
    controller, gui, viewer, vs_id = headless_gui_app

    assert dpg.does_item_exist("sync_buttons_table")
    assert dpg.does_item_exist("sync_toggle_spatial_btn")
    assert dpg.does_item_exist("sync_toggle_wl_btn")

    # Table contains 2 columns in slot 0
    cols = [
        item
        for item in dpg.get_item_children("sync_buttons_table", 0)
        if dpg.get_item_type(item) == "mvAppItemType::mvTableColumn"
    ]
    assert len(cols) == 2

    # Width when beginner mode is OFF vs ON
    gui.is_beginner_mode = False
    refresh_sync_ui(gui)
    assert dpg.get_item_configuration("sync_buttons_table")["width"] == -1

    gui.is_beginner_mode = True
    refresh_sync_ui(gui)
    assert dpg.get_item_configuration("sync_buttons_table")["width"] == -28


def test_sync_ui_spatial_state_transitions(headless_gui_app, synthetic_volume_factory):
    """Verifies label, theme, and tooltip changes across unlinked, fully linked, and partially linked states."""
    controller, gui, viewer1, vs1_id = headless_gui_app

    # Load second image
    path2 = synthetic_volume_factory("img2.nii.gz", val=200.0)
    vs2_id = controller.file.load_image(path2)
    num_total = len(controller.view_states)

    # 1. Initially unlinked
    controller.sync.unlink_all()
    refresh_sync_ui(gui)

    assert dpg.get_item_label("sync_toggle_spatial_btn") == "Link Views"
    tt_text = dpg.get_value("tooltip_text_sync_spatial")
    assert "Unlinked" in tt_text

    # 2. Toggle to link all
    _toggle_sync_all(gui)
    refresh_sync_ui(gui)

    assert all(vs.sync_group == 1 for vs in controller.view_states.values())
    assert dpg.get_item_label("sync_toggle_spatial_btn") == "Unlink Views"
    assert f"All {num_total} images linked" in dpg.get_value("tooltip_text_sync_spatial")

    # 3. Partially linked (unlink vs2 only)
    sp_items = ["None", "Grp 1", "Grp 2"]
    handle_sync_group_change(gui, None, "None", (vs2_id, sp_items))
    refresh_sync_ui(gui)

    assert controller.view_states[vs1_id].sync_group == 1
    assert controller.view_states[vs2_id].sync_group == 0
    assert dpg.get_item_label("sync_toggle_spatial_btn") == "Link Views"
    assert f"Partially linked ({num_total - 1}/{num_total} images)" in dpg.get_value(
        "tooltip_text_sync_spatial"
    )

    # 4. Clicking Link Views while partially linked brings all to group 1
    _toggle_sync_all(gui)
    refresh_sync_ui(gui)

    assert all(vs.sync_group == 1 for vs in controller.view_states.values())
    assert dpg.get_item_label("sync_toggle_spatial_btn") == "Unlink Views"

    # 5. Clicking Unlink Views while fully linked unlinks all
    _toggle_sync_all(gui)
    refresh_sync_ui(gui)

    assert all(vs.sync_group == 0 for vs in controller.view_states.values())
    assert dpg.get_item_label("sync_toggle_spatial_btn") == "Link Views"


def test_sync_ui_wl_state_transitions(headless_gui_app, synthetic_volume_factory):
    """Verifies W/L label, theme, and tooltip changes across unlinked, fully linked, and partially linked states."""
    controller, gui, viewer1, vs1_id = headless_gui_app

    # Load second image
    path2 = synthetic_volume_factory("img2_wl.nii.gz", val=200.0)
    vs2_id = controller.file.load_image(path2)
    num_total = len(controller.view_states)

    # 1. Initially unlinked
    controller.sync.unlink_all_wl()
    refresh_sync_ui(gui)

    assert dpg.get_item_label("sync_toggle_wl_btn") == "Link W/L"
    assert "Unlinked" in dpg.get_value("tooltip_text_sync_wl")

    # 2. Toggle to link all W/L
    _toggle_sync_all_wl(gui)
    refresh_sync_ui(gui)

    assert all(vs.sync_wl_group == 1 for vs in controller.view_states.values())
    assert dpg.get_item_label("sync_toggle_wl_btn") == "Unlink W/L"
    assert f"All {num_total} images linked (Group A)" in dpg.get_value("tooltip_text_sync_wl")

    # 3. Partially linked (set vs2 W/L to None)
    wl_items = ["None", "Grp A", "Grp B"]
    handle_wl_group_change(gui, None, "None", (vs2_id, wl_items))
    refresh_sync_ui(gui)

    assert controller.view_states[vs1_id].sync_wl_group == 1
    assert controller.view_states[vs2_id].sync_wl_group == 0
    assert dpg.get_item_label("sync_toggle_wl_btn") == "Link W/L"
    assert f"Partially linked ({num_total - 1}/{num_total} images)" in dpg.get_value(
        "tooltip_text_sync_wl"
    )

    # 4. Clicking Link W/L while partially linked links all
    _toggle_sync_all_wl(gui)
    refresh_sync_ui(gui)

    assert all(vs.sync_wl_group == 1 for vs in controller.view_states.values())
    assert dpg.get_item_label("sync_toggle_wl_btn") == "Unlink W/L"

    # 5. Clicking Unlink W/L while fully linked unlinks all
    _toggle_sync_all_wl(gui)
    refresh_sync_ui(gui)

    assert all(vs.sync_wl_group == 0 for vs in controller.view_states.values())
    assert dpg.get_item_label("sync_toggle_wl_btn") == "Link W/L"
