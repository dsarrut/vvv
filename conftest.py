import pytest
import dearpygui.dearpygui as dpg


@pytest.fixture(scope="session", autouse=True)
def boot_dpg_engine():
    """Boots the DPG C++ engine exactly once for the entire pytest session."""
    dpg.create_context()
    dpg.create_viewport(title="Test Viewport", width=1000, height=800)
    dpg.setup_dearpygui()
    yield


@pytest.fixture(autouse=True)
def fresh_dpg_context():
    """Soft-resets the UI state between every single test."""
    yield

    for window in dpg.get_windows():
        if dpg.does_item_exist(window):
            info = dpg.get_item_info(window)
            if info and info.get("type") == "mvWindowAppItem":
                try:
                    dpg.delete_item(window)
                except Exception:
                    pass

    for alias in list(dpg.get_aliases()):
        alias_str = str(alias)
        if dpg.does_item_exist(alias_str):
            if alias_str.startswith("tex_") or alias_str == "global_texture_registry":
                continue
            try:
                dpg.delete_item(alias_str)
            except Exception:
                pass
