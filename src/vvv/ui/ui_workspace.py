import dearpygui.dearpygui as dpg

from vvv.ui.ui_components import get_tooltip_delay

# FontAwesome 4 codepoints — same encoding the rest of the nav uses
_ICON_OPEN = "\uf07c"  # fa-folder-open
_ICON_SAVE = "\uf0c7"  # fa-save (floppy disk)
_ICON_SAVE_AS = "\ue001"  # custom: floppy disk with down arrow badge
_ICON_RELOAD = "\uf01e"  # fa-repeat: reload from disk, as in the other panels


def build_workspace_nav_icons(gui):
    """Workspace action icons inside nav_top_group, after the last tool button.

    Placed inside nav_top_group so they flow naturally below DVF without
    needing absolute positioning. Visual structure:

        [spacer]
        ─────────  (separator)
        [spacer]
        [  📁  ]   Open Workspace
        [  💾  ]   Save Workspace (shown only when a path is set)
        [  📥  ]   Save Workspace As
        [  ⟳  ]   Reload Workspace (shown only when a path is set)
    """
    cfg_l = gui.ui_cfg["layout"]
    btn_h = cfg_l["nav_btn_h"]

    cfg_c = gui.ui_cfg["colors"]

    with dpg.group(tag="nav_ws_group"):
        dpg.add_spacer(height=16)
        dpg.add_separator()
        dpg.add_spacer(height=4)
        dpg.add_text("Workspace", color=cfg_c["text_header"])
        dpg.add_spacer(height=2)

        for tag, icon, label, cb, tooltip_tag in [
            (
                "ws_nav_btn_open",
                _ICON_OPEN,
                "Open Workspace",
                gui.on_open_workspace_clicked,
                None,
            ),
            (
                "ws_nav_btn_save",
                _ICON_SAVE,
                "Save Workspace",
                gui.on_save_workspace_current_clicked,
                "ws_save_tooltip_text",
            ),
            (
                "ws_nav_btn_save_as",
                _ICON_SAVE_AS,
                "Save Workspace As",
                gui.on_save_workspace_clicked,
                None,
            ),
            (
                "ws_nav_btn_reload",
                _ICON_RELOAD,
                "Reload Workspace",
                gui.on_reload_workspace_clicked,
                "ws_reload_tooltip_text",
            ),
        ]:
            btn = dpg.add_button(
                label=icon,
                tag=tag,
                width=-1,
                height=btn_h,
                show=(tag not in ("ws_nav_btn_save", "ws_nav_btn_reload")),
                callback=cb,
            )
            dpg.bind_item_theme(btn, "theme_ws_nav_btn")
            if dpg.does_item_exist("icon_font_tag"):
                dpg.bind_item_font(btn, "icon_font_tag")

            delay = get_tooltip_delay(gui, always_on=True)
            tt_id = dpg.generate_uuid()
            with dpg.tooltip(
                btn, tag=tt_id, show=True, delay=delay
            ):
                if not hasattr(gui, "icon_tooltip_tags"):
                    gui.icon_tooltip_tags = []
                gui.icon_tooltip_tags.append(tt_id)

                if tooltip_tag:
                    dpg.add_text(label, tag=tooltip_tag)
                else:
                    dpg.add_text(label)

                desc_id = dpg.generate_uuid()
                dpg.add_text(
                    "A Workspace saves your exact session (loaded images, overlays, window/level, and ROIs) so you can resume your work later.",
                    tag=desc_id,
                    color=cfg_c["text_dim"],
                    show=getattr(gui, "is_beginner_mode", False),
                )
                if not hasattr(gui, "beginner_tags"):
                    gui.beginner_tags = []
                gui.beginner_tags.append(desc_id)
