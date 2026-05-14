import dearpygui.dearpygui as dpg
from vvv.ui.ui_components import build_section_title, build_help_button, build_beginner_tooltip

"""
ARCHITECTURE MANDATES (UI Components):
1. REACTIVE REFRESH ONLY: This module must never refresh itself. It must only 
   rebuild when MainGUI calls 'refresh_image_list_ui', triggered by the 
   'controller.ui_needs_refresh' flag.

2. STATE-DRIVEN BUILDING: Every checkbox and text field must pull its 
   current state directly from the 'Controller' data during the refresh cycle.

3. ONE-WAY DATA FLOW: UI callbacks must only update the 'Controller' or 
   'ViewState'. They must NOT manually update other UI elements.

4. THREAD SAFETY: No code in this module should ever be called from a 
   background thread.
"""


def build_tab_images(gui):
    """Builds the static layout for the Images tab."""
    cfg_c = gui.ui_cfg["colors"]
    with dpg.group(tag="tab_images", show=False):
        build_section_title("Loaded Images", cfg_c["text_header"])
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

    viewer_tooltips = {
        "V1": "Top Left viewer",
        "V2": "Top Right viewer",
        "V3": "Bottom Left viewer",
        "V4": "Bottom Right viewer"
    }

    for idx, (vs_id, vs) in enumerate(list(gui.controller.view_states.items()), start=1):
        with dpg.group(parent=container, horizontal=True):
            # --- Left Column: 2x2 Grid ---
            with dpg.group():
                with dpg.group(horizontal=True, horizontal_spacing=3):
                    for v_tag in ["V1", "V2"]:
                        is_active = gui.controller.layout[v_tag] == vs_id
                        cb = dpg.add_checkbox(
                            label=f"##{vs_id}_{v_tag}",
                            default_value=is_active,
                            user_data={"img_id": vs_id, "v_tag": v_tag},
                            callback=gui.on_image_viewer_toggle,
                        )
                        build_beginner_tooltip(cb, viewer_tooltips[v_tag], gui)
                        dpg.bind_item_theme(cb, "muted_checkbox_theme")
                with dpg.group(horizontal=True, horizontal_spacing=3):
                    for v_tag in ["V3", "V4"]:
                        is_active = gui.controller.layout[v_tag] == vs_id
                        cb = dpg.add_checkbox(
                            label=f"##{vs_id}_{v_tag}",
                            default_value=is_active,
                            user_data={"img_id": vs_id, "v_tag": v_tag},
                            callback=gui.on_image_viewer_toggle,
                        )
                        build_beginner_tooltip(cb, viewer_tooltips[v_tag], gui)
                        dpg.bind_item_theme(cb, "muted_checkbox_theme")

            # --- Right Column: Info & Actions ---
            with dpg.group():
                # Line 1: Image Name
                with dpg.group(horizontal=True):
                    name_str, is_outdated = gui.controller.get_image_display_name(vs_id)
                    lbl_id = dpg.add_text(name_str)

                    build_beginner_tooltip(lbl_id, vs.volume.get_human_readable_file_path(), gui)

                    if is_outdated:
                        dpg.configure_item(
                            lbl_id, color=gui.ui_cfg["colors"]["outdated"]
                        )

                    gui.image_label_tags[vs_id] = lbl_id

                # Line 2: Action Buttons
                with dpg.group(horizontal=True, horizontal_spacing=3):
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
                        
                    build_help_button("The 4 checkboxes assign this image to the 4 viewers (V1: Top Left, V2: Top Right, V3: Bottom Left, V4: Bottom Right).", gui)

        dpg.add_spacer(height=4, parent=container)
        dpg.add_separator(parent=container)
        dpg.add_spacer(height=4, parent=container)

    gui.refresh_recent_menu()
    if gui.context_viewer and gui.context_viewer.image_id:
        highlight_active_image_in_list(gui, gui.context_viewer.image_id)
