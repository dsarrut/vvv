"""Top menu bar: File / Workspace / System menus, recent files, rendering options."""

import json
import os
import shlex

import dearpygui.dearpygui as dpg

from vvv.ui.render_strategy import GL_NEAREST_SUPPORTED, _NUMBA_AVAILABLE
from vvv.ui.ui_components import build_beginner_tooltip, build_tooltip
from vvv.ui.ui_sequences import load_batch_images_sequence, load_single_image_sequence

MISSING_RECENT_COLOR = [255, 140, 0, 255]  # orange


def build_menu_bar(gui):
    """Builds the floating top menu bar."""
    cfg_l = gui.ui_cfg["layout"]

    with dpg.child_window(
        tag="menu_container",
        height=cfg_l["menu_h"],
        border=False,
        menubar=True,
        no_scrollbar=True,
    ):
        with dpg.menu_bar(tag="main_menu_bar"):
            with dpg.menu(label="File"):
                dpg.add_menu_item(
                    label="Open Image(s)...", callback=gui.on_open_file_clicked
                )
                with dpg.menu(label="Open Recent...", tag="menu_recent_files"):
                    pass
                menu_item_dicom = dpg.add_menu_item(
                    label="Open DICOM Browser...",
                    callback=gui.open_dicom_plugin_window,
                )
                build_beginner_tooltip(
                    menu_item_dicom,
                    "Scan local directories for DICOM series and load them.",
                    gui,
                )
                dpg.add_menu_item(
                    label="Open a 4D Sequence...",
                    callback=gui.on_open_4d_sequence_clicked,
                )

                dpg.add_separator()

                # Fetch the current setting state
                auto_save = gui.controller.settings.data.get("behavior", {}).get(
                    "auto_save_history", True
                )

                dpg.add_menu_item(
                    label="Auto-Save History on Exit",
                    check=True,
                    default_value=auto_save,
                    callback=lambda s, a, u: on_toggle_auto_save(gui, s, a, u),
                )

                dpg.add_separator()

                dpg.add_menu_item(
                    label="Settings...",
                    callback=lambda: gui.settings_window.show(),
                )
                dpg.add_menu_item(label="Exit", callback=gui.cleanup)

            with dpg.menu(label="Workspace"):
                dpg.add_menu_item(
                    label="Open Workspace...",
                    callback=gui.on_open_workspace_clicked,
                )
                dpg.add_menu_item(
                    label="Save Workspace As...",
                    callback=gui.on_save_workspace_clicked,
                )
                dpg.add_menu_item(
                    label="Save Workspace",
                    tag="menu_save_workspace",
                    show=False,
                    callback=gui.on_save_workspace_current_clicked,
                )

            with dpg.menu(label="System", tag="menu_system"):
                with dpg.menu(label="Rendering Options"):
                    dpg.add_menu_item(
                        label="NN Interpolation  [K]",
                        tag="menu_item_pixelated",
                        check=True,
                        callback=lambda s, a, u: on_menu_pixelated_zoom_toggled(gui, s, a, u),
                    )
                    dpg.add_separator()
                    with dpg.menu(label="NN Options"):
                        lazy_combo = dpg.add_combo(
                            ["Auto", "On", "Off"],
                            label="Lazy-Lin",
                            tag="menu_combo_lazy_lin",
                            width=100,
                            callback=lambda s, a, u: on_adv_rendering_changed(gui, s, a, u),
                        )
                        build_beginner_tooltip(
                            lazy_combo,
                            "Auto: use bilinear during drag when fusion is active,\nrestore NN after interaction stops.\nOn/Off: force always on or always off.",
                            gui,
                        )
                        tex_combo = dpg.add_combo(
                            ["Auto", "Single", "Dual"],
                            label="Texture Mode",
                            tag="menu_combo_single_tex",
                            width=100,
                            callback=lambda s, a, u: on_adv_rendering_changed(gui, s, a, u),
                        )
                        build_beginner_tooltip(
                            tex_combo,
                            "Auto: Single texture when fusion is active, Dual otherwise.\nSingle: CPU-blend base+overlay into one canvas texture.\nDual: separate textures for base and overlay.",
                            gui,
                        )
                        vox_combo = dpg.add_combo(
                            ["Auto", "Native", "Resampled"],
                            label="Voxel Mode",
                            tag="menu_combo_native_vox",
                            width=100,
                            callback=lambda s, a, u: on_adv_rendering_changed(gui, s, a, u),
                        )
                        build_beginner_tooltip(
                            vox_combo,
                            "Auto/Native: overlay rendered at its true voxel resolution.\nResampled: overlay NN-scaled from the base image grid.",
                            gui,
                        )
                        if GL_NEAREST_SUPPORTED:
                            gl_check = dpg.add_checkbox(
                                label="Hardware NN Filter",
                                tag="menu_check_gl_nearest",
                                callback=lambda s, a, u: on_adv_rendering_changed(gui, s, a, u),
                            )
                            build_beginner_tooltip(
                                gl_check,
                                "Use GPU GL_NEAREST for fast hardware NN upscaling.\nNot available on macOS.",
                                gui,
                            )
                        if _NUMBA_AVAILABLE:
                            nb_check = dpg.add_checkbox(
                                label="Numba Acceleration",
                                tag="menu_check_numba",
                                callback=lambda s, a, u: on_adv_rendering_changed(gui, s, a, u),
                            )
                            build_beginner_tooltip(
                                nb_check,
                                "Use Numba JIT for native voxel overlay rendering.\n~40x faster than NumPy for SW NN modes on macOS.\nDisable to fall back to NumPy (useful for debugging).",
                                gui,
                            )

            dpg.add_spacer(width=20)
            dpg.add_text(
                "",
                tag="global_status_text",
                color=gui.ui_cfg["colors"]["text_status_ok"],
            )

            dpg.add_text(
                "",
                tag="active_image_path_text",
                color=gui.ui_cfg["colors"]["text_dim"],
            )
            with dpg.tooltip("active_image_path_text"):
                dpg.add_text("", tag="active_image_path_tooltip_text")
            with dpg.item_handler_registry(tag="active_image_path_click_handler"):
                dpg.add_item_clicked_handler(
                    callback=gui.on_active_image_path_clicked
                )
            dpg.bind_item_handler_registry(
                "active_image_path_text", "active_image_path_click_handler"
            )

            # Define layout & screenshot buttons inside the menu_bar so they aren't clipped, but position them absolutely
            btn_screenshot = dpg.add_button(
                label="\uf030",
                callback=gui.on_copy_window_screenshot_clicked,
                tag="btn_screenshot",
            )
            btn_layout_4 = dpg.add_button(
                label="\uf009",
                callback=lambda: gui.set_viewport_layout("4"),
                tag="btn_layout_4",
            )
            btn_layout_2 = dpg.add_button(
                label="\uf0db",
                callback=lambda: gui.set_viewport_layout("2"),
                tag="btn_layout_2",
            )
            btn_layout_1 = dpg.add_button(
                label="\uf0c8",
                callback=lambda: gui.set_viewport_layout("1"),
                tag="btn_layout_1",
            )

            for btn in [btn_screenshot, btn_layout_4, btn_layout_2, btn_layout_1]:
                if dpg.does_item_exist("icon_font_tag"):
                    dpg.bind_item_font(btn, "icon_font_tag")
                if dpg.does_item_exist("icon_button_theme"):
                    dpg.bind_item_theme(btn, "icon_button_theme")

            build_tooltip(
                "btn_screenshot",
                "Copy Window Screenshot to Clipboard",
                gui,
                always_on=True,
            )
            build_tooltip("btn_layout_4", "4 Viewers Layout", gui, always_on=True)
            build_tooltip(
                "btn_layout_2",
                "2 Viewers (Left/Right) Layout",
                gui,
                always_on=True,
            )
            build_tooltip(
                "btn_layout_1", "1 Viewer (Full) Layout", gui, always_on=True
            )

    dpg.bind_item_theme("menu_container", "floating_menu_theme")


def _split_4d(entry):
    """Frame paths of a recent "4D:<shell-quoted paths>" entry ([] if unparsable)."""
    rest = entry[3:].replace("\\", "\\\\") if os.name == "nt" else entry[3:]
    try:
        return shlex.split(rest)
    except ValueError:
        return []


def _describe_recent(path_obj):
    """(label, tooltip, exists) of a resolved recent entry.

    An entry is a file path, a DICOM series (list of files) or a 4D sequence
    ("4D:" + shell-quoted frame paths); a series exists if its first file does.
    """
    if isinstance(path_obj, list):
        if not path_obj:
            return "[]", "[]", False
        label = os.path.basename(os.path.dirname(path_obj[0])) + " (DICOM Series)"
        return label, "\n".join(path_obj), os.path.exists(path_obj[0])
    if isinstance(path_obj, str) and path_obj.startswith("4D:"):
        frames = _split_4d(path_obj)
        label = "4D: " + os.path.basename(frames[0]) + "..." if frames else "4D Sequence"
        return label, path_obj, bool(frames) and os.path.exists(frames[0])
    if isinstance(path_obj, str):
        return os.path.basename(path_obj), path_obj, os.path.exists(path_obj)
    return str(path_obj), str(path_obj), False


def _missing_recent_theme():
    """One shared theme (created once) for the recent entries missing on disk."""
    if not dpg.does_item_exist("missing_recent_theme"):
        with dpg.theme(tag="missing_recent_theme"):
            with dpg.theme_component(dpg.mvMenuItem):
                dpg.add_theme_color(dpg.mvThemeCol_Text, MISSING_RECENT_COLOR)
    return "missing_recent_theme"


def refresh_recent_menu(gui):
    """Rebuild File > Open Recent from the settings; missing entries in orange."""
    if not dpg.does_item_exist("menu_recent_files"):
        return

    dpg.delete_item("menu_recent_files", children_only=True)
    recent = gui.controller.settings.data.get("behavior", {}).get("recent_files", [])

    if not recent:
        dpg.add_menu_item(
            label="No recent files", parent="menu_recent_files", enabled=False
        )
        return

    for path_str in recent:
        # DICOM series are stored as JSON lists
        try:
            path_obj = json.loads(path_str) if path_str.startswith("[") else path_str
        except Exception:
            path_obj = path_str
        path_obj = gui.controller.resolve_recent_path(path_obj)

        label, tooltip, exists = _describe_recent(path_obj)
        item = dpg.add_menu_item(
            label=label if exists else label + " (Missing)",
            parent="menu_recent_files",
            user_data=path_obj,
            callback=lambda s, a, u: on_recent_file_clicked(gui, s, a, u),
        )
        if not exists:
            dpg.bind_item_theme(item, _missing_recent_theme())
        build_beginner_tooltip(item, tooltip, gui)

    dpg.add_separator(parent="menu_recent_files")
    dpg.add_menu_item(
        label="Clear Recent Files",
        parent="menu_recent_files",
        callback=lambda s, a, u: on_clear_recent_clicked(gui, s, a, u),
    )


def on_toggle_auto_save(gui, sender, app_data, user_data):
    gui.controller.settings.data.setdefault("behavior", {})[
        "auto_save_history"
    ] = app_data


def on_recent_file_clicked(gui, sender, app_data, user_data):
    path = user_data
    if isinstance(path, str) and path.startswith("4D:"):
        gui.tasks.append(load_single_image_sequence(gui, gui.controller, path))
    else:
        gui.tasks.append(load_batch_images_sequence(gui, gui.controller, [path]))


def on_clear_recent_clicked(gui, sender, app_data, user_data):
    gui.controller.settings.data.setdefault("behavior", {})["recent_files"] = []
    refresh_recent_menu(gui)


def on_menu_pixelated_zoom_toggled(gui, sender, app_data, user_data):
    if gui.context_viewer and gui.context_viewer.view_state:
        gui.context_viewer.view_state.display.pixelated_zoom = app_data
        gui.context_viewer.view_state.is_data_dirty = True
        gui.controller.ui_needs_refresh = True


def refresh_rendering_menu(gui):
    """Sync the System > Rendering Options items with the settings and context viewer."""
    cfg = gui.controller.settings.data.get("rendering", {})
    viewer = gui.context_viewer

    has_fusion = False
    is_hw = False
    nn_on = False
    if viewer:
        vs = viewer.view_state
        has_fusion = bool(
            vs
            and vs.display.overlay.image_id
            and vs.display.overlay.mode == "Alpha"
        )
        use_gl = cfg.get("gl_nearest", True)
        is_hw = GL_NEAREST_SUPPORTED and use_gl
        nn_on = bool(vs and vs.display.pixelated_zoom)

    # Build the effective-mode suffix shown on the top-level menu item
    if nn_on:
        if is_hw:
            _mode_tag = "HW GL_NEAREST"
        else:
            _st = cfg.get("single_texture", "Auto")
            _nv = cfg.get("native_voxel", "Auto")
            _is_single = (
                has_fusion if _st == "Auto" else (_st is True or _st == "Single")
            )
            _is_native = True if _nv == "Auto" else (_nv is True or _nv == "Native")
            _ll = cfg.get("lazy_lin", "Auto")
            _lazy_on = (
                (has_fusion and not is_hw)
                if _ll == "Auto"
                else (_ll is True or _ll == "On")
            )
            _tex = "Single" if _is_single else "Dual"
            _vox = "Native" if _is_native else "Resampled"
            _lazy = " + Lazy" if _lazy_on else ""
            _mode_tag = f"{_tex}-{_vox}{_lazy}"
        nn_label = f"NN: {_mode_tag}  [K]"
    else:
        nn_label = "NN Interpolation  [K]"

    gui._safe_configure("menu_item_pixelated", label=nn_label)

    ll_auto_str = f"Auto ({'On' if (has_fusion and not is_hw) else 'Off'})"
    st_auto_str = f"Auto ({'Single' if has_fusion else 'Dual'})"
    nv_auto_str = "Auto (Native)"

    gui._safe_configure(
        "menu_combo_lazy_lin", items=[ll_auto_str, "On", "Off"], enabled=not is_hw
    )
    v = cfg.get("lazy_lin", "Auto")
    gui._safe_set(
        "menu_combo_lazy_lin",
        ll_auto_str if v == "Auto" else ("On" if v else "Off"),
    )

    gui._safe_configure(
        "menu_combo_single_tex", items=[st_auto_str, "Single", "Dual"]
    )
    v = cfg.get("single_texture", "Auto")
    gui._safe_set(
        "menu_combo_single_tex",
        st_auto_str if v == "Auto" else ("Single" if v else "Dual"),
    )

    gui._safe_configure(
        "menu_combo_native_vox", items=[nv_auto_str, "Native", "Resampled"]
    )
    v = cfg.get("native_voxel", "Auto")
    gui._safe_set(
        "menu_combo_native_vox",
        nv_auto_str if v == "Auto" else ("Native" if v else "Resampled"),
    )

    gui._safe_set("menu_check_gl_nearest", cfg.get("gl_nearest", True))
    gui._safe_set("menu_check_numba", cfg.get("numba", True))


def on_adv_rendering_changed(gui, sender, app_data, user_data):
    cfg = gui.controller.settings.data.setdefault("rendering", {})
    if sender == "menu_combo_lazy_lin":
        cfg["lazy_lin"] = (
            "Auto" if app_data.startswith("Auto") else (app_data == "On")
        )
    elif sender == "menu_combo_single_tex":
        cfg["single_texture"] = (
            "Auto" if app_data.startswith("Auto") else (app_data == "Single")
        )
    elif sender == "menu_combo_native_vox":
        cfg["native_voxel"] = (
            "Auto" if app_data.startswith("Auto") else (app_data == "Native")
        )
    elif sender == "menu_check_gl_nearest":
        cfg["gl_nearest"] = app_data
    elif sender == "menu_check_numba":
        cfg["numba"] = app_data
    gui.controller.save_settings()
    gui.controller._flag_all_viewers_dirty()
    refresh_rendering_menu(gui)
