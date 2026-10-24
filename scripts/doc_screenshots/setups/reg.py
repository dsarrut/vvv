# Registration: zoom on the head, all viewers centered on the crosshair
import numpy as np

for v in ctrl.viewers.values():
    if v.view_state:
        v.action_reset_view()  # also resets the crosshair: set it after
        v.zoom = v.zoom * 3.2
for vs_id, vs in ctrl.view_states.items():
    vs.update_crosshair_from_phys(np.array([-15.3, -26.3, 1963.8]))
    ctrl.sync.propagate_sync(vs_id)
    ctrl.update_all_viewers_of_image(vs_id)


def during():
    for _ in range(5):
        yield
    for v in ctrl.viewers.values():
        if v.view_state:
            v.action_center_view()
