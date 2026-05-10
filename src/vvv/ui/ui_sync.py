import dearpygui.dearpygui as dpg
from vvv.ui.ui_components import build_section_title

"""
ARCHITECTURE MANDATES (UI Components):
1. REACTIVE REFRESH ONLY: This module must only rebuild the sync matrix 
   when 'refresh_sync_ui' is called by the MainGUI. Trigger refreshes via 
   'gui.controller.ui_needs_refresh = True'.

2. STATE-DRIVEN BUILDING: Group dropdowns and link buttons must pull their 
   current state directly from 'ViewState.sync_group' and 
   'ViewState.sync_wl_group'.

3. ONE-WAY DATA FLOW: Callbacks must update the synchronization groups in 
   the 'Controller' or 'ViewState'. Do not manually update labels or colors 
   within the callback.
"""


def build_tab_sync(gui):
    """Builds the static layout for the Synchronization matrix tab."""
    cfg_c = gui.ui_cfg["colors"]
    with dpg.group(tag="tab_sync", show=False):
        build_section_title("Synchronization", cfg_c["text_header"])

        with dpg.group(horizontal=True):
            dpg.add_button(
                label="Link All",
                callback=lambda: gui.controller.link_all(),
                width=95,
            )
            dpg.add_button(
                label="Unlink All",
                callback=lambda: gui.controller.unlink_all(),
                width=95,
            )

        with dpg.group(horizontal=True):
            dpg.add_button(
                label="Link All W/L",
                callback=lambda: gui.controller.link_all_wl(),
                width=95,
            )
            dpg.add_button(
                label="Unlink All W/L",
                callback=lambda: gui.controller.unlink_all_wl(),
                width=95,
            )

        dpg.add_spacer(height=10)
        dpg.add_separator()
        with dpg.child_window(border=False, height=-1):
            dpg.add_group(tag="sync_list_container")


def refresh_sync_ui(gui):
    """Dynamically rebuilds the Sync matrix UI."""
    container = "sync_list_container"
    if not dpg.does_item_exist(container):
        return

    dpg.delete_item(container, children_only=True)
    gui.sync_label_tags.clear()

    # Get the total number of loaded images
    num_images = len(gui.controller.view_states)

    # Calculate Spatial Groups (1, 2, 3...)
    max_sp_group = max(
        [vs.sync_group for vs in list(gui.controller.view_states.values())] + [0]
    )
    num_sp_groups = max(num_images, max_sp_group)  # <-- Removed the hardcoded 3

    # Calculate W/L Groups (A, B, C...)
    max_wl_group = max(
        [getattr(vs, "sync_wl_group", 0) for vs in list(gui.controller.view_states.values())]
        + [0]
    )
    num_wl_groups = max(num_images, max_wl_group)  # <-- Removed the hardcoded 3

    sp_items = ["None"] + [f"Grp {i}" for i in range(1, num_sp_groups + 1)]

    wl_items = ["None"] + [f"Grp {chr(64 + i)}" for i in range(1, num_wl_groups + 1)]

    for idx, (vs_id, vs) in enumerate(list(gui.controller.view_states.items()), start=1):
        with dpg.group(parent=container):
            # --- LINE 1: Image Name ---
            with dpg.group(horizontal=True):
                name_str, is_outdated = gui.controller.get_image_display_name(vs_id)
                lbl_id = dpg.add_text(name_str)

                with dpg.tooltip(lbl_id):
                    dpg.add_text(vs.volume.get_human_readable_file_path())

                if is_outdated:
                    dpg.configure_item(lbl_id, color=gui.ui_cfg["colors"]["outdated"])

                gui.sync_label_tags[vs_id] = lbl_id

            # --- LINE 2: Dropdowns ---
            with dpg.group(horizontal=True, horizontal_spacing=8):
                dpg.add_spacer(width=17)
                dpg.add_text("Sync:", color=gui.ui_cfg["colors"]["text_dim"])
                dpg.add_combo(
                    items=sp_items,
                    default_value=(
                        "None" if not vs.sync_group else f"Grp {vs.sync_group}"
                    ),
                    width=70,
                    user_data=vs_id,
                    callback=lambda s, a, u: handle_sync_group_change(gui, s, a, u),
                )

                dpg.add_text("W/L:", color=gui.ui_cfg["colors"]["text_dim"])
                wl_val = vs.sync_wl_group
                is_rgb = vs.volume.is_rgb

                dpg.add_combo(
                    items=wl_items,
                    default_value=("None" if not wl_val else f"Grp {chr(64 + wl_val)}"),
                    width=70,
                    user_data=vs_id,
                    callback=lambda s, a, u: handle_wl_group_change(gui, s, a, u),
                    enabled=not is_rgb,
                )
            dpg.add_spacer(height=2, parent=container)

    if gui.context_viewer and gui.context_viewer.image_id:
        gui.highlight_active_image_in_list(gui.context_viewer.image_id)


def handle_sync_group_change(gui, sender, value, user_data):
    """UI callback for changing a spatial sync group."""
    vs_id = user_data
    # Convert "Grp 1" to 1, or "None" to 0
    new_group_id = 0 if value == "None" else int(value.split(" ")[1])

    gui.controller.set_sync_group(vs_id, new_group_id)
    gui.controller.ui_needs_refresh = True


def handle_wl_group_change(gui, sender, value, user_data):
    """Business logic for changing a radiometric (W/L) sync group."""
    vs_id = user_data
    vs = gui.controller.view_states[vs_id]

    if value == "None":
        if getattr(vs, "sync_wl_group", 0) == 0:
            return
        vs.sync_wl_group = 0
        gui.controller.ui_needs_refresh = True
        return

    # Parse "Grp A" -> 1, "Grp B" -> 2
    letter = value.split(" ")[1]
    new_group_id = ord(letter) - 64

    if getattr(vs, "sync_wl_group", 0) == new_group_id:
        return

    vs.sync_wl_group = new_group_id

    # Auto-pull W/L from an existing master in this group
    master_vs_id = None
    active_viewer = gui.context_viewer
    if active_viewer and active_viewer.image_id in gui.controller.view_states:
        active_vs = gui.controller.view_states[active_viewer.image_id]
        if active_vs.sync_wl_group == new_group_id:
            master_vs_id = active_viewer.image_id

    if not master_vs_id:
        for other_id, other_vs in list(gui.controller.view_states.items()):
            if other_id != vs_id and other_vs.sync_wl_group == new_group_id:
                master_vs_id = other_id
                break

    if master_vs_id:
        # State-Only Fix: Let the SyncManager handle the robust broadcast!
        # This ensures it hits not just the base image, but any active overlays as well.
        gui.controller.sync.propagate_window_level(master_vs_id)
        gui.controller.sync.propagate_colormap(master_vs_id)

    gui.controller.ui_needs_refresh = True
