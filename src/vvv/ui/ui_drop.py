"""OS-level file drag-and-drop support for DearPyGui 2.x.

DearPyGui 2.x does not expose a viewport drop callback, so each platform
needs its own integration layer.

Supported:
  - macOS  via PyObjC NSView overlay
  - Linux  via GLFW drop callback (DPG 2.x statically links GLFW)
"""

import sys
from typing import Any

# Linux: keep GLFW handle + window so cleanup_os_drop() can null the callback
# before DPG destroys its context (prevents segfault at exit).
_linux_filter_ref: Any = None
_linux_glfw: Any = None
_linux_window: Any = None


def install_os_drop(callback):
    """Register *callback(sender, file_paths, user_data)* for OS file drops.

    Must be called after the DPG viewport has been shown and at least one
    frame has been rendered so the underlying native window is fully created.
    """
    if sys.platform == "darwin":
        _install_macos_drop(callback)
    elif sys.platform.startswith("linux"):
        _install_linux_drop(callback)


def cleanup_os_drop():
    """Remove the OS drop callback. Call before dpg.destroy_context().

    On Linux, GLFW calls the Python callback during window cleanup; if Python
    is already tearing down at that point it segfaults. Nulling the callback
    here prevents that.
    """
    global _linux_glfw, _linux_window, _linux_filter_ref
    if _linux_glfw is not None and _linux_window is not None:
        try:
            import ctypes
            _linux_glfw.glfwSetDropCallback(ctypes.c_void_p(_linux_window), None)
        except Exception:
            pass
    _linux_filter_ref = None
    _linux_glfw = None
    _linux_window = None


# ---------------------------------------------------------------------------
# macOS implementation
# ---------------------------------------------------------------------------

def _install_macos_drop(callback):
    """Add a transparent NSView overlay that handles Finder drag-and-drop."""
    try:
        import objc
        from AppKit import (
            NSApplication,
            NSView,
            NSDragOperationCopy,
            NSDragOperationNone,
        )
        from Foundation import NSURL

        _NSFilenamesPboardType = "NSFilenamesPboardType"
        _NSPasteboardTypeFileURL = "public.file-url"

        class DropView(NSView):
            _drop_callback = None

            def initWithFrame_(self, frame):
                self = objc.super(DropView, self).initWithFrame_(frame)
                if self is None:
                    return None
                self.registerForDraggedTypes_(
                    [_NSFilenamesPboardType, _NSPasteboardTypeFileURL]
                )
                return self

            def draggingEntered_(self, sender):
                types = sender.draggingPasteboard().types()
                if _NSFilenamesPboardType in types or _NSPasteboardTypeFileURL in types:
                    return NSDragOperationCopy
                return NSDragOperationNone

            def draggingUpdated_(self, sender):
                return NSDragOperationCopy

            def prepareForDragOperation_(self, sender):
                return True

            def performDragOperation_(self, sender):
                pb = sender.draggingPasteboard()
                files = pb.propertyListForType_(_NSFilenamesPboardType)
                if not files:
                    urls = pb.readObjectsForClasses_options_([NSURL], {})
                    if urls:
                        files = [str(u.path()) for u in urls if u.isFileURL()]
                if files and self._drop_callback:
                    self._drop_callback(None, list(files), None)
                return True

            def isOpaque(self):
                return False

            # Don't block mouse events — SDL2 intercepts them at the app level
            # so returning None here still allows DPG to receive all input.
            def hitTest_(self, point):
                return None

        app = NSApplication.sharedApplication()
        main_window = None
        for w in app.windows():
            if w.isVisible() and w.isKeyWindow():
                main_window = w
                break
        if main_window is None:
            for w in app.windows():
                if w.isVisible():
                    main_window = w
                    break
        if main_window is None:
            print("Warning: VVV drag-and-drop: could not find main NSWindow")
            return

        content_view = main_window.contentView()
        frame = content_view.bounds()
        drop_view = DropView.alloc().initWithFrame_(frame)
        drop_view._drop_callback = callback
        # NSViewWidthSizable (2) | NSViewHeightSizable (16)
        drop_view.setAutoresizingMask_(18)
        # Place on top of SDL2's own view
        content_view.addSubview_positioned_relativeTo_(drop_view, 1, None)

    except Exception as e:
        print(f"Warning: VVV drag-and-drop install failed: {e}")


# ---------------------------------------------------------------------------
# Linux implementation (GLFW drop callback via ctypes)
#
# DearPyGui 2.x statically links GLFW into _dearpygui.so. GLFW handles the
# X11 XDND protocol internally and exposes glfwSetDropCallback — the
# cleanest possible hook for OS-level file drops.
# ---------------------------------------------------------------------------

def _install_linux_drop(callback):
    try:
        import ctypes
        import os
        import dearpygui

        dpg_so = os.path.join(os.path.dirname(dearpygui.__file__), "_dearpygui.so")
        glfw = ctypes.CDLL(dpg_so)

        if not hasattr(glfw, "glfwSetDropCallback"):
            print("Warning: VVV drag-and-drop: glfwSetDropCallback not found in _dearpygui.so")
            return

        # Declare return types for all GLFW functions that return pointers.
        # Without this ctypes defaults to c_int (4 bytes) and truncates 8-byte
        # pointers on 64-bit Linux, which corrupts the stack and causes segfaults.
        glfw.glfwGetCurrentContext.restype = ctypes.c_void_p
        glfw.glfwGetCurrentContext.argtypes = []
        glfw.glfwSetDropCallback.restype = ctypes.c_void_p   # returns old callback ptr
        glfw.glfwSetDropCallback.argtypes = [ctypes.c_void_p, ctypes.c_void_p]

        window = glfw.glfwGetCurrentContext()
        if not window:
            print("Warning: VVV drag-and-drop: glfwGetCurrentContext() returned NULL")
            return

        # void (*GLFWdropfun)(GLFWwindow*, int count, const char** paths)
        DropFun = ctypes.CFUNCTYPE(
            None,
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.POINTER(ctypes.c_char_p),
        )

        def _on_drop(_window, count, paths):
            try:
                file_paths = [paths[i].decode("utf-8", errors="replace") for i in range(count)]
                callback(None, file_paths, None)
            except Exception as exc:
                print(f"Warning: VVV drag-and-drop callback error: {exc}")

        global _linux_filter_ref, _linux_glfw, _linux_window
        func = DropFun(_on_drop)
        glfw.glfwSetDropCallback(ctypes.c_void_p(window), func)
        _linux_filter_ref = func    # prevent GC — GLFW holds a raw C pointer
        _linux_glfw = glfw          # needed by cleanup_os_drop()
        _linux_window = window

    except Exception as e:
        print(f"Warning: VVV drag-and-drop install failed: {e}")
