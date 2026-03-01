import SimpleITK as sitk
import numpy as np
import os
from pathlib import Path
import copy
import json
from vvv.utils import ViewMode


class ImageModel:
    """Store the image data and its properties."""

    def __init__(self, path):
        self.path = path
        self.name = os.path.basename(path)
        # read the image
        self.sitk_image = sitk.ReadImage(path)
        # raw pixel data : no copy between sitk and numpy
        self.data = sitk.GetArrayViewFromImage(self.sitk_image).astype(np.float32)
        # get some metadata
        self.pixel_type = None
        self.bytes_per_component = None
        self.num_components = None
        self.matrix = None
        self.spacing = None
        self.origin = None
        self.memory_mb = None
        self.read_image_metadata()

        """
        The dirty flag: if True the image, should be rendered
        Scope = Global
        The actual pixel values in the volume or the lookup table (Window/Level) changed.
        Ex: changing Brightness/Contrast, reloading the file, or applying a filter.
        """
        self.is_data_dirty = True

        # --- below is information shared among the viewers ---

        # Window/Level for this image
        self.ww = 2000
        self.wl = 270
        # Zoom level
        self.zoom = 1.0
        # Interpolation mode
        self.interpolation_linear = False
        # Current slices for all orientation (init to center)
        self.slices = {
            ViewMode.AXIAL: self.data.shape[0] // 2,
            ViewMode.SAGITTAL: self.data.shape[1] // 2,
            ViewMode.CORONAL: self.data.shape[2] // 2
        }
        # Current voxel information under the crosshair
        self.crosshair_phys_coord = None
        self.crosshair_voxel = None
        self.crosshair_value = None
        self.init_crosshair_to_slices()
        # Current pan for all orientation
        self.pan = {
            ViewMode.AXIAL: [0, 0],
            ViewMode.SAGITTAL: [0, 0],
            ViewMode.CORONAL: [0, 0]
        }
        # options
        self.grid_mode = False
        self.show_axis = True
        self.show_overlay = True
        self.show_crosshair = True
        # histogram
        self.hist_data_x = []
        self.hist_data_y = []
        self.bin_width = 10.0
        self.use_log_y = False
        self.update_histogram()
        # synchro
        self.sync_group = 0

    def read_image_metadata(self):
        self.pixel_type = self.sitk_image.GetPixelIDTypeAsString()
        self.bytes_per_component = self.sitk_image.GetSizeOfPixelComponent()
        self.num_components = self.sitk_image.GetNumberOfComponentsPerPixel()
        self.matrix = self.sitk_image.GetDirection()
        self.spacing = np.array(self.sitk_image.GetSpacing())
        self.origin = np.array(self.sitk_image.GetOrigin())
        bytes_per_pixel = self.bytes_per_component * self.num_components
        self.memory_mb = self.sitk_image.GetNumberOfPixels() * bytes_per_pixel / (1024 * 1024)

    def update_histogram(self):
        """Computes histogram for the entire 3D volume."""
        flat_data = self.data.flatten()
        # Filter out extreme values if necessary to keep the plot readable
        min_v, max_v = np.min(flat_data), np.max(flat_data)
        bins = np.arange(min_v, max_v + self.bin_width, self.bin_width)

        hist, bin_edges = np.histogram(flat_data, bins=bins)
        self.hist_data_y = hist.astype(np.float32)
        self.hist_data_x = bin_edges[:-1].astype(np.float32)

    def init_crosshair_to_slices(self):
        self.crosshair_voxel = [self.slices[ViewMode.CORONAL], self.slices[ViewMode.SAGITTAL],
                                self.slices[ViewMode.AXIAL]]
        self.crosshair_phys_coord = self.voxel_coord_to_physic_coord(self.crosshair_voxel)
        ix, iy, iz = self.crosshair_voxel
        self.crosshair_value = self.data[iz, iy, ix]

    def reset_view(self):
        """Resets zoom, pan, and crosshair to the center of the volume."""
        self.zoom = 1.0
        self.pan = {
            ViewMode.AXIAL: [0, 0],
            ViewMode.SAGITTAL: [0, 0],
            ViewMode.CORONAL: [0, 0]
        }
        self.slices = {
            ViewMode.AXIAL: self.data.shape[0] // 2,
            ViewMode.SAGITTAL: self.data.shape[1] // 2,
            ViewMode.CORONAL: self.data.shape[2] // 2
        }
        self.init_crosshair_to_slices()
        self.needs_render = True

    def get_slice_rgba(self, slice_idx, orientation=ViewMode.AXIAL):

        # 1. Determine the maximum index for the current orientation
        if orientation == ViewMode.AXIAL:
            max_s, h, w = self.data.shape[0], self.data.shape[1], self.data.shape[2]
        elif orientation == ViewMode.SAGITTAL:
            max_s, h, w = self.data.shape[2], self.data.shape[0], self.data.shape[1]
        elif orientation == ViewMode.CORONAL:
            max_s, h, w = self.data.shape[1], self.data.shape[0], self.data.shape[2]
        else:
            print(f"ERROR : orientation is not supported {orientation}")
            exit(0)

        # 2. Check if the slice is out of bounds
        if slice_idx < 0 or slice_idx >= max_s:
            # Return a black slice of the correct shape
            black_slice = np.zeros((h, w, 4), dtype=np.float32)
            black_slice[:, :, 3] = 1.0  # Opaque alpha
            return black_slice.flatten(), (h, w)

        """Extracts a slice with corrected orientations for vv parity."""
        idx = slice_idx
        if orientation == ViewMode.AXIAL:
            slice_data = self.data[idx, :, :]

        elif orientation == ViewMode.SAGITTAL:
            # Slice along X
            # Flip vertically (np.flipud) and horizontally (np.fliplr) for vv alignment
            slice_data = np.flipud(np.fliplr(self.data[:, :, idx]))

        else:
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

        if orientation == ViewMode.AXIAL:
            # X and Y axes
            return dx, dy
        elif orientation == ViewMode.SAGITTAL:
            # Y and Z axes
            return dy, dz
        else:
            # X and Z axes
            return dx, dz

    def voxel_coord_to_physic_coord(self, voxel):
        phys = (voxel * self.spacing) + self.origin - self.spacing / 2
        return phys

    def reload(self):
        """Re-reads data from the disk while preserving state if dimensions match."""
        # Read the new image from the existing path
        new_sitk = sitk.ReadImage(self.path)
        new_shape = new_sitk.GetSize()
        current_shape = self.sitk_image.GetSize()

        if new_shape == current_shape:
            # DIMENSIONS MATCH: Soft update
            self.sitk_image = new_sitk
            # Update the view (no copy)
            self.data = sitk.GetArrayViewFromImage(self.sitk_image).astype(np.float32)
            self.read_image_metadata()
            return False  # Indicates a soft reload
        else:
            # DIMENSIONS CHANGED: Full reset
            self.__init__(self.path)
            return True  # Indicates a full reset occurred

    def update_crosshair_from_2d(self, slice_x, slice_y, slice_idx, orientation):
        """Maps 2D slice coordinates back to 3D Voxel Indices and updates state."""
        _, shape = self.get_slice_rgba(slice_idx, orientation)
        real_h, real_w = shape[0], shape[1]

        if orientation == ViewMode.AXIAL:
            v = [slice_x, slice_y, slice_idx]
        elif orientation == ViewMode.SAGITTAL:
            v = [slice_idx, real_w - slice_x, real_h - slice_y]
        else:
            v = [slice_x, slice_idx, real_h - slice_y]

        self.crosshair_voxel = v
        self.crosshair_phys_coord = self.voxel_coord_to_physic_coord(np.array(v))

        ix, iy, iz = [int(np.clip(c, 0, limit - 1)) for c, limit in
                      zip(v, [self.data.shape[2], self.data.shape[1], self.data.shape[0]])]
        self.crosshair_value = self.data[iz, iy, ix]

    def update_crosshair_from_slice_scroll(self, new_slice_idx, orientation):
        """Updates the 3D crosshair depth when scrolling through slices."""
        vx, vy, vz = self.crosshair_voxel

        # Update only the coordinate corresponding to the current orientation
        if orientation == ViewMode.AXIAL:
            vz = new_slice_idx
        elif orientation == ViewMode.SAGITTAL:
            vx = new_slice_idx
        elif orientation == ViewMode.CORONAL:
            vy = new_slice_idx

        new_v = [vx, vy, vz]
        self.crosshair_voxel = new_v
        self.crosshair_phys_coord = self.voxel_coord_to_physic_coord(np.array(new_v))

        ix, iy, iz = [int(np.clip(c, 0, limit - 1)) for c, limit in
                      zip(new_v, [self.data.shape[2], self.data.shape[1], self.data.shape[0]])]
        self.crosshair_value = self.data[iz, iy, ix]


class Controller:
    """The central manager."""

    def __init__(self):
        self.gui = None
        self.images = {}  # { "id": ImageModel }
        self.viewers = {}  # { "id": SliceViewer } access by tag (V1, V2, etc)
        self.settings = SettingsManager()

    def default_viewers_orientation(self):
        n = len(self.images)
        if n == 1:
            self.viewers["V1"].set_orientation(ViewMode.AXIAL)
            self.viewers["V2"].set_orientation(ViewMode.SAGITTAL)
            self.viewers["V3"].set_orientation(ViewMode.CORONAL)
            self.viewers["V4"].set_orientation(ViewMode.AXIAL)
        elif n == 2:
            self.viewers["V1"].set_orientation(ViewMode.AXIAL)
            self.viewers["V2"].set_orientation(ViewMode.SAGITTAL)
            self.viewers["V3"].set_orientation(ViewMode.AXIAL)
            self.viewers["V4"].set_orientation(ViewMode.SAGITTAL)
        elif n == 3:
            self.viewers["V1"].set_orientation(ViewMode.AXIAL)
            self.viewers["V2"].set_orientation(ViewMode.AXIAL)
            self.viewers["V3"].set_orientation(ViewMode.AXIAL)
            self.viewers["V4"].set_orientation(ViewMode.SAGITTAL)
        elif n >= 4:
            self.viewers["V1"].set_orientation(ViewMode.AXIAL)
            self.viewers["V2"].set_orientation(ViewMode.AXIAL)
            self.viewers["V3"].set_orientation(ViewMode.AXIAL)
            self.viewers["V4"].set_orientation(ViewMode.AXIAL)

    def load_image(self, path):
        img_id = str(len(self.images))
        self.images[img_id] = ImageModel(path)
        self.gui.refresh_image_list_ui()
        return img_id

    def update_all_viewers_of_image(self, img_id):
        """Refresh every viewer currently displaying this specific image."""
        for viewer in self.viewers.values():
            if viewer.image_id == img_id:
                viewer.draw_crosshair()
                viewer.update_render()

    def update_setting(self, keys, value):
        if not keys or keys[-1] is None:
            print(f"DEBUG: Blocked update with keys {keys}")
            return

        # Update internal dict
        d = self.settings.data
        for key in keys[:-1]:
            d = d[key]

        # Handle the color conversion (0.0-1.0 float to 0-255 int)
        if keys[0] == "colors" and isinstance(value, (list, tuple)):
            # Check if the first element is a float to determine scaling
            if any(isinstance(x, float) for x in value):
                value = [int(x * 255) for x in value]
            else:
                value = [int(x) for x in value]

        d[keys[-1]] = value

        # Refresh visuals
        for viewer in self.viewers.values():
            viewer.update_render()
            if viewer.image_id:
                viewer.draw_crosshair()

    def reset_settings(self):
        self.settings.reset()
        # Refresh viewers to apply the default colors immediately
        for viewer in self.viewers.values():
            viewer.update_render()

    def save_settings(self):
        return self.settings.save()

    def reload_image(self, img_id):
        """Re-reads the image file from the original path."""
        if img_id in self.images:
            img_model = self.images[img_id]
            was_reset = img_model.reload()
            if was_reset:
                # If size changed, we must re-init textures and slice indices in viewers
                for viewer in self.viewers.values():
                    if viewer.image_id == img_id:
                        viewer.set_image(img_id)
            else:
                self.update_all_viewers_of_image(img_id)
            # Update the sidebar in case this was the active image
            if self.gui.context_viewer and self.gui.context_viewer.image_id == img_id:
                self.gui.context_viewer.update_sidebar_info()

    def close_image(self, img_id):
        """Removes the image from the controller and clears associated viewers."""
        if img_id in self.images:
            # Tell the viewers to clean up their own DPG items
            for viewer in self.viewers.values():
                if viewer.image_id == img_id:
                    viewer.drop_image()

            # Delete the image from the data dictionary
            del self.images[img_id]

            # If there are other images, fill the empty viewers with the first one
            if self.images:
                first_img_id = next(iter(self.images))
                for viewer in self.viewers.values():
                    if viewer.image_id is None:
                        viewer.set_image(first_img_id)

            # Refresh the UI list
            if self.gui:
                self.gui.refresh_image_list_ui()

    def on_visibility_toggle(self, sender, value, user_data):
        context_viewer = self.gui.context_viewer
        if not context_viewer or not context_viewer.image_model:
            return

        model = context_viewer.image_model
        if user_data == "axis":
            model.show_axis = value
        elif user_data == "grid":
            model.grid_mode = value
        elif user_data == "overlay":
            model.show_overlay = value
        elif user_data == "crosshair":
            model.show_crosshair = value

        # Refresh all viewers displaying this image
        self.update_all_viewers_of_image(context_viewer.image_id)

    def on_sync_group_change(self, sender, value, user_data):
        img_id = user_data
        img = self.images[img_id]

        # Parse the group ID from "Group X" or "None"
        if value == "None":
            img.sync_group = 0
            return

        new_group_id = int(value.split(" ")[1])
        img.sync_group = new_group_id

        # Immediate Alignment:
        # Find the first other image in this group and copy its state
        master_image = None
        for other_id, other_img in self.images.items():
            if other_id != img_id and other_img.sync_group == new_group_id:
                master_image = other_img
                break

        if master_image:
            img.zoom = master_image.zoom

            # Center the newly joined image based on the master viewer's physical center
            master_viewer = next((v for v in self.viewers.values() if v.image_id == master_image.image_id), None)
            if master_viewer:
                phys_center = master_viewer.get_center_physical_coord()
                for v in self.viewers.values():
                    if v.image_id == img_id:
                        v.center_on_physical_coord(phys_center)

            # Update all viewers to reflect the alignment
            self.update_all_viewers_of_image(img_id)

    def propagate_sync(self, source_img_id):
        source_img = self.images[source_img_id]
        if source_img.sync_group == 0:
            # Even if not in a group, we might need to update
            # other orientations of the SAME image
            target_ids = [source_img_id]
        else:
            # Sync with everyone in the group
            target_ids = [tid for tid, img in self.images.items()
                          if img.sync_group == source_img.sync_group]

        phys_pos = source_img.crosshair_phys_coord
        #shared_zoom = source_img.zoom

        for target_id in target_ids:
            target_img = self.images[target_id]

            # Update Physical & Voxel State
            target_vox = (phys_pos - target_img.origin + target_img.spacing / 2) / target_img.spacing
            target_img.crosshair_voxel = list(target_vox)
            target_img.crosshair_phys_coord = phys_pos

            # Update Slice Indices
            target_img.slices[ViewMode.AXIAL] = int(target_vox[2])
            target_img.slices[ViewMode.SAGITTAL] = int(target_vox[0])
            target_img.slices[ViewMode.CORONAL] = int(target_vox[1])

            # Sync View State (Zoom)
            #target_img.zoom = shared_zoom
            target_img.is_data_dirty = True

        # Trigger Viewers Refresh
        # We loop through viewers to find those looking at any of our target images
        for viewer in self.viewers.values():
            if viewer.image_id in target_ids:
                viewer.is_geometry_dirty = True

    def propagate_camera(self, source_viewer):
        """Syncs the zoom and physical center of the source viewer to all synced viewers."""
        if not source_viewer.image_model: return
        source_img = source_viewer.image_model

        # Determine which images should be affected
        if source_img.sync_group == 0:
            target_ids = [source_viewer.image_id]
        else:
            target_ids = [tid for tid, img in self.images.items()
                          if img.sync_group == source_img.sync_group]

        # Grab the exact physical point the driver viewer is looking at
        phys_center = source_viewer.get_center_physical_coord()
        if phys_center is None: return

        shared_zoom = source_viewer.zoom

        # Apply to all relevant viewers
        for viewer in self.viewers.values():
            if viewer.image_id in target_ids and viewer != source_viewer:
                target_img = viewer.image_model
                target_img.zoom = shared_zoom
                viewer.center_on_physical_coord(phys_center)

DEFAULT_SETTINGS = {
    "colors": {
        "crosshair": [0, 246, 7, 180],
        "overlay_text": [0, 246, 7, 255],
        "x": [255, 80, 80, 230],
        "y": [80, 255, 80, 230],
        "z": [80, 80, 255, 230],
        "grid": [255, 255, 255, 40]
    },
    "physics": {
        "search_radius": 25,
        "voxel_strip_threshold": 1500
    }
}


class SettingsManager:
    def __init__(self):
        # Platform-specific path
        if os.name == 'nt':
            self.config_dir = Path(os.getenv('APPDATA')) / "VVV"
        else:
            self.config_dir = Path.home() / ".config" / "vvv"

        self.config_path = self.config_dir / ".vv_settings"
        self.data = copy.deepcopy(DEFAULT_SETTINGS)
        self.load()

    def load(self):
        if self.config_path.exists():
            try:
                with open(self.config_path, "r") as f:
                    self.data.update(json.load(f))
            except Exception as e:
                print(f"Error loading settings: {e}")

    def reset(self):
        """Restores the data dictionary to default values."""
        self.data = copy.deepcopy(DEFAULT_SETTINGS)

    def save(self):
        self.config_dir.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, "w") as f:
            json.dump(self.data, f, indent=4)
        return str(self.config_path)  # Return the path for the UI hint
