#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import click
import dearpygui.dearpygui as dpg
from .gui import MainGUI
from .core import Controller
from .viewer import SliceViewer
import sys
import os
import re
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


@click.command()
@click.argument("datasets", nargs=-1)
@click.option("--linkall", "-l", is_flag=True, help="Enable sync all images")
@click.option("--sync", "-s", is_flag=True, help="Enable sync all images")
def main(datasets, linkall, sync):

    # 1. Smart Re-grouping: Handle spaces after commas AND colons from the shell
    grouped_datasets = []
    buf = []
    for item in datasets:
        buf.append(item)
        # If the argument is trailing a comma OR a colon, keep buffering!
        if not (item.endswith(",") or item.endswith(":")):
            grouped_datasets.append(" ".join(buf))
            buf = []
    if buf:  # Catch any trailing fragments
        grouped_datasets.append(" ".join(buf))

    # 2. Parse the composite strings
    image_tasks = []
    for ds in grouped_datasets:
        # Split by comma and clean up whitespace
        parts = [p.strip() for p in ds.split(",")]
        base_part = parts[0]
        sync_group = 0

        # --- Extract Sync Group Prefix allowing spaces (e.g. "1: path/to/image.nii") ---
        # \s* safely absorbs any spaces between the colon and the file path
        match = re.match(r"^(\d+):\s*(.*)$", base_part)
        if match:
            sync_group = int(match.group(1))
            base_part = match.group(2)
        # -------------------------------------------------------------------------------

        task = {
            "base": base_part,
            "fusion": None,
            "sync_group": sync_group,
            "base_cmap": None,
        }

        if len(parts) > 1:
            overlay_path = parts[1].strip()
            cmap = parts[2].strip() if len(parts) > 2 else "Jet"
            mode = "Alpha"

            # Normalize known colormaps case-insensitively
            known_cmaps = {
                "grayscale": "Grayscale",
                "hot": "Hot",
                "cold": "Cold",
                "jet": "Jet",
                "dosimetry": "Dosimetry",
                "segmentation": "Segmentation",
            }

            # Handle the "Reg" shorthand
            if cmap.lower() in ["reg", "registration"]:
                cmap = "Grayscale"
                mode = "Registration"

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

        image_tasks.append(task)

    # --- Setup Application ---
    icon_png = get_resource_path(os.path.join("icons", "py_vv.png"))
    icon_ico = get_resource_path(os.path.join("icons", "icon.ico"))
    set_macos_dock_info("VVV", icon_path=icon_png)

    dpg.create_context()
    controller = Controller()

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

    # Boot
    gui.run(boot_generator=gui.create_boot_sequence(image_tasks, sync, linkall))


if __name__ == "__main__":
    main()
