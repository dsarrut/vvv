import click
from .gui import *
from .core import *


@click.command()
@click.argument('image_path', type=click.Path(exists=True), required=False, nargs=-1)
def main(image_path):

    dpg.create_context()

    # Initialize main (non gui) controller
    controller = Controller()

    # initialize the main windows
    w = MainWindow(controller)
    controller.main_windows = w

    # Initialize the 4 viewers
    for tag in ["V1", "V2", "V3", "V4"]:
        controller.viewers[tag] = SliceViewer(tag, controller)

    # Load images if provided
    i=0
    img_ids = []
    for path in image_path:
        img_id = controller.load_image(path)
        img_ids.append(img_id)
        print(f"Loading image {img_id}...")
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

    # Initializing GUI
    create_gui(controller)

    # default orientations
    if len(image_path) == 1:
        controller.viewers["V1"].set_orientation("Axial")
        controller.viewers["V2"].set_orientation("Sagittal")
        controller.viewers["V3"].set_orientation("Coronal")
        controller.viewers["V4"].set_orientation("Axial")
    elif len(image_path) == 2:
        controller.viewers["V1"].set_orientation("Axial")
        controller.viewers["V2"].set_orientation("Sagittal")
        controller.viewers["V3"].set_orientation("Axial")
        controller.viewers["V4"].set_orientation("Sagittal")
    elif len(image_path) == 3:
        controller.viewers["V1"].set_orientation("Axial")
        controller.viewers["V2"].set_orientation("Axial")
        controller.viewers["V3"].set_orientation("Axial")
        controller.viewers["V4"].set_orientation("Sagittal")
    elif len(image_path) >= 4:
        controller.viewers["V1"].set_orientation("Axial")
        controller.viewers["V2"].set_orientation("Axial")
        controller.viewers["V3"].set_orientation("Axial")
        controller.viewers["V4"].set_orientation("Axial")

    # display the GUI
    dpg.create_viewport(title=f'VVV', width=900, height=700)
    dpg.setup_dearpygui()
    dpg.show_viewport()
    dpg.set_primary_window("PrimaryWindow", True)

    # Trigger an initial resize to ensure aspect ratio and layout are correct
    w.on_window_resize()

    # --- MANUAL MAIN LOOP ---
    # This is necessary for the Coordinate Overlay to update as the mouse moves
    while dpg.is_dearpygui_running():
        # Update coordinate/HU value probe
        w.update_overlays()

        # Standard DPG render call
        dpg.render_dearpygui_frame()

    dpg.destroy_context()


if __name__ == "__main__":
    main()
