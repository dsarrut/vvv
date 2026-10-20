"""The numba W/L + colormap kernel gives exactly the numpy path's result."""

import warnings

import numpy as np
import pytest

import vvv.maths.image as image
from vvv.maths.image import SliceRenderer

pytest.importorskip("numba")

DTYPES = (np.int16, np.uint8, np.uint16, np.int32, np.float32, np.float64)


def _slice(dtype):
    base = np.random.default_rng(1).normal(100, 600, (64, 80))
    if np.dtype(dtype).kind == "f":
        sl = base.astype(dtype)
        sl.flat[:4] = [np.nan, np.inf, -np.inf, 0.1]
        return sl
    info = np.iinfo(dtype)
    return np.clip(base, info.min, info.max).astype(dtype)


def _numpy_path(view, ww, wl, cmap, thr, monkeypatch):
    with monkeypatch.context() as m:
        m.setitem(image._fast, "disabled", True)
        return SliceRenderer._colorize_layer(view, False, 1, ww, wl, cmap, thr)


@pytest.mark.parametrize("dtype", DTYPES)
def test_fast_path_is_bit_identical(dtype, monkeypatch):
    warnings.simplefilter("ignore", RuntimeWarning)
    sl = _slice(dtype)
    for view in (sl, sl[::-1, ::-1]):  # contiguous and flipped (strided) slices
        key = image._fast_signature_key(view)
        image._compile_fast_signature(key, view.dtype)  # synchronous, for the test
        if image._fast["disabled"]:
            pytest.skip("no thread-safe numba threading layer")
        assert key in image._fast["ready"]
        for cmap in ("Grayscale", "Jet", "Hot"):
            for ww, wl, thr in [(400.0, 40.0, None), (2000.0, 0.0, 50.0), (0.37, 0.1, 0.1)]:
                fast = image._fast_colorize(view, ww, wl, image.COLORMAPS[cmap], thr)
                assert fast is not None
                ref_rgba, ref_norm = _numpy_path(view, ww, wl, cmap, thr, monkeypatch)
                assert np.array_equal(fast[0], ref_rgba)
                assert np.array_equal(fast[1], ref_norm, equal_nan=True)


def test_unready_signature_uses_numpy_path(monkeypatch):
    monkeypatch.setattr(image, "_request_fast_compile", lambda key, dtype: None)
    sl = np.zeros((4, 4), np.int8)  # int8: never compiled above
    assert image._fast_colorize(sl, 1.0, 0.5, image.COLORMAPS["Jet"], None) is None
    rgba, norm = SliceRenderer._colorize_layer(sl, False, 1, 1.0, 0.5, "Jet", None)
    assert rgba.shape == (4, 4, 4)
