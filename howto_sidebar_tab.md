Goal: Add a new navigation tab to the left panel (e.g., "Analysis").

1. **Create the Module:** In the `src/vvv/ui/` folder, create a new file named `ui_analysis.py`.
2. **Create the Layout Builder:** Define a `build_tab_analysis(gui)` function. Use `with dpg.tab(label="Analysis", tag="tab_analysis"):` and add your UI elements (buttons, sliders, text).
3. **Extract the Callbacks:** Keep the business logic isolated. If you add a button, define its callback within `ui_analysis.py` as a standalone function (e.g., `def handle_analysis_click(gui, sender, app_data, user_data):`). Assign it using a lambda: `callback=lambda s, a, u: handle_analysis_click(gui, s, a, u)`.
4. **Inject the Tab:** Open `gui.py`. Import your `build_tab_analysis` function at the top. Locate the `build_sidebar_top` method and call your build function inside the `dpg.tab_bar` block alongside the others.
5. **Bind Dynamic Data (Optional):** If your tab has inputs that should automatically update when the user changes images (like the W/L sliders do), add the UI tags and their corresponding `ViewState` properties to the `self.bindings` dictionary in `MainGUI.__init__`.