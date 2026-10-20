"""SliceRenderer.lut_lookup gives exactly the plain lut[index] result."""

import numpy as np
import pytest

from vvv.config import COLORMAPS
from vvv.maths.image import SliceRenderer


@pytest.mark.parametrize("name", sorted(COLORMAPS))
@pytest.mark.parametrize("shape", [(1, 1), (37, 53), (512, 512)])
def test_lut_lookup_matches_fancy_indexing(name, shape):
    lut = COLORMAPS[name]
    norm = np.random.default_rng(0).random(shape, dtype=np.float32)
    norm.flat[:3] = [0.0, 1.0, 0.999999]  # bounds
    idx = (norm * 255.0).astype(np.uint8)
    out = SliceRenderer.lut_lookup(lut, norm)
    assert out.dtype == lut.dtype and out.shape == shape + lut.shape[1:]
    assert np.array_equal(out, lut[idx])


def test_results_are_independent_buffers():
    lut = COLORMAPS["Grayscale"]
    a = SliceRenderer.lut_lookup(lut, np.zeros((8, 8), np.float32))
    b = SliceRenderer.lut_lookup(lut, np.ones((8, 8), np.float32))
    assert not np.shares_memory(a, b) and a[0, 0, 0] != b[0, 0, 0]
