import click
from .gui import *
from .core import *
from .window import MainWindow
from .viewer import SliceViewer

@click.command()
@click.argument('image_path', type=click.Path(exists=True), required=False, nargs=-1)
def main(image_path):

    # Initialize main (non gui) controller
    controller = Controller()

    # initialize the main windows
    dpg.create_context()
    w = MainWindow(controller)
    controller.main_windows = w

    # Initialize the 4 viewers
    for tag in ["V1", "V2", "V3", "V4"]:
        controller.viewers[tag] = SliceViewer(tag, controller)

    # Initializing GUI
    create_gui(controller)
    dpg.create_viewport(title=f'VVV', width=900, height=700)
    dpg.setup_dearpygui()
    dpg.show_viewport()
    dpg.set_primary_window("PrimaryWindow", True)

    # Load images (if provided)
    i=0
    img_ids = []
    for path in image_path:
        img_id = controller.load_image(path)
        img_ids.append(img_id)
        if i == 0:
            controller.viewers["V1"].set_image(img_id)
            controller.viewers["V2"].set_image(img_id)
            controller.viewers["V3"].set_image(img_id)
            controller.viewers["V4"].set_image(img_id)
        if i == 1:
            controller.viewers["V3"].set_image(img_id)
            controller.viewers["V4"].set_image(img_id)
        if i == 2:
            controller.viewers["V2"].set_image(img_ids[1])
            controller.viewers["V3"].set_image(img_id)
            controller.viewers["V4"].set_image(img_id)
        if i >= 3:
            controller.viewers["V4"].set_image(img_id)
        i = i+ 1

    # default orientations for the initial loaded images
    controller.default_viewers_orientation()

    # Trigger an initial resize to ensure aspect ratio and layout are correct
    w.on_window_resize()

    # --- MANUAL MAIN LOOP ---
    # This is necessary for the Coordinate Overlay to update as the mouse moves
    while dpg.is_dearpygui_running():
        # Update coordinate/pixel_value value probe
        w.update_overlays()

        # Standard DPG render call
        dpg.render_dearpygui_frame()

    # this is the end, my friend
    dpg.destroy_context()


if __name__ == "__main__":
    main()
