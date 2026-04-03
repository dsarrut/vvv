Goal: Add a new dropdown menu or item to the floating top bar.

1.  **Locate the Menu Bar:** Open `src/vvv/ui/gui.py` and find the `build_menu_bar` method.
2.  **Add the Item:**
    *   To add to an existing menu: Use `dpg.add_menu_item(label="New Action", callback=self.on_action_clicked)` inside an existing `with dpg.menu(...)` block.
    *   To add a new menu dropdown: Use `with dpg.menu(label="Tools"):` before the "Help" menu block.
3.  **Implement the Callback:** Create the corresponding method in `gui.py` to handle the click.
    *   The callback logic depends on the type of action:
    *   **For display changes** (e.g., colormap, overlays): Modify the properties on the `ViewState` object for the target viewer. The view will update automatically.
        ```python
        # In the callback:
        viewer = self.context_viewer
        if viewer and viewer.view_state:
            viewer.view_state.display.colormap = "viridis"
            # To sync this change with other linked images:
            self.controller.sync.propagate_colormap(viewer.image_id)
        ```
    *   **For state changes** (e.g., loading/removing images, modifying ROIs): Set the `ui_needs_refresh` flag. This will trigger a refresh of the sidebar UI panels.
        ```python
        self.controller.ui_needs_refresh = True
        ```
    *   For complex actions like opening dialogs, consider using helpers from `ui_sequences.py` or `ui_notifications.py`.
