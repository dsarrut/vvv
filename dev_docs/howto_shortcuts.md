Goal: Add a new keyboard/mouse trigger for a viewer action.

1. **Define the Key:** Open `config.py` and add your new action name and the default physical key (e.g., `"toggle_fullscreen": "F"`) to the `DEFAULT_SETTINGS["shortcuts"]` dictionary.
2. **Create the Action:** * *For Keyboard:* In `viewer.py`, add a method to the `SliceViewer` class (e.g., `def action_toggle_fullscreen(self): ...`) that performs the desired state change.
    * *For Continuous Mouse Math:* If the action requires continuous tracking (like Window/Level), implement the math inside `InteractionManager.on_mouse_move` or `NavigationTool.on_drag` in `ui_interaction.py`.
3. **Register the Shortcut:** In `viewer.py`, locate `init_shortcut_dispatcher` and add your new action to the `self._shortcut_map`.
4. **Provide a Fallback:** Open `ui_interaction.py` and locate `InteractionManager.on_key_press`. If your shortcut is new and might not exist in old `settings.json` user files, add a fallback check (e.g., `if val is None and action_name == "toggle_fullscreen": val = dpg.mvKey_F`).