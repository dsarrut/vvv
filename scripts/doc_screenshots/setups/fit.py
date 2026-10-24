# Fit all viewers, zoomed by $ZOOM (default 1), centered on the crosshair
import os
f = float(os.environ.get("ZOOM", "1"))
for v in ctrl.viewers.values():
    if v.view_state:
        v.action_reset_view()
        v.zoom = v.zoom * f
        v.action_center_view()
