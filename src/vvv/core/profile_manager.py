import weakref

import numpy as np


class ProfileManager:
    def __init__(self, controller):
        self.controller = controller
        self._cache = {}

    def clear_cache(self, vs_id=None):
        if vs_id is None:
            self._cache.clear()
        else:
            self._cache = {k: v for k, v in self._cache.items() if k[0] != vs_id}

    def _sample_points(self, vs_id, profile):
        """Returns (distances, intensities, pts_phys, vs, vol, distances_list) or None on failure."""
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

        # During live rotation preview the buffer is stale (reflects an older transform).
        # world_to_display(is_buffered=True) only strips translation, so it would sample
        # from the wrong voxels. Fall through to the full ITK inverse-transform path instead.
        in_preview = vs._preview_R is not None
        use_buffer = not in_preview and isinstance(vs.base_display_data, np.ndarray)
        data = vs.base_display_data if use_buffer else vol.data
        if use_buffer:
            target_shape = (
                data.shape[1:]
                if data.ndim == 4
                else data.shape
            )
        else:
            target_shape = vol.shape3d

        # The transform is edited in place (SetTranslation / SetRotation): key on
        # its parameters, not on the object
        space = getattr(vs, "space", None)
        tx = getattr(space, "transform", None)
        transform_token = (
            (bool(space.is_active), tuple(tx.GetParameters()), tuple(tx.GetFixedParameters()))
            if tx is not None
            else None
        )
        profile_id = getattr(profile, "id", "")
        spacing_key = tuple(vol.spacing.tolist()) if getattr(vol, "spacing", None) is not None else None
        cache_key = (
            vs_id,
            profile_id,
            tuple(p1.tolist()),
            tuple(p2.tolist()),
            spacing_key,
            t_idx,
            id(data),
            use_buffer,
            in_preview,
            transform_token,
        )
        # The entry holds a weak reference to the sampled array: a hit only if it
        # is still that array (an id can be reused once an array is freed), and
        # the cache keeps no image alive
        hit = self._cache.get(cache_key)
        if hit is not None and hit[4]() is data:
            distances, intensities, pts_phys, distances_list, _ = hit
            return (distances, intensities, pts_phys, vs, vol, distances_list)

        sx, sy, sz = target_shape[2], target_shape[1], target_shape[0]

        # Convert physical coordinates to voxel coordinates
        vox_list = []
        for pt in pts_phys:
            if use_buffer:
                vox = vs.world_to_display(pt, is_buffered=True)
            else:
                vox = vs.world_to_display(pt, is_buffered=False)
            if vox is None:
                vox_list.append([0.0, 0.0, 0.0])
            else:
                vox_list.append(vox)
        vox_arr = np.asarray(vox_list, dtype=np.float64)

        xs = vox_arr[:, 0]
        ys = vox_arr[:, 1]
        zs = vox_arr[:, 2]

        x0 = np.floor(xs).astype(np.int64)
        y0 = np.floor(ys).astype(np.int64)
        z0 = np.floor(zs).astype(np.int64)
        x1 = x0 + 1
        y1 = y0 + 1
        z1 = z0 + 1

        xd = (xs - x0).astype(np.float32)
        yd = (ys - y0).astype(np.float32)
        zd = (zs - z0).astype(np.float32)

        def sample_corner(cx, cy, cz):
            valid = (cx >= 0) & (cx < sx) & (cy >= 0) & (cy < sy) & (cz >= 0) & (cz < sz)
            cx_c = np.clip(cx, 0, sx - 1)
            cy_c = np.clip(cy, 0, sy - 1)
            cz_c = np.clip(cz, 0, sz - 1)

            if is_dvf or is_rgb:
                vals = np.zeros(len(cx), dtype=np.float32)
                valid_idx = np.nonzero(valid)[0]
                if valid_idx.size > 0:
                    if t_idx is not None:
                        sub = data[t_idx, cz_c[valid_idx], cy_c[valid_idx], cx_c[valid_idx]]
                    else:
                        sub = data[cz_c[valid_idx], cy_c[valid_idx], cx_c[valid_idx]]
                    if is_dvf:
                        vals[valid_idx] = np.linalg.norm(sub, axis=-1)
                    else:
                        vals[valid_idx] = np.mean(sub, axis=-1)
                return vals
            else:
                if t_idx is not None:
                    raw = data[t_idx, cz_c, cy_c, cx_c].astype(np.float32)
                else:
                    raw = data[cz_c, cy_c, cx_c].astype(np.float32)
                return np.where(valid, raw, 0.0)

        c00 = sample_corner(x0, y0, z0) * (1 - xd) + sample_corner(x1, y0, z0) * xd
        c01 = sample_corner(x0, y0, z1) * (1 - xd) + sample_corner(x1, y0, z1) * xd
        c10 = sample_corner(x0, y1, z0) * (1 - xd) + sample_corner(x1, y1, z0) * xd
        c11 = sample_corner(x0, y1, z1) * (1 - xd) + sample_corner(x1, y1, z1) * xd

        c0 = c00 * (1 - yd) + c10 * yd
        c1 = c01 * (1 - yd) + c11 * yd

        intensities = (c0 * (1 - zd) + c1 * zd).tolist()
        distances_list = distances.tolist()

        if len(self._cache) > 256:
            self._cache.pop(next(iter(self._cache)))
        self._cache[cache_key] = (distances, intensities, pts_phys, distances_list, weakref.ref(data))
        return (distances, intensities, pts_phys, vs, vol, distances_list)

    def get_profile_data(self, vs_id, profile):
        result = self._sample_points(vs_id, profile)
        if result is None:
            return None, None
        return result[5], result[1]

    def get_full_export_data(self, vs_id, profile):
        """Returns a dict with name, image, and per-point mm/voxel/intensity data."""
        result = self._sample_points(vs_id, profile)
        if result is None:
            return []
        distances, intensities, pts_phys, vs, vol = result[:5]

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
