import random
import numpy as np

# A deterministic seed ensures that if the Monkey finds a bug,
# you can re-run the test and it will do the EXACT same actions to reproduce it!
random.seed(42)


def test_chaos_monkey_survives_the_storm(headless_gui_app):
    """
    The Ultimate Architectural Guardrail.
    Subject the pure State-Only architecture to an explosion of stochastic events
    and verify that the math, the sync engine, and the main thread survive flawlessly.
    """
    # 1. THE ARENA SETUP
    # Extract the headless environment tools
    controller, gui, primary_viewer, primary_vs_id = headless_gui_app

    # Ensure we have multiple viewers and images to link/unlink
    vs_ids = list(controller.view_states.keys())
    viewers = list(controller.viewers.values())

    # We will simulate 500 frames of absolute chaos
    NUM_FRAMES = 500

    # Define our action boundaries
    pan_range = (-500.0, 500.0)
    zoom_range = (0.1, 20.0)
    coord_range = (-1000.0, 1000.0)  # Intentionally goes way outside the image bounds!
    wl_range = (-1000.0, 1000.0)

    # 2. THE MONKEY'S ARSENAL
    def action_random_pan():
        v = random.choice(viewers)
        v.pan_offset = [random.uniform(*pan_range), random.uniform(*pan_range)]
        v.is_geometry_dirty = True
        controller.sync.propagate_camera(v)

    def action_random_zoom():
        v = random.choice(viewers)
        v.zoom = random.uniform(*zoom_range)
        v.is_geometry_dirty = True
        controller.sync.propagate_camera(v)

    def action_random_crosshair():
        v = random.choice(viewers)
        # We pass coordinates that might be mathematically absurd
        px, py = random.uniform(*coord_range), random.uniform(*coord_range)
        v.update_crosshair_data(px, py)
        controller.sync.propagate_sync(v.image_id)

    def action_random_slice():
        v = random.choice(viewers)
        # Randomly throw it past the bounds of the volume
        v.slice_idx = random.randint(-50, 500)
        v.update_crosshair_from_slice()
        controller.sync.propagate_sync(v.image_id)

    def action_random_spatial_sync():
        vid = random.choice(vs_ids)
        # 0 = Unsynced, 1 = Group 1, 2 = Group 2
        controller.set_sync_group(vid, random.choice([0, 1, 2]))

    def action_random_wl_sync():
        vid = random.choice(vs_ids)
        vs = controller.view_states[vid]
        vs.sync_wl_group = random.choice([0, 1, 2])
        # Trigger the newly fixed instant-broadcast
        controller.sync.propagate_window_level(vid)

    def action_random_window_level():
        v = random.choice(viewers)
        # Width must be positive, Level can be anything
        ww = max(1e-5, random.uniform(0.1, 2000.0))
        wl = random.uniform(*wl_range)
        v.update_window_level(ww, wl)

    def action_hard_reset():
        vid = random.choice(vs_ids)
        controller.reset_image_view(vid, hard=True)
        controller.update_all_viewers_of_image(vid)

        # State-Only Fix: The monkey MUST broadcast ALL newly reset values!
        controller.sync.propagate_window_level(vid)
        controller.sync.propagate_colormap(vid)
        controller.sync.propagate_overlay_mode(vid)

        # ADD THIS: Pull all grouped images back to the center!
        controller.sync.propagate_sync(vid)

    def action_random_fusion():
        """Randomly mounts, unmounts, or alters an overlay on a base image."""
        vid_base = random.choice(vs_ids)
        vid_overlay = random.choice([v for v in vs_ids if v != vid_base])
        vs = controller.view_states[vid_base]

        # 50% chance to remove overlay if it exists, 50% chance to add/modify it
        if (
            getattr(vs.display, "overlay_id", None) == vid_overlay
            and random.random() > 0.5
        ):
            vs.set_overlay(None, None, controller)
        else:
            vs.set_overlay(vid_overlay, controller.volumes[vid_overlay], controller)
            vs.display.overlay_mode = random.choice(
                ["Alpha", "Registration", "Checkerboard"]
            )
            vs.display.overlay_opacity = random.uniform(0.1, 1.0)
            # Force the UI to refresh the new texture
            controller.update_all_viewers_of_image(vid_base)

    def action_random_registration():
        """Violently shifts the spatial matrix of an image."""
        vid = random.choice(vs_ids)
        tx, ty, tz = (
            random.uniform(-50, 50),
            random.uniform(-50, 50),
            random.uniform(-50, 50),
        )
        # Only applying translation to avoid complex rotation math assertions in this test
        controller.update_transform_manual(vid, tx, ty, tz, 0.0, 0.0, 0.0)

        # The monkey forces the sync manager to resolve the new spatial reality
        controller.view_states[vid].is_geometry_dirty = True
        for v in viewers:
            if v.image_id == vid:
                controller.sync.propagate_camera(v)
        controller.sync.propagate_sync(vid)

    def action_reload_image():
        """Simulates the user rapidly hitting 'Reload' on an active memory buffer."""
        vid = random.choice(vs_ids)
        controller.reload_image(vid)

        # The monkey must broadcast that the image was reset to the sync group
        controller.sync.propagate_window_level(vid)
        controller.sync.propagate_colormap(vid)
        controller.sync.propagate_sync(vid)

    arsenal = [
        action_random_pan,
        action_random_zoom,
        action_random_crosshair,
        action_random_slice,
        action_random_spatial_sync,
        action_random_wl_sync,
        action_random_window_level,
        action_hard_reset,
        action_random_fusion,
        action_random_registration,
        action_reload_image,
    ]

    # 3. RELEASE THE MONKEY
    for frame in range(NUM_FRAMES):
        # Pick 1 to 5 random actions to execute SIMULTANEOUSLY on this frame
        num_actions = random.randint(1, 5)
        for _ in range(num_actions):
            action = random.choice(arsenal)
            action()  # INVARIANT 1: No math exceptions thrown!

        # Resolve the chaos
        controller.tick()

        # 4. AUDIT THE INVARIANTS (Les Garde-Fous)

        # INVARIANT 2: Spatial Sync groups must share identical physical coordinates
        for group_id in [1, 2]:
            group_members = [
                vs
                for vs in controller.view_states.values()
                if vs.sync_group == group_id
            ]
            if len(group_members) > 1:
                master_coord = group_members[0].camera.crosshair_phys_coord
                for member in group_members[1:]:
                    # The spatial math MUST resolve to the exact same physical sub-millimeter coordinate
                    if (
                        master_coord is not None
                        and member.camera.crosshair_phys_coord is not None
                    ):
                        np.testing.assert_allclose(
                            master_coord,
                            member.camera.crosshair_phys_coord,
                            atol=1e-3,
                            err_msg=f"Frame {frame}: Spatial Sync torn! Group {group_id} failed to align.",
                        )

        # INVARIANT 3: Window/Level groups must share identical radiometric values
        for group_id in [1, 2]:
            group_members = [
                vs
                for vs in controller.view_states.values()
                if getattr(vs, "sync_wl_group", 0) == group_id
            ]
            if len(group_members) > 1:
                master_ww = group_members[0].display.ww
                master_wl = group_members[0].display.wl
                for member in group_members[1:]:
                    # Skip RGB images which don't participate in W/L sync
                    if not getattr(member.volume, "is_rgb", False):
                        assert (
                            abs(master_ww - member.display.ww) < 1e-5
                        ), f"Frame {frame}: W/L Sync torn for Width!"
                        assert (
                            abs(master_wl - member.display.wl) < 1e-5
                        ), f"Frame {frame}: W/L Sync torn for Level!"

        # INVARIANT 4: Coordinate Sanity (No NaNs, No Infs)
        for vs in controller.view_states.values():
            coord = vs.camera.crosshair_phys_coord
            if coord is not None:
                assert np.all(
                    np.isfinite(coord)
                ), f"Frame {frame}: Spatial engine generated a NaN/Inf coordinate!"

            vox = vs.camera.crosshair_voxel
            if vox is not None:
                assert np.all(
                    np.isfinite(vox)
                ), f"Frame {frame}: Spatial engine generated a NaN/Inf voxel!"

    # If we made it through 500 frames of pure chaos without an assertion firing
    # or the main thread crashing, the State-Only architecture is mathematically sound.
    assert True
