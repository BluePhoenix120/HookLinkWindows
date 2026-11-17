"""Offline, source-only relocation and SDK selection tests for portable HookLinkWindows.

No Apple SDK, game file, network, compiler or elevated privileges required.
"""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
ENGINE_TOOLCHAIN = REPO_ROOT / 'engine' / 'win' / 'toolchain.py'
PORTABLE_MODULE = REPO_ROOT / 'win' / 'hooklink_portable.py'


def toolchain_at(engine: Path):
    spec = importlib.util.spec_from_file_location('isolated_hooklink_toolchain', ENGINE_TOOLCHAIN)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.WIN = engine / 'win'
    module.REPO = engine
    module.CONFIG = module.WIN / 'toolchain.json'
    return module


def fake_sdk(path: Path, version='27.0', *, complete=True):
    path.mkdir(parents=True, exist_ok=True)
    (path / 'SDKSettings.json').write_text(json.dumps({'Version': version}), encoding='utf-8')
    if complete:
        (path / 'usr/include').mkdir(parents=True)
        (path / 'System/Library/Frameworks').mkdir(parents=True)
    return path


class SDKDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.addCleanup(self.td.cleanup)
        self.work = Path(self.td.name) / 'any volume' / 'user projects'
        self.engine = self.work / 'PortableFork' / 'engine'
        (self.engine / 'win').mkdir(parents=True)
        self.tc = toolchain_at(self.engine)
        self.env = mock.patch.dict(os.environ, {'NXW_IOS_SDK': ''})
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_stale_config_recovers_sdk_in_sibling_checkout_without_rewriting_json(self):
        sdk = fake_sdk(self.work / 'AlternateCheckout' / 'win/sdk/out/iPhoneOS.sdk')
        stale = str(self.work / 'old missing disk' / 'iPhoneOS.sdk')
        raw = json.dumps({'ios_sdk': stale, 'llvm': '/some/other/setting'})
        self.tc.CONFIG.write_text(raw, encoding='utf-8')
        selected, source, warnings = self.tc.ios_sdk_details()
        self.assertEqual(selected, sdk)
        self.assertIn('auto-discovered', source)
        self.assertTrue(any('toolchain.json' in w for w in warnings))
        self.assertEqual(self.tc.CONFIG.read_text(encoding='utf-8'), raw)
        self.assertEqual(self.tc.ios_sdk(), sdk)

    def test_explicit_valid_sdk_wins_over_discovered_newer_one(self):
        preferred = fake_sdk(self.work / 'manual' / 'iPhoneOS.sdk', '26.0')
        fake_sdk(self.work / 'AlternateCheckout' / 'win/sdk/out/iPhoneOS27.sdk', '27.0')
        self.tc.CONFIG.write_text(json.dumps({'ios_sdk': str(preferred)}))
        selected, source, warnings = self.tc.ios_sdk_details()
        self.assertEqual((selected, source, warnings), (preferred, 'toolchain.json', []))

    def test_environment_override_takes_precedence(self):
        configured = fake_sdk(self.work / 'manual' / 'iPhoneOS.sdk', '26.0')
        override = fake_sdk(self.work / 'another' / 'iPhoneOS27.sdk', '27.0')
        self.tc.CONFIG.write_text(json.dumps({'ios_sdk': str(configured)}))
        with mock.patch.dict(os.environ, {'NXW_IOS_SDK': str(override)}):
            self.assertEqual(self.tc.ios_sdk_details()[:2], (override, 'NXW_IOS_SDK'))

    def test_stale_env_path_falls_through_to_valid_json_path(self):
        valid = fake_sdk(self.work / 'manual' / 'iPhoneOS.sdk', '26.0')
        self.tc.CONFIG.write_text(json.dumps({'ios_sdk': str(valid)}))
        with mock.patch.dict(os.environ, {'NXW_IOS_SDK': str(self.work / 'absent')}):
            chosen, source, warnings = self.tc.ios_sdk_details()
        self.assertEqual(chosen, valid)
        self.assertEqual(source, 'toolchain.json')
        self.assertEqual(len(warnings), 1)

    def test_relative_json_path_resolves_from_toolchain_directory(self):
        sdk = fake_sdk(self.engine / 'win/sdk/out/iPhoneOS.sdk')
        self.tc.CONFIG.write_text(json.dumps({'ios_sdk': 'sdk/out/iPhoneOS.sdk'}))
        self.assertEqual(self.tc.ios_sdk_details()[:2], (sdk, 'toolchain.json'))

    def test_project_and_engine_placeholders_resolve_without_fixed_drive(self):
        sdk = fake_sdk(self.engine / 'win/sdk/out/iPhoneOS.sdk')
        for value in ('${ENGINE}/win/sdk/out/iPhoneOS.sdk', '${PROJECT}/engine/win/sdk/out/iPhoneOS.sdk'):
            with self.subTest(value=value):
                self.tc.CONFIG.write_text(json.dumps({'ios_sdk': value}))
                self.assertEqual(self.tc.ios_sdk_details()[:2], (sdk, 'toolchain.json'))

    def test_nested_sdk_folder_discovered(self):
        sdk = fake_sdk(self.work / 'other' / 'win/sdk/out/Platforms/iPhoneOS.platform/Developer/SDKs/iPhoneOS27.2.sdk', '27.2')
        self.assertEqual(self.tc.ios_sdk(), sdk)

    def test_incomplete_or_older_sdk_not_selected(self):
        fake_sdk(self.engine / 'win/sdk/out/iPhoneOS25.sdk', '25.4')
        fake_sdk(self.work / 'broken' / 'win/sdk/out/iPhoneOS26.sdk', '26.0', complete=False)
        sdk = fake_sdk(self.work / 'good' / 'win/sdk/out/iPhoneOS27.sdk', '27.0')
        self.assertEqual(self.tc.ios_sdk(), sdk)

    def test_no_valid_sdk_yields_none_without_mutating_config(self):
        raw = '{"ios_sdk":"C:/not/a/valid/sdk"}'
        self.tc.CONFIG.write_text(raw)
        self.assertIsNone(self.tc.ios_sdk())
        self.assertEqual(self.tc.CONFIG.read_text(), raw)

    def test_checkout_can_be_moved_and_renamed_with_sibling_sdk(self):
        sdk = fake_sdk(self.work / 'other' / 'win/sdk/out/iPhoneOS.sdk')
        self.assertEqual(self.tc.ios_sdk(), sdk)
        moved = self.work.parent / 'moved here' / 'Renamed Work'
        moved.parent.mkdir(parents=True)
        shutil.move(str(self.work), str(moved))
        new_engine = moved / 'PortableFork' / 'engine'
        new_tc = toolchain_at(new_engine)
        self.assertEqual(new_tc.ios_sdk(), moved / 'other' / 'win/sdk/out/iPhoneOS.sdk')

    def test_local_sdk_preferred_over_sibling_checkout(self):
        local = fake_sdk(self.engine / 'win/sdk/out/iPhoneOS.sdk', '26.0')
        fake_sdk(self.work / 'other' / 'win/sdk/out/iPhoneOS27.sdk', '27.0')
        self.assertEqual(self.tc.ios_sdk(), local)


class PortabilitySettingsTests(unittest.TestCase):
    def test_saved_donor_and_native_packaging_flags_survive_restart(self):
        spec = importlib.util.spec_from_file_location('isolated_hooklink_portable', PORTABLE_MODULE)
        mod = importlib.util.module_from_spec(spec)
        import sys
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / 'project'
            root.mkdir()
            settings = Path(td) / 'prefs.json'
            donor = str(Path(td) / 'donor')
            mod.SettingsStore(root, settings).save({'reuse_shader_work': donor, 'native_app_only': True})
            restored, warnings = mod.SettingsStore(root, settings).load()
            self.assertEqual(restored['reuse_shader_work'], os.path.normpath(donor))
            self.assertTrue(restored['native_app_only'])
            self.assertEqual(warnings, [])

    def test_gui_browse_buttons_apply_native_path_formatter(self):
        gui = (REPO_ROOT / 'win' / 'hooklink_gui.pyw').read_text(encoding='utf-8')
        self.assertIn('DEFAULT_WORK = ROOT.parent / DEFAULT_WORK_NAME', gui)
        self.assertIn('initialdir=str(Path(self.input_var.get()).parent if Path(self.input_var.get()).is_file() else ROOT.parent)', gui)
        for field in ('input_var', 'work_var', 'env_var', 'output_var'):
            self.assertIn(f'self.{field}.set(native_display_path(f))', gui)
        self.assertIn('self.reuse_var.set(native_display_path(folder))', gui)


if __name__ == '__main__':
    unittest.main()
