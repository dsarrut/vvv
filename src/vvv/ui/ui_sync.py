import dearpygui.dearpygui as dpg

def build_tab_sync(gui):
    """Builds the static layout for the Synchronization tab."""
    cfg_c = gui.ui_cfg["colors"]
    with dpg.tab(label="Sync", tag="tab_sync"):
        dpg.add_spacer(height=5)
        dpg.add_text("Sync Groups", color=cfg_c["text_header"])
        dpg.add_separator()

        # Give the container a defined width so columns lay out nicely
        with dpg.child_window(border=False, no_scrollbar=True):
            dpg.add_group(tag="sync_list_container")

            dpg.add_separator()
            dpg.add_spacer(height=5)
            with dpg.group(horizontal=True):
                dpg.add_button(
                    label="Link All",
                    callback=lambda: gui.controller.link_all(),
                    width=80,
                )
                dpg.add_button(
                    label="Unlink All",
                    callback=lambda: gui.controller.unlink_all(),
                    width=80,
                )


def refresh_sync_ui(gui):
    """Dynamically rebuilds the Sync list UI."""
    container = "sync_list_container"
    if not dpg.does_item_exist(container):
        return
    dpg.delete_item(container, children_only=True)
    gui.sync_label_tags.clear()

    max_active_group = max(
        [vs.sync_group for vs in gui.controller.view_states.values()] + [0]
    )
    num_groups = max(3, len(gui.controller.view_states), max_active_group)
    combo_items = ["None"] + [f"Group {i}" for i in range(1, num_groups + 1)]

    muted_col = gui.ui_cfg["colors"]["text_muted"]
    transparent = gui.ui_cfg["colors"]["transparent"]

    for vs_id, vs in gui.controller.view_states.items():
        with dpg.group(parent=container):
            # --- LINE 1: Image Name (Matches Images Tab) ---
            with dpg.group(horizontal=True):
                if vs.sync_group > 0:
                    dpg.add_text(f"[{vs.sync_group}]", color=muted_col)
                else:
                    dpg.add_text("   ", color=transparent)

                is_outdated = getattr(vs.volume, "_is_outdated", False)
                name_str = f"{vs.volume.name} *" if is_outdated else vs.volume.name

                lbl_id = dpg.add_text(name_str)

                if is_outdated:
                    dpg.configure_item(lbl_id, color=gui.ui_cfg["colors"]["outdated"])

                gui.sync_label_tags[vs_id] = lbl_id

            # --- LINE 2: Controls (Indented) ---
            with dpg.group(horizontal=True):
                dpg.add_spacer(width=15)  # Indent to match checkbox alignment
                dpg.add_combo(
                    items=combo_items,
                    default_value=(
                        "None" if not vs.sync_group else f"Group {vs.sync_group}"
                    ),
                    width=85,
                    user_data=vs_id,
                    callback=gui.on_sync_group_change,
                )
                dpg.add_spacer(width=5)

                is_rgb = getattr(vs.volume, "is_rgb", False)
                dpg.add_checkbox(
                    label="Sync W/L",
                    default_value=vs.sync_wl,
                    user_data=vs_id,
                    callback=gui.on_per_image_sync_wl_toggle,
                    enabled=not is_rgb,  # Don't allow W/L sync on RGB images
                )

            dpg.add_spacer(height=4)  # Tiny gap between image blocks