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
    if sys.platform != 'darwin':
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
            NSApplication, NSImage, NSApplicationActivationPolicyRegular,
            NSMenu, NSMenuItem
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
@click.argument('image_paths', type=click.Path(exists=True), required=False, nargs=-1)
@click.option('--link_all', "-l", is_flag=True, help='Enable sync all images')
@click.option('--sync', "-s", is_flag=True, help='Enable sync all images')
def main(image_paths, link_all, sync):
    # Resolve icon paths using the new resource helper
    icon_png = get_resource_path(os.path.join("icons", "icon.png"))
    icon_ico = get_resource_path(os.path.join("icons", "icon.ico"))

    # for the app icon
    set_macos_dock_info("VVV", icon_path=icon_png)

    dpg.create_context()
    controller = Controller()

    for tag in ["V1", "V2", "V3", "V4"]:
        controller.viewers[tag] = SliceViewer(tag, controller)

    gui = MainGUI(controller)
    controller.gui = gui
    dpg.create_viewport(title='VVV', width=1000, height=800)

    # Window Icons (using absolute paths)
    if sys.platform == "win32":
        dpg.set_viewport_small_icon(icon_ico)
        dpg.set_viewport_large_icon(icon_ico)
    else:
        dpg.set_viewport_small_icon(icon_png)
        dpg.set_viewport_large_icon(icon_png)

    # Start the app, passing the boot sequence generator from GUI
    gui.run(boot_generator=gui.create_boot_sequence(image_paths, sync, link_all))


if __name__ == "__main__":
    main()
