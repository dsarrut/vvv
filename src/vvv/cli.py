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

    # Convert to a generator that yields control back to the UI
    def boot_sequence():
        if not image_paths:
            return

        total = len(image_paths)

        # 1. Build the Loading Modal
        with dpg.window(tag="loading_modal", modal=True, show=True, no_title_bar=True,
                        no_resize=True, no_move=True, width=350, height=100):
            dpg.add_text("Initializing...", tag="loading_text")
            dpg.add_spacer(height=5)
            dpg.add_progress_bar(tag="loading_progress", width=-1, default_value=0.0)

        # Center the modal on the screen
        vp_width = dpg.get_viewport_client_width()
        vp_height = dpg.get_viewport_client_height()
        dpg.set_item_pos("loading_modal", [vp_width // 2 - 175, vp_height // 2 - 50])

        yield  # Let DPG draw the empty modal

        # 2. Load the images one by one
        img_ids = []
        for i, path in enumerate(image_paths):
            filename = os.path.basename(path)

            # Update UI state
            dpg.set_value("loading_text", f"Loading image {i + 1}/{total}...\n{filename}")
            dpg.set_value("loading_progress", i / total)

            yield  # Let DPG render the new text and progress bar BEFORE reading the file

            # Do the heavy lifting
            img_id = controller.load_image(path)
            img_ids.append(img_id)

            # Viewport assignment
            if i == 0:
                for tag in ["V1", "V2", "V3", "V4"]:
                    controller.viewers[tag].set_image(img_id)
            elif i == 1:
                controller.viewers["V3"].set_image(img_id)
                controller.viewers["V4"].set_image(img_id)
            elif i == 2:
                controller.viewers["V2"].set_image(img_ids[1])
                controller.viewers["V3"].set_image(img_id)
                controller.viewers["V4"].set_image(img_id)
            elif i >= 3:
                controller.viewers["V4"].set_image(img_id)

        # 3. Finalize and Sync
        dpg.set_value("loading_text", "Applying synchronization and layouts...")
        dpg.set_value("loading_progress", 1.0)
        yield  # Render the 100% completion state

        controller.default_viewers_orientation()

        # Unify the absolute scale across different orientations of the SAME image
        for img_id in img_ids:
            # Find all viewers showing this specific image
            same_image_viewers = [v.tag for v in controller.viewers.values() if v.image_id == img_id]
            if same_image_viewers:
                controller.unify_ppm(same_image_viewers)

        if sync or link_all:
            for img_id in img_ids:
                controller.on_sync_group_change(None, "Group 1", img_id)
            gui.refresh_sync_ui()

        gui.on_window_resize()
        controller.gui.refresh_image_list_ui()

        # 4. Clean up
        dpg.delete_item("loading_modal")
        yield  # Let DPG remove the modal before entering the main loop

    # Start the app, passing the generator
    gui.run(boot_generator=boot_sequence())


if __name__ == "__main__":
    main()
