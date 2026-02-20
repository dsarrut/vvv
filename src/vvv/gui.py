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
                        no_scroll_with_mouse=True):
            with dpg.item_handler_registry(tag="window_resize_handler"):
                dpg.add_item_resize_handler(callback=lambda: controller.main_windows.on_window_resize())
            dpg.bind_item_handler_registry("PrimaryWindow", "window_resize_handler")

            with dpg.group(horizontal=True):
                # 2. LEFT PANEL: Fixed width
                with dpg.child_window(width=250,
                                      tag="side_panel",
                                      no_scrollbar=True,
                                      no_scroll_with_mouse=True):
                    dpg.add_text("Loaded Images", color=[0, 255, 127])
                    dpg.add_listbox(tag="ui_image_list", items=[], num_items=10)
                    # ...

                # 3. RIGHT PANEL: This group will contain the 4 viewers
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
            dpg.draw_image(viewer.texture_tag, [0, 0], [1, 1], tag=f"img_{tag}")
            # The grid node layer (for high zoom)
            #dpg.add_draw_node(tag=f"grid_node_{tag}")
            dpg.add_draw_node(tag=f"grid_node_A_{tag}")
            dpg.add_draw_node(tag=f"grid_node_B_{tag}")
            viewer.active_grid_node = f"grid_node_A_{tag}"  # Keep track of which is currently shown
            # the crosshair layer
            dpg.add_draw_node(tag=f"crosshair_node_{tag}")

        # the overlay with the current pixel coordinate/value
        dpg.add_text("", tag=f"overlay_{tag}", color=[0, 246, 7], pos=[5, 5])
