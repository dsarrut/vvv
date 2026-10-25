"""The vvv application objects, built in one place: the controller, its four
viewers and the GUI (the CLI, the screenshot mode, the doc screenshots, the
benches and the tests all build the same app)."""

VIEWER_TAGS = ("V1", "V2", "V3", "V4")


def build_app(use_history=True, with_gui=True):
    """(controller, gui): a Controller with its viewers V1..V4 and, unless
    with_gui is False, the MainGUI linked to it (gui is then None). A DPG
    context must exist (dpg.create_context) to build the GUI."""
    from vvv.core.controller import Controller
    from vvv.ui.viewer import SliceViewer

    controller = Controller()
    controller.use_history = use_history
    for tag in VIEWER_TAGS:
        controller.viewers[tag] = SliceViewer(tag, controller)
    if not with_gui:
        return controller, None
    from vvv.ui.gui import MainGUI

    gui = MainGUI(controller)
    controller.gui = gui
    return controller, gui
