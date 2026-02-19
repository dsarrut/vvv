import click
from .gui import *
from .core import *


@click.command()
@click.argument('image_path', type=click.Path(exists=True), required=False)
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

    # Load image if provided
    if image_path:
        img_id = controller.load_image(image_path)
        print(f"Loading image {img_id}...")
        for v in controller.viewers.values():
            v.set_image(img_id)

    print("Initializing GUI...")
    create_gui(controller)

    # display the GUI
    dpg.create_viewport(title=f'VVV', width=900, height=700)
    dpg.setup_dearpygui()
    dpg.show_viewport()
    dpg.set_primary_window("PrimaryWindow", True)

    #dpg.start_dearpygui()

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
