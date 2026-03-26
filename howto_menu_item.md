Goal: Add a new dropdown menu or item to the floating top bar.

1. **Locate the Menu Bar:** Open `src/vvv/ui/gui.py` and find the `build_menu_bar` method.
2. **Add the Item:** * *To add to an existing menu:* Use `dpg.add_menu_item(label="New Action", callback=self.on_action_clicked)` inside the existing `with dpg.menu` block.
    * *To add a new menu dropdown:* Use `with dpg.menu(label="Tools"):` before the "Help" menu block.
3. **Implement the Callback:** Create the corresponding method in `gui.py` to handle the click.
    * *Note:* If the action involves complex UI generation (like opening a file browser or showing a modal), consider routing the callback to a sequence in `ui_sequences.py` or using the modals provided in `ui_notifications.py`.
    * If the action modifies image data, ensure it calls `self.controller.update_all_viewers_of_image()` afterward to refresh the display.