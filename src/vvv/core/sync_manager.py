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
            for tid, vs in list(self.controller.view_states.items())
            if vs.sync_group == source_vs.sync_group
        ]

        # Filter out any image that is not currently visible on the screen
        if active_only:
            active_set = {source_vs_id}  # Always include the source
            for viewer in self.controller.viewers.values():
                if viewer.image_id:
                    active_set.add(viewer.image_id)
                    # Also keep the overlay active if it's being displayed.
                    if viewer.view_state and viewer.view_state.display.overlay_id:
                        active_set.add(viewer.view_state.display.overlay_id)
            group_ids = [tid for tid in group_ids if tid in active_set]

        return group_ids

    def get_sync_wl_group_vs_ids(self, source_vs_id):
        """Returns all ViewState IDs in the same Window/Level sync group as the source image."""
        source_vs = self.controller.view_states.get(source_vs_id)
        wl_grp = getattr(source_vs, "sync_wl_group", 0) if source_vs else 0
        if wl_grp == 0:
            return [source_vs_id]
        return [
            tid
            for tid, vs in list(self.controller.view_states.items())
            if getattr(vs, "sync_wl_group", 0) == wl_grp
        ]

    def trigger_redraw(self, modified_ids):
        """Flags images to redraw. Viewers will autonomously react to this."""
        for tid in modified_ids:
            vs = self.controller.view_states.get(tid)
            if vs:
                vs.is_data_dirty = True

        # If any modified image is acting as an overlay, force its base image to redraw too
        for vs in list(self.controller.view_states.values()):
            if vs.display.overlay_id in modified_ids:
                vs.is_data_dirty = True

    # ==========================================
    # PUBLIC SYNC METHODS
    # ==========================================

    def propagate_transform_sync(self, source_vs_id):
        """Notify sync group that the source image's transform changed.

        Unlike propagate_sync, this does NOT update crosshair_voxel (which would
        move the crosshair on screen) or pan/zoom. It only marks synced images as
        data-dirty so they redraw with the correct slice_idx, which auto-derives
        from crosshair_phys_coord via _get_crosshair_display_voxel().
        """
        source_vs = self.controller.view_states.get(source_vs_id)
        if not source_vs:
            return
        target_ids = self.get_sync_group_vs_ids(source_vs_id, active_only=True)
        dirty_ids = [tid for tid in target_ids if tid != source_vs_id]
        self.trigger_redraw(dirty_ids)

    def propagate_time_idx(self, source_vs_id):
        """Propagate time_idx to all sync group members, clamping to their max timepoints."""
        source_vs = self.controller.view_states.get(source_vs_id)
        if not source_vs:
            return
        target_ids = self.get_sync_group_vs_ids(source_vs_id, active_only=False)
        for target_id in target_ids:
            if target_id == source_vs_id:
                continue
            target_vs = self.controller.view_states.get(target_id)
            if target_vs:
                if source_vs.volume.num_timepoints > 1:
                    nt = target_vs.volume.num_timepoints
                    target_vs.camera.time_idx = min(source_vs.camera.time_idx, nt - 1)

    def propagate_sync(self, source_vs_id):
        source_vs = self.controller.view_states.get(source_vs_id)

        if not source_vs or source_vs.camera.crosshair_voxel is None:
            # If the source has no crosshair yet, we can't sync others to it.
            return

        target_ids = self.get_sync_group_vs_ids(source_vs_id, active_only=True)

        world_phys = source_vs.camera.crosshair_phys_coord

        for target_id in target_ids:
            if target_id == source_vs_id:
                continue

            target_vs = self.controller.view_states.get(target_id)
            if not target_vs:
                continue

            if source_vs.volume.num_timepoints > 1:
                nt = target_vs.volume.num_timepoints
                target_vs.camera.time_idx = min(source_vs.camera.time_idx, nt - 1)

            target_vs.update_crosshair_from_phys(world_phys)

        self.trigger_redraw(target_ids)

    def propagate_colormap(self, source_vs_id):
        source_vs = self.controller.view_states.get(source_vs_id)
        if not source_vs:
            return
        dirty_ids = set([source_vs_id])

        # --- NEW DECOUPLED W/L LOGIC ---
        for tid in self.get_sync_wl_group_vs_ids(source_vs_id):
            if tid != source_vs_id:
                vs = self.controller.view_states[tid]
                if not getattr(vs.volume, "is_rgb", False):
                    vs.display.colormap = source_vs.display.colormap
                    dirty_ids.add(tid)

        self.trigger_redraw(list(dirty_ids))

    def propagate_window_level(self, source_vs_id):
        source_vs = self.controller.view_states.get(source_vs_id)
        if not source_vs:
            return
            
        new_ww = source_vs.display.ww
        new_wl = source_vs.display.wl
        new_thr = source_vs.display.base_threshold

        dirty_ids = set([source_vs_id])

        # 1. GROUP SYNC (Horizontal) - NEW DECOUPLED W/L LOGIC
        for vs_id in self.get_sync_wl_group_vs_ids(source_vs_id):
            if vs_id != source_vs_id:
                vs = self.controller.view_states[vs_id]
                if not getattr(vs.volume, "is_rgb", False):
                    vs.display.ww = new_ww
                    vs.display.wl = new_wl
                    vs.display.base_threshold = new_thr
                dirty_ids.add(vs_id)

        # 2. OVERLAY SYNC (Vertical - Top-Down & Bottom-Up)
        for tid in list(dirty_ids):
            t_vs = self.controller.view_states.get(tid)
            if not t_vs:
                continue

            # 1. Top-Down
            if t_vs.display.overlay_id and t_vs.display.overlay_mode == "Registration":
                ovs = self.controller.view_states.get(t_vs.display.overlay_id)
                if ovs and not getattr(ovs.volume, "is_rgb", False):
                    ovs.display.ww = new_ww
                    ovs.display.wl = new_wl
                    ovs.display.base_threshold = new_thr
                    dirty_ids.add(t_vs.display.overlay_id)

            # 2. Bottom-Up
            for base_id, base_vs in list(self.controller.view_states.items()):
                if (
                    base_vs.display.overlay_id == tid
                    and base_vs.display.overlay_mode == "Registration"
                ):
                    if not getattr(base_vs.volume, "is_rgb", False):
                        base_vs.display.ww = new_ww
                        base_vs.display.wl = new_wl
                        base_vs.display.base_threshold = new_thr
                        dirty_ids.add(base_id)

        self.trigger_redraw(list(dirty_ids))

    def propagate_ppm(self, target_viewer_tags):
        valid_viewers = [
            self.controller.viewers[tag]
            for tag in target_viewer_tags
            if self.controller.viewers[tag].view_state
        ]
        if not valid_viewers:
            return

        max_ppm = max([v.get_pixels_per_mm() for v in valid_viewers] + [0])

        if max_ppm > 0:
            # State-Only: Just write the target to the shared memory.
            for viewer in valid_viewers:
                viewer.view_state.camera.target_ppm = max_ppm

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

        # State-Only: Just write the targets to the synced ViewStates.
        for tid in target_ids:
            vs = self.controller.view_states.get(tid)
            if not vs:
                continue
            vs.camera.target_ppm = target_ppm
            vs.camera.target_center = phys_center

    def propagate_camera_to_viewer(self, source_vs_id, target_viewer):
        source_vs = self.controller.view_states.get(source_vs_id)
        if not source_vs or not target_viewer.view_state:
            return

        # State-Only: If the master has an active target, naturally inherit it
        if getattr(source_vs.camera, "target_ppm", None) is not None:
            target_viewer.view_state.camera.target_ppm = source_vs.camera.target_ppm
            target_viewer.view_state.camera.target_center = (
                source_vs.camera.target_center
            )
        else:
            # If the master hasn't moved yet, extract its starting point
            source_viewer = next(
                (
                    v
                    for v in self.controller.viewers.values()
                    if v.image_id == source_vs_id
                ),
                None,
            )
            if source_viewer:
                target_viewer.view_state.camera.target_ppm = (
                    source_viewer.get_pixels_per_mm()
                )
                target_viewer.view_state.camera.target_center = (
                    source_viewer.get_center_physical_coord()
                )

    def propagate_tracker(self, source_viewer, phys=None):
        if not source_viewer.view_state:
            return

        target_ids = self.get_sync_group_vs_ids(
            source_viewer.image_id, active_only=True
        )

        # State-Only: Write the physical coordinate to synced ViewStates.
        for tid in target_ids:
            if tid != source_viewer.image_id:
                vs = self.controller.view_states.get(tid)
                if vs:
                    vs.camera.target_tracker_phys = phys

    def propagate_overlay_mode(self, source_vs_id):
        source_vs = self.controller.view_states.get(source_vs_id)
        if not source_vs:
            return
        target_ids = self.get_sync_group_vs_ids(source_vs_id)

        for tid in target_ids:
            vs = self.controller.view_states.get(tid)
            if not vs:
                continue
            vs.display.overlay_mode = source_vs.display.overlay_mode
            vs.display.overlay_checkerboard_size = (
                source_vs.display.overlay_checkerboard_size
            )
            vs.display.overlay_checkerboard_swap = (
                source_vs.display.overlay_checkerboard_swap
            )

        self.trigger_redraw(target_ids)

    def link_all(self):
        """Assigns all currently loaded images to spatial sync group 1."""
        if not self.controller.view_states:
            return

        for vs in list(self.controller.view_states.values()):
            vs.sync_group = 1

        # Trigger the sync propagation logic you built in Step 2
        # (Assuming the first loaded view state acts as the master)
        first_vs_id = next(iter(self.controller.view_states))
        self.controller.set_sync_group(first_vs_id, 1)
        self.controller.ui_needs_refresh = True

    def unlink_all(self):
        """Removes all images from spatial sync groups."""
        for vs in list(self.controller.view_states.values()):
            vs.sync_group = 0

        for vs_id in list(self.controller.view_states.keys()):
            self.controller.update_all_viewers_of_image(vs_id)
        self.controller.ui_needs_refresh = True

    def link_all_wl(self):
        """Assigns all currently loaded images to Window/Level sync group 1."""
        if not self.controller.view_states:
            return

        for vs in list(self.controller.view_states.values()):
            vs.sync_wl_group = 1

        # State-Only: Instantly broadcast the W/L and Colormap to the whole group.
        first_vs_id = next(iter(self.controller.view_states))
        self.propagate_window_level(first_vs_id)
        self.propagate_colormap(first_vs_id)

        # Flag the GUI to refresh the sync tab
        self.controller.ui_needs_refresh = True

    def unlink_all_wl(self):
        """Removes all images from Window/Level sync groups."""
        for vs in list(self.controller.view_states.values()):
            vs.sync_wl_group = 0  # Changed from sync_wl to sync_wl_group

        for vs_id in list(self.controller.view_states.keys()):
            self.controller.update_all_viewers_of_image(vs_id)

        # Flag the GUI to refresh the sync tab
        self.controller.ui_needs_refresh = True
