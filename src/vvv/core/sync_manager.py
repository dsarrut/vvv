import numpy as np
from vvv.utils import ViewMode


class SyncManager:
    """Handles synchronization of camera physics and radiometrics across grouped viewers."""

    def __init__(self, controller):
        self.controller = controller

    # ==========================================
    # INTERNAL HELPERS
    # ==========================================

    def get_sync_group_vs_ids(self, source_vs_id, active_only=False):
        """Returns all ViewState IDs in the same sync group as the source image."""
        source_vs = self.controller.view_states.get(source_vs_id)
        if not source_vs or source_vs.sync_group == 0:
            return [source_vs_id]

        group_ids = [
            tid
            for tid, vs in self.controller.view_states.items()
            if vs.sync_group == source_vs.sync_group
        ]

        # Filter out any image that is not currently visible on the screen
        if active_only:
            active_set = {source_vs_id}  # Always include the source
            for viewer in self.controller.viewers.values():
                if viewer.image_id:
                    active_set.add(viewer.image_id)
                    # Also keep the overlay active if it's being displayed!
                    if viewer.view_state and viewer.view_state.display.overlay_id:
                        active_set.add(viewer.view_state.display.overlay_id)
            group_ids = [tid for tid in group_ids if tid in active_set]

        return group_ids

    def trigger_redraw(self, modified_ids):
        """Flags images and viewers to redraw if they or their overlays were modified."""
        for tid in modified_ids:
            if tid in self.controller.view_states:
                self.controller.view_states[tid].is_data_dirty = True

        # If any modified image is acting as an overlay, force its base image to redraw too!
        for vs in self.controller.view_states.values():
            if vs.display.overlay_id in modified_ids:
                vs.is_data_dirty = True

        for viewer in self.controller.viewers.values():
            if viewer.view_state and (
                viewer.image_id in modified_ids
                or viewer.view_state.display.overlay_id in modified_ids
            ):
                viewer.is_geometry_dirty = True

    # ==========================================
    # PUBLIC SYNC METHODS
    # ==========================================

    def propagate_ppm(self, target_viewer_tags):
        valid_viewers = [
            self.controller.viewers[tag]
            for tag in target_viewer_tags
            if self.controller.viewers[tag].view_state
        ]
        if not valid_viewers:
            return

        max_ppm = 0.0
        for viewer in valid_viewers:
            ppm = viewer.get_pixels_per_mm()
            if ppm > max_ppm:
                max_ppm = ppm

        if max_ppm > 0:
            for viewer in valid_viewers:
                viewer.set_pixels_per_mm(max_ppm)
                viewer.is_geometry_dirty = True

    def propagate_sync(self, source_vs_id):
        source_vs = self.controller.view_states[source_vs_id]
        target_ids = self.get_sync_group_vs_ids(source_vs_id, active_only=True)

        # Use the explicit display-aware method to get the true World Coordinate
        is_src_buf = source_vs.base_display_data is not None
        world_phys = source_vs.space.display_to_world(
            np.array(source_vs.camera.crosshair_voxel[:3]), is_buffered=is_src_buf
        )

        for target_id in target_ids:
            target_vs = self.controller.view_states[target_id]

            if target_id == source_vs_id:
                source_vox = source_vs.camera.crosshair_voxel
                target_vs.camera.crosshair_voxel = source_vox.copy()
                target_vs.camera.crosshair_phys_coord = world_phys

                target_vs.camera.slices[ViewMode.AXIAL] = int(source_vox[2])
                target_vs.camera.slices[ViewMode.SAGITTAL] = int(source_vox[0])
                target_vs.camera.slices[ViewMode.CORONAL] = int(source_vox[1])
            else:
                phys_pos = world_phys
                target_vol = target_vs.volume

                is_tgt_buf = target_vs.base_display_data is not None
                target_vox = target_vs.space.world_to_display(
                    phys_pos, is_buffered=is_tgt_buf
                )

                nt = target_vs.volume.num_timepoints
                target_vs.camera.time_idx = min(source_vs.camera.time_idx, nt - 1)

                target_vs.camera.crosshair_voxel = [
                    target_vox[0],
                    target_vox[1],
                    target_vox[2],
                    target_vs.camera.time_idx,
                ]
                target_vs.camera.crosshair_phys_coord = phys_pos

                target_vs.camera.slices[ViewMode.AXIAL] = int(
                    np.clip(np.floor(target_vox[2] + 0.5), 0, target_vol.shape3d[0] - 1)
                )
                target_vs.camera.slices[ViewMode.SAGITTAL] = int(
                    np.clip(np.floor(target_vox[0] + 0.5), 0, target_vol.shape3d[2] - 1)
                )
                target_vs.camera.slices[ViewMode.CORONAL] = int(
                    np.clip(np.floor(target_vox[1] + 0.5), 0, target_vol.shape3d[1] - 1)
                )

            # --- THE FIX: Pure Physical Coordinates for Value Lookup ---
            # By passing is_buffered=False, we force the SpatialEngine to map the world coordinate
            # backwards through any active transforms straight into the original RAW array!
            raw_vox = target_vs.space.world_to_display(
                target_vs.camera.crosshair_phys_coord, is_buffered=False
            )
            ix, iy, iz = [int(np.floor(c + 0.5)) for c in raw_vox[:3]]

            mz, my, mx = target_vs.volume.shape3d
            if 0 <= ix < mx and 0 <= iy < my and 0 <= iz < mz:
                t = min(target_vs.camera.time_idx, target_vs.volume.num_timepoints - 1)
                if target_vs.volume.num_timepoints > 1:
                    target_vs.crosshair_value = target_vs.volume.data[t, iz, iy, ix]
                else:
                    target_vs.crosshair_value = target_vs.volume.data[iz, iy, ix]
            else:
                target_vs.crosshair_value = None

        self.trigger_redraw(target_ids)

    def propagate_colormap(self, source_vs_id):
        source_vs = self.controller.view_states[source_vs_id]
        dirty_ids = set([source_vs_id])

        # --- NEW DECOUPLED W/L LOGIC ---
        wl_grp = getattr(source_vs, "sync_wl_group", 0)
        if wl_grp > 0:
            for tid, vs in self.controller.view_states.items():
                if tid != source_vs_id and getattr(vs, "sync_wl_group", 0) == wl_grp:
                    if not getattr(vs.volume, "is_rgb", False):
                        vs.display.colormap = source_vs.display.colormap
                        dirty_ids.add(tid)

        self.trigger_redraw(list(dirty_ids))

    def propagate_window_level(self, source_vs_id):
        source_vs = self.controller.view_states[source_vs_id]
        dirty_ids = set([source_vs_id])

        # 1. GROUP SYNC (Horizontal) - NEW DECOUPLED W/L LOGIC
        wl_grp = getattr(source_vs, "sync_wl_group", 0)
        if wl_grp > 0:
            for vs_id, vs in self.controller.view_states.items():
                if vs_id != source_vs_id and getattr(vs, "sync_wl_group", 0) == wl_grp:
                    vs.display.ww = source_vs.display.ww
                    vs.display.wl = source_vs.display.wl
                    vs.display.base_threshold = source_vs.display.base_threshold
                    vs.is_data_dirty = True
                    dirty_ids.add(vs_id)

        # 2. OVERLAY SYNC (Vertical - Top-Down & Bottom-Up)
        for tid in list(dirty_ids):
            t_vs = self.controller.view_states[tid]

            # 1. Top-Down
            if t_vs.display.overlay_id and t_vs.display.overlay_mode == "Registration":
                ovs = self.controller.view_states.get(t_vs.display.overlay_id)
                if ovs and not getattr(ovs.volume, "is_rgb", False):
                    ovs.display.ww = t_vs.display.ww
                    ovs.display.wl = t_vs.display.wl
                    ovs.display.base_threshold = t_vs.display.base_threshold
                    dirty_ids.add(t_vs.display.overlay_id)

            # 2. Bottom-Up
            for base_id, base_vs in self.controller.view_states.items():
                if (
                    base_vs.display.overlay_id == tid
                    and base_vs.display.overlay_mode == "Registration"
                ):
                    if not getattr(base_vs.volume, "is_rgb", False):
                        base_vs.display.ww = t_vs.display.ww
                        base_vs.display.wl = t_vs.display.wl
                        base_vs.display.base_threshold = t_vs.display.base_threshold
                        dirty_ids.add(base_id)

        self.trigger_redraw(list(dirty_ids))

    def propagate_camera(self, source_viewer):
        if not source_viewer.view_state:
            return

        target_ids = self.get_sync_group_vs_ids(
            source_viewer.image_id, active_only=True
        )

        phys_center = source_viewer.get_center_physical_coord()
        if phys_center is None:
            return

        target_ppm = source_viewer.get_pixels_per_mm()

        for viewer in self.controller.viewers.values():
            if viewer.image_id in target_ids and viewer != source_viewer:
                viewer.set_pixels_per_mm(target_ppm)
                viewer.center_on_physical_coord(phys_center)

    def propagate_overlay_mode(self, source_vs_id):
        source_vs = self.controller.view_states[source_vs_id]
        target_ids = self.get_sync_group_vs_ids(source_vs_id)

        for tid in target_ids:
            vs = self.controller.view_states[tid]
            vs.display.overlay_mode = source_vs.display.overlay_mode
            vs.display.overlay_checkerboard_size = (
                source_vs.display.overlay_checkerboard_size
            )
            vs.display.overlay_checkerboard_swap = (
                source_vs.display.overlay_checkerboard_swap
            )

        self.trigger_redraw(target_ids)
