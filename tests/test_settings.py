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

if __name__ == "__main__":
    unittest.main()
