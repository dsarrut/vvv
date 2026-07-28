"""Quick benchmark of compute_software_nearest_neighbor at various zoom levels."""
import numpy as np
import time
from vvv.ui.render_strategy import compute_software_nearest_neighbor

# Simulate typical medical image sizes
for img_size, canvas in [(512, 1000), (512, 2000), (256, 1000), (128, 1000)]:
    rgba = np.random.rand(img_size, img_size, 4).astype(np.float32)
    canvas_w, canvas_h = canvas, canvas
    buf = np.zeros((canvas_h, canvas_w, 4), dtype=np.float32)

    # Simulate zoomed-in: image covers full canvas (pmin near 0, pmax near canvas)
    pmin = [0, 0]
    pmax = [canvas_w, canvas_h]

    # Warmup
    compute_software_nearest_neighbor(rgba, pmin, pmax, canvas_w, canvas_h, out_buffer=buf)

    # Benchmark
    N = 20
    t0 = time.perf_counter()
    for _ in range(N):
        result, crop = compute_software_nearest_neighbor(
            rgba, pmin, pmax, canvas_w, canvas_h, out_buffer=buf
        )
        # Simulate what the upload path does
        flat = result.ravel()
    dt = (time.perf_counter() - t0) / N * 1000
    print(f"  img={img_size}x{img_size}  canvas={canvas_w}x{canvas_h}  "
          f"result_shape={result.shape}  time={dt:.1f}ms  "
          f"ravel_is_view={flat.base is result}")

    # Now simulate deep zoom: only a portion of image visible
    pmin2 = [100, 100]
    pmax2 = [canvas_w + 100, canvas_h + 100]
    t0 = time.perf_counter()
    for _ in range(N):
        result2, crop2 = compute_software_nearest_neighbor(
            rgba, pmin2, pmax2, canvas_w, canvas_h, out_buffer=buf
        )
        flat2 = result2.ravel()
    dt2 = (time.perf_counter() - t0) / N * 1000
    print(f"  img={img_size}x{img_size}  canvas={canvas_w}x{canvas_h} (partial) "
          f"result_shape={result2.shape}  time={dt2:.1f}ms")
