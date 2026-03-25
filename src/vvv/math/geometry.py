import numpy as np
import SimpleITK as sitk


class SpatialEngine:
    """
    The absolute source of truth for 3D coordinate mapping.
    Handles the Base Geometry, the Active Transform, and the Camera Illusions.
    """

    def __init__(self, volume):
        self.spacing = volume.spacing
        self.origin = volume.origin
        self.matrix = volume.matrix
        self.inverse_matrix = volume.inverse_matrix
        self.shape3d = volume.shape3d

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
    # 1. CORE GEOMETRY (The Absolute Truth)
    # ==========================================
    def raw_voxel_to_phys(self, voxel):
        return self.origin + self.matrix @ (voxel * self.spacing)

    def phys_to_raw_voxel(self, phys):
        return (self.inverse_matrix @ (phys - self.origin)) / self.spacing

    # ==========================================
    # 2. WORLD MAPPING (The Registration Physics)
    # ==========================================
    def get_world_phys(self, raw_voxel):
        phys = self.raw_voxel_to_phys(raw_voxel)
        if self.is_active and self.transform:
            phys = self.transform.TransformPoint(phys.tolist())
        return np.array(phys)

    def get_raw_voxel(self, world_phys):
        phys = np.array(world_phys)
        if self.is_active and self.transform:
            phys = np.array(self.transform.GetInverse().TransformPoint(phys.tolist()))
        return self.phys_to_raw_voxel(phys)

    # ==========================================
    # 3. DISPLAY MAPPING (The Visual Illusions)
    # ==========================================
    def display_to_world(self, display_voxel, is_buffered=False):
        phys = self.raw_voxel_to_phys(display_voxel)
        if self.is_active and self.transform:
            if is_buffered:
                # Buffer Space: Rotation is baked in. Only apply translation to find World.
                t = np.array(self.transform.GetTranslation())
                return phys + t
            else:
                # Fast Path (Camera Pan): Apply the full transform.
                return np.array(self.transform.TransformPoint(phys.tolist()))
        return phys

    def world_to_display(self, world_phys, is_buffered=False):
        phys = np.array(world_phys)
        if self.is_active and self.transform:
            if is_buffered:
                # Buffer Space: Only reverse the translation.
                t = np.array(self.transform.GetTranslation())
                phys = phys - t
            else:
                # Fast Path (Camera Pan): Reverse the full transform.
                phys = np.array(
                    self.transform.GetInverse().TransformPoint(phys.tolist())
                )
        return self.phys_to_raw_voxel(phys)

    # ==========================================
    # 4. TRANSFORM CONTROLLERS
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
            return None
        rot_t = sitk.Euler3DTransform()
        rot_t.SetCenter(self.cor.tolist())
        rot_t.SetRotation(
            self.transform.GetAngleX(),
            self.transform.GetAngleY(),
            self.transform.GetAngleZ(),
        )
        return rot_t
