import numpy as np
from vvv.maths.image import SliceRenderer
from vvv.config import COLORMAPS


def test_lut_lookup_does_not_mutate_norm():
    """Regression test for a bug (introduced 2026-07-10, fixed 2026-07-29) where
    lut_lookup() scaled its `norm` argument to [0,255] in place. _colorize_layer()
    returns that same array back as base_norm/over_norm, and _blend_registration()
    (Registration/diff fusion mode) consumes those expecting [0,1] — the in-place
    scaling silently fed it values ~255x too large, turning any real per-pixel
    difference between two images into saturated color noise. Alpha-blend mode
    never showed the bug since it doesn't use base_norm/over_norm at all.
    """
    norm = np.array([[0.0, 0.25], [0.5, 1.0]], dtype=np.float32)
    norm_before = norm.copy()

    SliceRenderer.lut_lookup(COLORMAPS["Grayscale"], norm)

    assert np.array_equal(norm, norm_before), (
        "lut_lookup() must not mutate its `norm` argument in place"
    )


def test_colorize_layer_norm_stays_in_unit_range():
    """End-to-end version of the same contract: _colorize_layer()'s returned norm
    (used as base_norm/over_norm by _blend_registration) must stay in [0,1]."""
    slice_data = np.array([[-100.0, 0.0], [300.0, 1000.0]], dtype=np.float32)

    _, norm = SliceRenderer._colorize_layer(
        slice_data, False, 1, ww=600.0, wl=0.0, cmap_name="Grayscale", threshold=None
    )

    assert norm.min() >= 0.0
    assert norm.max() <= 1.0


def test_blend_registration_output_bounded_for_normalized_inputs():
    """Sanity check on _blend_registration()'s output range: for genuinely
    normalized ([0,1]) base/overlay inputs, the result must stay roughly in
    [0,1] too. This would have caught the 255x-amplified-norm bug as a coarse
    signal even without pinpointing lut_lookup() as the cause."""
    h, w = 8, 8
    rng = np.random.default_rng(0)
    base_norm = rng.random((h, w), dtype=np.float32)
    over_norm = rng.random((h, w), dtype=np.float32)

    base_rgba = np.zeros((h, w, 4), dtype=np.float32)
    base_rgba[..., :3] = base_norm[..., None]
    base_rgba[..., 3] = 1.0

    over_rgba = np.zeros((h, w, 4), dtype=np.float32)
    over_rgba[..., :3] = over_norm[..., None]
    over_rgba[..., 3] = 1.0

    res = SliceRenderer._blend_registration(
        base_rgba, base_norm, over_rgba, over_norm, False, False, opacity=0.5
    )

    assert res[..., :3].min() >= -1e-5
    assert res[..., :3].max() <= 1.0 + 1e-5
