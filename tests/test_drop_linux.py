#!/usr/bin/env python3
"""Standalone drag-and-drop diagnostic for VVV on Linux.

Run with:  python tests/test_drop_linux.py

It prints a diagnostic report then opens a small DPG window.
Drag any file from your file manager onto the window and watch
the terminal for output.
"""

import ctypes
import ctypes.util
import faulthandler
import os
import sys

faulthandler.enable()  # print C-level stack trace on segfault


# ---------------------------------------------------------------------------
# 1. Diagnostic: what SDL is loaded / available
# ---------------------------------------------------------------------------

def diagnose():
    import dearpygui

    print(f"\nPython      : {sys.version}")
    print(f"Platform    : {sys.platform}")
    print(f"DearPyGui   : {dearpygui.__version__}")
    print(f"DPG path    : {dearpygui.__file__}")

    dpg_dir = os.path.dirname(dearpygui.__file__)
    dpg_so  = os.path.join(dpg_dir, "_dearpygui.so")

    # ---- /proc/self/maps ---------------------------------------------------
    print("\n[1] SDL entries in /proc/self/maps (after importing dearpygui):")
    try:
        with open("/proc/self/maps") as f:
            lines = [l.strip() for l in f if "sdl" in l.lower()]
        if lines:
            for l in lines:
                print(f"      {l}")
        else:
            print("      (none — SDL is probably statically linked into _dearpygui.so)")
    except OSError as e:
        print(f"      ERROR: {e}")

    # ---- SDL symbols in _dearpygui.so -------------------------------------
    print(f"\n[2] SDL symbols exported by {os.path.basename(dpg_so)}:")
    try:
        lib = ctypes.CDLL(dpg_so)
        for sym in [
            "SDL_AddEventWatch",
            "SDL_EventState",         # SDL2 only
            "SDL_SetEventEnabled",    # SDL3 only
            "SDL_PollEvent",
        ]:
            found = hasattr(lib, sym)
            print(f"      {'✓' if found else '✗'}  {sym}")
    except OSError as e:
        print(f"      ERROR loading {dpg_so}: {e}")

    # ---- system SDL --------------------------------------------------------
    print("\n[3] System SDL libraries (via ldconfig):")
    for tag, name in [("SDL2", ctypes.util.find_library("SDL2")),
                      ("SDL3", ctypes.util.find_library("SDL3"))]:
        print(f"      find_library('{tag}') → {name}")

    # ---- dearpygui package directory contents -----------------------------
    print(f"\n[4] Files in DPG package dir ({dpg_dir}):")
    for fname in sorted(os.listdir(dpg_dir)):
        print(f"      {fname}")

    # ---- site-packages siblings (bundled .libs) ---------------------------
    sp = os.path.dirname(dpg_dir)
    dpg_libs = os.path.join(sp, "dearpygui.libs")
    if os.path.isdir(dpg_libs):
        print(f"\n[5] Bundled libs in {dpg_libs}:")
        for fname in sorted(os.listdir(dpg_libs)):
            print(f"      {fname}")
    else:
        print(f"\n[5] No dearpygui.libs directory found at {dpg_libs}")

    # ---- ldd: what does _dearpygui.so actually link against? --------------
    print(f"\n[6] ldd {os.path.basename(dpg_so)}:")
    try:
        import subprocess
        result = subprocess.run(["ldd", dpg_so], capture_output=True, text=True)
        for line in result.stdout.splitlines():
            print(f"      {line.strip()}")
    except Exception as e:
        print(f"      ERROR: {e}")

    # ---- What windowing backend symbols are present? ----------------------
    print(f"\n[7] Windowing-backend symbols in _dearpygui.so:")
    try:
        lib = ctypes.CDLL(dpg_so)
        for sym in [
            # GLFW
            "glfwInit", "glfwSetDropCallback", "glfwGetX11Window",
            # Raw X11
            "XOpenDisplay", "XSendEvent",
            # Vulkan / GL
            "vkCreateInstance", "glClear",
            # SDL2
            "SDL_Init", "SDL_AddEventWatch",
            # SDL3
            "SDL_Init", "SDL_AddEventWatch",
        ]:
            if hasattr(lib, sym):
                print(f"      ✓  {sym}")
    except OSError as e:
        print(f"      ERROR: {e}")

    # ---- Full /proc/self/maps (all unique .so files) ----------------------
    print("\n[8] All shared libraries loaded by the process:")
    try:
        with open("/proc/self/maps") as f:
            seen: set = set()
            for line in f:
                parts = line.strip().split()
                path = parts[-1] if parts and parts[-1].startswith("/") and ".so" in parts[-1] else None
                if path and path not in seen:
                    seen.add(path)
                    print(f"      {path}")
    except OSError as e:
        print(f"      ERROR: {e}")

    print()


# ---------------------------------------------------------------------------
# 2. Best-effort SDL loader (same logic as ui_drop._load_sdl_lib)
# ---------------------------------------------------------------------------

def _load_sdl():
    """Try every known location; return (CDLL, is_sdl3) or (None, False)."""
    import dearpygui
    dpg_dir = os.path.dirname(dearpygui.__file__)

    candidates = []

    # a) _dearpygui.so itself (SDL statically linked)
    candidates.append((os.path.join(dpg_dir, "_dearpygui.so"), None))

    # b) bundled dearpygui.libs/
    sp = os.path.dirname(dpg_dir)
    libs_dir = os.path.join(sp, "dearpygui.libs")
    if os.path.isdir(libs_dir):
        for fname in os.listdir(libs_dir):
            low = fname.lower()
            if "sdl3" in low:
                candidates.append((os.path.join(libs_dir, fname), True))
            elif "sdl2" in low:
                candidates.append((os.path.join(libs_dir, fname), False))

    # c) /proc/self/maps
    try:
        with open("/proc/self/maps") as f:
            seen: set = set()
            for line in f:
                parts = line.strip().split()
                path = parts[-1] if parts and parts[-1].startswith("/") else None
                if not path or path in seen:
                    continue
                seen.add(path)
                base = os.path.basename(path).lower()
                if "sdl3" in base:
                    candidates.append((path, True))
                elif "sdl2" in base:
                    candidates.append((path, False))
    except OSError:
        pass

    # d) system name search
    for name, is_sdl3 in [
        (ctypes.util.find_library("SDL3"), True),
        (ctypes.util.find_library("SDL2"), False),
        ("libSDL3.so.0",     True),
        ("libSDL3.so",       True),
        ("libSDL2-2.0.so.0", False),
        ("libSDL2-2.0.so",   False),
    ]:
        if name:
            candidates.append((name, is_sdl3))

    for path, is_sdl3 in candidates:
        if not path:
            continue
        try:
            lib = ctypes.CDLL(path)
            if not hasattr(lib, "SDL_AddEventWatch"):
                continue
            # Detect SDL2 vs SDL3 if not already known
            if is_sdl3 is None:
                is_sdl3 = hasattr(lib, "SDL_SetEventEnabled")
            print(f"[drop] Using SDL from: {path}  (SDL3={is_sdl3})")
            return lib, is_sdl3
        except OSError:
            continue

    return None, False


# ---------------------------------------------------------------------------
# 3. Install the watcher
# ---------------------------------------------------------------------------

_filter_ref = None   # keep alive — SDL holds a raw C pointer


def install_drop(callback):
    """Install GLFW drop callback (step-by-step output for debugging)."""
    global _filter_ref

    import dearpygui
    dpg_so = os.path.join(os.path.dirname(dearpygui.__file__), "_dearpygui.so")

    print(f"[drop] Step 1: loading {dpg_so}")
    glfw = ctypes.CDLL(dpg_so)

    print("[drop] Step 2: checking glfwSetDropCallback symbol")
    if not hasattr(glfw, "glfwSetDropCallback"):
        print("[drop] ERROR: glfwSetDropCallback not found — cannot install drop handler")
        return

    print("[drop] Step 3: setting restype for GLFW pointer-returning functions")
    glfw.glfwGetCurrentContext.restype = ctypes.c_void_p
    glfw.glfwGetCurrentContext.argtypes = []
    glfw.glfwSetDropCallback.restype = ctypes.c_void_p   # returns old callback ptr
    glfw.glfwSetDropCallback.argtypes = [ctypes.c_void_p, ctypes.c_void_p]

    print("[drop] Step 4: glfwGetCurrentContext()")
    window = glfw.glfwGetCurrentContext()
    print(f"[drop]         window = {window!r}  (0x{window:016x} if not None)" if window else
          "[drop]         window = NULL")
    if not window:
        print("[drop] WARNING: no current GLFW context — cannot install drop handler")
        return

    print("[drop] Step 5: creating DropFun CFUNCTYPE")
    DropFun = ctypes.CFUNCTYPE(
        None,
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.POINTER(ctypes.c_char_p),
    )

    def _on_drop(_win, count, paths):
        try:
            file_paths = [paths[i].decode("utf-8", errors="replace") for i in range(count)]
            print(f"[drop] *** DROP: {file_paths}")
            for p in file_paths:
                callback(p)
        except Exception as exc:
            print(f"[drop] callback error: {exc}")

    print("[drop] Step 6: wrapping Python callback in DropFun")
    _filter_ref = DropFun(_on_drop)

    print("[drop] Step 7: calling glfwSetDropCallback — if it segfaults, check above")
    glfw.glfwSetDropCallback(ctypes.c_void_p(window), _filter_ref)
    print("[drop] Step 7: glfwSetDropCallback returned OK")


# ---------------------------------------------------------------------------
# 4. Minimal DPG window
# ---------------------------------------------------------------------------

def main():
    diagnose()

    import dearpygui.dearpygui as dpg

    dpg.create_context()
    dpg.create_viewport(title="VVV drag-drop test — drop a file here", width=500, height=200)
    dpg.setup_dearpygui()

    with dpg.window(tag="win", label="Drop test"):
        dpg.add_text("Drag a file from your file manager onto this window.")
        dpg.add_text("Watch the terminal for output.", color=(180, 180, 180))
        dpg.add_separator()
        dpg.add_text("(nothing dropped yet)", tag="result")

    dpg.show_viewport()
    dpg.set_primary_window("win", True)

    for _ in range(3):
        dpg.render_dearpygui_frame()

    dropped = []

    def on_drop(path):
        dropped.append(path)
        print(f"[drop] *** SUCCESS: {path}")
        dpg.set_value("result", f"Dropped: {path}")

    install_drop(on_drop)

    while dpg.is_dearpygui_running():
        dpg.render_dearpygui_frame()

    # Null the GLFW drop callback before DPG destroys the window to
    # prevent a segfault from GLFW calling back into a torn-down Python.
    if hasattr(install_drop, '_cleanup'):
        install_drop._cleanup()

    import ctypes as _ct
    import dearpygui as _dpg_pkg
    import os as _os
    _dpg_so = _os.path.join(_os.path.dirname(_dpg_pkg.__file__), "_dearpygui.so")
    try:
        _glfw = _ct.CDLL(_dpg_so)
        _glfw.glfwSetDropCallback.restype = _ct.c_void_p
        _glfw.glfwSetDropCallback.argtypes = [_ct.c_void_p, _ct.c_void_p]
        _glfw.glfwGetCurrentContext.restype = _ct.c_void_p
        _win = _glfw.glfwGetCurrentContext()
        if _win:
            _glfw.glfwSetDropCallback(_ct.c_void_p(_win), None)
    except Exception:
        pass

    dpg.destroy_context()


if __name__ == "__main__":
    main()
