# CT soft tissue window on V1
gui.set_context_viewer(ctrl.viewers["V1"])
ctrl.view_states[ctrl.viewers["V1"].image_id].apply_wl_preset("CT: Soft Tissue")
