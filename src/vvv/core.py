import SimpleITK as sitk
import numpy as np
import os
import dearpygui.dearpygui as dpg


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
        self.pixel_type = self.sitk_image.GetPixelIDTypeAsString()
        self.bytes_per_component = self.sitk_image.GetSizeOfPixelComponent()
        self.num_components = self.sitk_image.GetNumberOfComponentsPerPixel()
        self.matrix = self.sitk_image.GetDirection()
        self.spacing = np.array(self.sitk_image.GetSpacing())
        self.origin = np.array(self.sitk_image.GetOrigin())
        bytes_per_pixel = self.bytes_per_component * self.num_components
        self.memory_mb = self.sitk_image.GetNumberOfPixels() * bytes_per_pixel / (1024 * 1024)

        # --- below is information shared among the viewers ---

        # Window/Level for this image
        self.ww = 2000
        self.wl = 270
        # Zoom level
        self.zoom = 1.0
        # Interpolation mode
        self.interpolation_linear = False
        # Grid mode
        self.grid_mode = False
        # Current slices for all orientation (init to center)
        print(self.data.shape)
        self.slices = {
            "Axial": self.data.shape[0] // 2,
            "Sagittal": self.data.shape[1] // 2,
            "Coronal": self.data.shape[2] // 2
        }
        # Current voxel information under the crosshair
        self.crosshair_phys_coord = None
        self.crosshair_pixel_coord = None
        self.crosshair_pixel_value = None
        self.set_crosshair_to_slices()
        # Current pan for all orientation
        self.pan = {"Axial": [0, 0], "Sagittal": [0, 0], "Coronal": [0, 0]}

    def set_crosshair_to_slices(self):
        self.crosshair_pixel_coord = [self.slices["Coronal"], self.slices["Sagittal"], self.slices["Axial"]]
        self.crosshair_phys_coord = self.voxel_coord_to_physic_coord(self.crosshair_pixel_coord)
        ix,iy,iz = self.crosshair_pixel_coord
        #print(v)
        #ix, iy, iz = [int(np.clip(c, 0, limit - 1)) for c, limit in
        #              zip(v, [self.data.shape[2], self.data.shape[1], self.data.shape[0]])]
        #print(ix,iy,iz)
        self.crosshair_pixel_value = self.data[ix,iy,iz]
        #print(f"{self.crosshair_pixel_coord} {self.crosshair_phys_coord} {self.crosshair_pixel_value}")

    def get_orientation_str(self, orientation):
        # FIXME to remove and change
        if orientation == "Axial":
            return "+X +Y (Z)"
        if orientation == "Sagittal":
            return "-Y -Z (X)"
        return "+X -Z (Y)"

    def get_slice_rgba(self, slice_idx, orientation="Axial"):
        """if slice_idx is None:
            if orientation == "Axial":
                slice_idx = self.data.shape[0] // 2
            elif orientation == "Sagittal":
                slice_idx = self.data.shape[2] // 2
            else:
                slice_idx = self.data.shape[1] // 2"""

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

    def voxel_coord_to_physic_coord(self, voxel):
        phys = (voxel * self.spacing) + self.origin - self.spacing / 2
        return phys


class ViewStateNOPE:
    """Holds the visualization state for a specific view of an image."""

    def __init__(self, image_model):
        self.image = image_model
        # Use a dict for slices to handle all orientations independently
        self.slices = {
            "Axial": image_model.data.shape[0] // 2,
            "Sagittal": image_model.data.shape[2] // 2,
            "Coronal": image_model.data.shape[1] // 2
        }
        self.pan = {"Axial": [0, 0], "Sagittal": [0, 0], "Coronal": [0, 0]}
        self.crosshair_phys_coord = image_model.crosshair_phys_coord
        self.crosshair_pixel_coord = image_model.crosshair_pixel_coord
        self.crosshair_pixel_value = image_model.crosshair_pixel_value

    # Properties redirecting to ImageModel for shared values
    @property
    def zoom(self): return self.image.zoom

    @zoom.setter
    def zoom(self, val): self.image.zoom = val

    @property
    def ww(self): return self.image.ww

    @ww.setter
    def ww(self, val): self.image.ww = val

    @property
    def wl(self): return self.image.wl

    @wl.setter
    def wl(self, val): self.image.wl = val

    @property
    def crosshair_pixel_coord(self):
        return self.image.crosshair_pixel_coord

    @crosshair_pixel_coord.setter
    def crosshair_pixel_coord(self, val):
        self.image.crosshair_pixel_coord = val

    @property
    def crosshair_pixel_value(self):
        return self.image.crosshair_pixel_value

    @crosshair_pixel_value.setter
    def crosshair_pixel_value(self, val):
        self.image.crosshair_pixel_value = val

    @property
    def crosshair_phys_coord(self):
        return self.image.crosshair_phys_coord

    @crosshair_phys_coord.setter
    def crosshair_phys_coord(self, val):
        self.image.crosshair_phys_coord = val


class Controller:
    """The central manager."""

    def __init__(self):
        self.main_windows = None
        self.images = {}  # { "id": ImageModel }
        self.viewers = {}  # { "id": SliceViewer } access by tag (V1, V2, etc)

    def load_image(self, path):
        img_id = str(len(self.images))
        self.images[img_id] = ImageModel(path)
        self.refresh_image_list_ui()
        return img_id

    def update_all_viewers_of_image(self, img_id):
        """Refresh every viewer currently displaying this specific image."""
        for viewer in self.viewers.values():
            if viewer.image_id == img_id:
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

    def on_sidebar_wl_change(self):
        context_viewer = self.main_windows.context_viewer
        if not context_viewer or context_viewer.image_id is None:
            return

        # Get the new values from the UI
        try:
            new_ww = float(dpg.get_value("info_window"))
            new_wl = float(dpg.get_value("info_level"))
        except ValueError:
            # If the user typed something invalid (like letters), do nothing or reset
            return

        # Update the ImageModel
        context_viewer.update_window_level(max(1.0, new_ww), new_wl)

    def refresh_image_list_ui(self):
        container = "image_list_container"
        if not dpg.does_item_exist(container):
            return

        dpg.delete_item(container, children_only=True)

        for img_id, img_model in self.images.items():
            with dpg.group(parent=container):
                with dpg.group(horizontal=True):
                    dpg.add_text(f"{img_model.name}")

                with dpg.group(horizontal=True):
                    dpg.add_spacer(width=10)
                    for v_tag in ["V1", "V2", "V3", "V4"]:
                        # Check if this image is currently in this viewer
                        is_active = self.viewers[v_tag].image_id == img_id
                        dpg.add_checkbox(
                            label="",
                            default_value=is_active,
                            user_data={"img_id": img_id, "v_tag": v_tag},
                            callback=self._on_image_viewer_toggle
                        )
                    # Reload Button
                    btn_reload = dpg.add_button(label="\uf01e", width=20,
                                                callback=lambda s, a, u: self.reload_image(u),
                                                user_data=img_id)
                    # Close Button
                    btn_close = dpg.add_button(label="\uf00d", width=20,
                                               callback=lambda s, a, u: self.close_image(u),
                                               user_data=img_id)

                    # Bind the font to these specific buttons
                    if dpg.does_item_exist("icon_font_tag"):
                        dpg.bind_item_font(btn_reload, "icon_font_tag")
                        dpg.bind_item_font(btn_close, "icon_font_tag")

                    # Bind Themes for visual feedback
                    if dpg.does_item_exist("delete_button_theme"):
                        dpg.bind_item_theme(btn_close, "delete_button_theme")
                    if dpg.does_item_exist("icon_button_theme"):
                        dpg.bind_item_theme(btn_reload, "icon_button_theme")

    def _on_image_viewer_toggle(self, sender, value, user_data):
        img_id = user_data["img_id"]
        v_tag = user_data["v_tag"]
        viewer = self.viewers[v_tag]

        # Rule: If the user tries to uncheck the active image, force it back to True
        if not value and viewer.image_id == img_id:
            dpg.set_value(sender, True)
            return

        if value:  # Checkbox checked
            viewer.set_image(img_id)
            # Update the sidebar info to reflect the newly selected image
            viewer.update_sidebar_info()

        # Refresh UI to ensure only one image is checked per viewer row if desired,
        # or to keep the checkboxes in sync with the state.
        self.refresh_image_list_ui()

    def reload_image(self, img_id):
        """Re-reads the image file from the original path."""
        if img_id in self.images:
            path = self.images[img_id].path
            # Re-initialize the ImageModel with the same path
            self.images[img_id] = ImageModel(path)
            # Refresh all viewers that were using this image
            self.update_all_viewers_of_image(img_id)
            # Update sidebar in case this was the active image
            if self.main_windows.context_viewer and self.main_windows.context_viewer.image_id == img_id:
                self.main_windows.context_viewer.update_sidebar_info()

    def close_image(self, img_id):
        """Removes the image from the controller and clears associated viewers."""
        if img_id in self.images:
            # Remove from any viewer currently displaying it
            for viewer in self.viewers.values():
                if viewer.image_id == img_id:
                    viewer.image_id = None
                    # Clear the texture/render
                    if dpg.does_item_exist(viewer.image_tag):
                        dpg.configure_item(viewer.image_tag, show=False)
                    viewer.update_render()

            # Delete from the data dictionary
            del self.images[img_id]

            # If there are other images, fill the empty viewers with the first one
            if self.images:
                first_img_id = next(iter(self.images))
                for viewer in self.viewers.values():
                    if viewer.image_id is None:
                        viewer.set_image(first_img_id)

            # Refresh the UI list
            self.refresh_image_list_ui()
