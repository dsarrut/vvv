import SimpleITK as sitk
import numpy as np
import os
import dearpygui.dearpygui as dpg
from pathlib import Path
import copy
import json
import threading
import time


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
        self.needs_render = True

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
            "Axial": self.data.shape[0] // 2,
            "Sagittal": self.data.shape[1] // 2,
            "Coronal": self.data.shape[2] // 2
        }
        # Current voxel information under the crosshair
        self.crosshair_phys_coord = None
        self.crosshair_pixel_coord = None
        self.crosshair_pixel_value = None
        self.init_crosshair_to_slices()
        # Current pan for all orientation
        self.pan = {"Axial": [0, 0], "Sagittal": [0, 0], "Coronal": [0, 0]}
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
        self.crosshair_pixel_coord = [self.slices["Coronal"], self.slices["Sagittal"], self.slices["Axial"]]
        self.crosshair_phys_coord = self.voxel_coord_to_physic_coord(self.crosshair_pixel_coord)
        ix, iy, iz = self.crosshair_pixel_coord
        self.crosshair_pixel_value = self.data[iz, iy, ix]

    def get_slice_rgba_initial(self, slice_idx, orientation="Axial"):
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

    def get_slice_rgba(self, slice_idx, orientation="Axial"):

        # 1. Determine the maximum index for the current orientation
        if orientation == "Axial":
            max_s, h, w = self.data.shape[0], self.data.shape[1], self.data.shape[2]
        elif orientation == "Sagittal":
            max_s, h, w = self.data.shape[2], self.data.shape[0], self.data.shape[1]
        else:  # Coronal
            max_s, h, w = self.data.shape[1], self.data.shape[0], self.data.shape[2]

        # 2. Check if the slice is out of bounds
        if slice_idx < 0 or slice_idx >= max_s:
            # Return a black slice of the correct shape
            black_slice = np.zeros((h, w, 4), dtype=np.float32)
            black_slice[:, :, 3] = 1.0  # Opaque alpha
            return black_slice.flatten(), (h, w)

        """Extracts a slice with corrected orientations for vv parity."""
        idx = slice_idx
        if orientation == "Axial":
            slice_data = self.data[idx, :, :]

        elif orientation == "Sagittal":
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


class Controller:
    """The central manager."""

    def __init__(self):
        self.main_windows = None
        self.images = {}  # { "id": ImageModel }
        self.viewers = {}  # { "id": SliceViewer } access by tag (V1, V2, etc)
        self.settings = SettingsManager()

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

    def load_image(self, path):
        img_id = str(len(self.images))
        self.images[img_id] = ImageModel(path)
        self.refresh_image_list_ui()
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
        data = self.settings.data

        # Reset Physics inputs
        dpg.set_value("set_search_radius", data["physics"]["search_radius"])
        dpg.set_value("set_strip_threshold", data["physics"]["voxel_strip_threshold"])

        # Programmatically reset all color pickers
        for key, value in data["colors"].items():
            tag = f"set_col_{key}"
            if dpg.does_item_exist(tag):
                dpg.set_value(tag, value)

        # Refresh viewers to apply the default colors immediately
        for viewer in self.viewers.values():
            viewer.update_render()

    def save_settings_with_hint(self):
        # 1. Perform the save and get the path
        path = self.settings.save()

        # 2. Update the UI text
        hint_msg = f"Saved in: {path}"
        dpg.set_value("save_status_text", hint_msg)

        # 3. Optional: Clear the message after 3 seconds using a thread
        # (So the UI doesn't freeze)
        def clear_hint():
            time.sleep(3.0)
            if dpg.does_item_exist("save_status_text"):
                dpg.set_value("save_status_text", "")

        threading.Thread(target=clear_hint, daemon=True).start()

    def refresh_image_list_ui(self):
        container = "image_list_container"
        if not dpg.does_item_exist(container):
            return

        dpg.delete_item(container, children_only=True)

        for img_id, img_model in self.images.items():
            with dpg.group(parent=container):
                with dpg.group(horizontal=True):
                    dpg.add_text(f"{img_model.name}", tag=f"img_label_{img_id}")

                with dpg.group(horizontal=True):
                    dpg.add_spacer(width=10)
                    for v_tag in ["V1", "V2", "V3", "V4"]:
                        # Check if this image is currently in this viewer
                        is_active = self.viewers[v_tag].image_id == img_id
                        dpg.add_checkbox(
                            label="",
                            default_value=is_active,
                            user_data={"img_id": img_id, "v_tag": v_tag},
                            callback=self.on_image_viewer_toggle
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

        self.refresh_sync_ui()

    def refresh_sync_ui(self):
        container = "sync_list_container"
        if not dpg.does_item_exist(container): return
        dpg.delete_item(container, children_only=True)

        # Table for alignment
        with dpg.table(parent=container, header_row=False):
            dpg.add_table_column(label="Image")
            dpg.add_table_column(label="Group", width_fixed=True)

            for img_id, img in self.images.items():
                with dpg.table_row():
                    dpg.add_text(img.name)
                    # Dropdown to pick a group (0 = None)
                    dpg.add_combo(
                        items=["None", "Group 1", "Group 2", "Group 3"],
                        default_value="None" if not img.sync_group else f"Group {img.sync_group}",
                        width=100,
                        user_data=img_id,
                        callback=self.on_sync_group_change
                    )

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

    def on_image_viewer_toggle(self, sender, value, user_data):
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

    def on_visibility_toggle(self, sender, value, user_data):
        context_viewer = self.main_windows.context_viewer
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
            # Copy spatial state from the existing group member
            # img.ww = master_image.ww
            # img.wl = master_image.wl
            img.zoom = master_image.zoom
            # img.slices = copy.deepcopy(master_image.slices)
            # img.pan = copy.deepcopy(master_image.pan)

            # Update all viewers to reflect the alignment
            self.update_all_viewers_of_image(img_id)

    def propagate_sync(self, source_img_id):
        source_img = self.images[source_img_id]
        if source_img.sync_group == 0: return

        phys_pos = source_img.crosshair_phys_coord
        shared_zoom = source_img.zoom
        shared_pan = copy.deepcopy(source_img.pan)

        for target_id, target_img in self.images.items():
            if target_id != source_img_id and target_img.sync_group == source_img.sync_group:
                # Calculate TRUE floating point voxel position (Unclipped)
                target_vox = (phys_pos - target_img.origin + target_img.spacing / 2) / target_img.spacing

                # Store the unclipped coordinate for the crosshair lines
                target_img.crosshair_pixel_coord = [target_vox[0], target_vox[1], target_vox[2]]

                # 2. Handle the Pixel Value (Clipped for data safety)
                ix, iy, iz = [int(np.clip(c, 0, limit - 1)) for c, limit in
                              zip(target_vox,
                                  [target_img.data.shape[2], target_img.data.shape[1], target_img.data.shape[0]])]

                # Check if actually inside to show value or "Out of bounds"
                if 0 <= target_vox[0] < target_img.data.shape[2] and \
                        0 <= target_vox[1] < target_img.data.shape[1] and \
                        0 <= target_vox[2] < target_img.data.shape[0]:
                    target_img.crosshair_pixel_value = target_img.data[iz, iy, ix]
                else:
                    target_img.crosshair_pixel_value = float('nan')

                # Update physical and slice data
                vz_raw = target_vox[2]
                vx_raw = target_vox[0]
                vy_raw = target_vox[1]
                target_img.crosshair_phys_coord = phys_pos
                target_img.slices["Axial"] = int(vz_raw)
                target_img.slices["Sagittal"] = int(vx_raw)
                target_img.slices["Coronal"] = int(vy_raw)

                # Zoom and Pan Sync
                target_img.zoom = shared_zoom
                #target_img.pan = shared_pan

                # Redraw followers safely
                target_img.needs_render = True

                for viewer in self.viewers.values():
                    if viewer.image_model and viewer.image_model.sync_group == source_img.sync_group:
                        #if viewer.image_id != source_img_id:
                            # Tell followers to re-calculate their pan based on
                            # their own geometry and the new physical crosshair
                        #    viewer.needs_recenter = True
                        viewer.needs_refresh = True

    def propagate_sync_initial(self, source_img_id):
        source_img = self.images[source_img_id]
        if source_img.sync_group == 0:
            return

        phys_pos = source_img.crosshair_phys_coord
        shared_zoom = source_img.zoom
        shared_pan = copy.deepcopy(source_img.pan)  # Contains all 3 orientations

        for target_id, target_img in self.images.items():
            if target_id != source_img_id and target_img.sync_group == source_img.sync_group:
                # Physical Position Sync
                target_vox = (phys_pos - target_img.origin + target_img.spacing / 2) / target_img.spacing
                target_img.crosshair_phys_coord = phys_pos
                target_img.crosshair_pixel_coord = [
                    np.clip(target_vox[0], 0, target_img.data.shape[2] - 1),
                    np.clip(target_vox[1], 0, target_img.data.shape[1] - 1),
                    np.clip(target_vox[2], 0, target_img.data.shape[0] - 1)
                ]

                # Update slices based on new voxel coords
                target_img.slices["Axial"] = int(target_img.crosshair_pixel_coord[2])
                target_img.slices["Sagittal"] = int(target_img.crosshair_pixel_coord[0])
                target_img.slices["Coronal"] = int(target_img.crosshair_pixel_coord[1])

                ix, iy, iz = [int(c) for c in target_img.crosshair_pixel_coord]
                target_img.crosshair_pixel_value = target_img.data[iz, iy, ix]

                # Zoom and Pan Sync
                target_img.zoom = shared_zoom
                target_img.pan = shared_pan

                # Redraw followers safely
                target_img.needs_render = True

                for viewer in self.viewers.values():
                    if viewer.image_model and viewer.image_model.sync_group == source_img.sync_group:
                        viewer.needs_refresh = True


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
