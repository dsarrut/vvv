class ContourManager:
    """Manages the lifecycle, memory, and properties of Vector Contours."""

    def __init__(self, controller):
        self.controller = controller

    def _ensure_dict(self, vs):
        if not hasattr(vs, "contours"):
            vs.contours = {}

    def add_contour(self, base_id, contour_roi):
        """Registers a new contour to a specific image."""
        vs = self.controller.view_states.get(base_id)
        if not vs:
            return None

        self._ensure_dict(vs)

        # Generate a unique ID
        contour_id = str(self.controller.next_image_id)
        self.controller.next_image_id += 1

        contour_roi.id = contour_id
        vs.contours[contour_id] = contour_roi

        vs.is_geometry_dirty = True
        self.controller.update_all_viewers_of_image(base_id, data_dirty=False)
        return contour_id

    def remove_contour(self, base_id, contour_id):
        """Safely deletes a contour and triggers a redraw."""
        vs = self.controller.view_states.get(base_id)
        self._ensure_dict(vs)

        if vs and contour_id in vs.contours:
            # Wipe the heavy polygon arrays from memory
            del vs.contours[contour_id]

            vs.is_geometry_dirty = True
            self.controller.update_all_viewers_of_image(base_id, data_dirty=False)

    def set_visible(self, base_id, contour_id, visible):
        vs = self.controller.view_states.get(base_id)
        self._ensure_dict(vs)
        if vs and contour_id in vs.contours:
            vs.contours[contour_id].visible = visible
            vs.is_geometry_dirty = True
            self.controller.update_all_viewers_of_image(base_id, data_dirty=False)

    def set_color(self, base_id, contour_id, color):
        vs = self.controller.view_states.get(base_id)
        self._ensure_dict(vs)
        if vs and contour_id in vs.contours:
            vs.contours[contour_id].color = color
            vs.is_geometry_dirty = True
            self.controller.update_all_viewers_of_image(base_id, data_dirty=False)

    def set_thickness(self, base_id, contour_id, thickness):
        vs = self.controller.view_states.get(base_id)
        self._ensure_dict(vs)
        if vs and contour_id in vs.contours:
            vs.contours[contour_id].thickness = thickness
            vs.is_geometry_dirty = True
            self.controller.update_all_viewers_of_image(base_id, data_dirty=False)
