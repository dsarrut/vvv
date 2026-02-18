import dearpygui.dearpygui as dpg
import numpy as np

def create_gui(controller):
    #dpg.create_context()

    # 1. Menubar
    with dpg.viewport_menu_bar():
        with dpg.menu(label="File"):
            dpg.add_menu_item(label="Open Image...")
            dpg.add_menu_item(label="Exit")
        with dpg.menu(label="Link"):
            dpg.add_menu_item(label="Link All", callback=lambda: controller.link_all())

    with dpg.window(tag="PrimaryWindow"):
        with dpg.group(horizontal=True):
            # 2. LEFT PANEL: Image List & Info
            with dpg.child_window(width=250):
                dpg.add_text("Loaded Images", color=[0, 255, 127])
                dpg.add_listbox(tag="ui_image_list", items=[], num_items=10)
                dpg.add_separator()
                dpg.add_text("Viewer Info", color=[100, 100, 255])
                dpg.add_input_text(tag="info_pixel", readonly=True, label="Value")
                dpg.add_checkbox(label="Link this viewer", tag="ui_link_check")

            # 3. RIGHT PANEL: 2x2 Grid
            with dpg.group():
                with dpg.group(horizontal=True):
                    # Top-Left, Top-Right
                    create_viewer_widget("V1", controller)
                    create_viewer_widget("V2", controller)
                with dpg.group(horizontal=True):
                    # Bottom-Left, Bottom-Right
                    create_viewer_widget("V3", controller)
                    create_viewer_widget("V4", controller)

    dpg.create_viewport(title=f'VVV', width=900, height=700)
    dpg.setup_dearpygui()
    dpg.show_viewport()
    dpg.set_primary_window("PrimaryWindow", True)

    dpg.start_dearpygui()
    dpg.destroy_context()


class SliceViewer:
    def __init__(self, tag_id, controller):
        self.tag = tag_id
        self.controller = controller
        self.current_image_id = None
        self.slice_idx = 0
        self.ww, self.wl = 400, 40
        self.texture_tag = f"tex_{tag_id}"
        self.image_tag = f"img_{tag_id}"

        # Initialize a default small texture; will be recreated on image load
        with dpg.texture_registry():
            dpg.add_dynamic_texture(width=1, height=1,
                                    default_value=np.zeros(4),
                                    tag=self.texture_tag)

    def set_image(self, img_id):
        self.current_image_id = img_id
        img = self.controller.images[img_id]
        print(f'GUI getting image {img_id}...')

        # Recreate texture with correct dimensions for the real image size
        dpg.delete_item(self.texture_tag)
        print('after delete')
        with dpg.texture_registry():
            # Get dimensions from the ImageModel data (Z, Y, X) -> X=width, Y=height
            h, w = img.data.shape[1], img.data.shape[2]
            print(f'Creating texture for image {img_id} with size {w}x{h}...')
            dpg.add_dynamic_texture(width=w, height=h,
                                    default_value=np.zeros(w * h * 4),
                                    tag=self.texture_tag)

        self.slice_idx = img.data.shape[0] // 2
        self.update_render()

    def update_render(self):
        if self.current_image_id is None:
            return

        img_model = self.controller.images[self.current_image_id]
        rgba_data = img_model.get_slice_rgba(self.slice_idx, self.ww, self.wl)

        # Update the texture data
        dpg.set_value(self.texture_tag, rgba_data)


def create_viewer_widget(tag, controller):
    """Helper to create a quadrant with fixed size."""
    # The child window remains a fixed 400x400
    with dpg.child_window(width=400, height=400, border=True, tag=f"win_{tag}"):
        dpg.add_text(f"Viewer {tag}")
        # The 'width' and 'height' here force DPG to rescale the texture to fit the window
        dpg.add_image(f"tex_{tag}", tag=f"img_{tag}", width=380, height=350)