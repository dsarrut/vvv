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
        self.ww = 2000
        self.wl = 270

    def get_slice_rgba(self, slice_idx, orientation="Axial"):
        """Extracts a slice with corrected orientations for vv parity."""
        if orientation == "Axial":
            max_s = self.data.shape[0] - 1
            idx = np.clip(slice_idx, 0, max_s)
            slice_data = self.data[idx, :, :]

        elif orientation == "Sagittal":
            max_s = self.data.shape[2] - 1
            idx = np.clip(slice_idx, 0, max_s)
            # Slice along X
            # Flip vertically (np.flipud) and horizontally (np.fliplr) for vv alignment
            slice_data = np.flipud(np.fliplr(self.data[:, :, idx]))

        elif orientation == "Coronal":
            max_s = self.data.shape[1] - 1
            idx = np.clip(slice_idx, 0, max_s)
            # Slice along Y, Flip vertically
            slice_data = np.flipud(self.data[:, idx, :])

        slice_data = slice_data.astype(np.float32)
        min_val = self.wl - self.ww / 2
        display_img = np.clip((slice_data - min_val) / self.ww, 0, 1)

        rgba = np.stack([display_img] * 3 + [np.ones_like(display_img)], axis=-1)
        return rgba.flatten(), slice_data.shape

    def get_physical_aspect_ratio(self, orientation):
        """Calculates (width_scale, height_scale) based on mm spacing."""
        # spacing is (dx, dy, dz)
        dx, dy, dz = self.spacing

        if orientation == "Axial":
            # X and Y axes
            return dx, dy
        elif orientation == "Sagittal":
            # Y and Z axes
            return dy, dz
        else:
            # X and Z axes
            return dx, dz

    def voxel_to_physic_coord(self, voxel):
        phys = (voxel * self.spacing) + self.origin
        return phys


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
