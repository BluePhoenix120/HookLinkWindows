"""Platform-neutral unit checks for the Alpha V1.0.0 Windows translator bootstrap.

These tests do not invoke dotnet, change the shader chain, or require Apple SDKs.
"""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

BOOT = Path(__file__).resolve().parents[1] / 'win' / 'bootstrap_translator.py'
spec = importlib.util.spec_from_file_location('hlw_alpha_bootstrap', BOOT)
bootstrap = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(bootstrap)


class TestAlphaTranslatorBootstrap(unittest.TestCase):
    def test_source_fingerprint_is_ordered_raw_bytes(self):
        with tempfile.TemporaryDirectory() as folder:
            src = Path(folder)
            (src / 'Program.cs').write_bytes(b'hello\r\n')
            (src / 'dmsh_xlate.csproj').write_bytes(b'project\n')
            import hashlib
            digest = hashlib.sha256(b'hello\r\nproject\n').hexdigest()[:16]
            self.assertEqual(bootstrap.source_sha(src), digest)

    def test_portable_root_paths(self):
        root = Path('C:/TestCheckout')
        names = bootstrap.paths(root)
        self.assertEqual(names['project'], root / 'engine/dm/gfx/tools/dmsh_xlate')
        self.assertEqual(names['header'], root / 'engine/dm/gfx/nvn/dmsh_chain.h')

    def test_explicit_spirv_tool_must_exist(self):
        with tempfile.TemporaryDirectory() as folder:
            fake = Path(folder) / 'spirv-cross.exe'
            with self.assertRaisesRegex(RuntimeError, 'SPIRV-Cross missing'):
                bootstrap.locate_spirv(None, str(fake))
            fake.write_bytes(b'fake binary')
            self.assertEqual(bootstrap.locate_spirv(None, str(fake)), fake.resolve())

    def test_missing_consent_does_not_modify_files(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with mock.patch.object(bootstrap, 'inspect', return_value=({}, {'ready': False})):
                with self.assertRaisesRegex(RuntimeError, 'accept-new-chain'):
                    bootstrap.install(root, None, False)
            self.assertEqual(list(root.iterdir()), [])

    def test_already_verified_is_a_no_op(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with mock.patch.object(bootstrap, 'inspect', return_value=({}, {'ready': True})):
                bootstrap.install(root, None, False)
            self.assertEqual(list(root.iterdir()), [])

    def test_no_git_metadata_requires_no_clean_state_check(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            bootstrap.ensure_clean_tracked_state({'root': root})

    def test_hidden_process_options_windows(self):
        from types import SimpleNamespace
        startup = SimpleNamespace(dwFlags=0, wShowWindow=-1)
        with mock.patch.object(bootstrap.os, 'name', 'nt'), \
             mock.patch.object(bootstrap.subprocess, 'STARTUPINFO', return_value=startup, create=True), \
             mock.patch.object(bootstrap.subprocess, 'STARTF_USESHOWWINDOW', 1, create=True), \
             mock.patch.object(bootstrap.subprocess, 'SW_HIDE', 0, create=True), \
             mock.patch.object(bootstrap.subprocess, 'CREATE_NO_WINDOW', 0x08000000, create=True):
            options = bootstrap.hidden_process_options()
        self.assertEqual(options['creationflags'], 0x08000000)
        self.assertEqual(options['startupinfo'].dwFlags, 1)
        self.assertEqual(options['startupinfo'].wShowWindow, 0)

    def test_hidden_process_options_non_windows(self):
        with mock.patch.object(bootstrap.os, 'name', 'posix'):
            self.assertEqual(bootstrap.hidden_process_options(), {})

    def test_dotnet_build_disables_background_servers_without_global_settings(self):
        with mock.patch.dict(bootstrap.os.environ, {'SAMPLE': 'kept', 'DOTNET_CLI_DO_NOT_USE_MSBUILD_SERVER': '0'}, clear=True):
            env = bootstrap.isolated_dotnet_build_environment()
            self.assertEqual(env['SAMPLE'], 'kept')
            self.assertEqual(env['DOTNET_CLI_DO_NOT_USE_MSBUILD_SERVER'], '1')
            self.assertEqual(env['MSBUILDDISABLENODEREUSE'], '1')
            self.assertEqual(bootstrap.os.environ['DOTNET_CLI_DO_NOT_USE_MSBUILD_SERVER'], '0')

    def test_clean_git_checks_use_hidden_process_options(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / '.git').mkdir()
            with mock.patch.object(bootstrap.shutil, 'which', return_value='git'), \
                 mock.patch.object(bootstrap, 'hidden_process_options', return_value={'creationflags': 0x08000000}), \
                 mock.patch.object(bootstrap.subprocess, 'run') as runner:
                runner.return_value.returncode = 0
                bootstrap.ensure_clean_tracked_state({'root': root})
                self.assertEqual(runner.call_count, 2)
                self.assertTrue(all(call.kwargs.get('creationflags') == 0x08000000 for call in runner.call_args_list))


class TestPinnedEngineSourceIdentity(unittest.TestCase):
    OLD = '3a28152fe7052c9f45ede460022d39be6c91e3cf'
    X2 = '7ba845ab8b7e8f04639f179ee2adc6aad17ddfdf'
    REPO = 'https://github.com/dsi-hub/nxnative.git'

    def make_checkout(self, root, version='3.0', sha=None, include_manifest=True):
        sha = self.X2 if sha is None else sha
        (root / 'VERSION').write_text(version + '\n', encoding='utf-8')
        pin = {'hooklink_base': version, 'nxnative_repo': self.REPO,
               'nxnative_commit': sha, 'engine_location': 'engine/'}
        (root / 'ENGINE_PIN.json').write_text(json.dumps(pin), encoding='utf-8')
        if include_manifest:
            manifest = {'nxnative_repo': self.REPO, 'nxnative_commit': sha,
                        'changed_paths': [{'path': f'engine/dm/test{i}', 'sha': 'f' * 40}
                                          for i in range(25)]}
            (root / 'ENGINE_PIN_FILES.json').write_text(json.dumps(manifest), encoding='utf-8')
        return pin

    def test_actual_checkout_is_accepted_before_toolchain_setup(self):
        root = BOOT.parents[1]
        data = json.loads((root / 'ENGINE_PIN.json').read_text(encoding='utf-8'))
        version = (root / 'VERSION').read_text(encoding='utf-8').strip()
        self.assertIn((version, data['nxnative_commit']), (
            ('3.0', self.X2),
            ('3.0.1', '0b5fd6020093407af8bb5ad166e78e00bd2b7242'),
            ('3.0.1', 'd2fd78b402f92d5a83b78987e49aba22e8626719'),
            ('3.0.1', '3ec5b785f37f8c87d78433f152914d89c4ef93c9'),
            ('3.0.1', '3e1ada5b96acb61293ac790bd6dd093a947abed6'),
            ('4.0', '5dfc86ae80c53a62262c3b3c66eab043f1fc574a'),
        ))
        self.assertEqual(bootstrap.verify_source_identity(root), (version, data['nxnative_commit']))

    def test_x2_snapshot_passes_without_dotnet_or_metal(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.make_checkout(root)
            with mock.patch.object(bootstrap.shutil, 'which', side_effect=AssertionError('external tools must not run')):
                self.assertEqual(bootstrap.verify_source_identity(root), ('3.0', self.X2))

    def test_hybrid_official_nxnative_with_hooklink_custom_engine(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            latest = '0b5fd6020093407af8bb5ad166e78e00bd2b7242'
            custom = '698b46bc5b14510fffc0a4b8fd4bf78309004e4c'
            repo = 'https://github.com/seedds/nxnative.git'
            pin = self.make_checkout(root, version='3.0.1', sha=latest, include_manifest=False)
            pin['nxnative_repo'] = repo
            (root / 'ENGINE_PIN.json').write_text(json.dumps(pin), encoding='utf-8')
            manifest = {'nxnative_repo': repo, 'nxnative_commit': latest,
                        'from_commit': self.X2, 'hooklink_engine_commit': custom,
                        'windows_overlays': ['engine/win/build_app.py'],
                        'changed_paths': [{'path': f'engine/dm/test{i}', 'sha': 'f' * 40}
                                          for i in range(300)]}
            (root / 'ENGINE_PIN_FILES.json').write_text(json.dumps(manifest), encoding='utf-8')
            self.assertEqual(bootstrap.verify_source_identity(root), ('3.0.1', latest))
            manifest['changed_paths'] = manifest['changed_paths'][:20]
            (root / 'ENGINE_PIN_FILES.json').write_text(json.dumps(manifest), encoding='utf-8')
            with self.assertRaisesRegex(RuntimeError, 'integration manifest is incomplete'):
                bootstrap.verify_source_identity(root)

    def test_legacy_hooklink_two_is_still_recognized(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.make_checkout(root, version='2.0', sha=self.OLD, include_manifest=False)
            self.assertEqual(bootstrap.verify_source_identity(root), ('2.0', self.OLD))

    def test_version_and_pin_must_identify_same_known_release(self):
        for version, sha in (('2.0', self.X2), ('3.0', self.OLD),
                             ('4.0', self.X2), ('3.0', 'f' * 40)):
            with self.subTest(version=version, sha=sha), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                self.make_checkout(root, version=version, sha=sha)
                with self.assertRaisesRegex(RuntimeError, 'Unsupported HookLink'):
                    bootstrap.verify_source_identity(root)

    def test_mismatched_hooklink_base_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            pin = self.make_checkout(root)
            pin['hooklink_base'] = '2.0'
            (root / 'ENGINE_PIN.json').write_text(json.dumps(pin), encoding='utf-8')
            with self.assertRaisesRegex(RuntimeError, 'disagrees'):
                bootstrap.verify_source_identity(root)

    def test_missing_and_corrupt_x2_manifest_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.make_checkout(root, include_manifest=False)
            with self.assertRaisesRegex(RuntimeError, 'manifest missing'):
                bootstrap.verify_source_identity(root)
            (root / 'ENGINE_PIN_FILES.json').write_text('{bad json', encoding='utf-8')
            with self.assertRaisesRegex(RuntimeError, 'Invalid ENGINE_PIN_FILES.json'):
                bootstrap.verify_source_identity(root)
            (root / 'ENGINE_PIN_FILES.json').write_text(
                json.dumps({'nxnative_repo': self.REPO, 'nxnative_commit': self.OLD,
                            'changed_paths': [{}] * 25}), encoding='utf-8')
            with self.assertRaisesRegex(RuntimeError, 'manifest does not match'):
                bootstrap.verify_source_identity(root)

    def test_untrusted_repo_and_malformed_sha_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            pin = self.make_checkout(root)
            pin['nxnative_repo'] = 'https://github.com/other/nxnative.git'
            (root / 'ENGINE_PIN.json').write_text(json.dumps(pin), encoding='utf-8')
            with self.assertRaisesRegex(RuntimeError, 'Unexpected NXNative source'):
                bootstrap.verify_source_identity(root)
            pin['nxnative_repo'] = self.REPO
            pin['nxnative_commit'] = ['not a SHA']
            (root / 'ENGINE_PIN.json').write_text(json.dumps(pin), encoding='utf-8')
            with self.assertRaisesRegex(RuntimeError, 'commit SHA string'):
                bootstrap.verify_source_identity(root)


if __name__ == '__main__':
    unittest.main()
