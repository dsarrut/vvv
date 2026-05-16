import numpy as np

class ProfileManager:
    def __init__(self, controller):
        self.controller = controller

    def get_profile_data(self, vs_id, profile):
        vs = self.controller.view_states.get(vs_id)
        vol = self.controller.volumes.get(vs_id)
        if not vs or not vol:
            return None, None

        p1 = profile.pt1_phys
        p2 = profile.pt2_phys

        if p1 is None or p2 is None:
            return None, None

        dist = np.linalg.norm(p2 - p1)
        if dist == 0:
            return None, None

        step = min(vol.spacing) / 2.0
        num_points = max(2, int(dist / step))

        distances = np.linspace(0, dist, num_points)
        t = np.linspace(0, 1, num_points)

        pts_phys = p1[None, :] + t[:, None] * (p2 - p1)[None, :]
        
        intensities = []
        for i in range(num_points):
            v_idx = vol.physic_coord_to_voxel_coord(pts_phys[i])
            x, y, z = v_idx
            
            x0, y0, z0 = int(np.floor(x)), int(np.floor(y)), int(np.floor(z))
            x1, y1, z1 = x0 + 1, y0 + 1, z0 + 1
            
            xd, yd, zd = x - x0, y - y0, z - z0
            
            def get_val(ix, iy, iz):
                if 0 <= ix < vol.shape3d[2] and 0 <= iy < vol.shape3d[1] and 0 <= iz < vol.shape3d[0]:
                    if vol.num_timepoints > 1:
                        t_idx = min(vs.camera.time_idx, vol.num_timepoints - 1)
                        v = vol.data[t_idx, iz, iy, ix]
                    else:
                        v = vol.data[iz, iy, ix]
                    return float(np.linalg.norm(v) if getattr(vol, "is_dvf", False) else np.mean(v) if getattr(vol, "is_rgb", False) else v)
                return 0.0

            c000 = get_val(x0, y0, z0)
            c100 = get_val(x1, y0, z0)
            c010 = get_val(x0, y1, z0)
            c110 = get_val(x1, y1, z0)
            c001 = get_val(x0, y0, z1)
            c101 = get_val(x1, y0, z1)
            c011 = get_val(x0, y1, z1)
            c111 = get_val(x1, y1, z1)

            c00 = c000 * (1 - xd) + c100 * xd
            c01 = c001 * (1 - xd) + c101 * xd
            c10 = c010 * (1 - xd) + c110 * xd
            c11 = c011 * (1 - xd) + c111 * xd

            c0 = c00 * (1 - yd) + c10 * yd
            c1 = c01 * (1 - yd) + c11 * yd

            c = c0 * (1 - zd) + c1 * zd
            intensities.append(c)

        return distances.tolist(), intensities