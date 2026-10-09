# DICOM Browser Plugin Developer Guide

The DICOM Browser plugin provides recursive folder scanning, DICOM series identification, metadata/tag extraction, patient and study summary information, dynamic tag tables, and batch loading of DICOM slice series.

## File Structure

- **[plugin_dicom.py](../src/vvv/plugins/dicom/plugin_dicom.py)**: Plugin entry point conforming to `PluginProtocol`. Sets `show_in_sidebar = False` to omit the plugin from the left sidebar nav panel. Exposes the launcher via a File menu item in `MainGUI`.
- **[control_dicom.py](../src/vvv/plugins/dicom/control_dicom.py)**: Controller coordinating scanning events, loaded images lifecycle, and UI stubs.
- **[ui_dicom_plugin.py](../src/vvv/plugins/dicom/ui_dicom_plugin.py)**: Namespaced popup browser window. Spawns background scanning threads, handles selection list rendering, metadata text mapping, keyboard arrow key navigation routing, and sanitization of string formatting.
- **[test_dicom.py](../src/vvv/plugins/dicom/test_dicom.py)**: Unit test suite covering scanning progress, series list selection, metadata rendering, and open actions.

---

## 1. Background Scanning Thread & Asynchronous UI Updates

Scanning a large directory for DICOM files can be computationally expensive and block the main DearPyGui rendering thread. To prevent UI freezes, the scanning process is decoupled:

1. **Daemon Scanning Thread**: Triggering a folder scan calls `on_select_folder()` and starts a daemon `threading.Thread` with a clearable `self._stop_event: threading.Event`.
2. **Generator-Based Progression**: The scanning thread processes folders recursively (or not), yielding progression percentages and folder names, and compiling lists of valid scanned DICOM series.
3. **UI Tick polling**: The main loop thread pulls results via `tick()`, updating the progress bar and status text safely without blocking the DearPyGui render cycle.
4. **Thread Event Safety**: Setting `self._stop_event` inside `destroy()` or when starting a new scan terminates any stale scanning threads immediately.

---

## 2. DearPyGui String Sanitization & Prevention of Segmentation Faults

- **Root Cause**: DearPyGui's C++ bindings crash with a NULL pointer dereference in `strlen` (resulting in a hard segmentation fault) when receiving Python strings containing null bytes (`\x00`) or surrogate code points (`0xD800`–`0xDFFF`). These characters commonly occur in corrupted metadata fields or unencodable binary payloads parsed by `pydicom`.
- **Sanitization Helper (`clean_string`)**: Implements a robust filter:
  ```python
  def clean_string(val):
      if val is None:
          return ""
      try:
          val_str = str(val).replace('\x00', '')
          val_str = "".join(c for c in val_str if not (0xD800 <= ord(c) <= 0xDFFF))
          return val_str.encode('utf-8', 'ignore').decode('utf-8')
      except Exception:
          return "Unknown"
  ```
- **Applied Boundaries**: The helper is used to sanitize every string sent to DearPyGui, including series selectable labels, patient/study summary fields, and all rows of the DICOM tags detail table.

---

## 3. Keyboard / Arrow Key Routing

Keyboard navigation is routed to improve accessibility and review speed:
- In `InteractionManager.on_key_press` in `src/vvv/ui/ui_interaction.py`, keyboard focus checks route arrow presses (Up/Down) to `move_selection` when the DICOM browser is visible.
- This changes the active series selection, highlights the selectable row, focuses the list item, and updates the tag detail table on the right dynamically.

---

## 4. Sidebar Omission & File Menu Integration

- Setting `show_in_sidebar = False` in `plugin_dicom.py` hides the DICOM browser from the left sidebar nav panel.
- Instead, the DICOM browser window is launched exclusively via the **File -> Open DICOM Browser...** menu item.
- An informative beginner mode tooltip is attached to the menu item to explain how folder scanning works.
