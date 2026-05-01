import numpy as np
import SimpleITK as sitk


class SpatialEngine:
    """
    The absolute source of truth for 3D coordinate mapping.
    Handles the Base Geometry (via native SimpleITK), the Active Transform, and Camera Illusions.
    """

    def __init__(self, volume, view_state=None):
        self.volume = volume  # Keep a reference to the VolumeData!
        self.shape3d = volume.shape3d
        self.view_state = view_state # Keep a reference to the ViewState

        # Transform State
        self.transform = None
        self.transform_file = "None"
        self.is_active = False

        # Center of Rotation (Anatomical center)
        cx = (self.shape3d[2] - 1) / 2.0
        cy = (self.shape3d[1] - 1) / 2.0
        cz = (self.shape3d[0] - 1) / 2.0
        self.cor = self.raw_voxel_to_phys(np.array([cx, cy, cz]))

    # ==========================================
    # 1. CORE GEOMETRY (The Absolute Truth via ITK)
    # ==========================================
    def raw_voxel_to_phys(self, voxel, use_buffered_geometry=False):
        if voxel is None or len(voxel) < 3:
            return np.array([0.0, 0.0, 0.0])

        target_sitk_image = self.volume.sitk_image
        if use_buffered_geometry and self.view_state and self.view_state._sitk_base_cache:
            target_sitk_image = self.view_state._sitk_base_cache

        # Tombstone fallback: Use pure Python math if C++ memory is temporarily detached or not available
        if target_sitk_image is None:
            return self.volume.voxel_coord_to_physic_coord(np.array(voxel[:3]))

        # Handle 3D coordinates, but pad for 4D images to prevent ITK dimension mismatch.
        idx = [float(voxel[0]), float(voxel[1]), float(voxel[2])]
        dim = target_sitk_image.GetDimension()
        if dim == 4:
            idx.append(0.0)  # Pad the time dimension
        elif dim == 2:
            idx = idx[:2]  # Strip Z for 2D images

        try:
            phys = target_sitk_image.TransformContinuousIndexToPhysicalPoint(idx)
        except Exception: # Fallback for corrupted SITK image or bad index
            # This should ideally not happen if target_sitk_image is valid
            return self.volume.voxel_coord_to_physic_coord(np.array(voxel[:3]))

        if len(phys) == 2:
            return np.array([phys[0], phys[1], 0.0])
        return np.array(phys[:3])  # Only return the X, Y, Z physical coordinates

    def phys_to_raw_voxel(self, phys, use_buffered_geometry=False):
        if phys is None or len(phys) < 3:
            return np.array([0.0, 0.0, 0.0])

        target_sitk_image = self.volume.sitk_image
        if use_buffered_geometry and self.view_state and self.view_state._sitk_base_cache:
            target_sitk_image = self.view_state._sitk_base_cache

        # Tombstone fallback
        if target_sitk_image is None:
            return self.volume.physic_coord_to_voxel_coord(np.array(phys[:3]))

        pt = [float(phys[0]), float(phys[1]), float(phys[2])]
        dim = target_sitk_image.GetDimension()
        if dim == 4:
            pt.append(0.0)  # Pad the time dimension
        elif dim == 2:
            pt = pt[:2]  # Strip Z for 2D images

        try:
            idx = target_sitk_image.TransformPhysicalPointToContinuousIndex(pt)
        except Exception: # Fallback for corrupted SITK image or bad physical point
            return self.volume.physic_coord_to_voxel_coord(np.array(phys[:3]))

        if len(idx) == 2:
            return np.array([idx[0], idx[1], 0.0])
        return np.array(idx[:3])

    # ==========================================
    # 2. DISPLAY MAPPING (The Visual Illusions)
    # ==========================================
    def display_to_world(self, display_voxel, is_buffered=False):
        if display_voxel is None:
            return None

        # Convert display_voxel to physical coordinates using the appropriate geometry
        phys = self.raw_voxel_to_phys(display_voxel, use_buffered_geometry=is_buffered)

        if self.is_active and self.transform:
            # Always apply the full transform to get to world physical coordinates
            return np.array(self.transform.TransformPoint(phys.tolist()))
        return phys

    def world_to_display(self, world_phys, is_buffered=False):
        if world_phys is None:
            return None

        if self.is_active and self.transform:
            try:
                # Reverse the full Registration transform to get to the image's native physical space
                phys = np.array(self.transform.GetInverse().TransformPoint(world_phys.tolist()))
            except Exception:
                phys = np.array(world_phys)  # Failsafe against singular inverse matrices
        else:
            phys = np.array(world_phys)

        # Convert physical coordinates back to display_voxel using the appropriate geometry
        return self.phys_to_raw_voxel(phys, use_buffered_geometry=is_buffered)

    # ==========================================
    # 3. TRANSFORM CONTROLLERS
    # ==========================================
    def set_manual_transform(self, tx, ty, tz, rx_rad, ry_rad, rz_rad):
        if not self.transform:
            self.transform = sitk.Euler3DTransform()
            self.transform.SetCenter(self.cor.tolist())

        self.transform.SetTranslation((float(tx), float(ty), float(tz)))
        self.transform.SetRotation(float(rx_rad), float(ry_rad), float(rz_rad))

    def get_parameters(self):
        """Returns (rx, ry, rz, tx, ty, tz) in radians/mm"""
        if not self.transform:
            return (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
        return self.transform.GetParameters()

    def has_rotation(self, tolerance=1e-5):
        if not self.transform:
            return False
        rx, ry, rz = (
            self.transform.GetAngleX(),
            self.transform.GetAngleY(),
            self.transform.GetAngleZ(),
        )
        return abs(rx) > tolerance or abs(ry) > tolerance or abs(rz) > tolerance

    def get_rotation_only_transform(self):
        if not self.transform:
            return (
                sitk.Euler3DTransform()
            )  # Return identity instead of None to prevent AttributeError downstream

        rot_t = sitk.Euler3DTransform()

        # Respect the user's custom CoR
        rot_t.SetCenter(self.transform.GetCenter())

        rot_t.SetRotation(
            self.transform.GetAngleX(),
            self.transform.GetAngleY(),
            self.transform.GetAngleZ(),
        )
        return rot_t
