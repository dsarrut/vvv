import numpy as np

class PluginAPI:
    def __init__(self, gui):
        self._gui = gui
        self._controller = gui.controller

    @property
    def is_dirty(self):
        """Returns True if the UI or the active viewer state has changed."""
        viewer = self._gui.context_viewer
        # Check if the controller flagged a refresh or the active viewer is dirty
        return (
            self._controller.ui_needs_refresh or 
            (viewer and viewer.view_state and viewer.view_state.is_data_dirty)
        )

    def get_active_image_name(self):
        viewer = self._gui.context_viewer
        if viewer and viewer.image_id:
            name, _ = self._controller.get_image_display_name(viewer.image_id)
            return name
        return "None"

    def get_crosshair_world(self):
        viewer = self._gui.context_viewer
        if viewer and viewer.view_state and viewer.view_state.camera.crosshair_phys_coord is not None:
            return viewer.view_state.camera.crosshair_phys_coord
        return [0.0, 0.0, 0.0]

    def get_mouse_position(self):
        if hasattr(self._gui.interaction, "last_mouse_pos"):
            return self._gui.interaction.last_mouse_pos
        return [0, 0]