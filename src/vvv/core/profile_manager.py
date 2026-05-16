from vvv.utils import ViewMode
import numpy as np


class ProfileManager:
    def __init__(self, controller):
        self.controller = controller

    def _sample_points(self, vs_id, profile):
        """Returns (distances, intensities, pts_phys, vs, vol) or None on failure."""
        vs = self.controller.view_states.get(vs_id)
        vol = self.controller.volumes.get(vs_id)
        if not vs or not vol:
            return None

        p1, p2 = profile.pt1_phys, profile.pt2_phys
        if p1 is None or p2 is None:
            return None

        dist = np.linalg.norm(p2 - p1)
        if dist == 0:
            return None

        sp = vol.spacing  # [x, y, z]
        if profile.orientation == ViewMode.AXIAL:
            in_plane = [sp[0], sp[1]]
        elif profile.orientation == ViewMode.SAGITTAL:
            in_plane = [sp[1], sp[2]]
        else:
            in_plane = [sp[0], sp[2]]

        step = min(in_plane)
        num_points = max(2, int(np.ceil(dist / step)) + 1)

        t = np.linspace(0, 1, num_points)
        distances = np.linspace(0, dist, num_points)
        pts_phys = p1[None, :] + t[:, None] * (p2 - p1)[None, :]

        t_idx = min(vs.camera.time_idx, vol.num_timepoints - 1) if vol.num_timepoints > 1 else None
        is_dvf = getattr(vol, "is_dvf", False)
        is_rgb = getattr(vol, "is_rgb", False)

        def get_val(ix, iy, iz):
            if not (0 <= ix < vol.shape3d[2] and 0 <= iy < vol.shape3d[1] and 0 <= iz < vol.shape3d[0]):
                return 0.0
            v = vol.data[t_idx, iz, iy, ix] if t_idx is not None else vol.data[iz, iy, ix]
            return float(np.linalg.norm(v) if is_dvf else np.mean(v) if is_rgb else v)

        intensities = []
        for pt in pts_phys:
            x, y, z = vol.physic_coord_to_voxel_coord(pt)
            x0, y0, z0 = int(np.floor(x)), int(np.floor(y)), int(np.floor(z))
            x1, y1, z1 = x0 + 1, y0 + 1, z0 + 1
            xd, yd, zd = x - x0, y - y0, z - z0

            c00 = get_val(x0, y0, z0) * (1 - xd) + get_val(x1, y0, z0) * xd
            c01 = get_val(x0, y0, z1) * (1 - xd) + get_val(x1, y0, z1) * xd
            c10 = get_val(x0, y1, z0) * (1 - xd) + get_val(x1, y1, z0) * xd
            c11 = get_val(x0, y1, z1) * (1 - xd) + get_val(x1, y1, z1) * xd
            c0 = c00 * (1 - yd) + c10 * yd
            c1 = c01 * (1 - yd) + c11 * yd
            intensities.append(c0 * (1 - zd) + c1 * zd)

        return distances, intensities, pts_phys, vs, vol

    def get_profile_data(self, vs_id, profile):
        result = self._sample_points(vs_id, profile)
        if result is None:
            return None, None
        distances, intensities, _, _, _ = result
        return distances.tolist(), intensities

    def get_full_export_data(self, vs_id, profile):
        """Returns a dict with name, image, and per-point mm/voxel/intensity data."""
        result = self._sample_points(vs_id, profile)
        if result is None:
            return []
        distances, intensities, pts_phys, vs, vol = result

        export_list = []
        for i, phys in enumerate(pts_phys):
            vox = vol.physic_coord_to_voxel_coord(phys)
            native_vox = vs.world_to_display(phys, is_buffered=False)
            export_list.append(
                {
                    "distance_mm": float(distances[i]),
                    "intensity": float(intensities[i]),
                    "point_phys_mm": phys.tolist(),
                    "point_voxel_index": vox.tolist(),
                    "point_native_voxel": native_vox.tolist() if native_vox is not None else None,
                }
            )

        return {
            "profile_name": profile.name,
            "image_name": vol.name,
            "data": export_list,
        }
