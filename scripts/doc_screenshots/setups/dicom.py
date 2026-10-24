# DICOM browser: scan data/conventional (a pig phantom: no patient data), select the series
import os
p = next(p for p in gui.plugins if p.plugin_id == "dicom_plugin")
p.show_window()
def find(attr):
    for o in (p, *vars(p).values()):
        if hasattr(o, attr):
            return o
ui = find("on_scan_clicked")
print("DICOM", ui.window_tag)
def during():
    for _ in range(5):
        yield
    dpg.set_value(ui._t("input_folder_path"), os.path.abspath("data/conventional"))
    ui.on_scan_clicked()
    import time
    t0 = time.time()
    while not ui.scanned_series and time.time() - t0 < 30:
        yield
    for _ in range(5):
        yield
    sender = ui._t("sel_0")
    dpg.set_value(sender, True)
    ui.on_series_selected(sender, None, 0)
