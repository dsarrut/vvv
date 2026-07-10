# AI Instructions for `vvv` Project

This document outlines the conventions, architectural guidelines, and specific tools used in the `vvv` project. It serves as foundational knowledge for all AI agent and assistant interactions within this workspace.

## 1. Project Overview
- **Name**: `vvv`
- **Description**: A Python-based 3D/4D image viewer inspired by VV.
- **Language**: Python (requires >= 3.9)
- **Primary Dependencies**:
  - `dearpygui`: For the graphical user interface.
  - `SimpleITK`, `numpy`, `scikit-image`: For image processing and mathematical operations.
  - `click`: For the Command Line Interface.
  - `pytest`: For the testing framework.

## 2. Code Conventions & Style
- **Python Style**: Adhere to standard PEP-8 guidelines.
  - `PascalCase` for classes.
  - `snake_case` for variables, functions, and methods.
- **Type Hinting**: Use type hinting (`typing`) where appropriate to enhance readability and safety.
- **Documentation**: Use clear docstrings for complex functions and classes.
- **Imports**: Prefer absolute imports over relative ones (e.g., `from vvv.ui.viewer import SliceViewer`).

## 3. Architecture & Structure
The `src/vvv` directory is structured as follows:
- **`core/`**: Contains core business logic, controllers, and state management (e.g., `controller.py`, `view_state.py`). Keep UI logic out of here.
- **`ui/`**: Contains `dearpygui` specific code (e.g., `gui.py`, `viewer.py`, `ui_components.py`).
- **`maths/`**: Contains all image processing, geometry, and transformation logic (e.g., `image.py`, `geometry.py`).
- **Root `src/vvv/`**: Entry points like `cli.py`, configuration, and utilities.

**Rule**: Maintain a strict separation between UI (`dearpygui`) code and Core/Math code. The UI should interact with the Core via controllers or event callbacks.

## 4. Testing
- **Framework**: `pytest`.
- **Location**: All tests are located in the `tests/` directory.
- **Convention**: Test files must be prefixed with `test_` (e.g., `test_gui.py`, `test_viewer.py`).
- **Running Tests**: Run tests using the `pytest` command. When adding a new feature or fixing a bug, ensure a corresponding test is added or updated.

## 5. Development Workflow
- When implementing a change, first understand the interplay between `ui` and `core`.
- Do not bypass type system or silence warnings without explicit permission.
- **Testing**: Run `pytest` to validate changes.
- **OS Specifics**: Be aware of macOS-specific logic (e.g., `pyobjc-framework-Cocoa` in dependencies) and handle OS differences gracefully as shown in `cli.py`.

## 6. Prohibited Actions
- Do NOT commit changes directly unless explicitly requested.
- Do NOT disable or suppress warnings globally.
- Do NOT log or hardcode sensitive information.
