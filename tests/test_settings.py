import platform
import unittest
from typing import cast
from vvv.core.controller import Controller

class TestSettingsUpdate(unittest.TestCase):
    def setUp(self):
        self.controller = Controller()

    def test_update_existing_setting(self):
        self.controller.update_setting(["behavior", "recent_files"], ["test_file.nii"])
        self.assertEqual(
            self.controller.settings.data["behavior"]["recent_files"],
            ["test_file.nii"]
        )

    def test_update_missing_nested_setting(self):
        self.controller.update_setting(["plugins", "my_new_plugin", "enable_mode"], True)
        self.assertIn("plugins", self.controller.settings.data)
        plugins = cast(dict, self.controller.settings.data["plugins"])
        self.assertIn("my_new_plugin", plugins)
        my_new_plugin = cast(dict, plugins["my_new_plugin"])
        self.assertEqual(my_new_plugin["enable_mode"], True)

    def test_update_non_dict_guard(self):
        self.controller.update_setting(["behavior", "flat_val"], "hello")
        self.assertEqual(self.controller.settings.data["behavior"]["flat_val"], "hello")

        # Traversing deeper than a flat value should return safely without raising an error
        self.controller.update_setting(["behavior", "flat_val", "deeper_nested"], 42)
        self.assertEqual(self.controller.settings.data["behavior"]["flat_val"], "hello")

    def test_add_recent_file_absolute(self):
        # Storing a relative path should make it absolute
        self.controller.add_recent_file("test_file.nii")
        recent = cast(list, self.controller.settings.data["behavior"]["recent_files"])
        import os
        self.assertEqual(recent[0], os.path.abspath("test_file.nii"))

        # Storing a 4D path with relative paths
        self.controller.add_recent_file('4D: "test_a.nii" "test_b.nii"')
        recent = cast(list, self.controller.settings.data["behavior"]["recent_files"])
        expected_4d = '4D:"{}" "{}"'.format(os.path.abspath("test_a.nii"), os.path.abspath("test_b.nii"))
        self.assertEqual(recent[0], expected_4d)

        # Storing a list of relative paths (DICOM series)
        self.controller.add_recent_file(["d1.dcm", "d2.dcm"])
        recent = cast(list, self.controller.settings.data["behavior"]["recent_files"])
        import json
        expected_list = json.dumps([os.path.abspath("d1.dcm"), os.path.abspath("d2.dcm")])
        self.assertEqual(recent[0], expected_list)

    @unittest.skipIf(platform.system() == "Windows", "Unix-specific test")
    def test_resolve_recent_path_home_users(self):
        # Using a file that is known to exist inside the repository
        import os
        repo_file = os.path.abspath("conftest.py")
        
        # If the file exists, it returns it
        self.assertEqual(self.controller.resolve_recent_path(repo_file), repo_file)

        # Construct a fake path starting with another user's path structure.
        # repo_file is /Users/dsarrut/src/py/vvv/conftest.py
        # rel_part is src/py/vvv/conftest.py
        home = os.path.expanduser("~")
        rel_part = os.path.relpath(repo_file, home)
        
        # Test /Users/xxx path resolution
        fake_users_path = os.path.join("/Users", "another_user", rel_part)
        resolved = self.controller.resolve_recent_path(fake_users_path)
        self.assertEqual(resolved, repo_file)

        # Test /home/xxx path resolution
        fake_home_path = os.path.join("/home", "another_user", rel_part)
        resolved = self.controller.resolve_recent_path(fake_home_path)
        self.assertEqual(resolved, repo_file)

class TestHistoryManager(unittest.TestCase):
    def setUp(self):
        import tempfile
        import shutil
        from pathlib import Path
        from vvv.core.history_manager import HistoryManager
        
        self.temp_dir = tempfile.mkdtemp()
        self.history = HistoryManager()
        self.history.config_dir = Path(self.temp_dir)
        self.history.history_path = Path(self.temp_dir) / "history.json"
        self.history.data = {}
        self.shutil = shutil

    def tearDown(self):
        self.shutil.rmtree(self.temp_dir)

    def test_portable_key_resolution(self):
        import os
        from pathlib import Path
        from vvv.utils import get_history_path_key
        
        home = Path.home().resolve()
        path_inside = home / "my_image.nii"
        path_outside = Path("/some/other/path/image.nii")
        
        key_inside = get_history_path_key(str(path_inside))
        key_outside = get_history_path_key(str(path_outside))
        
        self.assertTrue(key_inside.startswith("~/"))
        if os.name != "nt":
            self.assertEqual(key_outside, "/some/other/path/image.nii")

    def test_history_limit(self):
        from unittest.mock import MagicMock
        self.history.max_history_files = 5
        for i in range(10):
            self.history.data[f"item_{i}"] = {"shape3d": [10, 10, 10]}
        
        self.history.save()
        
        controller = MagicMock()
        controller.view_states = {}
        controller.volumes = {}
        
        volume = MagicMock()
        volume.file_paths = ["/tmp/new_image.nii"]
        volume.shape3d = (10, 10, 10)
        volume.spacing = (1.0, 1.0, 1.0)
        volume.origin = (0.0, 0.0, 0.0)
        volume.is_dvf = False
        
        vs = MagicMock()
        vs.camera.to_dict.return_value = {}
        vs.display.to_dict.return_value = {}
        vs.sync_group = 0
        vs.sync_wl_group = 0
        
        controller.volumes["img1"] = volume
        controller.view_states["img1"] = vs
        controller.gui = None
        
        self.history.save_image_state(controller, "img1")
        self.assertEqual(len(self.history.data), 5)

if __name__ == "__main__":
    unittest.main()
