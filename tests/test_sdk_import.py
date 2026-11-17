"""SDK import tests with tiny fake XIP files; no proprietary Apple archives involved."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'win'))
from hooklink_sdk_import import import_sdk, validate_xip_archive
from hooklink_toolchain_setup import configured_ios_sdk, validate_ios_sdk

spec = importlib.util.spec_from_file_location('hlw_xip_extractor', ROOT / 'engine/win/sdk/extract_xip.py')
xip_extractor = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(xip_extractor)


class SDKImportTests(unittest.TestCase):
    def fixture(self, root):
        extractor = root / 'engine/win/sdk/extract_xip.py'
        extractor.parent.mkdir(parents=True, exist_ok=True)
        extractor.write_text('pass', encoding='utf-8')
        archive = root / 'Xcode_27.2.xip'
        archive.write_bytes(b'xar!testing without a proprietary archive')
        return archive

    @staticmethod
    def create_fake_sdk(_archive, dst, version='27.2'):
        sdk = dst / 'iPhoneOS.sdk'
        (sdk / 'usr/include').mkdir(parents=True)
        (sdk / 'System/Library/Frameworks').mkdir(parents=True)
        (sdk / 'SDKSettings.json').write_text(json.dumps({'Version': version}), encoding='utf-8')

    def test_archive_validation_requires_xip_extension_and_header(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            file = root / 'Xcode.xip'
            file.write_bytes(b'not xar')
            with self.assertRaisesRegex(ValueError, 'not a valid'):
                validate_xip_archive(file)
            file.write_bytes(b'xar!test')
            self.assertEqual(validate_xip_archive(file), file.resolve(strict=False))
            with self.assertRaisesRegex(ValueError, 'Select a downloaded'):
                validate_xip_archive(root / 'not-here.xip')

    def test_successful_import_registers_sdk_without_overwriting_old_settings(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            archive = self.fixture(root)
            cfg = root / 'engine/win/toolchain.json'
            cfg.write_text(json.dumps({'llvm': 'C:/LLVM', 'metal_tools': 'C:/Metal'}), encoding='utf-8')
            sdk = import_sdk(root, archive, extractor_function=self.create_fake_sdk)
            self.assertTrue(sdk.is_dir())
            self.assertEqual(validate_ios_sdk(str(sdk)), sdk)
            self.assertEqual(configured_ios_sdk(root), str(sdk))
            data = json.loads(cfg.read_text(encoding='utf-8'))
            self.assertEqual(data['llvm'], 'C:/LLVM')
            self.assertEqual(data['metal_tools'], 'C:/Metal')
            self.assertEqual(archive.read_bytes()[:4], b'xar!')
            self.assertEqual(list((root / 'engine/win/sdk/out').glob('.xip-import-*')), [])

    def test_invalid_archive_does_not_change_existing_sdk(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            archive = self.fixture(root)
            cfg = root / 'engine/win/toolchain.json'
            cfg.write_text(json.dumps({'ios_sdk': 'C:/existing/iPhoneOS.sdk'}), encoding='utf-8')
            def old_sdk(_archive, dest):
                self.create_fake_sdk(_archive, dest, version='25.0')
            with self.assertRaisesRegex(ValueError, 'Expected one complete'):
                import_sdk(root, archive, extractor_function=old_sdk)
            self.assertEqual(configured_ios_sdk(root), 'C:/existing/iPhoneOS.sdk')
            self.assertEqual(list((root / 'engine/win/sdk/out').iterdir()), [])

    def test_extraction_failure_cleans_staging_and_preserves_config(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            archive = self.fixture(root)
            def broken(_archive, dest):
                (dest / 'garbage').write_text('partial extraction', encoding='utf-8')
                raise RuntimeError('synthetic extraction failure')
            with self.assertRaisesRegex(RuntimeError, 'synthetic'):
                import_sdk(root, archive, extractor_function=broken)
            self.assertFalse((root / 'engine/win/toolchain.json').exists())
            self.assertEqual(list((root / 'engine/win/sdk/out').iterdir()), [])

    def test_safe_sdk_paths_reject_archive_traversal(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / 'sdk'
            root.mkdir()
            for rel in ('../escape', 'iPhoneOS.sdk/../../escape', '/absolute', 'C:/Windows/system32',
                        'iPhoneOS.sdk\\escape', 'iPhoneOS.sdk//double', 'iPhoneOS.sdk/./item',
                        'iPhoneOS.sdk/../escape', 'x\x00y'):
                with self.subTest(rel=rel):
                    with self.assertRaises(ValueError):
                        xip_extractor.safe_sdk_entry(root, rel)
            self.assertEqual(xip_extractor.safe_sdk_entry(root, 'iPhoneOS.sdk/usr/include'),
                             root / 'iPhoneOS.sdk/usr/include')

    def test_gui_includes_import_dialog_consent_and_recheck(self):
        gui = (ROOT / 'win/hooklink_gui.pyw').read_text(encoding='utf-8')
        self.assertIn("text='Import SDK from Xcode .xip…'", gui)
        self.assertIn("text='Download .xip'", gui)
        self.assertIn('webbrowser.open_new_tab(XCODE_XIP_DOWNLOAD_URL)', gui)
        self.assertIn("filetypes=[('Xcode XIP archives', '*.xip')", gui)
        self.assertIn("Do you confirm that you are authorized to proceed?", gui)
        self.assertIn("'hooklink_sdk_import.py'", gui)
        self.assertIn("if title == 'iPhoneOS SDK import':", gui)
        self.assertIn("GUI_VERSION = 'Alpha V1.0.7'", gui)


if __name__ == '__main__':
    unittest.main()
