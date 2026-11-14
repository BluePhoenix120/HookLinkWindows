"""Offline clean-room/relocation regression tests; do not invoke compilers or games."""
from __future__ import annotations
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'win'))
from hooklink_portable import (SettingsStore, check_project_installation, locate_engine_root,
                               user_settings_path, PRESET_REL)

REQUIRED = ('win/build_ipa_windows.py', 'win/build_app.py', 'win/doctor.py',
            'win/toolchain.py', 'win/sdk/extract_xip.py', 'dm/host/Makefile', 'dm/gfx/tools/dmsh_build.py',
            'scripts/build_ipa_from_nsp.py', PRESET_REL)


def make_fake_complete_checkout(root):
    for rel in REQUIRED:
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text('# placeholder for offline structural test\n', encoding='utf-8')


class PortableTests(unittest.TestCase):
    def test_standalone_overlay_identifies_missing_engine(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / 'Unpacked from GitHub'
            (root / 'win').mkdir(parents=True)
            (root / 'win' / 'hooklink_gui.pyw').write_text('')
            report = check_project_installation(root)
            self.assertFalse(report.ready_for_doctor)
            self.assertTrue(any('Windows IPA driver' in x for x in report.blockers))

    def test_incomplete_checkout_explains_cause_and_remedy_next_to_status(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / 'GUI-only'
            root.mkdir()
            report = check_project_installation(root)
            summary = report.summary()
            self.assertIn('Repository layout: incomplete', summary)
            self.assertIn('Why: This folder does not contain the complete', summary)
            self.assertIn('How to fix: Download the complete', summary)
            self.assertIn('HookLinkWindows.exe', summary)
            self.assertIn('Check prerequisites again', summary)
            self.assertLess(summary.index('Repository layout: incomplete'), summary.index('Why:'))
            self.assertLess(summary.index('Why:'), summary.index('How to fix:'))


    def test_public_hooklink_fork_uses_nested_engine_layout(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / 'HookLinkWindows'
            for rel in REQUIRED:
                base = root if rel == PRESET_REL else root / 'engine'
                p = base / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text('# source placeholder\n', encoding='utf-8')
            report = check_project_installation(root)
            self.assertTrue(report.ready_for_doctor, report.summary())
            self.assertTrue(locate_engine_root(root).samefile(root / 'engine'))
            self.assertIn('under engine/', report.summary())
            self.assertTrue((root / 'config' / 'iphone-oot.env').is_file())

    def test_public_fork_missing_engine_has_precise_remedy(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / 'HookLink fork only'
            (root / PRESET_REL).parent.mkdir(parents=True)
            (root / PRESET_REL).write_text('DM_NVN_BARRIER=full\n', encoding='utf-8')
            report = check_project_installation(root)
            self.assertFalse(report.ready_for_doctor)
            self.assertTrue(any('engine/win/build_ipa_windows.py' in x for x in report.blockers))
            self.assertIn('engine/ Windows source tree', report.summary())

    def test_relocated_checkout_recognized_without_fixed_absolute_root(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            root_a = p / 'Downloads' / 'HookLinkWindows'
            root_b = p / 'Other Drive' / 'Projects' / 'HookLinkWindows'
            make_fake_complete_checkout(root_a)
            self.assertTrue(check_project_installation(root_a).ready_for_doctor)
            shutil.move(str(root_a), str(root_b))
            report = check_project_installation(root_b)
            self.assertTrue(report.ready_for_doctor, report.summary())
            self.assertEqual(report.root, root_b.resolve())
            self.assertFalse(any('C:\\HookLinkWindows' in x for x in report.summary().splitlines()))

    def test_preferences_survive_move_with_project_relative_config(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            root_a = p / 'checkout-one'
            root_b = p / 'checkout-two'
            root_a.mkdir()
            root_b.mkdir()
            conf_a = root_a / PRESET_REL
            conf_a.parent.mkdir(parents=True)
            conf_a.write_text('DM_NVN_BARRIER=full\n')
            settings_path = p / 'user profile' / 'HookLinkWindows' / 'gui-settings.json'
            values = {'input_path': str(p / 'my games' / 'OOT.nup'),
                      'work_dir': str(p / 'work'),
                      'env_file': str(conf_a),
                      'output_ipa': str(p / 'work' / 'myapp.ipa'),
                      'bundle_id': 'org.sample.oot', 'workers': 8,
                      'allow_damaged': False, 'allow_metal': True,
                      'entitlements': True, 'output_auto': False}
            SettingsStore(root_a, settings_path).save(values)
            stored = json.loads(settings_path.read_text())
            self.assertEqual(stored['settings']['env_file'], '${PROJECT}/config/iphone-oot.env')
            fetched, warnings = SettingsStore(root_b, settings_path).load()
            self.assertEqual(warnings, [])
            self.assertEqual(fetched['env_file'], str(root_b / PRESET_REL))
            self.assertEqual(fetched['work_dir'], values['work_dir'])
            self.assertEqual(fetched['bundle_id'], values['bundle_id'])
            self.assertEqual(fetched['output_auto'], False)

    def test_old_preferences_upgrade_flags_without_losing_paths(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / 'gui-settings.json'
            old = {'version': 1, 'settings': {'allow_damaged': False,
                   'allow_metal': False, 'bundle_id': 'org.test.sample',
                   'work_dir': str(Path(td) / 'Build'), 'workers': 8}}
            p.write_text(json.dumps(old), encoding='utf-8')
            store = SettingsStore(Path(td), p)
            values, warnings = store.load()
            self.assertTrue(warnings)
            self.assertNotIn('allow_damaged', values)
            self.assertNotIn('allow_metal', values)
            self.assertEqual(values['bundle_id'], 'org.test.sample')
            self.assertEqual(values['workers'], 8)
            self.assertEqual(json.loads(p.read_text()), old)  # no changes until saved
            values['allow_damaged'] = True
            values['allow_metal'] = True
            store.save(values)
            saved = json.loads(p.read_text(encoding='utf-8'))
            self.assertEqual(saved['version'], 2)
            new_values, warnings = store.load()
            self.assertEqual(warnings, [])
            self.assertTrue(new_values['allow_damaged'])
            self.assertTrue(new_values['allow_metal'])

    def test_new_preferences_respect_user_disabled_flags(self):
        with tempfile.TemporaryDirectory() as td:
            store = SettingsStore(Path(td), Path(td) / 'prefs.json')
            store.save({'allow_damaged': False, 'allow_metal': False})
            values, warnings = store.load()
            self.assertFalse(values['allow_damaged'])
            self.assertFalse(values['allow_metal'])
            self.assertFalse(warnings)

    def test_bad_preferences_do_not_crash_and_are_not_overwritten(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / 'gui-settings.json'
            p.write_text('This is not JSON', encoding='utf-8')
            values, warnings = SettingsStore(Path(td), p).load()
            self.assertEqual(values, {})
            self.assertTrue(warnings)
            self.assertEqual(p.read_text(), 'This is not JSON')

    def test_stale_local_toolchain_paths_reported_not_rewritten(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / 'Repo'
            make_fake_complete_checkout(root)
            config = root / 'win' / 'toolchain.json'
            original = json.dumps({'ios_sdk': str(Path(td) / 'Removed' / 'iPhoneOS.sdk')})
            config.write_text(original, encoding='utf-8')
            report = check_project_installation(root)
            self.assertTrue(report.ready_for_doctor)
            self.assertTrue(any('ios_sdk' in x and 'missing' in x for x in report.advisories))
            self.assertEqual(config.read_text(), original)

    def test_app_data_settings_path_not_repo_relative(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td) / 'UserAppData'
            path = user_settings_path(home=Path(td) / 'user', local_appdata=str(base))
            self.assertEqual(path, base / 'HookLinkWindows' / 'gui-settings.json')

if __name__ == '__main__':
    unittest.main()

# Keep source-only safeguards independent from the GUI runtime.
class SourceReleaseAuditTests(unittest.TestCase):
    def test_flags_private_artifacts(self):
        import importlib.util
        script = ROOT / 'tools' / 'release_audit.py'
        spec = importlib.util.spec_from_file_location('release_audit_for_test', script)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / 'win').mkdir()
            (root / 'win' / 'toolchain.json').write_text('{}')
            (root / 'game.nup').write_bytes(b'private')
            (root / 'game.ipa').write_bytes(b'private')
            flagged, _ = mod.audit(root)
            self.assertIn('game.nup', flagged)
            self.assertIn('game.ipa', flagged)
            self.assertIn('win/toolchain.json', flagged)

    def test_public_overlay_has_no_private_artifact_names(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location('release_audit_for_test2', ROOT / 'tools' / 'release_audit.py')
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        flagged, _ = mod.audit(ROOT)
        self.assertEqual(flagged, [])
