# AI Developer Guide & Architecture Reference

This document serves as the global entry point and instruction manual for AI agents working on the `vvv` project. It summarizes the core architecture, development guidelines, folder organization, and provides an index of the existing documentation.

---

## 1. Project Overview & Core Principles

`vvv` is a Python-based 3D/4D medical image viewer inspired by VV, built using **DearPyGui (DPG)** for the user interface and **SimpleITK / NumPy** for image processing.

### Key Architectural Guidelines

*   **Strict separation of UI and Backend**: Keep all GUI/DearPyGui imports and logic inside the `ui/` folder or plugins. The core logic and mathematical/image operations must remain completely headless (no DPG references) to allow scripting or testing without a GUI.
*   **Model-View-Controller (MVC) Pattern**:
    *   **Model**: [VolumeData](src/vvv/core/volume_data.py) (immutable image/array data source of truth) and [ViewState](src/vvv/core/view_state.py) (transient display parameters).
    *   **View**: `ui/` modules (e.g., [SliceViewer](src/vvv/ui/viewer.py) for the viewports, [MainGUI](src/vvv/ui/gui.py)).
    *   **Controller**: [Controller](src/vvv/core/controller.py) coordinates state, holds view states, and delegates to specialized sub-managers (e.g., `FileManager`, `SyncManager`, `ROIManager`).
*   **Dirty-Flag Reactive Render Loop**:
    *   The render loop tick occurs in [MainGUI.tick()](src/vvv/ui/gui.py).
    *   `is_geometry_dirty`: Indicates that 2D bounds, zoom, pan, or window shapes need recalculation.
    *   `is_data_dirty`: Indicates that the underlying slice image must be re-extracted, window/level (W/L) applied, and pushed to the GPU texture.
*   **Concurrency & Thread Safety**:
    *   **Main Thread**: The exclusive owner of all DearPyGui calls. Never invoke DPG functions from background threads.
    *   **Background Threads**: Perform heavy operations (e.g., loading files, resampling, ITK computations) and set flags like `controller.ui_needs_refresh` to schedule UI updates.
*   **Spatial Coordinate Systems**:
    *   **Voxel**: Integer NumPy array coordinates in `[Z, Y, X]` order.
    *   **Physical**: Real-world millimeter coordinates `[x, y, z]` used for spatial synchronization, overlay registration, and measurement.
    *   **Pixel**: Screen/monitor space pixels used for DPG window rendering and mouse interactions.
*   **"Less is More" & No Over-engineering**: Keep code simple, direct, and readable. Prioritize minimal, clean solutions (e.g., reusing existing UI components, simple callbacks, and clear MVC separation) over complex design patterns, premature optimizations, or excessive abstractions.

---

## 2. Directory Structure & Organization

```
vvv/
├── docs/                      # Reference manuals and how-to guides (detailed in Section 3)
├── src/vvv/                   # Core application codebase
│   ├── core/                  # State management, view state, controller, sub-managers
│   │   ├── controller.py      # State bridge
│   │   ├── view_state.py      # Transient viewer properties
│   │   └── ...
│   ├── maths/                 # Coordinate systems, geometries, transforms, SimpleITK helpers
│   │   ├── image.py
│   │   ├── geometry.py
│   │   └── ...
│   ├── ui/                    # DearPyGui-specific view layers and components
│   │   ├── gui.py             # Main entry point for UI and render loop tick()
│   │   ├── viewer.py          # SliceViewer component
│   │   ├── ui_theme.py        # UI theme & styling constants
│   │   └── ...
│   ├── plugins/               # Modular features (auto-discovered)
│   │   ├── __init__.py        # Plugin API definitions & discovery
│   │   └── <plugin_name>/     # Individual plugins (see conventions below)
│   ├── cli.py                 # Command line interface (click-based)
│   └── config.py              # App-wide settings and paths
├── tests/                     # Unit and integration tests (prefixed with test_)
└── pyproject.toml             # Python build and dependencies configuration
```

### Plugin 3-Class Convention
Most new tools and features are modular plugins located in [src/vvv/plugins/](src/vvv/plugins/). Each plugin should adhere to the 3-file structure:
1.  `plugin_<name>.py`: Thin wrapper class implementing the lifecycle contract (`create_ui`, `update`, `on_image_loaded`, etc.).
2.  `ui_<name>.py`: Pure DPG widget layout creation. No business logic.
3.  `control_<name>.py`: State, callback logic, and synchronization with the main controller via `PluginAPI`.

---

## 3. Developer Documentation Index (docs/)

When implementing a task, refer to the specific markdown documents in the [docs/](docs/) folder:

### Core Guides & Architecture
*   [core_overview.md](docs/core_overview.md): High-level system architecture, threading model, render loop lifecycle, and coordinate definitions.
*   [core_image_types.md](docs/core_image_types.md): Specification document on image types (2D, 3D, 4D, DVF, RGB), loading pipelines, and tool capabilities.
*   [core_rendering.md](docs/core_rendering.md): Slice blending, window leveling math, Numba acceleration, and texture mapping logic.
*   [core_sync.md](docs/core_sync.md): How viewports are synchronized spatially and temporally.
*   [core_viewstate_property.md](docs/core_viewstate_property.md): How to add new reactive properties to `ViewState` (handling synchronization, events, and redraw triggers).

### How-To Integration Recipes
*   [howto_sidebar_tab.md](docs/howto_sidebar_tab.md): Step-by-step instructions to add a new tab to the sidebar menu.
*   [howto_menu_item.md](docs/howto_menu_item.md): Guide to extending the main window menu bar.
*   [howto_shortcuts.md](docs/howto_shortcuts.md): How to bind global keyboard/mouse shortcuts in `MainGUI`.
*   [howto_overlay_mode.md](docs/howto_overlay_mode.md): Guide for drawing visual overlays on top of the slice viewer (e.g. crosshairs, contours).

### Plugins Subsystem & Features
*   [plugin_architecture.md](docs/plugin_architecture.md): Comprehensive guide on the plugin contract, lifetime hooks, settings serialization, and the `PluginAPI` reference.
*   [plugin_api_method.md](docs/plugin_api_method.md): How to safely add new methods to `PluginAPI` and export them from the core.
*   [plugin_image_list.md](docs/plugin_image_list.md): Details of the image list sidepanel tool.
*   [plugin_roi.md](docs/plugin_roi.md): Outline of region-of-interest (ROI) tools and managers.
*   [plugin_contours.md](docs/plugin_contours.md): Guide on the contour detection and drawing architecture.
*   [plugin_registration.md](docs/plugin_registration.md): Extrinsic rigid registration preview and resample logic.
*   [plugin_dicom.md](docs/plugin_dicom.md): Recursive DICOM folder scanning, tag/metadata lists, and thread safety.
*   [plugin_intensity.md](docs/plugin_intensity.md): Window/Level presets, dynamic slider speeds, and async histogram computing.
*   [plugin_threshold.md](docs/plugin_threshold.md): Interactive min/max intensity threshold previews and image extraction.
*   [plugin_profile.md](docs/plugin_profile.md): Intensity line profiles, sampling, coordinate spaces, and XY plots.
*   [plugin_dvf.md](docs/plugin_dvf.md): Vector field, component-wise, and RGB visualization parameters for displacement vector fields.

---

## 4. Coding Conventions & Best Practices

1.  **Imports**: Always use absolute imports within the package (e.g., `from vvv.ui.viewer import SliceViewer` instead of `from ..ui.viewer import SliceViewer`).
2.  **Type Hinting**: Provide explicit type hints for method signatures, especially in public APIs or plugin boundaries.
3.  **DPG Tag Namespacing**: Always prefix DearPyGui item tags in plugins with the unique `plugin_id` (e.g. using `f"{self.plugin_id}_widget_name"`) to avoid namespace conflicts.
4.  **Testing**:
    *   All test files are in the `tests/` directory and must be prefixed with `test_` (e.g., `test_gui.py`).
    *   Run tests locally with `pytest`. Ensure new features or bug fixes have associated unit tests.
5.  **macOS Specifics**: Be aware that the project runs on macOS (with some Cocoa bindings, e.g., in file dialogs or menus) and Linux. Maintain cross-platform compatibility.
6.  **Prohibited Actions**:
    *   Do not bypass the dirty-flag architecture. Modify state flags (`is_data_dirty`, `is_geometry_dirty`, etc.) and let `tick()` trigger the updates instead of calling render updates directly.
    *   Do not add DPG imports inside `core/` or `maths/` folders.
    *   Do not suppress global warnings or hardcode sensitive information.
7.  **Documentation Links**: When creating or editing developer documentation (`.md` files) in the repository, always use relative repository paths (e.g., `../src/vvv/ui/ui_image_list.py`) instead of absolute `file:///` URLs so that links function correctly across all developer environments and hosting platforms.
8.  **Shared UI Components**: Avoid recreating common widgets like text rename fields or stepped sliders. Always import and reuse components from [ui_components.py](src/vvv/ui/ui_components.py) (e.g., `build_renamable_input` for input fields with focus-loss renaming, `build_stepped_slider`, `build_help_button`, and `build_beginner_tooltip`) to preserve styling and behavior consistency.
