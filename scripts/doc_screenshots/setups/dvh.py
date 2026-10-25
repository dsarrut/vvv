# Open the DVH window of the dose plugin
def find(attr):
    for p in gui.plugins:
        for o in (p, *vars(p).values()):
            if hasattr(o, attr):
                return o
ui = find("on_open_dvh_clicked")
ui.on_open_dvh_clicked()
win = ui.dvh_win
DVH_TAG = win.window_tag
print("DVH", DVH_TAG)
