#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import click
import dearpygui.dearpygui as dpg
from .gui import MainGUI
from .core import Controller
from .viewer import SliceViewer
import sys
import os
from .resources import get_resource_path


def set_macos_dock_info(name, icon_path=None):
    """Promotes script, sets focus, icon, process name, and fixes Cmd+Q."""
    if sys.platform != "darwin":
        return

    # --- Set Process Title (Activity Monitor / Terminal) ---
    try:
        import setproctitle

        setproctitle.setproctitle(name)
    except ImportError:
        print("Warning: 'setproctitle' not installed. Run: pip install setproctitle")

    # --- macOS UI, Focus, and Menu Bar Fix ---
    try:
        from Cocoa import (
            NSApplication,
            NSImage,
            NSApplicationActivationPolicyRegular,
            NSMenu,
            NSMenuItem,
        )

        app = NSApplication.sharedApplication()

        # Promote to regular app and steal focus
        app.setActivationPolicy_(NSApplicationActivationPolicyRegular)
        app.activateIgnoringOtherApps_(True)

        # --- Fix Command+Q by creating a minimal Main Menu ---
        main_menu = NSMenu.alloc().init()
        app.setMainMenu_(main_menu)

        app_menu_item = NSMenuItem.alloc().init()
        main_menu.addItem_(app_menu_item)

        app_menu = NSMenu.alloc().init()
        app_menu_item.setSubmenu_(app_menu)

        # "terminate:" is the native macOS action for quitting. "q" binds to Cmd+Q.
        quit_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            f"Quit {name}", "terminate:", "q"
        )
        app_menu.addItem_(quit_item)
        # -----------------------------------------------------

        # Set the Dock Icon
        if icon_path and os.path.exists(icon_path):
            image = NSImage.alloc().initWithContentsOfFile_(str(icon_path))
            app.setApplicationIconImage_(image)

    except ImportError:
        print("Warning: PyObjC not installed. Run: pip install pyobjc-framework-Cocoa")


@click.command()
@click.argument("datasets", nargs=-1)
@click.option("--linkall", "-l", is_flag=True, help="Enable sync all images")
@click.option("--sync", "-s", is_flag=True, help="Enable sync all images")
def main(datasets, linkall, sync):

    # Parse the composite strings: "base[,overlay,cmap,opacity,threshold]"
    image_tasks = []
    for ds in datasets:
        parts = ds.split(",")
        task = {"base": parts[0], "fusion": None}

        if len(parts) > 1:
            task["fusion"] = {
                "path": parts[1],
                "cmap": parts[2] if len(parts) > 2 else "Jet",
                "opacity": float(parts[3]) if len(parts) > 3 else 0.5,
                "threshold": float(parts[4]) if len(parts) > 4 else 0,
            }
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
