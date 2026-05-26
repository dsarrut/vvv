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

        step = min(vol.spacing)
        num_points = max(2, int(np.ceil(dist / step)) + 1)

        t = np.linspace(0, 1, num_points)
        distances = np.linspace(0, dist, num_points)
        pts_phys = p1[None, :] + t[:, None] * (p2 - p1)[None, :]

        t_idx = min(vs.camera.time_idx, vol.num_timepoints - 1) if vol.num_timepoints > 1 else None
        is_dvf = getattr(vol, "is_dvf", False)
        is_rgb = getattr(vol, "is_rgb", False)

        use_buffer = isinstance(vs.base_display_data, np.ndarray)
        data = vs.base_display_data if use_buffer else vol.data
        if use_buffer:
            target_shape = (
                data.shape[1:]
                if data.ndim == 4
                else data.shape
            )
        else:
            target_shape = vol.shape3d

        def get_val(ix, iy, iz):
            if not (0 <= ix < target_shape[2] and 0 <= iy < target_shape[1] and 0 <= iz < target_shape[0]):
                return 0.0
            v = data[t_idx, iz, iy, ix] if t_idx is not None else data[iz, iy, ix]
            return float(np.linalg.norm(v) if is_dvf else np.mean(v) if is_rgb else v)

        intensities = []
        for pt in pts_phys:
            if use_buffer:
                vox = vs.world_to_display(pt, is_buffered=True)
                if vox is None:
                    x, y, z = 0.0, 0.0, 0.0
                else:
                    x, y, z = vox
            else:
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

        use_buffer = isinstance(vs.base_display_data, np.ndarray)
        if use_buffer:
            sx, sy, sz = vs.base_display_data.shape[-1], vs.base_display_data.shape[-2], vs.base_display_data.shape[-3]
        else:
            sx, sy, sz = vol.shape3d[2], vol.shape3d[1], vol.shape3d[0]

        export_list = []
        for i, phys in enumerate(pts_phys):
            if use_buffer:
                vox_val = vs.world_to_display(phys, is_buffered=True)
                vox = vox_val if vox_val is not None else np.array([0.0, 0.0, 0.0])
            else:
                vox = vol.physic_coord_to_voxel_coord(phys)
            x, y, z = vox
            in_bounds = (0.0 <= x <= sx - 1) and (0.0 <= y <= sy - 1) and (0.0 <= z <= sz - 1)
            display_vox = vs.world_to_display(phys, is_buffered=False)
            export_list.append(
                {
                    "distance_mm": float(distances[i]),
                    "intensity": float(intensities[i]),
                    "in_bounds": in_bounds,
                    "point_phys_mm": phys.tolist(),
                    "point_voxel_coord": vox.tolist(),
                    "point_voxel_index": [int(round(x)), int(round(y)), int(round(z))],
                    "point_display_voxel": display_vox.tolist() if display_vox is not None else None,
                }
            )

        return {
            "profile_name": profile.name,
            "image_name": vol.name,
            "coordinate_systems": {
                "point_phys_mm": "World-space physical coordinates (mm)",
                "point_voxel_coord": "Fractional voxel coordinates used for trilinear interpolation (x, y, z)",
                "point_voxel_index": "Nearest integer voxel index for direct array access (x, y, z)",
                "point_display_voxel": "Voxel coordinates in un-buffered display space (post-registration, pre-padding)",
            },
            "data": export_list,
        }
