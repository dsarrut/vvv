import dearpygui.dearpygui as dpg
import SimpleITK as sitk
import numpy as np
import os


class ImageModel:
    """Store the image data and its unique properties."""

    def __init__(self, path):
        self.path = path
        print(f'Loading image: {path}...')
        self.name = os.path.basename(path)
        self.sitk_image = sitk.ReadImage(path)
        print(f'Image size: {self.sitk_image.GetSize()}')
        self.data = sitk.GetArrayFromImage(self.sitk_image)
        self.spacing = self.sitk_image.GetSpacing()
        self.origin = self.sitk_image.GetOrigin()

    def get_slice_rgba(self, slice_idx, ww, wl):
        """Extracts a slice and applies window/leveling, returning RGBA float32."""
        # Clamp slice_idx to valid range
        slice_idx = np.clip(slice_idx, 0, self.data.shape[0] - 1)
        slice_data = self.data[slice_idx, :, :].astype(np.float32)

        # Apply Window/Level
        min_val = wl - ww / 2
        display_img = np.clip((slice_data - min_val) / ww, 0, 1)

        # Convert to RGBA (DPG requirement)
        rgba = np.stack([display_img] * 3 + [np.ones_like(display_img)], axis=-1)
        return rgba.flatten()


class Controller:
    """The central manager."""

    def __init__(self):
        self.images = {}  # { "id": ImageModel }
        self.viewers = {}  # { "id": SliceViewer } access by tag (V1, V2, etc)
        self.selected_viewer_idx = 0
        self.link_group = set()

    def load_image(self, path):
        img_id = str(len(self.images))
        self.images[img_id] = ImageModel(path)
        return img_id

    def get_hovered_viewer(self):
        """Finds which quadrant the mouse is currently over."""
        for tag, viewer in self.viewers.items():
            if dpg.is_item_hovered(f"win_{tag}"):
                print(f'Hovered on {tag}')
                return viewer
        return None

    def on_global_scroll(self, delta):
        viewer = self.get_hovered_viewer()
        if viewer:
            viewer.on_scroll(delta)
            # Add linking logic here:
            # if viewer.is_linked: sync others...

    def on_global_drag(self, data):
        viewer = self.get_hovered_viewer()
        if viewer:
            viewer.on_drag(data)

    def on_global_release(self):
        for v in self.viewers.values():
            v.last_dx, v.last_dy = 0, 0

    def on_window_resize(self):
        # 1. Get current window dimensions
        window_width = dpg.get_item_width("PrimaryWindow")
        window_height = dpg.get_item_height("PrimaryWindow")

        # 2. Subtract the sidebar and margins
        side_panel_width = 250
        available_width = window_width - side_panel_width - 40
        available_height = window_height - 80

        # 3. Calculate size for each quadrant (2x2)
        quad_w = available_width // 2
        quad_h = available_height // 2

        for tag, viewer in self.viewers.items():
            if not dpg.does_item_exist(f"win_{tag}"):
                continue

            # Set the container size
            dpg.set_item_width(f"win_{tag}", quad_w)
            dpg.set_item_height(f"win_{tag}", quad_h)

            # 4. Aspect Ratio Calculation
            if viewer.current_image_id is not None:
                img = self.images[viewer.current_image_id]
                img_h, img_w = img.data.shape[1], img.data.shape[2]

                # Available space for the image (accounting for title/margins)
                target_w = quad_w - 20
                target_h = quad_h - 60

                # Determine scaling factor
                # Use the smaller ratio to ensure it fits both ways
                scale = min(target_w / img_w, target_h / img_h)

                new_w = int(img_w * scale)
                new_h = int(img_h * scale)

                if dpg.does_item_exist(f"img_{tag}"):
                    dpg.set_item_width(f"img_{tag}", new_w)
                    dpg.set_item_height(f"img_{tag}", new_h)

                    # Optional: Center the image in the quadrant
                    padding_x = (target_w - new_w) // 2
                    dpg.set_item_pos(f"img_{tag}", [padding_x + 10, 40])

    def cleanup(self):
        dpg.stop_dearpygui()