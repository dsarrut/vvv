import os

def test_rename():
    renames = [
        ("docs/readme_dev.md", "docs/core_overview.md"),
        ("docs/readme_tools_image_types.md", "docs/core_image_types.md"),
        ("docs/readme_dev_rendering.md", "docs/core_rendering.md"),
        ("docs/readme_dev_sync.md", "docs/core_sync.md"),
        ("docs/readme_dev_viewstate_property.md", "docs/core_viewstate_property.md"),
        ("docs/readme_dev_plugins.md", "docs/plugin_architecture.md"),
        ("docs/readme_dev_plugin_api_method.md", "docs/plugin_api_method.md"),
        ("docs/readme_dev_image_list.md", "docs/plugin_image_list.md"),
        ("docs/readme_dev_roi.md", "docs/plugin_roi.md"),
        ("docs/readme_dev_contours.md", "docs/plugin_contours.md"),
        ("docs/readme_dev_reg.md", "docs/plugin_registration.md"),
    ]
    for src, dst in renames:
        if os.path.exists(src):
            print(f"Renaming {src} to {dst}")
            os.rename(src, dst)
        else:
            print(f"Source not found: {src}")
