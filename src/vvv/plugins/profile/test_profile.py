import unittest
from unittest.mock import MagicMock
import numpy as np
import dearpygui.dearpygui as dpg
from vvv.plugins.profile.plugin_profile import ProfilePlugin
from vvv.core.view_state import ProfileLineState


class TestProfilePlugin(unittest.TestCase):
    def setUp(self):
        self.plugin = ProfilePlugin()
        self.mock_api = MagicMock()
        self.mock_api.is_beginner_mode = False
        self.mock_api.get_ui_config.return_value = {
            "colors": {
                "text_header": [255, 255, 255],
                "text_active": [255, 255, 255],
                "text_dim": [128, 128, 128],
                "outdated": [255, 165, 0],
            }
        }
        self.mock_api.get_active_viewer.return_value = None
        self.mock_api.is_mip_active.return_value = False

    def test_metadata(self):
        self.assertEqual(self.plugin.plugin_id, "profile_plugin")
        self.assertEqual(self.plugin.label, "Profiles")
        self.assertIsNotNone(self.plugin.description)
        self.assertEqual(self.plugin.order, 20)

    def test_state_lifecycle(self):
        self.assertEqual(self.plugin.serialize_image_state("image1"), {})
        self.plugin.restore_image_state("image1", {"profiles": {}})

    def test_create_ui(self):
        if not dpg.is_dearpygui_running():
            dpg.create_context()
        with dpg.window(tag="test_parent"):
            self.plugin.create_ui(parent="test_parent", api=self.mock_api)
        self.assertTrue(dpg.does_item_exist("profile_plugin"))
        dpg.delete_item("test_parent")

    def test_update_ui(self):
        if not dpg.is_dearpygui_running():
            dpg.create_context()
        with dpg.window(tag="test_parent"):
            self.plugin.create_ui(parent="test_parent", api=self.mock_api)

        # Update when no viewer active
        self.plugin.update(self.mock_api)

        # Update when viewer is active
        viewer = MagicMock()
        viewer.image_id = "image_abc"
        viewer.view_state = MagicMock()

        # Add a real profile to profiles dict
        profile = ProfileLineState()
        profile.id = "p1"
        profile.name = "My Test Profile"
        profile.pt1_phys = np.array([0.0, 0.0, 0.0])
        profile.pt2_phys = np.array([10.0, 10.0, 0.0])
        viewer.view_state.profiles = {"p1": profile}

        viewer.volume = MagicMock()
        viewer.volume.is_rgb = False
        self.mock_api.get_active_viewer.return_value = viewer
        self.mock_api.get_image_display_name.return_value = ("Image ABC", False)

        self.plugin.update(self.mock_api)
        self.assertEqual(dpg.get_value("profile_plugin_active_title"), "Image ABC")

        # Verify list table row was built
        table_id = "profile_plugin_list_table"
        self.assertTrue(dpg.does_item_exist(table_id))
        rows = dpg.get_item_children(table_id, slot=1)
        self.assertIsNotNone(rows)
        self.assertEqual(len(rows), 1)

        dpg.delete_item("test_parent")

    def test_open_close_all_plots(self):
        if not dpg.is_dearpygui_running():
            dpg.create_context()
        with dpg.window(tag="test_parent"):
            self.plugin.create_ui(parent="test_parent", api=self.mock_api)

        # Setup active viewer with a profile
        viewer = MagicMock()
        viewer.image_id = "image_abc"
        viewer.view_state = MagicMock()
        profile = ProfileLineState()
        profile.id = "p1"
        profile.name = "My Test Profile"
        profile.pt1_phys = np.array([0.0, 0.0, 0.0])
        profile.pt2_phys = np.array([10.0, 10.0, 0.0])
        viewer.view_state.profiles = {"p1": profile}
        viewer.volume = MagicMock()
        self.mock_api.get_active_viewer.return_value = viewer
        self.mock_api.get_image_display_name.return_value = ("Image ABC", False)
        self.mock_api.get_profile_data.return_value = (
            np.array([0, 10]),
            np.array([100, 200]),
        )

        # Render list
        self.plugin.update(self.mock_api)

        # Test Open All
        self.plugin._ui.on_open_all_clicked(None, None, None)
        win_tag = "profile_plugin_plot_win_p1"
        self.assertTrue(dpg.does_item_exist(win_tag))
        self.assertTrue(profile.plot_open)

        # Test Close All
        self.plugin._ui.on_close_all_clicked(None, None, None)
        self.assertFalse(dpg.does_item_exist(win_tag))
        self.assertFalse(profile.plot_open)

        dpg.delete_item("test_parent")

    def test_plot_position_persistence(self):
        if not dpg.is_dearpygui_running():
            dpg.create_context()
        with dpg.window(tag="test_parent"):
            self.plugin.create_ui(parent="test_parent", api=self.mock_api)

        # Setup active viewer with a profile
        viewer = MagicMock()
        viewer.image_id = "image_abc"
        viewer.view_state = MagicMock()
        profile = ProfileLineState()
        profile.id = "p1"
        profile.name = "My Test Profile"
        profile.pt1_phys = np.array([0.0, 0.0, 0.0])
        profile.pt2_phys = np.array([10.0, 10.0, 0.0])
        viewer.view_state.profiles = {"p1": profile}
        viewer.volume = MagicMock()
        self.mock_api.get_active_viewer.return_value = viewer
        self.mock_api.get_image_display_name.return_value = ("Image ABC", False)
        self.mock_api.get_profile_data.return_value = (
            np.array([0, 10]),
            np.array([100, 200]),
        )

        # Render list
        self.plugin.update(self.mock_api)

        # Open the plot window
        self.plugin._ui.on_plot_clicked(None, None, "p1")
        win_tag = "profile_plugin_plot_win_p1"
        self.assertTrue(dpg.does_item_exist(win_tag))
        self.assertTrue(profile.plot_open)

        # Set a custom position
        custom_pos = [150.0, 250.0]
        dpg.set_item_pos(win_tag, custom_pos)

        # Close the plot window (which should capture the position)
        self.plugin._ui.on_plot_closed(win_tag, None, "p1")
        self.assertEqual(profile.plot_position, custom_pos)
        self.assertFalse(profile.plot_open)

        # Reopen the plot window (which should restore the position)
        self.plugin._ui.on_plot_clicked(None, None, "p1")
        restored_pos = dpg.get_item_pos(win_tag)
        self.assertEqual(restored_pos, custom_pos)

        # Serialize using serialize_image_state
        self.plugin.serialize_image_state("image_abc")
        serialized = profile.to_dict()
        self.assertEqual(serialized["plot_position"], custom_pos)

        # Deserialize into a new ProfileLineState
        new_profile = ProfileLineState()
        new_profile.from_dict(serialized)
        self.assertEqual(new_profile.plot_position, custom_pos)

        # Cleanup
        self.plugin._ui.on_plot_closed(win_tag, None, "p1")
        dpg.delete_item("test_parent")

    def test_gather_plots(self):
        if not dpg.is_dearpygui_running():
            dpg.create_context()
        with dpg.window(tag="test_parent"):
            self.plugin.create_ui(parent="test_parent", api=self.mock_api)

        # Setup active viewer with a profile
        viewer = MagicMock()
        viewer.image_id = "image_abc"
        viewer.view_state = MagicMock()
        profile = ProfileLineState()
        profile.id = "p1"
        profile.name = "My Test Profile"
        profile.pt1_phys = np.array([0.0, 0.0, 0.0])
        profile.pt2_phys = np.array([10.0, 10.0, 0.0])
        viewer.view_state.profiles = {"p1": profile}
        viewer.volume = MagicMock()
        self.mock_api.get_active_viewer.return_value = viewer
        self.mock_api.get_image_display_name.return_value = ("Image ABC", False)
        self.mock_api.get_profile_data.return_value = (
            np.array([0, 10]),
            np.array([100, 200]),
        )

        # Render list and open plot window
        self.plugin.update(self.mock_api)
        self.plugin._ui.on_plot_clicked(None, None, "p1")
        win_tag = "profile_plugin_plot_win_p1"
        self.assertTrue(dpg.does_item_exist(win_tag))

        # Test gathering plots
        self.plugin._ui.on_gather_plots_clicked(None, None, None)
        
        pos = dpg.get_item_pos(win_tag)
        self.assertIsNotNone(pos)
        self.assertEqual(profile.plot_position, pos)

        # Cleanup
        self.plugin._ui.on_plot_closed(win_tag, None, "p1")
        dpg.delete_item("test_parent")

    def test_copy_profile(self):
        from vvv.utils import ViewMode
        
        # 1. Setup mock source and target images/view states
        src_vs = MagicMock()
        target_vs = MagicMock()
        target_vs.profiles = {}
        target_vs.world_to_display.return_value = np.array([5.0, 5.0, 12.0])
        
        target_vol = MagicMock()
        target_vol.shape3d = (20, 20, 20)

        view_states = {"image_src": src_vs, "image_target": target_vs}
        volumes = {"image_target": target_vol}
        
        self.mock_api.get_view_states.return_value = view_states
        self.mock_api.get_volumes.return_value = volumes
        self.mock_api.get_image_display_name.side_effect = lambda img_id: (img_id, False)

        profile = ProfileLineState()
        profile.id = "p1"
        profile.name = "Copied Profile"
        profile.color = [255, 0, 0, 255]
        profile.pt1_phys = np.array([0.0, 0.0, 0.0])
        profile.pt2_phys = np.array([10.0, 10.0, 0.0])
        profile.orientation = ViewMode.AXIAL
        profile.slice_idx = 5
        profile.visible = True
        profile.use_log = True

        controller = self.plugin._controller
        controller.bind(self.mock_api)
        
        # 2. Call copy_profile_to_image
        controller.copy_profile_to_image(profile, "image_target")

        # 3. Assert target_vs.profiles has a cloned profile with expected properties
        self.assertEqual(len(target_vs.profiles), 1)
        cloned_id = list(target_vs.profiles.keys())[0]
        cloned = target_vs.profiles[cloned_id]
        
        self.assertEqual(cloned.name, "Copied Profile")
        self.assertEqual(cloned.color, [255, 0, 0, 255])
        self.assertTrue(np.array_equal(cloned.pt1_phys, profile.pt1_phys))
        self.assertTrue(np.array_equal(cloned.pt2_phys, profile.pt2_phys))
        self.assertEqual(cloned.orientation, ViewMode.AXIAL)
        self.assertEqual(cloned.slice_idx, 12)  # Projected to slice 12 based on midpoint (Z/v_idx=2)
        self.assertTrue(cloned.use_log)
        self.assertTrue(cloned.visible)
        
        self.assertTrue(target_vs.is_geometry_dirty)
        self.mock_api.notify.assert_called_with("Copied profile 'Copied Profile' to 'image_target'")
        self.mock_api.request_refresh.assert_called_once()

    def test_on_image_removed_closes_tracked_plot_windows(self):
        """Verify on_image_removed closes plot windows even when view_state is already deleted (PA10)."""
        if not dpg.is_dearpygui_running():
            dpg.create_context()
        controller = self.plugin._controller
        controller.bind(self.mock_api)

        win_tag = controller._t("plot_win_test_p1")
        if dpg.does_item_exist(win_tag):
            dpg.delete_item(win_tag)
        dpg.add_window(tag=win_tag)
        self.assertTrue(dpg.does_item_exist(win_tag))

        controller.track_plot_window("img_removed", win_tag)

        # view state is already gone from api
        self.mock_api.get_view_states.return_value = {}

        controller.on_image_removed("img_removed")
        self.assertFalse(dpg.does_item_exist(win_tag))

    def test_on_plot_closed_when_another_image_is_active(self):
        """Verify on_plot_closed marks plot_open=False on the owning image even if another image is active (PA10)."""
        if not dpg.is_dearpygui_running():
            dpg.create_context()
        ui = self.plugin._ui
        controller = self.plugin._controller
        controller.bind(self.mock_api)

        p1 = ProfileLineState()
        p1.id = "p1"
        p1.plot_open = True

        vs_img1 = MagicMock()
        vs_img1.profiles = {"p1": p1}

        vs_img2 = MagicMock()
        vs_img2.profiles = {}

        self.mock_api.get_view_states.return_value = {"img1": vs_img1, "img2": vs_img2}

        # Active viewer is for img2
        viewer_img2 = MagicMock()
        viewer_img2.image_id = "img2"
        viewer_img2.view_state = vs_img2
        self.mock_api.get_active_viewer.return_value = viewer_img2

        win_tag = controller._t("plot_win_p1")
        if dpg.does_item_exist(win_tag):
            dpg.delete_item(win_tag)
        dpg.add_window(tag=win_tag)
        controller.track_plot_window("img1", win_tag)

        # Close the window from img1
        ui.on_plot_closed(win_tag, None, {"image_id": "img1", "profile_id": "p1"})

        self.assertFalse(p1.plot_open)
        self.assertFalse(dpg.does_item_exist(win_tag))


if __name__ == "__main__":
    unittest.main()
