def handle_sync_group_change(gui, sender, value, user_data):
    """Business logic for changing a sync group, formerly in MainGUI."""
    vs_id = user_data
    vs = gui.controller.view_states[vs_id]

    if value == "None":
        vs.sync_group = 0
        gui.refresh_image_list_ui()
        return

    new_group_id = int(value.split(" ")[1])
    vs.sync_group = new_group_id

    master_vs_id = None
    for other_id, other_vs in gui.controller.view_states.items():
        if other_id != vs_id and other_vs.sync_group == new_group_id:
            master_vs_id = other_id
            break

    group_viewer_tags = []
    for v in gui.controller.viewers.values():
        if v.view_state and v.view_state.sync_group == new_group_id:
            group_viewer_tags.append(v.tag)

    if not group_viewer_tags:
        return

    gui.controller.sync.propagate_ppm(group_viewer_tags)

    if master_vs_id:
        master_viewer = next(
            (v for v in gui.controller.viewers.values() if v.image_id == master_vs_id),
            None,
        )
        if master_viewer:
            phys_center = master_viewer.get_center_physical_coord()
            if phys_center is not None:
                for tag in group_viewer_tags:
                    gui.controller.viewers[tag].center_on_physical_coord(phys_center)
        gui.controller.sync.propagate_sync(master_vs_id)

    gui.controller.update_all_viewers_of_image(vs_id)
    gui.refresh_image_list_ui()


def handle_sync_wl_toggle(gui, sender, app_data, user_data):
    """Business logic for toggling W/L sync, formerly in MainGUI."""
    vs_id = user_data
    vs = gui.controller.view_states[vs_id]
    vs.sync_wl = app_data  # True or False

    if app_data and vs.sync_group > 0:
        for other_vs in gui.controller.view_states.values():
            if (
                other_vs != vs
                and other_vs.sync_group == vs.sync_group
                and other_vs.sync_wl
            ):
                vs.display.ww = other_vs.display.ww
                vs.display.wl = other_vs.display.wl
                vs.display.base_threshold = other_vs.display.base_threshold
                vs.is_data_dirty = True
                gui.controller.update_all_viewers_of_image(vs_id)
                break
