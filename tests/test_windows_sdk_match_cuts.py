"""Regression for the V1.2.5 Windows SDK CUTS crash after NXnative MATCH_CUTS migration.

The legacy raw SDK scanner must not compete with the official function
matcher. A fixed CUTS entry suppresses all function-matched patches for
that build in upstream dm/tools/patch_nso.py.
"""
from pathlib import Path
from types import SimpleNamespace
import importlib.util
import unittest

ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "engine/win/build_ipa_windows.py"
SDK_PATCHES = ROOT / "engine/dm/tools/sdk_patches.py"
PATCH_NSO = ROOT / "engine/dm/tools/patch_nso.py"


def source_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class WindowsSDKPatchCompatibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.windows = source_module(WRAPPER, "hooklinkwindows_sdk_compat")
        cls.upstream = source_module(SDK_PATCHES, "hooklinkwindows_sdk_rules")

    def test_current_original_sdk_wide_registry_needs_no_legacy_scanner(self):
        # This used to crash at import_module('sdk_patches').CUTS.
        self.assertTrue(self.upstream.MATCH_CUTS.get("sdk"))
        self.assertFalse(self.windows.needs_legacy_sdk_cuts(
            self.upstream, "1234567890abcdef1234567890abcdef"
        ))

    def test_registered_fixed_build_still_skips_scanner(self):
        for rules in ({}, {"sdk": ["matched upstream rule"]}):
            table = SimpleNamespace(CUTS={"abc": [(1, "00", "ff", "fixed")]},
                                    MATCH_CUTS=rules)
            self.assertFalse(self.windows.needs_legacy_sdk_cuts(table, "abc"))

    def test_old_sdk_table_without_match_rules_uses_legacy_fallback(self):
        for table in (SimpleNamespace(), SimpleNamespace(CUTS={}),
                      SimpleNamespace(CUTS={}, MATCH_CUTS={}),
                      SimpleNamespace(CUTS={}, MATCH_CUTS={"main": [1]})):
            self.assertTrue(self.windows.needs_legacy_sdk_cuts(table, "abc"))

    def test_no_sdk_function_matcher_is_not_conflated_with_other_modules(self):
        table = SimpleNamespace(MATCH_CUTS={"main": [1], "sdk": []})
        self.assertTrue(self.windows.needs_legacy_sdk_cuts(table, "abc"))

    def test_wrapper_defers_to_native_matcher_instead_of_creating_cuts(self):
        wrapper = WRAPPER.read_text(encoding="utf-8")
        native = PATCH_NSO.read_text(encoding="utf-8")
        self.assertIn("if needs_legacy_sdk_cuts(patches, bid):", wrapper)
        self.assertNotIn("import_module('sdk_patches').CUTS", wrapper)
        self.assertIn("if BUILD_ID not in PATCHES['CUTS']:", native)
        self.assertIn("PATCHES['SDK_MATCH_CUTS'].get(NAME, [])", native)

    def test_default_no_mod_path_remains_unmodified(self):
        shim = (ROOT / "engine/win/pyshim/sitecustomize.py").read_text(encoding="utf-8")
        # Only the legacy SDK fallback registers fixed CUTS through the shim.
        # User mods must not create a CUTS entry, which disables native matching.
        self.assertIn("if os.environ.get('NXW_AUTO_SDK_CUTS'):", shim)
        self.assertNotIn("NXW_MOD_CUTS", shim)
        self.assertIn("if not hasattr(m, 'CUTS'): m.CUTS = {}", shim)
        native = PATCH_NSO.read_text(encoding="utf-8")
        self.assertLess(native.index("if BUILD_ID not in PATCHES['CUTS']:"),
                        native.index("if os.environ.get('NXW_MOD_CUTS'):"))
        self.assertLess(native.index("if os.environ.get('NXW_MOD_CUTS'):"),
                        native.index("ALIAS_APPLIED ="))


if __name__ == "__main__":
    unittest.main()
