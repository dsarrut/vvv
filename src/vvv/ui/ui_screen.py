"""Main screen size and the start size of the window."""

import ctypes
import ctypes.util
import re
import subprocess
import sys

START_FRACTION = 0.85  # default window: this fraction of the screen...
SCREEN_MARGIN = (40, 80)  # ...and never larger than the screen minus this (bars, dock)


def main_screen_size():
    """(width, height) of the main screen in window units, or None if unknown."""
    try:
        if sys.platform == "darwin":
            cg = ctypes.CDLL(ctypes.util.find_library("CoreGraphics"))
            cg.CGMainDisplayID.restype = ctypes.c_uint32
            cg.CGDisplayPixelsWide.restype = ctypes.c_size_t
            cg.CGDisplayPixelsHigh.restype = ctypes.c_size_t
            d = cg.CGMainDisplayID()
            size = (cg.CGDisplayPixelsWide(d), cg.CGDisplayPixelsHigh(d))  # points
        elif sys.platform == "win32":
            user32 = ctypes.windll.user32  # type: ignore[attr-defined]
            size = (user32.GetSystemMetrics(0), user32.GetSystemMetrics(1))
        else:
            out = subprocess.run(
                ["xrandr", "--current"], capture_output=True, text=True, timeout=2
            ).stdout
            # The primary monitor, else the first connected one
            m = re.search(r" connected primary (\d+)x(\d+)", out) or re.search(
                r" connected (?:primary )?(\d+)x(\d+)", out
            )
            size = (int(m.group(1)), int(m.group(2))) if m else None
    except Exception:
        return None
    return size if size and size[0] > 0 and size[1] > 0 else None


def start_window_geometry(width, height, default_size, screen):
    """(width, height, x, y) of the window at start, from the size in the
    settings. The default size grows with the screen (START_FRACTION); any
    size is clamped to the screen and the window is centered on it."""
    if screen is None:
        return width, height, None, None
    sw, sh = screen
    if (width, height) == tuple(default_size):  # not chosen by the user
        width = max(width, round(sw * START_FRACTION))
        height = max(height, round(sh * START_FRACTION))
    width = min(width, sw - SCREEN_MARGIN[0])
    height = min(height, sh - SCREEN_MARGIN[1])
    return width, height, max(0, (sw - width) // 2), max(25, (sh - height) // 2)
