import numpy as np
from vvv.utils import ViewMode


class SyncManager:
    """Handles synchronization of camera physics and radiometrics across grouped viewers."""

    def __init__(self, controller):
        self.controller = controller

    def unify_ppm(self, target_viewer_tags):
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
        if source_vs.sync_group == 0:
            target_ids = [source_vs_id]
        else:
            target_ids = [
                tid
                for tid, vs in self.controller.view_states.items()
                if vs.sync_group == source_vs.sync_group
            ]

        # Use the explicit display-aware method!
        # Use the Black Box for the source!
        is_src_buf = source_vs.base_display_data is not None
        world_phys = source_vs.space.display_to_world(
            np.array(source_vs.camera.crosshair_voxel[:3]), is_buffered=is_src_buf
        )

        for target_id in target_ids:
            target_vs = self.controller.view_states[target_id]

            if target_id == source_vs_id:
                source_vox = source_vs.camera.crosshair_voxel
                target_vs.camera.crosshair_voxel = source_vox.copy()
                target_vs.camera.crosshair_phys_coord = (
                    target_vs.space.display_to_world(
                        np.array(source_vox[:3]), is_buffered=is_src_buf
                    )
                )

                target_vs.camera.slices[ViewMode.AXIAL] = int(source_vox[2])
                target_vs.camera.slices[ViewMode.SAGITTAL] = int(source_vox[0])
                target_vs.camera.slices[ViewMode.CORONAL] = int(source_vox[1])
            else:
                phys_pos = world_phys
                target_vol = target_vs.volume

                # Use the Black Box for the target!
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

            ix, iy, iz = [
                int(np.clip(np.floor(c + 0.5), 0, limit - 1))
                for c, limit in zip(
                    target_vs.camera.crosshair_voxel[:3],
                    [
                        target_vs.volume.shape3d[2],
                        target_vs.volume.shape3d[1],
                        target_vs.volume.shape3d[0],
                    ],
                )
            ]

            if target_vs.volume.num_timepoints > 1:
                target_vs.crosshair_value = target_vs.volume.data[
                    target_vs.camera.time_idx, iz, iy, ix
                ]
            else:
                target_vs.crosshair_value = target_vs.volume.data[iz, iy, ix]

            target_vs.is_data_dirty = True

        for viewer in self.controller.viewers.values():
            if viewer.image_id in target_ids:
                viewer.is_geometry_dirty = True

    def propagate_colormap(self, source_vs_id):
        source_vs = self.controller.view_states[source_vs_id]

        sync_wl = False
        if self.controller.gui and hasattr(self.controller.gui, "get_sync_wl_state"):
            sync_wl = self.controller.gui.get_sync_wl_state()

        target_group = source_vs.sync_group
        if sync_wl and target_group != 0:
            for target_id, vs in self.controller.view_states.items():
                if vs.sync_group == target_group and not getattr(
                    vs.volume, "is_rgb", False
                ):
                    vs.display.colormap = source_vs.display.colormap
                    vs.is_data_dirty = True
        else:
            source_vs.is_data_dirty = True

        for viewer in self.controller.viewers.values():
            if viewer.view_state:
                if (
                    viewer.image_id == source_vs_id
                    or (
                        sync_wl
                        and target_group != 0
                        and viewer.view_state.sync_group == target_group
                    )
                    or viewer.view_state.display.overlay_id == source_vs_id
                ):
                    viewer.update_render()
                    viewer.is_geometry_dirty = True

    def propagate_window_level(self, source_vs_id):
        source_vs = self.controller.view_states[source_vs_id]

        sync_wl = False
        if self.controller.gui and hasattr(self.controller.gui, "get_sync_wl_state"):
            sync_wl = self.controller.gui.get_sync_wl_state()

        dirty_ids = {source_vs_id}

        target_group = source_vs.sync_group
        if sync_wl and target_group != 0:
            for target_id, vs in self.controller.view_states.items():
                if vs.sync_group == target_group and not getattr(
                    vs.volume, "is_rgb", False
                ):
                    vs.display.ww = source_vs.display.ww
                    vs.display.wl = source_vs.display.wl
                    vs.display.base_threshold = source_vs.display.base_threshold
                    dirty_ids.add(target_id)

        # Perform a single pass to sync Window/Level across the flat Base <-> Overlay hierarchy
        for tid in list(dirty_ids):
            t_vs = self.controller.view_states[tid]

            # 1. Top-Down: If this image is a Base with a Registration overlay, push W/L down to the overlay
            if t_vs.display.overlay_id and t_vs.display.overlay_mode == "Registration":
                ovs = self.controller.view_states.get(t_vs.display.overlay_id)
                if ovs and not getattr(ovs.volume, "is_rgb", False):
                    ovs.display.ww, ovs.display.wl = t_vs.display.ww, t_vs.display.wl
                    dirty_ids.add(t_vs.display.overlay_id)

            # 2. Bottom-Up: If this image is acting as an Overlay for a Base in Registration mode, push W/L up to the Base
            for base_id, base_vs in self.controller.view_states.items():
                if (
                    base_vs.display.overlay_id == tid
                    and base_vs.display.overlay_mode == "Registration"
                ):
                    if not getattr(base_vs.volume, "is_rgb", False):
                        base_vs.display.ww, base_vs.display.wl = (
                            t_vs.display.ww,
                            t_vs.display.wl,
                        )
                        dirty_ids.add(base_id)

        for tid in dirty_ids:
            self.controller.view_states[tid].is_data_dirty = True

        for viewer in self.controller.viewers.values():
            if viewer.view_state:
                if (
                    viewer.image_id in dirty_ids
                    or viewer.view_state.display.overlay_id in dirty_ids
                ):
                    viewer.update_render()
                    viewer.is_geometry_dirty = True

    def propagate_camera(self, source_viewer):
        if not source_viewer.view_state:
            return
        source_vs = source_viewer.view_state

        if source_vs.sync_group == 0:
            target_ids = [source_viewer.image_id]
        else:
            target_ids = [
                tid
                for tid, vs in self.controller.view_states.items()
                if vs.sync_group == source_vs.sync_group
            ]

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
        target_group = source_vs.sync_group

        if target_group != 0:
            for vs in self.controller.view_states.values():
                if vs.sync_group == target_group:
                    vs.display.overlay_mode = source_vs.display.overlay_mode
                    vs.display.overlay_checkerboard_size = (
                        source_vs.display.overlay_checkerboard_size
                    )
                    vs.display.overlay_checkerboard_swap = (
                        source_vs.display.overlay_checkerboard_swap
                    )
                    vs.is_data_dirty = True
        else:
            source_vs.is_data_dirty = True

        for viewer in self.controller.viewers.values():
            if viewer.view_state and (
                viewer.image_id == source_vs_id
                or viewer.view_state.sync_group == target_group
            ):
                viewer.update_render()
