import importlib
import pkgutil
import sys
import unittest


class TestCoreIsolation(unittest.TestCase):
    def test_core_modules_import_without_odoo(self):
        sys.modules["odoo"] = None
        try:
            core = importlib.import_module("core")
            names = [
                info.name
                for info in pkgutil.iter_modules(core.__path__, prefix="core.")
                if not info.ispkg
            ]
            self.assertTrue(names)
            for name in names:
                importlib.import_module(name)
        finally:
            sys.modules.pop("odoo", None)
