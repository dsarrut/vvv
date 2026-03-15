Goal: Add a new keyboard trigger for a viewer action.

Define the Key: Open config.py and add your new action name and the default physical key (e.g., "toggle_fullscreen": "F") to the DEFAULT_SETTINGS["shortcuts"] dictionary.

Create the Action: In viewer.py, add a method to the SliceViewer class (e.g., def action_toggle_fullscreen(self): ...) that performs the desired state change.

Register the Shortcut: In viewer.py, locate init_shortcut_dispatcher and add your new action to the self._shortcut_map.

Sync the UI (Optional): If this shortcut changes a value that appears in the sidebar, ensure the property name in ViewState matches the key in the gui.py self.bindings dictionary to keep the checkboxes in sync.


