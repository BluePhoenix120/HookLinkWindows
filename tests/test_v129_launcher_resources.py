"""Regression tests for the Windows-native X3 resource and controller ports."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("launcher_resources", ROOT / "engine/win/launcher_resources.py")
resources = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(resources)


class LauncherResourceTests(unittest.TestCase):
    def test_control_and_packed_default_picture(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            engine = root / "engine"
            app = root / "app"
            dm = app / "dm"
            dm.mkdir(parents=True)
            control = root / "control.nacp"
            control.write_bytes(b"control")
            photo = root / "Resources/presets/launcher_background.jpg"
            photo.parent.mkdir(parents=True)
            photo.write_bytes(b"picture")
            resources.stage_launcher_resources(engine, app, dm, control, root / "RomFS.img", True, {})
            self.assertEqual((dm / "control.nacp").read_bytes(), b"control")
            self.assertEqual((dm / "launcher_background.jpg").read_bytes(), b"picture")
            self.assertFalse((app / "mods_rstb.bin").exists())

    def test_new_engine_mod_table_is_optional_and_failure_cleans_partial_file(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            engine = root / "engine"
            generator = engine / "scripts/oot_mods_rstb.py"
            generator.parent.mkdir(parents=True)
            generator.touch()
            app = root / "app"
            dm = app / "dm"
            dm.mkdir(parents=True)
            output = app / "mods_rstb.bin"
            def fake_run(cmd, **kwargs):
                self.assertEqual(Path(cmd[3]), output)
                output.write_bytes(b"partial")
                return SimpleNamespace(returncode=1, stderr="invalid table", stdout="")
            with patch.object(resources.subprocess, "run", side_effect=fake_run):
                resources.stage_launcher_resources(engine, app, dm, root / "control", root / "RomFS.img", True, {})
            self.assertFalse(output.exists())

    def test_native_game_menu_offers_custom_layout_only_when_supported(self):
        source = (ROOT / "engine/win/ios/GameMenu.m").read_text(encoding="utf-8")
        self.assertIn('@"Custom"', source)
        self.assertIn("dm_pad_layout_offered(4)", source)
        self.assertIn("dm_pad_custom_edit()", source)


if __name__ == "__main__":
    unittest.main()
