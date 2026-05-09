
# Developer Guide: Rendering Pipeline

This document describes the rendering strategies, platform-specific paths, interaction optimizations, and default configuration for each platform.

---

## 1. Architecture Overview

Every viewer frame goes through three stages:

1. **Slice extraction** — CPU extracts a 2D RGBA slice from the 3D volume (`SliceRenderer.get_slice_rgba`), storing it in `last_rgba_flat` (base) and `last_overlay_rgba_flat` (overlay, fusion only).
2. **Texture preparation** — `_upload_base_texture()` and `_upload_overlay_texture()` convert the raw slices into GPU-ready arrays, applying NN upscaling if needed.
3. **GPU draw** — DearPyGui uploads the texture(s) and stretches them to fill the viewer canvas.

The rendering strategy (which code path steps 2–3 take) is determined by `viewer.nn_mode` and `viewer.lazy_lin`, both computed from the rendering config and the current fusion state.

---

## 2. User-Facing Controls

| Control | Effect |
|---|---|
| **K** | Toggle NN / Linear interpolation (strictly two-state; never touches Strip mode) |
| **M** | Toggle Voxel Strip mode (independent of K) |
| **Rendering → NN Options** | Advanced submenu — tune lazy-lin, texture mode, voxel mode, hardware filter, Numba |

The "Rendering" menu item label updates live to show the **effective active mode**:
- NN off → `NN Interpolation  [K]`
- NN on, macOS, no fusion → `NN: Dual-Native  [K]`
- NN on, macOS, with fusion → `NN: Single-Native + Lazy  [K]`
- NN on, Linux → `NN: HW GL_NEAREST  [K]`

**Debug-only keys** (require `--debug` flag): `J` cycles texture/voxel sub-modes, `T` cycles lazy-lin states.

---

## 3. Rendering Modes (`NNMode` enum)

Defined in `render_strategy.py`:

```
NNMode.HW_GL_NEAREST     = 0   GPU GL_NEAREST filter — Linux/Windows only
NNMode.SW_DUAL_NATIVE    = 1   2 textures; overlay at true voxel resolution
NNMode.SW_DUAL_RESAMPLED = 2   2 textures; overlay NN-scaled from ITK-resampled grid
NNMode.SW_SINGLE_MERGED  = 3   1 texture; CPU alpha-blend base+overlay then NN scale
NNMode.SW_SINGLE_NATIVE  = 4   1 texture; NN base + native-voxel overlay painted in
```

### HW GL_NEAREST (Linux & Windows only)
Both base and overlay remain as small native-resolution textures. VVV injects `glTexParameteri(GL_NEAREST)` via ctypes (`try_set_gl_nearest()`) so the GPU handles blocky upscaling at near-zero CPU cost.

### SW Dual-Native
Two canvas-sized textures:
- **Base** — upscaled by `compute_software_nearest_neighbor()` (RLE `np.repeat` trick, avoids scatter-gather).
- **Overlay** — rendered by `compute_native_voxel_overlay()`: analytically maps canvas pixels backward through registration matrices directly into the raw 3D overlay array, preserving true physical voxel size (e.g. 4 mm SPECT blocks over 1 mm CT). **Numba-accelerated when available (~40× faster than NumPy)**.

### SW Dual-Resampled
Two canvas-sized textures, both upscaled via RLE from ITK-resampled slice grids. Faster than Dual-Native but loses the true voxel size of the overlay.

### SW Single-Merged
One canvas-sized texture. Alpha-blends the ITK-resampled overlay onto the base slice on the CPU (`blend_slices_cpu`), then runs RLE upscaling on the combined image. Halves GPU upload bandwidth.

### SW Single-Native
One canvas-sized texture. RLE-upscales the base, then `compute_native_voxel_overlay()` alpha-blends native-voxel overlay pixels directly into the same buffer before upload. **Numba-accelerated**. Default on macOS with fusion.

---

## 4. Mode Selection Logic

Mode and lazy-lin are computed by two **pure functions** in `render_strategy.py`, which makes them independently testable:

```python
select_nn_mode(cfg: dict, has_fusion: bool) -> NNMode
should_use_lazy_lin(cfg: dict, has_fusion: bool, is_hw: bool, use_numba: bool = False) -> bool
```

`viewer.nn_mode` and `viewer.lazy_lin` are thin property wrappers that call these functions with the current settings config and `viewer.has_fusion`.

`has_fusion` is true when the viewer displays an overlay in Alpha mode (`vs.display.overlay_mode == "Alpha"`).

The `select_nn_mode` logic, in priority order:
1. If `GL_NEAREST_SUPPORTED` and `cfg["gl_nearest"]` → `HW_GL_NEAREST`
2. `single_texture` setting: `"Auto"` → Single only if `has_fusion`; else explicit Single/Dual
3. `native_voxel` setting: `"Auto"` → always Native; else explicit Native/Resampled
4. Combine → one of the four SW modes

---

## 5. Lazy Rendering (Interaction Optimization)

Heavy CPU NN computations would drop framerate during continuous interaction (pan, zoom, W/L drag). The **lazy-lin** system solves this:

- **During interaction** (`_lazy_live_flag = True`): `_effective_pixelated_zoom()` returns `False`, so the viewer uses GPU bilinear (cheapest possible path). The lazy flag is set by `_mark_lazy_interaction()`.
- **After 150 ms of inactivity** (`lazy_settle_ms`): the settle timer fires, `is_geometry_dirty` and `is_viewer_data_dirty` are set, and the viewer re-renders at full NN quality.

### What triggers `_mark_lazy_interaction()`

`_mark_lazy_interaction()` iterates **all viewers** and marks those with `lazy_lin=True` as lazy-live. It is therefore called unconditionally (no guard on `self.lazy_lin`) at every interaction site, so that viewers **synced to** the interacting viewer also benefit:

| Interaction | File |
|---|---|
| Pan drag (Ctrl+mouse) | `viewer.py` `on_drag()` |
| Zoom (scroll wheel / I/O keys) | `viewer.py` `on_zoom()` |
| Auto-window (W/X keys) | `viewer.py` `apply_local_auto_window()` |
| W/L slider | `ui_intensities.py` `on_ww_changed()`, `on_wl_changed()` |
| W/L mouse drag (Shift+drag) | `ui_interaction.py` `on_mouse_move()` |

**Cross-viewer example:** viewer B (no fusion, `lazy_lin=False`) pans → `_mark_lazy_interaction()` is still called → synced A+B viewers (fusion, `lazy_lin=True`) correctly enter lazy mode.

### Crosshair drag (orientation-aware lazy)

Dragging the crosshair in orientation X forces other orientations to re-slice. The code in `on_drag()` directly marks only **differently-oriented** synced viewers:

```python
if v.orientation != self.orientation and v.lazy_lin:
    ...mark v lazy...
```

Same-orientation viewers are not marked lazy because a crosshair drag in the same plane does not change their slice position. `self.lazy_lin` is not checked — so a B-only viewer dragging its crosshair correctly lazifies the A+B coronal/sagittal viewers.

### Scroll-wheel slicing

Scroll slicing (`on_scroll`) does **not** use lazy-lin. The bottleneck there is the CPU slice extraction from the volume, not NN upscaling, so lazy-lin would not help.

---

## 6. Numba Acceleration

`compute_native_voxel_overlay` is the most expensive call in the SW NN paths (~20–100 ms for large overlays in NumPy). A Numba JIT kernel `_native_ov_kernel_nb` replaces the inner loop when Numba is installed.

**Benchmark (500×800 canvas crop, 200×256×256 overlay):**
- NumPy: ~22 ms per call
- Numba (`parallel=True`, `fastmath=True`): ~0.6 ms per call
- **~40× speedup**

Why so fast:
- No intermediate 2D arrays (`s_x`, `s_y`, `s_z` at canvas size) — computed per-pixel inline
- Row contribution hoisted out of inner loop
- Per-pixel early exit for out-of-bounds
- `numba.prange` parallelises across rows using all CPU cores

**Enabling / disabling:** the "Numba Acceleration" checkbox in the NN Options submenu writes `cfg["rendering"]["numba"]`. Disabling falls back to the NumPy path (useful for debugging pixel-level differences).

Numba JIT-compiles on first call per dtype and caches to disk (`cache=True`). Expect a 2–5 s pause on first launch after install or code change.

---

## 7. Key Files

| File | Responsibility |
|---|---|
| `render_strategy.py` | `NNMode` enum, `select_nn_mode`, `should_use_lazy_lin`, `compute_software_nearest_neighbor`, `compute_native_voxel_overlay`, Numba kernel |
| `viewer.py` | `has_fusion`, `nn_mode`, `lazy_lin`, `_is_hw_gl` properties; `_mark_lazy_interaction`, `_effective_pixelated_zoom`, `_upload_base_texture`, `_upload_overlay_texture` |
| `ui_interaction.py` | Mouse/keyboard event routing; W/L drag lazy marking |
| `ui_intensities.py` | W/L slider lazy marking |
| `gui.py` | Rendering menu construction and sync (`build_menu_bar`, `_init_rendering_menu`, `on_adv_rendering_changed`) |
| `config.py` | Default rendering settings |

---

## 8. Default Options Per Platform

### macOS — no fusion

| Setting | Value | Effective |
|---|---|---|
| `gl_nearest` | `True` | **ignored** — GL_NEAREST not supported on macOS |
| `single_texture` | `"Auto"` | → **Dual** (no fusion) |
| `native_voxel` | `"Auto"` | → **Native** |
| `lazy_lin` | `"Auto"` | → **Off** (no fusion) |
| `numba` | `True` | → **On** |
| **Active mode** | | **SW Dual-Native** (Numba) |

During interaction (pan/zoom): full NN quality at all times (no lazy-lin). The Numba kernel keeps the overlay render fast enough that this is acceptable.

### macOS — with fusion (Alpha overlay)

| Setting | Value | Effective |
|---|---|---|
| `gl_nearest` | `True` | **ignored** |
| `single_texture` | `"Auto"` | → **Single** (fusion active) |
| `native_voxel` | `"Auto"` | → **Native** |
| `lazy_lin` | `"Auto"` | → **Off** (Numba makes full NN fast enough) |
| `numba` | `True` | → **On** |
| **Active mode** | | **SW Single-Native** (Numba, no lazy) |

Full NN per frame costs ~0.8–3 ms with Numba (benchmark at 1000×650 canvas, 512×512 base, 256×256×200 overlay), well within the 16.7 ms/frame budget at 60 fps. Lazy-lin adds a 150 ms settle delay with no quality benefit, so Auto disables it when Numba is active.

If Numba is disabled (or not installed), Auto re-enables lazy-lin for fusion viewers, reverting to the bilinear-during-drag / settle pattern.

### Linux / Windows — no fusion

| Setting | Value | Effective |
|---|---|---|
| `gl_nearest` | `True` | → **On** |
| `lazy_lin` | `"Auto"` | → **Off** (HW path) |
| `numba` | `True` | → **unused** (HW path skips `compute_native_voxel_overlay`) |
| **Active mode** | | **HW GL_NEAREST** |

GPU handles all NN upscaling at zero CPU cost. Lazy-lin is disabled because HW GL_NEAREST is already fast enough.

### Linux / Windows — with fusion (Alpha overlay)

| Setting | Value | Effective |
|---|---|---|
| `gl_nearest` | `True` | → **On** |
| `lazy_lin` | `"Auto"` | → **Off** (HW path) |
| `numba` | `True` | → **unused** |
| **Active mode** | | **HW GL_NEAREST** |

Same as no-fusion on Linux/Windows: HW GL_NEAREST handles both base and overlay. The overlay is displayed as a separate native-resolution texture; the GPU composites them. Lazy-lin is not needed.
