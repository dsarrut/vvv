# How to Add a Sidebar Tab

This guide explains how to add a new tool panel or tab to VVV's left collapsible sidebar.

---

## 1. Choose Implementation Path: Core Tab vs. Plugin

* **Plugin (Recommended for modular features)**:
  * If your feature is self-contained (e.g. Landmarks, Registration, DVF, Profiles), implement it as a plugin in `src/vvv/plugins/<name>/`.
  * Plugins automatically get discovered and added to the sidebar without modifying `gui.py`. See [plugin_architecture.md](plugin_architecture.md).
* **Core Tab (For built-in application infrastructure)**:
  * Used for core panels like Image List, Viewport Sync, and Fusion Overlay. Follow the steps below.

---

## 2. Step-by-Step for Core Sidebar Tabs

### Step 1: Create the UI Layout Module
Create a new file under `src/vvv/ui/` (e.g., `src/vvv/ui/ui_mytool.py`):

```python
import dearpygui.dearpygui as dpg
from vvv.ui.ui_components import build_section_title

def build_tab_mytool(gui):
    cfg_c = gui.ui_cfg["colors"]
    with dpg.group(tag="tab_mytool", show=False):
        build_section_title("My Tool Title", cfg_c["text_header"])
        dpg.add_text("Tool controls go here...")
        # Add buttons, sliders, etc.
```

### Step 2: Add Navigation Icon Button
In `src/vvv/ui/gui.py`, locate `build_sidebar_left()`:
1. Choose an icon glyph from FontAwesome (embedded in `icon_font_tag`).
2. Add your tab identifier to the navigation buttons loop or add a button:
```python
btn_mytool = dpg.add_button(
    label="\uf0ad",  # FontAwesome icon code (e.g. wrench)
    width=-1,
    height=cfg_l["nav_btn_h"],
    user_data="mytool",
    callback=self.on_nav_clicked,
)
dpg.bind_item_theme(btn_mytool, "theme_rounded_nav")
if dpg.does_item_exist("icon_font_tag"):
    dpg.bind_item_font(btn_mytool, "icon_font_tag")
```

### Step 3: Mount the Container in the Top Panel
In `src/vvv/ui/gui.py`, locate `build_sidebar_top()`:
Import and call your layout function:
```python
from vvv.ui.ui_mytool import build_tab_mytool
# Inside build_sidebar_top():
build_tab_mytool(self)
```

### Step 4: Handle Navigation Switching
In `src/vvv/ui/gui.py`, locate `on_nav_clicked()`:
Ensure your container's visibility is updated when its tab is active:
```python
dpg.configure_item("tab_mytool", show=(self.active_tab == "mytool"))
```

### Step 5: State Synchronization
* When background state changes (e.g., images loaded or modified), flag `self.controller.ui_needs_refresh = True`.
* If widgets need per-frame synchronization with the active viewer, add a `sync_mytool_ui(gui)` function called inside `MainGUI.tick()`.

