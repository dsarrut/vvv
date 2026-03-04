#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import click
import os
import dearpygui.dearpygui as dpg
from .gui import MainGUI
from .core import Controller
from .viewer import SliceViewer


@click.command()
@click.argument('image_paths', type=click.Path(exists=True), required=False, nargs=-1)
@click.option('--link_all', is_flag=True, help='Enable sync all images')
@click.option('--sync', is_flag=True, help='Enable sync all images')
def main(image_paths, link_all, sync):
    dpg.create_context()
    controller = Controller()

    for tag in ["V1", "V2", "V3", "V4"]:
        controller.viewers[tag] = SliceViewer(tag, controller)

    gui = MainGUI(controller)
    controller.gui = gui
    dpg.create_viewport(title='VVV', width=1000, height=800)

    # Start the app, passing the boot sequence generator from GUI
    gui.run(boot_generator=gui.create_boot_sequence(image_paths, sync, link_all))


if __name__ == "__main__":
    main()
