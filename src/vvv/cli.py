#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import click
import dearpygui.dearpygui as dpg
import sys
import os
import re
from .gui import MainGUI
from .core import Controller
from .viewer import SliceViewer
from .resources import get_resource_path


def set_macos_dock_info(name, icon_path=None):
    """Promotes script, sets focus, icon, process name, and fixes Cmd+Q."""
    if sys.platform != "darwin":
        return

    try:
        import setproctitle

        setproctitle.setproctitle(name)
    except ImportError:
        pass

    try:
        from Cocoa import (
            NSApplication,
            NSImage,
            NSApplicationActivationPolicyRegular,
            NSMenu,
            NSMenuItem,
        )

        app = NSApplication.sharedApplication()
        app.setActivationPolicy_(NSApplicationActivationPolicyRegular)
        app.activateIgnoringOtherApps_(True)

        main_menu = NSMenu.alloc().init()
        app.setMainMenu_(main_menu)

        app_menu_item = NSMenuItem.alloc().init()
        main_menu.addItem_(app_menu_item)

        app_menu = NSMenu.alloc().init()
        app_menu_item.setSubmenu_(app_menu)

        quit_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            f"Quit {name}", "terminate:", "q"
        )
        app_menu.addItem_(quit_item)

        if icon_path and os.path.exists(icon_path):
            image = NSImage.alloc().initWithContentsOfFile_(str(icon_path))
            app.setApplicationIconImage_(image)

    except ImportError:
        pass


def parse_cli_arguments(datasets):
    """
    Parses raw command line arguments into structured image tasks.
    Handles shell-expanded 4D sequences, sync groups, and comma-separated fusion parameters.
    """
    # 1. Re-group shell-split arguments (4D sequences and comma spaces)
    grouped_datasets = []
    buf = []
    in_4d = False

    for item in datasets:
        if item.startswith("4D:") or item.startswith("4d:") or item == "4D:":
            in_4d = True

        buf.append(item)

        if in_4d:
            # Swallow expanded files until we hit a comma (overlay trigger)
            if item.endswith(","):
                grouped_datasets.append(" ".join(buf))
                buf = []
                in_4d = False
        else:
            if not (item.endswith(",") or item.endswith(":")):
                grouped_datasets.append(" ".join(buf))
                buf = []

    if buf:
        grouped_datasets.append(" ".join(buf))

    # 2. Parse the composite strings into tasks
    image_tasks = []

    # Normalize known colormaps case-insensitively
    known_cmaps = {
        "grayscale": "Grayscale",
        "hot": "Hot",
        "cold": "Cold",
        "jet": "Jet",
        "dosimetry": "Dosimetry",
        "segmentation": "Segmentation",
    }

    for ds in grouped_datasets:
        parts = [p.strip() for p in ds.split(",")]
        base_part = parts[0]
        sync_group = 0

        # Extract Sync Group (e.g. "1: file.mhd")
        match = re.match(r"^(\d+):\s*(.*)$", base_part)
        if match:
            sync_group = int(match.group(1))
            base_part = match.group(2)

        task = {
            "base": base_part,
            "fusion": None,
            "sync_group": sync_group,
            "base_cmap": None,
        }

        if len(parts) > 1:
            overlay_path = parts[1].strip()
            cmap_input = parts[2].strip() if len(parts) > 2 else "Jet"
            mode = "Alpha"

            cmap_lower = cmap_input.lower()
            if cmap_lower in ["reg", "registration"]:
                cmap = "Grayscale"
                mode = "Registration"
            else:
                cmap = known_cmaps.get(cmap_lower, cmap_input.capitalize())

            if overlay_path:
                task["fusion"] = {
                    "path": overlay_path,
                    "cmap": cmap,
                    "mode": mode,
                    "opacity": float(parts[3]) if len(parts) > 3 else 0.5,
                    "threshold": float(parts[4]) if len(parts) > 4 else 0.0,
                }
            else:
                # User left the overlay blank (e.g. "image.nii,,Jet") to apply cmap to base!
                task["base_cmap"] = cmap
                if len(parts) > 4:
                    task["base_threshold"] = float(parts[4])

        image_tasks.append(task)

    return image_tasks


@click.command()
@click.argument("datasets", nargs=-1)
@click.option("--linkall", "-l", is_flag=True, help="Enable sync all images")
@click.option("--sync", "-s", is_flag=True, help="Enable sync all images")
@click.option(
    "--no-history",
    "-nh",
    is_flag=True,
    help="Ignore saved history and load with defaults.",
)
def main(no_history, datasets, linkall, sync):
    """Entry point for the VVV command line interface."""

    # Parse the tasks cleanly
    image_tasks = parse_cli_arguments(datasets)

    # --- Setup Application ---
    icon_png = get_resource_path(os.path.join("icons", "py_vv.png"))
    icon_ico = get_resource_path(os.path.join("icons", "icon.ico"))
    set_macos_dock_info("VVV", icon_path=icon_png)

    dpg.create_context()
    controller = Controller()

    if no_history:
        controller.use_history = False

    for tag in ["V1", "V2", "V3", "V4"]:
        controller.viewers[tag] = SliceViewer(tag, controller)

    gui = MainGUI(controller)
    controller.gui = gui
    win_w = controller.settings.data["layout"]["window_width"]
    win_h = controller.settings.data["layout"]["window_height"]

    dpg.create_viewport(title="VVV", width=win_w, height=win_h)

    if sys.platform == "win32":
        dpg.set_viewport_small_icon(icon_ico)
        dpg.set_viewport_large_icon(icon_ico)
    else:
        dpg.set_viewport_small_icon(icon_png)
        dpg.set_viewport_large_icon(icon_png)

    # 1. Detect if a workspace file was passed in the arguments
    workspace_file = None
    for file_path in datasets:  # Assuming 'files' is your click argument list
        if file_path.lower().endswith(".vvw"):
            workspace_file = file_path
            break

    # 2. Swap the boot generator based on the file type
    if workspace_file:
        if len(datasets) > 1:
            print(
                f"Find workspace {workspace_file}, ignoring other files on the command line"
            )
        # Use the workspace loader
        boot_gen = gui.load_workspace_sequence(workspace_file)
    else:
        # Standard image loading sequence
        boot_gen = gui.create_boot_sequence(image_tasks, sync, linkall)

    # 3. Run the application
    gui.run(boot_generator=boot_gen)


if __name__ == "__main__":
    main()
