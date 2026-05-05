"""OS-level file drag-and-drop support for DearPyGui 2.x.

DearPyGui 2.x does not expose a viewport drop callback, so each platform
needs its own integration layer.

Supported:
  - macOS   via PyObjC NSView overlay
  - Linux   via GLFW drop callback (DPG 2.x statically links GLFW)
  - Windows via GLFW drop callback; falls back to Win32 WM_DROPFILES
            if GLFW symbols are not exported from _dearpygui.pyd
"""

import sys
from typing import Any

# Linux: keep GLFW handle + window so cleanup_os_drop() can null the callback
# before DPG destroys its context (prevents segfault at exit).
_linux_filter_ref: Any = None
_linux_glfw: Any = None
_linux_window: Any = None

# Windows: keep new WndProc + original WndProc + hwnd alive (raw C pointers).
_windows_drop_refs: Any = None


def install_os_drop(callback):
    """Register *callback(sender, file_paths, user_data)* for OS file drops.

    Must be called after the DPG viewport has been shown and at least one
    frame has been rendered so the underlying native window is fully created.
    """
    if sys.platform == "darwin":
        _install_macos_drop(callback)
    elif sys.platform.startswith("linux"):
        _install_linux_drop(callback)
    elif sys.platform == "win32":
        _install_windows_drop(callback)


def cleanup_os_drop():
    """Remove the OS drop callback. Call before dpg.destroy_context().

    On Linux/Windows the native layer holds raw C pointers into Python objects;
    nulling them here before DPG tears down its window prevents a segfault.
    """
    global _linux_glfw, _linux_window, _linux_filter_ref
    global _windows_drop_refs

    # Linux
    if _linux_glfw is not None and _linux_window is not None:
        try:
            import ctypes
            _linux_glfw.glfwSetDropCallback(ctypes.c_void_p(_linux_window), None)
        except Exception:
            pass
    _linux_filter_ref = None
    _linux_glfw = None
    _linux_window = None

    # Windows
    if _windows_drop_refs is not None:
        try:
            import ctypes
            hwnd     = _windows_drop_refs[1]
            orig_ptr = _windows_drop_refs[2]
            windll = getattr(ctypes, "windll")   # only exists on Windows
            user32  = windll.user32
            shell32 = windll.shell32
            user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
            user32.SetWindowLongPtrW(hwnd, -4, orig_ptr)   # restore original WndProc
            shell32.DragAcceptFiles(hwnd, False)
        except Exception:
            pass
    _windows_drop_refs = None


# ---------------------------------------------------------------------------
# macOS implementation
# ---------------------------------------------------------------------------

def _install_macos_drop(callback):
    """Add a transparent NSView overlay that handles Finder drag-and-drop."""
    try:
        import objc  # type: ignore[import-untyped]
        from AppKit import (  # type: ignore[import-untyped]
            NSApplication,# type: ignore[import-untyped]
            NSView,# type: ignore[import-untyped]
            NSDragOperationCopy,# type: ignore[import-untyped]
            NSDragOperationNone,# type: ignore[import-untyped]
        )
        from Foundation import NSURL  # type: ignore[import-untyped]

        _NSFilenamesPboardType = "NSFilenamesPboardType"
        _NSPasteboardTypeFileURL = "public.file-url"

        class DropView(NSView):
            _drop_callback = None

            def initWithFrame_(self, frame):
                self = objc.super(DropView, self).initWithFrame_(frame)  # type: ignore[misc]
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


# ---------------------------------------------------------------------------
# Windows implementation
#
# Primary: GLFW drop callback via ctypes on _dearpygui.pyd (same as Linux).
#   Works if DPG's Windows build exports GLFW symbols.
# Fallback: Win32 WM_DROPFILES via WndProc subclassing.
#   Requires no extra libraries — uses only ctypes + shell32/user32.
# ---------------------------------------------------------------------------

def _get_dpg_hwnd_windows():
    """Return the HWND for DPG's main window on Windows."""
    import ctypes
    import os
    import dearpygui

    # Prefer glfwGetWin32Window — most reliable since it's the exact window
    try:
        dpg_pyd = os.path.join(os.path.dirname(dearpygui.__file__), "_dearpygui.pyd")
        glfw = ctypes.CDLL(dpg_pyd)
        if hasattr(glfw, "glfwGetCurrentContext") and hasattr(glfw, "glfwGetWin32Window"):
            glfw.glfwGetCurrentContext.restype = ctypes.c_void_p
            glfw.glfwGetCurrentContext.argtypes = []
            glfw.glfwGetWin32Window.restype = ctypes.c_void_p
            glfw.glfwGetWin32Window.argtypes = [ctypes.c_void_p]
            window = glfw.glfwGetCurrentContext()
            if window:
                return glfw.glfwGetWin32Window(ctypes.c_void_p(window))
    except Exception:
        pass

    # Fallback: find by viewport title
    windll = getattr(ctypes, "windll")
    return windll.user32.FindWindowW(None, "VVV")


def _install_windows_drop(callback):
    try:
        import ctypes
        import os
        import dearpygui

        # --- Primary: GLFW drop callback (same mechanism as Linux) ----------
        dpg_pyd = os.path.join(os.path.dirname(dearpygui.__file__), "_dearpygui.pyd")
        try:
            glfw = ctypes.CDLL(dpg_pyd)
            if hasattr(glfw, "glfwSetDropCallback") and hasattr(glfw, "glfwGetCurrentContext"):
                glfw.glfwGetCurrentContext.restype = ctypes.c_void_p
                glfw.glfwGetCurrentContext.argtypes = []
                glfw.glfwSetDropCallback.restype = ctypes.c_void_p
                glfw.glfwSetDropCallback.argtypes = [ctypes.c_void_p, ctypes.c_void_p]

                window = glfw.glfwGetCurrentContext()
                if window:
                    DropFun = ctypes.CFUNCTYPE(
                        None,
                        ctypes.c_void_p,
                        ctypes.c_int,
                        ctypes.POINTER(ctypes.c_char_p),
                    )

                    def _on_drop_glfw(_, count, paths):
                        try:
                            files = [paths[i].decode("utf-8", errors="replace")
                                     for i in range(count)]
                            callback(None, files, None)
                        except Exception as exc:
                            print(f"Warning: VVV drag-and-drop callback error: {exc}")

                    global _linux_filter_ref, _linux_glfw, _linux_window
                    func = DropFun(_on_drop_glfw)
                    glfw.glfwSetDropCallback(ctypes.c_void_p(window), func)
                    # Reuse Linux globals — cleanup_os_drop() handles both
                    _linux_filter_ref = func
                    _linux_glfw = glfw
                    _linux_window = window
                    return   # success — no need for WndProc fallback
        except Exception:
            pass

        # --- Fallback: Win32 WM_DROPFILES via WndProc subclassing -----------
        windll = getattr(ctypes, "windll")
        user32  = windll.user32
        shell32 = windll.shell32

        WM_DROPFILES = 0x0233
        GWL_WNDPROC  = -4

        # Set correct restypes for Win32 APIs returning pointer-sized values
        user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
        user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
        user32.CallWindowProcW.restype   = ctypes.c_ssize_t
        user32.CallWindowProcW.argtypes  = [
            ctypes.c_void_p,
            ctypes.c_void_p,   # HWND
            ctypes.c_uint,
            ctypes.c_size_t,   # WPARAM
            ctypes.c_ssize_t,  # LPARAM
        ]
        shell32.DragQueryFileW.restype  = ctypes.c_uint
        shell32.DragQueryFileW.argtypes = [
            ctypes.c_void_p, ctypes.c_uint, ctypes.c_wchar_p, ctypes.c_uint
        ]

        hwnd = _get_dpg_hwnd_windows()
        if not hwnd:
            print("Warning: VVV drag-and-drop: cannot find main window HWND")
            return

        shell32.DragAcceptFiles(hwnd, True)

        import ctypes.wintypes as wt
        WINFUNCTYPE = getattr(ctypes, "WINFUNCTYPE")  # Windows-only, not known to pyright
        WndProcType = WINFUNCTYPE(
            ctypes.c_ssize_t, wt.HWND, ctypes.c_uint, wt.WPARAM, wt.LPARAM
        )

        orig_ptr = user32.GetWindowLongPtrW(hwnd, GWL_WNDPROC)

        def _wndproc(hwnd_, msg, wparam, lparam):
            if msg == WM_DROPFILES:
                hdrop = wparam
                count = shell32.DragQueryFileW(hdrop, 0xFFFFFFFF, None, 0)
                buf   = ctypes.create_unicode_buffer(32768)
                files = []
                for i in range(count):
                    shell32.DragQueryFileW(hdrop, i, buf, 32768)
                    files.append(buf.value)
                shell32.DragFinish(hdrop)
                if files:
                    callback(None, files, None)
                return 0
            return user32.CallWindowProcW(orig_ptr, hwnd_, msg, wparam, lparam)

        new_proc = WndProcType(_wndproc)
        user32.SetWindowLongPtrW(hwnd, GWL_WNDPROC, new_proc)

        global _windows_drop_refs
        _windows_drop_refs = (new_proc, hwnd, orig_ptr)

    except Exception as e:
        print(f"Warning: VVV drag-and-drop install failed: {e}")
