import click
import dearpygui.dearpygui as dpg
from .gui import MainGUI
from .core import Controller
from .window import MainWindow
from .viewer import SliceViewer


@click.command()
@click.argument('image_paths', type=click.Path(exists=True), required=False, nargs=-1)
@click.option('--link_all', is_flag=True, help='Enable sync all images')
@click.option('--sync', is_flag=True, help='Enable sync all images')
def main(image_paths, link_all, sync):

    # Initialize DPG context first
    dpg.create_context()

    # Initialize Controller and related objects
    controller = Controller()

    # Initialize the main window manager
    w = MainWindow(controller)
    controller.main_windows = w

    # Initialize the 4 viewers
    for tag in ["V1", "V2", "V3", "V4"]:
        controller.viewers[tag] = SliceViewer(tag, controller)

    # Initialize GUI structure
    gui = MainGUI(controller)
    dpg.create_viewport(title='VVV', width=1000, height=800)

    # Load images (if provided)
    img_ids = []
    for i, path in enumerate(image_paths):
        img_id = controller.load_image(path)
        img_ids.append(img_id)

        # Initial image assignment logic
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

    # Set default orientations
    controller.default_viewers_orientation()

    # Initial UI updates
    w.on_window_resize()
    controller.refresh_image_list_ui()

    # Sync ?
    if sync or link_all:
        for img in controller.images.values():
            img.sync_group = 1

    # Start the application
    gui.run()


if __name__ == "__main__":
    main()
