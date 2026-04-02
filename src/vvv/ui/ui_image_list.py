import dearpygui.dearpygui as dpg
from vvv.ui.ui_sync import handle_sync_group_change, handle_sync_wl_toggle


def build_tab_images(gui):
    """Builds the static layout for the Images tab."""
    cfg_c = gui.ui_cfg["colors"]
    with dpg.tab(label="Images", tag="tab_images"):
        dpg.add_spacer(height=5)

        # Move the Link/Unlink buttons to the header!
        with dpg.group(horizontal=True):
            dpg.add_text("Loaded Images", color=cfg_c["text_header"])
            dpg.add_spacer(width=20)
            dpg.add_button(
                label="Link All", callback=lambda: gui.controller.link_all(), width=60
            )
            dpg.add_button(
                label="Unlink All",
                callback=lambda: gui.controller.unlink_all(),
                width=70,
            )

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
    """Dynamically rebuilds the Image list UI with ultra-compact Sync controls."""
    container = "image_list_container"
    if not dpg.does_item_exist(container):
        return

    dpg.delete_item(container, children_only=True)
    gui.image_label_tags.clear()
    gui.sync_label_tags.clear()  # Keep for legacy safety

    # Calculate Sync Group Combo Items using the compact "G 1" format
    max_active_group = max(
        [vs.sync_group for vs in gui.controller.view_states.values()] + [0]
    )
    num_groups = max(3, len(gui.controller.view_states), max_active_group)
    combo_items = ["---"] + [f"G {i}" for i in range(1, num_groups + 1)]

    # 1. ADD ENUMERATE HERE
    for idx, (vs_id, vs) in enumerate(gui.controller.view_states.items(), start=1):
        with dpg.group(parent=container):

            # --- LINE 1: Image Name ---
            with dpg.group(horizontal=True):
                is_outdated = getattr(vs.volume, "_is_outdated", False)
                # 2. INJECT [idx] INTO THE NAME STRING
                base_name = f"[{idx}] {vs.volume.name}"
                name_str = f"{base_name} *" if is_outdated else base_name
                lbl_id = dpg.add_text(name_str)

                with dpg.tooltip(lbl_id):
                    dpg.add_text(vs.volume.get_human_readable_file_path())

                if is_outdated:
                    dpg.configure_item(lbl_id, color=gui.ui_cfg["colors"]["outdated"])

                gui.image_label_tags[vs_id] = lbl_id

            # --- LINE 2: Controls (Ultra-Packed Layout) ---
            # horizontal_spacing=3 forces widgets to sit shoulder-to-shoulder
            with dpg.group(horizontal=True, horizontal_spacing=3):

                # 1. Viewers (V1, V2, V3, V4)
                for v_tag in ["V1", "V2", "V3", "V4"]:
                    is_active = gui.controller.viewers[v_tag].image_id == vs_id
                    dpg.add_checkbox(
                        label="",  # Ensure no ghost label width
                        default_value=is_active,
                        user_data={"img_id": vs_id, "v_tag": v_tag},
                        callback=gui.on_image_viewer_toggle,
                    )

                dpg.add_spacer(width=2)

                # 2. Sync Controls
                dpg.add_combo(
                    items=combo_items,
                    default_value=(
                        "---" if not vs.sync_group else f"G {vs.sync_group}"
                    ),
                    width=55,  # Shrunk from 75px to 55px!
                    user_data=vs_id,
                    callback=lambda s, a, u: handle_sync_group_change(gui, s, a, u),
                )

                is_rgb = getattr(vs.volume, "is_rgb", False)
                dpg.add_checkbox(
                    label="W/L",
                    default_value=vs.sync_wl,
                    user_data=vs_id,
                    callback=lambda s, a, u: handle_sync_wl_toggle(gui, s, a, u),
                    enabled=not is_rgb,
                )

                dpg.add_spacer(width=2)

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

                # Apply Styles
                if dpg.does_item_exist("icon_font_tag"):
                    dpg.bind_item_font(btn_save, "icon_font_tag")
                    dpg.bind_item_font(btn_reload, "icon_font_tag")
                    dpg.bind_item_font(btn_close, "icon_font_tag")
                if dpg.does_item_exist("delete_button_theme"):
                    dpg.bind_item_theme(btn_close, "delete_button_theme")
                if dpg.does_item_exist("icon_button_theme"):
                    dpg.bind_item_theme(btn_reload, "icon_button_theme")

    gui.refresh_recent_menu()
    if gui.context_viewer and gui.context_viewer.image_id:
        highlight_active_image_in_list(gui, gui.context_viewer.image_id)
