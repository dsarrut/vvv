def __getattr__(name):
    # Lazy so that importing any vvv submodule (e.g. headless vvv.maths) does not
    # pull in DearPyGui, PIL and the whole GUI through vvv.screenshot.
    if name == "vvv_screenshot":
        from vvv.screenshot import vvv_screenshot

        return vvv_screenshot
    raise AttributeError(f"module 'vvv' has no attribute {name!r}")
