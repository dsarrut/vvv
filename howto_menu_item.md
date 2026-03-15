Goal: Add a new dropdown menu or item to the top bar.

Locate the Menu Bar: Open gui.py and find the build_menu_bar method.

Add the Item: * To add to an existing menu: Use dpg.add_menu_item(label="New Action", callback=self.on_action_clicked) inside the existing with dpg.menu block.

To add a new menu: Use with dpg.menu(label="Tools"): before the "Help" menu.

Implement the Callback: Create the corresponding method in gui.py to handle the click. If the action modifies image data, ensure it calls self.controller.update_all_viewers_of_image() afterward to refresh the display.

