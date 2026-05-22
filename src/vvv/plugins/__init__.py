import importlib
import pkgutil
import os

def discover_plugins():
    """
    Dynamically discovers and instantiates plugins in the vvv.plugins package.
    
    Scans for subdirectories (packages) and inspects them for classes that
    define the basic Plugin interface:
      - Has attributes: `plugin_id` and `label`
      - Exposes methods: `create_ui` and `update`
    
    Returns:
        List of instantiated plugin objects.
    """
    plugins = []
    
    # Get the filesystem path of the current package
    package_path = os.path.dirname(__file__)
    
    for _, module_name, is_pkg in pkgutil.iter_modules([package_path]):
        if not is_pkg:
            continue
            
        full_module_name = f"vvv.plugins.{module_name}"
        try:
            module = importlib.import_module(full_module_name)
            
            for attr_name in dir(module):
                if attr_name.startswith("__"):
                    continue
                attr = getattr(module, attr_name)
                
                # Check if it is a class and implements the duck-typed Plugin interface
                if (
                    isinstance(attr, type)
                    and hasattr(attr, "plugin_id")
                    and hasattr(attr, "label")
                    and hasattr(attr, "create_ui")
                    and hasattr(attr, "update")
                ):
                    try:
                        plugin_instance = attr()
                        plugins.append(plugin_instance)
                    except Exception as inst_err:
                        print(f"Error instantiating plugin {attr_name} from {full_module_name}: {inst_err}")
        except Exception as imp_err:
            # Prevent import errors in a single plugin from crashing the whole app
            print(f"Error importing plugin module {full_module_name}: {imp_err}")
            
    return plugins

__all__ = ["discover_plugins"]
