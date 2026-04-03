Goal: Add a new navigation tab to the left panel (e.g., "Analysis").

1.  **Create the Module:** In the `src/vvv/ui/` folder, create a new Python file (e.g., `ui_analysis.py`).
2.  **Create the Layout Builder Function:** Inside your new module, define a function to build the tab's UI (e.g., `def build_tab_analysis(gui):`).
    *   Within this function, use `with dpg.tab(label="Analysis", tag="tab_analysis"):` to define the tab's content. Add your desired UI elements (buttons, sliders, text, etc.) inside this block.
3.  **Implement Callbacks:** For any interactive UI elements (like buttons or sliders), define their callback functions within your new module. These functions should accept `gui`, `sender`, `app_data`, and `user_data` as arguments.
    *   **Important:** If your callback needs to interact with the main GUI or controller, ensure you pass the `gui` object to it.
    *   If your action changes the overall UI state (e.g., adds/removes images, modifies ROIs), set `gui.controller.ui_needs_refresh = True` to trigger a refresh of relevant UI components.
    ```python
    # Example callback in ui_analysis.py
    def on_analysis_button_clicked(gui, sender, app_data, user_data):
        # ... perform analysis ...
        gui.controller.ui_needs_refresh = True # If the analysis changes image list or ROIs
    ```
4.  **Inject the Tab into MainGUI:**
    *   Open `src/vvv/ui/gui.py`.
    *   Import your new `build_tab_analysis` function at the top: `from vvv.ui.ui_analysis import build_tab_analysis`.
    *   Locate the `MainGUI.build_sidebar_top` method. Inside the `with dpg.tab_bar(tag="sidebar_tabs", ...):` block, call your builder function: `build_tab_analysis(self)`.
5.  **Bind Dynamic Data (Optional):** If your tab contains input fields or displays values that should automatically update when the active image or its properties change, add the UI tags and their corresponding `ViewState` property names to the `self.bindings` dictionary in `MainGUI.__init__`.
    ```python
    # Example binding in MainGUI.__init__
    self.bindings = {
        # ... existing bindings ...
        "my_analysis_input_tag": "analysis_state.some_property",
    }
    ```
    You will also need to ensure your `ViewState` (or a similar state object) has the `analysis_state` and `some_property` defined.
