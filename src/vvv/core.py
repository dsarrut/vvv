import SimpleITK as sitk
import numpy as np
import os


class ImageModel:
    """Store the image data and its properties."""

    def __init__(self, path):
        self.path = path
        self.name = os.path.basename(path)
        self.sitk_image = sitk.ReadImage(path)
        self.pixel_type = self.sitk_image.GetPixelIDTypeAsString()
        self.data = sitk.GetArrayFromImage(self.sitk_image).astype(np.float32)
        self.spacing = np.array(self.sitk_image.GetSpacing())
        self.origin = np.array(self.sitk_image.GetOrigin())
        # Window/Level for this image
        self.ww = 2000
        self.wl = 270
        # Zoom level
        self.zoom = 1.0
        # Interpolation mode
        self.interpolation_linear = False
        # Grid mode
        self.grid_mode = False

    def get_orientation_str(self, orientation):
        if orientation == "Axial":
            return "+X +Y (Z)"
        if orientation == "Sagittal":
            return "-Y -Z (X)"
        return "+X -Z (Y)"

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

        else:
            max_s = self.data.shape[1] - 1
            idx = np.clip(slice_idx, 0, max_s)
            # Slice along Y, Flip vertically
            slice_data = np.flipud(self.data[:, idx, :])

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
        phys = (voxel * self.spacing) + self.origin - self.spacing / 2
        return phys


class Controller:
    """The central manager."""

    def __init__(self):
        self.main_windows = None
        self.images = {}  # { "id": ImageModel }
        self.viewers = {}  # { "id": SliceViewer } access by tag (V1, V2, etc)

    def load_image(self, path):
        img_id = str(len(self.images))
        self.images[img_id] = ImageModel(path)
        return img_id


    def update_all_viewers_of_image(self, img_id):
        """Refresh every viewer currently displaying this specific image."""
        for viewer in self.viewers.values():
            if viewer.current_image_id == img_id:
                viewer.update_render()

    def default_viewers_orientation(self):
        n = len(self.images)
        if n == 1:
            self.viewers["V1"].set_orientation("Axial")
            self.viewers["V2"].set_orientation("Sagittal")
            self.viewers["V3"].set_orientation("Coronal")
            self.viewers["V4"].set_orientation("Axial")
        elif n == 2:
            self.viewers["V1"].set_orientation("Axial")
            self.viewers["V2"].set_orientation("Sagittal")
            self.viewers["V3"].set_orientation("Axial")
            self.viewers["V4"].set_orientation("Sagittal")
        elif n == 3:
            self.viewers["V1"].set_orientation("Axial")
            self.viewers["V2"].set_orientation("Axial")
            self.viewers["V3"].set_orientation("Axial")
            self.viewers["V4"].set_orientation("Sagittal")
        elif n >= 4:
            self.viewers["V1"].set_orientation("Axial")
            self.viewers["V2"].set_orientation("Axial")
            self.viewers["V3"].set_orientation("Axial")
            self.viewers["V4"].set_orientation("Axial")
