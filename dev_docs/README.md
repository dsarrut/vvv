# VVV Documentation Hub

Welcome to the **VVV** documentation. This directory contains architectural specifications, plugin references, and step-by-step developer guides.

---

## 1. Core Architecture & Engine

Fundamental architectural specifications governing state management, rendering, and coordinate systems:

* **[core_overview.md](core_overview.md)**: High-level system architecture, MVC model, threading model, and coordinate spaces (Voxel, Physical, Pixel).
* **[core_image_types.md](core_image_types.md)**: Image type capabilities and behavior matrix across 2D, 3D, 4D, DVF, and RGB images.
* **[core_image_list.md](core_image_list.md)**: Core Image List tool, viewport assignment matrix, volume renaming, and lifecycle management.
* **[core_rendering.md](core_rendering.md)**: Slice blending, Window/Level mapping, Numba JIT acceleration, NN/Bilinear modes, and caching.
* **[core_sync.md](core_sync.md)**: Multi-viewer synchronization engine (PPM physical scale, crosshairs, radiometrics, 4D timepoints).
* **[core_units.md](core_units.md)**: Physical voxel intensity units (HU, SUV, SUL, Bq/mL, Gy), sidecar JSON persistence, clinical presets, and publication colorbars.
* **[core_viewstate_property.md](core_viewstate_property.md)**: How to add new reactive properties to `ViewState` (dirty flags, serialization, sync).
* **[core_contours.md](core_contours.md)**: Architecture of the dual contour extraction pipelines (Threshold live preview and ROI outlines).

---

## 2. Plugins & Modular Tools

VVV uses an extensible plugin system located in `src/vvv/plugins/`:

### Plugin Infrastructure
* **[plugin_architecture.md](plugin_architecture.md)**: Plugin contract, discovery mechanisms, lifecycle hooks, and `PluginAPI` reference.
* **[plugin_checklist.md](plugin_checklist.md)**: Checklist for implementing, reviewing, and verifying new plugins.
* **[plugin_api_method.md](plugin_api_method.md)**: How to safely expose new methods on `PluginAPI`.

### Feature Plugins
* **[plugin_intensity.md](plugin_intensity.md)**: Window/Level presets, dynamic slider speeds, asynchronous histograms, and colorscales.
* **[plugin_landmark.md](plugin_landmark.md)**: 3D physical point landmarks, voxel snapping, CSV import/export, and spatial navigation.
* **[plugin_mip.md](plugin_mip.md)**: Maximum Intensity Projection, interactive rotation, slab thickness, and Numba acceleration.
* **[plugin_threshold.md](plugin_threshold.md)**: Interactive thresholding, live contour previews, and binary mask creation.
* **[plugin_roi.md](plugin_roi.md)**: Region-of-Interest (ROI) mask overlays, contours, colors, and visibility toggles.
* **[plugin_registration.md](plugin_registration.md)**: 6-DOF manual rigid registration, real-time 2D preview, and 3D volume resampling.
* **[plugin_profile.md](plugin_profile.md)**: Interactive line profile drawing, physical length measurement, voxel sampling, and 1D plots.
* **[plugin_dvf.md](plugin_dvf.md)**: Displacement Vector Field visualization (arrow grids, component maps, and RGB color direction).
* **[plugin_dicom.md](plugin_dicom.md)**: DICOM folder scanning, series parsing, metadata browser, and thread safety.

---

## 3. Developer How-To Recipes

Quick step-by-step recipes for extending VVV:

* **[howto_sidebar_tab.md](howto_sidebar_tab.md)**: Adding a core tab or tool panel to the left collapsible sidebar.
* **[howto_menu_item.md](howto_menu_item.md)**: Extending the main floating menu bar.
* **[howto_shortcuts.md](howto_shortcuts.md)**: Binding global keyboard and mouse shortcuts.
* **[howto_overlay_mode.md](howto_overlay_mode.md)**: Implementing custom fusion blending algorithms (e.g. Difference, Alpha).
* **[howto_programmatic_screenshots.md](howto_programmatic_screenshots.md)**: Generating headless or programmatic screenshots from workspaces.

