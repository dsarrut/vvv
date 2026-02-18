import click
from .gui import *
from .core import *


@click.command()
@click.argument('image_path', type=click.Path(exists=True), required=False)
def main(image_path):

    print("Starting VVV...")
    dpg.create_context()
    controller = VVController()

    # Initialize viewers
    for tag in ["V1", "V2", "V3", "V4"]:
        print(f"Creating viewer {tag}...")
        controller.viewers[tag] = SliceViewer(tag, controller)

    # Load image if provided and assign to V1
    if image_path:
        img_id = controller.load_image(image_path)
        print(f"Loading image {img_id}...")
        for v in controller.viewers.values():
            v.set_image(img_id)

    print("Starting GUI...")
    create_gui(controller)


if __name__ == "__main__":
    main()
