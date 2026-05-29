"""
Mixed-feature integration tests.

Each test exercises two or more features together on real loaded volumes.
controller.tick() drives viewer.tick() for all viewers, which triggers
the threshold update_preview path and geometry updates.
"""
import numpy as np
from vvv.core.view_state import ProfileLineState
from vvv.utils import ViewMode


def make_profile(pt1, pt2) -> ProfileLineState:
    p = ProfileLineState()
    p.pt1_phys = np.array(pt1, dtype=float)
    p.pt2_phys = np.array(pt2, dtype=float)
    return p


def _get_threshold_plugin(gui):
    return next(p for p in gui.plugins if p.plugin_id == "threshold_plugin")


def _enable_threshold(gui, vs_id, thr_min, thr_max, viewer=None):
    thr = _get_threshold_plugin(gui)
    state = thr._controller.get_image_state(vs_id)
    state.is_enabled = True
    state.show_preview = True
    state.threshold_min = thr_min
    state.threshold_max = thr_max
    if viewer is not None:
        viewer.is_geometry_dirty = True
    return thr


def _roi_min(vs):
    return next(
        (c for c in vs.contours.values() if getattr(c, "is_plugin_draft_min", False)),
        None,
    )


# ---------------------------------------------------------------------------
# Test 1: Profile on 4D volume samples from the current timepoint
# ---------------------------------------------------------------------------

def test_4d_profile_follows_time_scrub(headless_4d_overlay_app):
    controller, gui, _, _, viewer_v2, vs_id_4d = headless_4d_overlay_app
    vs = controller.view_states[vs_id_4d]

    # Profile along X through the centre of the volume
    profile = make_profile([1.0, 10.0, 15.0], [18.0, 10.0, 15.0])

    means = []
    for t in range(4):
        vs.camera.time_idx = t
        dist, vals = controller.profiles.get_profile_data(vs_id_4d, profile)
        assert dist is not None and vals is not None, f"No profile data at t={t}"
        means.append(float(np.mean(vals)))

    # Frame t has all voxels = t*50 → means should be 0, 50, 100, 150
    for t in range(4):
        assert abs(means[t] - t * 50.0) < 2.0, f"t={t}: expected ~{t*50}, got {means[t]}"

    # Strictly increasing — no stale caching across timepoints
    assert means[0] < means[1] < means[2] < means[3]


# ---------------------------------------------------------------------------
# Test 2: Threshold contour cache invalidates when time_idx changes
# ---------------------------------------------------------------------------

def test_threshold_cache_invalidates_on_time_scrub(headless_4d_overlay_app):
    controller, gui, _, _, viewer_v2, vs_id_4d = headless_4d_overlay_app
    vs = controller.view_states[vs_id_4d]

    # Enable threshold: range 60-200. At t=0 all voxels=0 (below), at t=2 all=100 (above).
    _enable_threshold(gui, vs_id_4d, thr_min=60.0, thr_max=200.0, viewer=viewer_v2)

    # --- Timepoint 0: all voxels = 0, nothing above threshold ---
    vs.camera.time_idx = 0
    controller.tick()

    roi = _roi_min(vs)
    assert roi is not None, "Threshold plugin should have created preview ROI after tick"
    assert roi.last_computed_time_idx == 0

    # --- Timepoint 2: all voxels = 100, above threshold 60 ---
    vs.camera.time_idx = 2
    controller.tick()

    roi = _roi_min(vs)
    assert roi is not None
    assert roi.last_computed_time_idx == 2, (
        f"Cache not invalidated: last_computed_time_idx={roi.last_computed_time_idx}"
    )

    # At t=2, voxels=100 > threshold 60 → contours should be computed for the current slice
    polys_t2 = roi.polygons.get(ViewMode.AXIAL, {}).get(viewer_v2.slice_idx, None)
    if polys_t2 is not None:
        assert len(polys_t2) > 0, "Expected non-empty contours at t=2 (all voxels above threshold)"


# ---------------------------------------------------------------------------
# Test 3: Threshold contours survive overlay mount and unmount
# ---------------------------------------------------------------------------

def test_threshold_contours_survive_overlay_mount_unmount(headless_4d_overlay_app):
    controller, gui, viewer_v1, vs_id_3d, _, vs_id_4d = headless_4d_overlay_app
    vs = controller.view_states[vs_id_3d]
    vol4d = controller.volumes[vs_id_4d]

    # Enable threshold on 3D base (all voxels=100): range 50-200 → contours appear
    _enable_threshold(gui, vs_id_3d, thr_min=50.0, thr_max=200.0, viewer=viewer_v1)
    controller.tick()

    roi = _roi_min(vs)
    assert roi is not None, "Threshold ROI should exist after first tick"
    roi_id_before = id(roi)

    # Mount 4D volume as overlay
    vs.set_overlay(vs_id_4d, vol4d, controller)
    controller.tick()

    roi_after_mount = _roi_min(vs)
    assert roi_after_mount is not None, "Threshold ROI should survive overlay mount"
    assert id(roi_after_mount) == roi_id_before, "ROI object should not be recreated on overlay mount"

    # Unmount overlay
    vs.set_overlay(None, None)
    controller.tick()

    roi_after_unmount = _roi_min(vs)
    assert roi_after_unmount is not None, "Threshold ROI should survive overlay unmount"


# ---------------------------------------------------------------------------
# Test 4: Profile values are unchanged by overlay mount / unmount
# ---------------------------------------------------------------------------

def test_profile_stable_across_overlay_mount_unmount(headless_4d_overlay_app):
    controller, gui, viewer_v1, vs_id_3d, _, vs_id_4d = headless_4d_overlay_app
    vs = controller.view_states[vs_id_3d]
    vol4d = controller.volumes[vs_id_4d]

    profile = make_profile([1.0, 10.0, 15.0], [18.0, 10.0, 15.0])

    _, vals_before = controller.profiles.get_profile_data(vs_id_3d, profile)
    assert vals_before is not None

    vs.set_overlay(vs_id_4d, vol4d, controller)
    controller.tick()
    _, vals_with_overlay = controller.profiles.get_profile_data(vs_id_3d, profile)

    vs.set_overlay(None, None)
    controller.tick()
    _, vals_after = controller.profiles.get_profile_data(vs_id_3d, profile)

    # Profile always samples from the base volume (all-100) — overlay must not affect values
    assert np.allclose(vals_before, vals_with_overlay, atol=1.0), \
        "Profile values changed when overlay was mounted"
    assert np.allclose(vals_before, vals_after, atol=1.0), \
        "Profile values changed after overlay was unmounted"
    assert all(abs(v - 100.0) < 1.0 for v in vals_before), \
        f"Base profile values should be ~100.0, got {vals_before[:3]}"


# ---------------------------------------------------------------------------
# Test 5: 4D base + 3D overlay — time scrub beyond overlay frame count is safe
# ---------------------------------------------------------------------------

def test_4d_base_3d_overlay_time_scrub_no_crash(headless_4d_overlay_app):
    controller, gui, _, vs_id_3d, viewer_v2, vs_id_4d = headless_4d_overlay_app
    vs4d = controller.view_states[vs_id_4d]
    vol3d = controller.volumes[vs_id_3d]

    # Mount 3D (1 timepoint) as overlay on 4D base (4 timepoints)
    vs4d.set_overlay(vs_id_3d, vol3d, controller)

    for t in [0, 1, 2, 3, 5]:  # t=5 exceeds num_timepoints=4
        vs4d.camera.time_idx = t
        controller.tick()  # must not raise

    # Overlay must remain mounted throughout — rendering the clamped frame must not clear it
    assert vs4d.display.overlay.image_id == vs_id_3d, \
        "Overlay was unexpectedly cleared during time scrub"


# ---------------------------------------------------------------------------
# Test 6: Profile and threshold contours coexist without interfering
# ---------------------------------------------------------------------------

def test_profile_and_threshold_coexist(headless_4d_overlay_app):
    controller, gui, viewer_v1, vs_id_3d, _, _ = headless_4d_overlay_app
    vs = controller.view_states[vs_id_3d]

    # Enable threshold on 3D base
    _enable_threshold(gui, vs_id_3d, thr_min=50.0, thr_max=200.0, viewer=viewer_v1)

    # Inject a profile directly into the view state
    profile = make_profile([1.0, 10.0, 15.0], [18.0, 10.0, 15.0])
    profile.id = "mixed_test_profile"
    vs.profiles["mixed_test_profile"] = profile

    controller.tick()

    # Profile must not have been cleared by threshold logic
    assert "mixed_test_profile" in vs.profiles, \
        "Threshold logic cleared the profile during tick"

    # Threshold ROI must not have been cleared by profile logic
    roi = _roi_min(vs)
    assert roi is not None, "Profile logic cleared threshold contours during tick"

    # Profile data must still be extractable
    dist, vals = controller.profiles.get_profile_data(vs_id_3d, profile)
    assert vals is not None
    assert all(abs(v - 100.0) < 1.0 for v in vals), \
        f"Profile values should be ~100.0, got {vals[:3]}"
