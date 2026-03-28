import numpy as np
import SimpleITK as sitk


class SpatialEngine:
    """
    The absolute source of truth for 3D coordinate mapping.
    Handles the Base Geometry (via native SimpleITK), the Active Transform, and Camera Illusions.
    """

    def __init__(self, volume):
        self.volume = volume  # Keep a reference to the VolumeData!
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
    # 1. CORE GEOMETRY (The Absolute Truth via ITK)
    # ==========================================
    def raw_voxel_to_phys(self, voxel):
        # SimpleITK natively handles Origin, Spacing, and Direction Matrix perfectly!
        idx = [float(voxel[0]), float(voxel[1]), float(voxel[2])]
        phys = self.volume.sitk_image.TransformContinuousIndexToPhysicalPoint(idx)
        return np.array(phys)

    def phys_to_raw_voxel(self, phys):
        # SimpleITK natively reverse-maps back to the exact floating-point array index
        pt = [float(phys[0]), float(phys[1]), float(phys[2])]
        idx = self.volume.sitk_image.TransformPhysicalPointToContinuousIndex(pt)
        return np.array(idx)

    # ==========================================
    # 2. DISPLAY MAPPING (The Visual Illusions)
    # ==========================================
    def display_to_world(self, display_voxel, is_buffered=False):
        phys = self.raw_voxel_to_phys(display_voxel)

        if self.is_active and self.transform:
            if is_buffered:
                # Buffer Space: Rotation is baked into the resampled UI numpy array.
                # We only apply translation to find World.
                t = np.array(self.transform.GetTranslation())
                return phys + t
            else:
                # Fast Path (Camera Pan): Apply the full Registration transform.
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
                # Fast Path (Camera Pan): Reverse the full Registration transform.
                phys = np.array(
                    self.transform.GetInverse().TransformPoint(phys.tolist())
                )

        return self.phys_to_raw_voxel(phys)

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
            return None
        rot_t = sitk.Euler3DTransform()
        rot_t.SetCenter(self.cor.tolist())
        rot_t.SetRotation(
            self.transform.GetAngleX(),
            self.transform.GetAngleY(),
            self.transform.GetAngleZ(),
        )
        return rot_t
