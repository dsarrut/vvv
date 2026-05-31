import numpy as np
from vvv.plugins.mip.math_mip import compute_mip_projection


def test_mip_projections():
    # Create a simple 3D volume (D=4, H=3, W=5)
    data = np.zeros((4, 3, 5), dtype=np.float32)
    data[2, 1, 3] = 100.0  # z=2, y=1, x=3
    data[0, 2, 4] = 50.0   # z=0, y=2, x=4

    # 1. Project along Z (axial) -> output shape (H=3, W=5)
    mip_z = compute_mip_projection(data, axis="Z", depth_cueing=False)
    assert mip_z.shape == (3, 5)
    assert mip_z[1, 3] == 100.0
    assert mip_z[2, 4] == 50.0

    # 2. Project along Y (coronal) -> output shape (D=4, W=5)
    mip_y = compute_mip_projection(data, axis="Y", depth_cueing=False)
    assert mip_y.shape == (4, 5)
    assert mip_y[2, 3] == 100.0
    assert mip_y[0, 4] == 50.0

    # 3. Project along X (sagittal) -> output shape (D=4, H=3)
    mip_x = compute_mip_projection(data, axis="X", depth_cueing=False)
    assert mip_x.shape == (4, 3)
    assert mip_x[2, 1] == 100.0
    assert mip_x[0, 2] == 50.0


def test_mip_depth_cueing():
    # Create a volume where voxel values increase along Z
    data = np.zeros((10, 3, 3), dtype=np.float32)
    for z in range(10):
        data[z, :, :] = float(z + 1) * 10.0  # z=0: 10, z=9: 100

    # With no depth cueing, the maximum value (100.0) is at z=9
    mip_z_no_cue = compute_mip_projection(data, axis="Z", depth_cueing=False)
    assert np.allclose(mip_z_no_cue, 100.0)

    # With depth cueing (strength=0.9):
    # At z=0: factor = 1.0 -> 10.0 * 1.0 = 10.0
    # At z=9: factor = 1.0 - 0.9 * (9/9) = 0.1 -> 100.0 * 0.1 = 10.0
    # Let's check a middle voxel, e.g. z=5: value = 60.0. factor = 1.0 - 0.9 * (5/9) = 0.5 -> 60.0 * 0.5 = 30.0
    # The maximum attenuated value along the ray should be greater than 10.0.
    mip_z_cue = compute_mip_projection(data, axis="Z", depth_cueing=True, depth_cueing_strength=0.9)
    assert np.all(mip_z_cue > 10.0)
    assert np.allclose(mip_z_cue, 30.0)  # Max should be 30.0 at z=5


def test_mip_rotation():
    # Simple volume (D=5, H=5, W=5)
    data = np.zeros((5, 5, 5), dtype=np.float32)
    data[2, 2, 2] = 100.0  # Center voxel is hot-spot
    
    # 0 degree rotation should match non-rotated projection
    mip_y_0 = compute_mip_projection(data, axis="Y", depth_cueing=False, rotation_angle=0.0)
    mip_y_normal = compute_mip_projection(data, axis="Y", depth_cueing=False)
    assert np.allclose(mip_y_0, mip_y_normal)
    
    # 45 degree rotation
    mip_y_45 = compute_mip_projection(data, axis="Y", depth_cueing=False, rotation_angle=45.0)
    assert mip_y_45.shape == mip_y_normal.shape
    # Center voxel (2,2) should still project to the center area
    assert mip_y_45[2, 2] == 100.0


