import dearpygui.dearpygui as dpg


def create_gui(controller):
    # 1. Menubar
    with dpg.viewport_menu_bar():
        with dpg.menu(label="File"):
            dpg.add_menu_item(label="Open Image...")
            dpg.add_menu_item(label="Exit")
        with dpg.menu(label="Link"):
            dpg.add_menu_item(label="Link All", callback=lambda: controller.link_all())

        # Define a theme for the viewers
        with dpg.theme() as viewer_theme:
            with dpg.theme_component(dpg.mvAll):
                # Change the background of the child window
                dpg.add_theme_color(dpg.mvThemeCol_ChildBg, [0, 0, 0], category=dpg.mvThemeCat_Core)
                # Change border color
                dpg.add_theme_color(dpg.mvThemeCol_Border, [50, 50, 50], category=dpg.mvThemeCat_Core)
                # force 0 padding inside the viewer windows
                dpg.add_theme_style(dpg.mvStyleVar_WindowPadding, 0, 0, category=dpg.mvThemeCat_Core)
                dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing, 0, 0, category=dpg.mvThemeCat_Core)
                dpg.add_theme_style(dpg.mvStyleVar_FramePadding, 0, 0, category=dpg.mvThemeCat_Core)

        # We add a resize_callback to the primary window
        with dpg.window(tag="PrimaryWindow",
                        on_close=controller.main_windows.cleanup,
                        no_scrollbar=True,
                        no_scroll_with_mouse=True,
                        no_move=True,
                        no_resize=True,  # We handle resize via code
                        no_collapse=True,
                        no_title_bar=True,
                        no_bring_to_front_on_focus=True):
            with dpg.item_handler_registry(tag="window_resize_handler"):
                dpg.add_item_resize_handler(callback=lambda: controller.main_windows.on_window_resize())
            dpg.bind_item_handler_registry("PrimaryWindow", "window_resize_handler")

            with dpg.group(horizontal=True):
                # LEFT PANEL: Fixed width
                create_left_panel(controller)

                # RIGHT PANEL: This group will contain the 4 viewers
                with dpg.child_window(tag="viewers_container",
                                      border=False,
                                      no_scrollbar=True,
                                      no_scroll_with_mouse=True):
                    with dpg.group(horizontal=True):
                        create_viewer_widget("V1", controller)
                        create_viewer_widget("V2", controller)
                    with dpg.group(horizontal=True):
                        create_viewer_widget("V3", controller)
                        create_viewer_widget("V4", controller)

        dpg.bind_item_theme("viewers_container", viewer_theme)
        # Bind the theme to all viewer windows
        for tag in ["V1", "V2", "V3", "V4"]:
            dpg.bind_item_theme(f"win_{tag}", viewer_theme)

    # Add this at the end of create_gui before viewport setup:
    with dpg.handler_registry():
        dpg.add_mouse_wheel_handler(callback=lambda s, d: controller.main_windows.on_global_scroll(d))
        dpg.add_mouse_drag_handler(callback=lambda s, d: controller.main_windows.on_global_drag(d))
        dpg.add_mouse_release_handler(callback=lambda: controller.main_windows.on_global_release())
        dpg.add_key_press_handler(callback=lambda s, d: controller.main_windows.on_key_press(d))
        dpg.add_mouse_click_handler(callback=lambda s, d: controller.main_windows.on_global_click(d))


def create_viewer_widget(tag, controller):
    viewer = controller.viewers[tag]
    with dpg.child_window(tag=f"win_{tag}",
                          border=True,
                          no_scrollbar=True,
                          no_scroll_with_mouse=True):
        with dpg.drawlist(tag=f"drawlist_{tag}", width=-1, height=-1):
            dpg.draw_image(viewer.texture_tag, [0, 0], [1, 1], tag=viewer.image_tag)
            # The strip node layer (for high zoom)
            dpg.add_draw_node(tag=viewer.strips_a_tag)
            dpg.add_draw_node(tag=viewer.strips_b_tag)
            viewer.active_strips_node = viewer.strips_a_tag
            # The grid node layer (for high zoom)
            dpg.add_draw_node(tag=viewer.grid_a_tag)
            dpg.add_draw_node(tag=viewer.grid_b_tag)
            viewer.active_grid_node = viewer.grid_a_tag
            # the crosshair layer
            dpg.add_draw_node(tag=viewer.crosshair_tag)

        # the overlay with the current pixel coordinate/value
        dpg.add_text("", tag=viewer.overlay_tag, color=[0, 246, 7], pos=[5, 5])


# Helper function to create a labeled copiable field
def create_labeled_field(label, tag):
    with dpg.group(horizontal=True):
        dpg.add_text(f"{label}:", tag=f"{tag}_label")
        dpg.add_input_text(tag=tag, readonly=True, width=-1)


def create_left_panel(controller):
    with dpg.child_window(width=controller.main_windows.side_panel_width,
                          tag="side_panel",
                          no_scrollbar=True,
                          no_scroll_with_mouse=True,
                          border=True):
        # Add a small vertical space before "Loaded Images"
        dpg.add_spacer(height=3)

        # --- TOP PANEL: Loaded Images ---
        with dpg.child_window(tag="top_panel", height=300, resizable_y=True, border=False):
            dpg.add_text("Loaded Images", color=[93, 93, 93])
            dpg.add_separator()
            # Dynamically filled by controller
            dpg.add_group(tag="image_list_container")

        dpg.add_spacer(height=5)

        # --- BOTTOM PANEL: Active Viewer Info ---
        with dpg.child_window(tag="bottom_panel", border=False):
            dpg.add_text("Active Viewer", color=[93, 93, 93])
            dpg.add_separator()

            # Image Stats Section
            with dpg.group(tag="image_info_group"):
                create_labeled_field("", tag="info_name")
                create_labeled_field("Type", tag="info_voxel_type")
                create_labeled_field("Size", tag="info_size")
                create_labeled_field("Spacing", tag="info_spacing")
                create_labeled_field("Origin", tag="info_origin")
                create_labeled_field("Matrix", tag="info_matrix")
                #create_labeled_field("Memory", tag="info_memory")
                dpg.add_input_text(tag="info_memory", readonly=True, width=-1)
                create_window_level(controller)

            dpg.add_spacer(height=10)
            dpg.add_text("Crosshair", color=[93, 93, 93])
            dpg.add_separator()

            # Live Pixel Data Section
            with dpg.group(tag="image_crosshair_group"):
                create_labeled_field("Voxel", tag="info_vox")
                create_labeled_field("Coord", tag="info_phys")
                create_labeled_field("Value", tag="info_val")

    # Styling tip: To make input_text look like regular text:
    with dpg.theme() as readonly_theme:
        with dpg.theme_component(dpg.mvInputText):
            dpg.add_theme_color(dpg.mvThemeCol_FrameBg, [0, 0, 0, 0])  # Transparent bg
            dpg.add_theme_style(dpg.mvStyleVar_FrameBorderSize, 0)  # No border
            dpg.add_theme_color(dpg.mvThemeCol_Text, [0, 246, 7])

    dpg.bind_item_theme("image_info_group", readonly_theme)
    dpg.bind_item_theme("image_crosshair_group", readonly_theme)


def create_window_level(controller):
    # Create a parent group to hold both Window and Level on one line
    with dpg.group(horizontal=True):
        # Window Section
        with dpg.group(horizontal=True):
            dpg.add_text("Window")
            dpg.add_input_text(tag="info_window",
                               width=70,  # Fixed width to leave room for Level
                               on_enter=True,
                               callback=lambda: controller.on_sidebar_wl_change())

        dpg.add_spacer(width=5)  # Small gap between the two

        # Level Section
        with dpg.group(horizontal=True):
            dpg.add_text("Level")
            dpg.add_input_text(tag="info_level",
                               width=-1,  # Fill the remaining space
                               on_enter=True,
                               callback=lambda: controller.on_sidebar_wl_change())
