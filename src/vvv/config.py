import numpy as np

DEFAULT_SETTINGS = {
    "colors": {
        "crosshair": [0, 246, 7, 120],
        "tracker_text": [0, 246, 7, 255],
        "x": [255, 80, 80, 230],
        "y": [80, 255, 80, 230],
        "z": [80, 80, 255, 230],
        "grid": [255, 255, 255, 40],
        "viewer": [10, 246, 7, 120],
        "legend_bg": [0, 0, 0, 150],
    },
    "physics": {"auto_window_fov": 0.20, "voxel_strip_threshold": 5000},
    "shortcuts": {
        "open_file": "O",
        "next_image": "N",
        "auto_window": "W",
        "auto_window_overlay": "X",
        "scroll_up": "Up",
        "scroll_down": "Down",
        "fast_scroll_up": 517,  # Page up
        "fast_scroll_down": 518,  # Page down
        "zoom_in": "I",
        "zoom_out": "O",
        "reset_view": "R",
        "center_view": "C",
        "view_axial": "F1",
        "view_sagittal": "F2",
        "view_coronal": "F3",
        "view_histogram": "F4",
        "toggle_interp": "K",
        "toggle_legend": "L",
        "toggle_grid": "G",
        "toggle_axis": "A",
        "toggle_scalebar": "B",
        "hide_all": "H",
        "time_forward": "Right",
        "time_backward": "Left",
    },
    "interaction": {
        "zoom_speed": 1.1,
        "fast_scroll_steps": 10,
        "wl_drag_sensitivity": 2.0,
        "active_viewer_mode": "hybrid",
    },
    "layout": {"window_width": 1200, "window_height": 1000, "side_panel_width": 315},
    "behavior": {
        "auto_save_history": True,
    },
}

WL_PRESETS = {
    "Optimal": None,
    "Min/Max": None,
    "Binary Mask": {"ww": 1.0, "wl": 0.5},
    "CT: Soft Tissue": {"ww": 400.0, "wl": 50.0},
    "CT: Bone": {"ww": 2000.0, "wl": 400.0},
    "CT: Lung": {"ww": 1500.0, "wl": -600.0},
    "CT: Brain": {"ww": 80.0, "wl": 40.0},
}

ROI_COLORS = [
    [255, 50, 50],  # Red
    [50, 255, 50],  # Green
    [50, 150, 255],  # Blue
    [255, 200, 50],  # Yellow
    [255, 50, 255],  # Magenta
    [50, 255, 255],  # Cyan
    [255, 100, 50],  # Orange
    [150, 50, 255],  # Purple
    [255, 105, 97],  # Pastel Red
    [119, 221, 119],  # Pastel Green
    [174, 198, 207],  # Pastel Blue
    [253, 253, 150],  # Pastel Yellow
    [203, 153, 201],  # Pastel Purple
    [255, 179, 71],  # Pastel Orange
    [244, 154, 194],  # Pastel Pink
    [119, 158, 203],  # Darker Pastel Blue
    [255, 209, 220],  # Pastel Rose
    [150, 222, 209],  # Pastel Turquoise
    [255, 229, 180],  # Pastel Peach
    [207, 207, 196],  # Pastel Grey
    [194, 59, 34],  # Brick Red
    [3, 192, 60],  # Darker Pastel Green
    [179, 158, 181],  # Pastel Lavender
    [253, 180, 75],  # Deep Pastel Orange
]


def generate_colormaps():
    cmaps = {}
    x = np.linspace(0, 1, 256)
    ones = np.ones(256)

    cmaps["Grayscale"] = np.column_stack([x, x, x, ones]).astype(np.float32)

    r = np.clip(3 * x, 0, 1)
    g = np.clip(3 * x - 1, 0, 1)
    b = np.clip(3 * x - 2, 0, 1)
    cmaps["Hot"] = np.column_stack([r, g, b, ones]).astype(np.float32)

    cmaps["Cold"] = np.column_stack([b, g, r, ones]).astype(np.float32)

    r = np.clip(1.5 - np.abs(4 * x - 3), 0, 1)
    g = np.clip(1.5 - np.abs(4 * x - 2), 0, 1)
    b = np.clip(1.5 - np.abs(4 * x - 1), 0, 1)
    cmaps["Jet"] = np.column_stack([r, g, b, ones]).astype(np.float32)

    r = np.clip(4 * x - 1.5, 0, 1)
    g = np.clip(2 - np.abs(4 * x - 2), 0, 1)
    b = np.clip(2.5 - 4 * x, 0, 1)
    cmaps["Dosimetry"] = np.column_stack([r, g, b, ones]).astype(np.float32)

    np.random.seed(42)
    seg_r = np.random.rand(256)
    seg_g = np.random.rand(256)
    seg_b = np.random.rand(256)
    seg_r[0], seg_g[0], seg_b[0] = 0, 0, 0
    cmaps["Segmentation"] = np.column_stack([seg_r, seg_g, seg_b, ones]).astype(
        np.float32
    )

    return cmaps


COLORMAPS = generate_colormaps()
