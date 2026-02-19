import SimpleITK as sitk
import numpy as np
import os


class ImageModel:
    """Store the image data and its properties."""

    def __init__(self, path):
        self.path = path
        self.name = os.path.basename(path)
        self.sitk_image = sitk.ReadImage(path)
        self.data = sitk.GetArrayFromImage(self.sitk_image)
        self.spacing = self.sitk_image.GetSpacing()
        self.origin = self.sitk_image.GetOrigin()

        # Shared Window/Level for this image
        self.ww = 400
        self.wl = 40

    def get_slice_rgba(self, slice_idx):
        """Extracts a slice and applies window/leveling, returning RGBA float32."""
        # Clamp slice_idx to valid range
        slice_idx = np.clip(slice_idx, 0, self.data.shape[0] - 1)
        slice_data = self.data[slice_idx, :, :].astype(np.float32)

        # Apply Window/Level
        min_val = self.wl - self.ww / 2
        display_img = np.clip((slice_data - min_val) / self.ww, 0, 1)

        # Convert to RGBA (DPG requirement)
        rgba = np.stack([display_img] * 3 + [np.ones_like(display_img)], axis=-1)
        return rgba.flatten()


class Controller:
    """The central manager."""

    def __init__(self):
        self.main_windows = None
        self.images = {}  # { "id": ImageModel }
        self.viewers = {}  # { "id": SliceViewer } access by tag (V1, V2, etc)
        self.selected_viewer_idx = 0
        self.link_group = set()

    def load_image(self, path):
        img_id = str(len(self.images))
        self.images[img_id] = ImageModel(path)
        return img_id

    def update_all_viewers_of_image(self, img_id):
        """Refresh every viewer currently displaying this specific image."""
        for viewer in self.viewers.values():
            if viewer.current_image_id == img_id:
                viewer.update_render()