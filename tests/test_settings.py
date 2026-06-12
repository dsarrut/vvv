import unittest
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
        self.assertIn("my_new_plugin", self.controller.settings.data["plugins"])
        self.assertEqual(
            self.controller.settings.data["plugins"]["my_new_plugin"]["enable_mode"],
            True
        )

    def test_update_non_dict_guard(self):
        self.controller.update_setting(["behavior", "flat_val"], "hello")
        self.assertEqual(self.controller.settings.data["behavior"]["flat_val"], "hello")

        # Traversing deeper than a flat value should return safely without raising an error
        self.controller.update_setting(["behavior", "flat_val", "deeper_nested"], 42)
        self.assertEqual(self.controller.settings.data["behavior"]["flat_val"], "hello")

    def test_add_recent_file_absolute(self):
        # Storing a relative path should make it absolute
        self.controller.add_recent_file("test_file.nii")
        recent = self.controller.settings.data["behavior"]["recent_files"]
        import os
        self.assertEqual(recent[0], os.path.abspath("test_file.nii"))

        # Storing a 4D path with relative paths
        self.controller.add_recent_file('4D: "test_a.nii" "test_b.nii"')
        recent = self.controller.settings.data["behavior"]["recent_files"]
        expected_4d = '4D:"{}" "{}"'.format(os.path.abspath("test_a.nii"), os.path.abspath("test_b.nii"))
        self.assertEqual(recent[0], expected_4d)

        # Storing a list of relative paths (DICOM series)
        self.controller.add_recent_file(["d1.dcm", "d2.dcm"])
        recent = self.controller.settings.data["behavior"]["recent_files"]
        import json
        expected_list = json.dumps([os.path.abspath("d1.dcm"), os.path.abspath("d2.dcm")])
        self.assertEqual(recent[0], expected_list)

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

if __name__ == "__main__":
    unittest.main()
