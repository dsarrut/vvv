import dearpygui.dearpygui as dpg


def build_tab_images(gui):
    """Builds the static layout for the Images tab."""
    cfg_c = gui.ui_cfg["colors"]
    with dpg.tab(label="Images", tag="tab_images"):
        dpg.add_spacer(height=5)
        with dpg.group(horizontal=True):
            dpg.add_text("Loaded Images", color=cfg_c["text_header"])
        dpg.add_separator()
        with dpg.child_window(border=False, height=-1):
            dpg.add_group(tag="image_list_container")


def highlight_active_image_in_list(gui, active_img_id):
    """Highlights the currently active image in both the Images and Sync tabs."""
    for img_id, label_tag in gui.image_label_tags.items():
        if dpg.does_item_exist(label_tag):
            if img_id == active_img_id:
                dpg.bind_item_theme(label_tag, "active_image_list_theme")
            else:
                dpg.bind_item_theme(label_tag, "")

    for img_id, label_tag in gui.sync_label_tags.items():
        if dpg.does_item_exist(label_tag):
            if img_id == active_img_id:
                dpg.bind_item_theme(label_tag, "active_image_list_theme")
            else:
                dpg.bind_item_theme(label_tag, "")


def refresh_image_list_ui(gui):
    """Dynamically rebuilds the pure Image list UI."""
    container = "image_list_container"
    if not dpg.does_item_exist(container):
        return

    dpg.delete_item(container, children_only=True)
    gui.image_label_tags.clear()

    muted_col = gui.ui_cfg["colors"]["text_muted"]
    if not dpg.does_item_exist("muted_checkbox_theme"):
        with dpg.theme(tag="muted_checkbox_theme"):
            with dpg.theme_component(dpg.mvCheckbox):
                dpg.add_theme_color(dpg.mvThemeCol_Text, muted_col)

    for idx, (vs_id, vs) in enumerate(gui.controller.view_states.items(), start=1):
        with dpg.group(parent=container):
            # --- LINE 1: Image Name ---
            with dpg.group(horizontal=True):
                name_str, is_outdated = gui.controller.get_image_display_name(vs_id)
                lbl_id = dpg.add_text(name_str)

                with dpg.tooltip(lbl_id):
                    dpg.add_text(vs.volume.get_human_readable_file_path())

                if is_outdated:
                    dpg.configure_item(lbl_id, color=gui.ui_cfg["colors"]["outdated"])

                gui.image_label_tags[vs_id] = lbl_id

            # --- LINE 2: Controls ---
            with dpg.group(horizontal=True, horizontal_spacing=3):
                dpg.add_spacer(width=17)
                # 1. Viewers
                for v_tag in ["V1", "V2", "V3", "V4"]:
                    is_active = gui.controller.viewers[v_tag].image_id == vs_id
                    cb = dpg.add_checkbox(
                        label=f"##{vs_id}_{v_tag}",
                        default_value=is_active,
                        user_data={"img_id": vs_id, "v_tag": v_tag},
                        callback=gui.on_image_viewer_toggle,
                    )
                    dpg.bind_item_theme(cb, "muted_checkbox_theme")
                    with dpg.tooltip(cb):
                        dpg.add_text(f"Toggle in {v_tag}")

                dpg.add_spacer(width=5)

                # 3. Action Buttons
                btn_save = dpg.add_button(
                    label="\uf0c7",
                    width=20,
                    callback=lambda s, a, u: gui.on_save_image_clicked(u),
                    user_data=vs_id,
                )
                btn_reload = dpg.add_button(
                    label="\uf01e",
                    width=20,
                    callback=lambda s, a, u: gui.controller.reload_image(u),
                    user_data=vs_id,
                )
                btn_close = dpg.add_button(
                    label="\uf00d",
                    width=20,
                    callback=lambda s, a, u: gui.controller.file.close_image(u),
                    user_data=vs_id,
                )

                if dpg.does_item_exist("icon_font_tag"):
                    dpg.bind_item_font(btn_save, "icon_font_tag")
                    dpg.bind_item_font(btn_reload, "icon_font_tag")
                    dpg.bind_item_font(btn_close, "icon_font_tag")
                if dpg.does_item_exist("delete_button_theme"):
                    dpg.bind_item_theme(btn_close, "delete_button_theme")
                if dpg.does_item_exist("icon_button_theme"):
                    dpg.bind_item_theme(btn_reload, "icon_button_theme")

        dpg.add_spacer(height=2, parent=container)

    gui.refresh_recent_menu()
    if gui.context_viewer and gui.context_viewer.image_id:
        gui.highlight_active_image_in_list(gui.context_viewer.image_id)

    # Keep the invisible Sync tab locked to the new array state!
    if hasattr(gui, "refresh_sync_ui"):
        gui.refresh_sync_ui()
