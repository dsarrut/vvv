"""The native-overlay culling bbox follows the frame of a 4D overlay."""

import numpy as np

from vvv.ui.render_strategy import _nonzero_bbox


class _Vol:
    pass


def test_bbox_is_per_frame_and_per_threshold():
    data = np.zeros((2, 10, 20, 20), np.float32)
    data[0, 1:3, 2:4, 2:4] = 5.0  # frame 0: near the origin
    data[1, 6:9, 14:18, 15:19] = 5.0  # frame 1: opposite corner
    vol = _Vol()
    assert _nonzero_bbox(vol, data[0], 0, 1.0) == (2, 4, 2, 4, 1, 3)
    assert _nonzero_bbox(vol, data[1], 1, 1.0) == (15, 19, 14, 18, 6, 9)
    assert _nonzero_bbox(vol, data[0], 0, 9.0) == (0, 20, 0, 20, 0, 10)  # nothing above
