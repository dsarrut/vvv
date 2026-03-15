
Goal: Add a new navigation tab to the left panel.

Create the Layout: In gui.py, create a new method (e.g., build_tab_analysis). Use with dpg.tab(label="Analysis"): and add your buttons, sliders, or text.

Inject the Tab: Locate build_sidebar_top in gui.py and call your new method inside the dpg.tab_bar block.

Bind the Data: Add any new UI tags and their corresponding ViewState properties to the self.bindings dictionary in MainGUI.__init__.

Register Callbacks: If your tab uses buttons that trigger logic, define the callback in gui.py and have it communicate with the self.controller to maintain clean separation.


