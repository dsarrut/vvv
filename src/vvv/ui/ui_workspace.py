import dearpygui.dearpygui as dpg

# FontAwesome 4 codepoints — same encoding the rest of the nav uses
_ICON_OPEN    = ""   # fa-folder-open
_ICON_SAVE    = ""   # fa-save (floppy disk)
_ICON_SAVE_AS = ""   # fa-files-o (two stacked documents)


def build_workspace_nav_icons(gui):
    """Workspace action icons inside nav_top_group, after the last tool button.

    Placed inside nav_top_group so they flow naturally below DVF without
    needing absolute positioning. Visual structure:

        [spacer]
        ─────────  (separator)
        [spacer]
        [  📁  ]   Open Workspace
        [  💾  ]   Save Workspace    (disabled until a path is set)
        [  📋  ]   Save Workspace As
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
                "ws_nav_btn_save_as",
                _ICON_SAVE_AS,
                "Save Workspace As",
                gui.on_save_workspace_clicked,
                None,
            ),
            (
                "ws_nav_btn_save",
                _ICON_SAVE,
                "Save Workspace",
                gui.on_save_workspace_current_clicked,
                "ws_save_tooltip_text",
            ),
        ]:
            btn = dpg.add_button(
                label=icon,
                tag=tag,
                width=-1,
                height=btn_h,
                enabled=(tag != "ws_nav_btn_save"),
                callback=cb,
            )
            dpg.bind_item_theme(btn, "theme_ws_nav_btn")
            if dpg.does_item_exist("icon_font_tag"):
                dpg.bind_item_font(btn, "icon_font_tag")

            tt_id = dpg.generate_uuid()
            with dpg.tooltip(btn, tag=tt_id, show=getattr(gui, "is_beginner_mode", False)):
                if not hasattr(gui, "beginner_tags"):
                    gui.beginner_tags = []
                gui.beginner_tags.append(tt_id)

                if tooltip_tag:
                    dpg.add_text(label, tag=tooltip_tag)
                else:
                    dpg.add_text(label)
                    
                dpg.add_text("A Workspace saves your exact session (loaded images, overlays, window/level, and ROIs) so you can resume your work later.", color=cfg_c["text_dim"])

            if tag == "ws_nav_btn_save":
                txt = dpg.add_text("", tag="ws_nav_filename_text", color=cfg_c["text_dim"])
                if dpg.does_item_exist("small_font_tag"):
                    dpg.bind_item_font(txt, "small_font_tag")
                with dpg.tooltip(txt):
                    dpg.add_text("", tag="ws_nav_path_tooltip")
