"""Offline tests for the GUI toolchain setup; no compilers, SDKs or games needed."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'win'))
from hooklink_toolchain_setup import configured_ios_sdk, save_ios_sdk, validate_ios_sdk


class ToolchainSetupTests(unittest.TestCase):
    def make_sdk(self, root, version='27.2'):
        sdk = root / 'LicensedTools' / 'iPhoneOS.sdk'
        (sdk / 'usr' / 'include').mkdir(parents=True)
        (sdk / 'System' / 'Library' / 'Frameworks').mkdir(parents=True)
        (sdk / 'SDKSettings.json').write_text(json.dumps({'Version': version}), encoding='utf-8')
        return sdk

    def test_sdk_picker_saves_and_preserves_existing_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sdk = self.make_sdk(root)
            cfg = root / 'engine' / 'win' / 'toolchain.json'
            cfg.parent.mkdir(parents=True)
            cfg.write_text(json.dumps({'llvm': 'C:/Program Files/LLVM', 'metal_tools': 'D:/MetalTools'}))
            selected = save_ios_sdk(root, str(sdk))
            self.assertEqual(selected, sdk.resolve())
            data = json.loads(cfg.read_text())
            self.assertEqual(data['llvm'], 'C:/Program Files/LLVM')
            self.assertEqual(data['metal_tools'], 'D:/MetalTools')
            self.assertEqual(configured_ios_sdk(root), str(sdk.resolve()))

    def test_sdk_picker_rejects_incomplete_sdk_and_does_not_write_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sdk = self.make_sdk(root)
            (sdk / 'usr' / 'include').rmdir()
            with self.assertRaisesRegex(ValueError, 'incomplete'):
                save_ios_sdk(root, str(sdk))
            self.assertFalse((root / 'engine' / 'win' / 'toolchain.json').exists())

    def test_sdk_picker_rejects_old_sdk(self):
        with tempfile.TemporaryDirectory() as tmp:
            sdk = self.make_sdk(Path(tmp), version='25.0')
            with self.assertRaisesRegex(ValueError, '26 or later'):
                validate_ios_sdk(str(sdk))

    def test_invalid_existing_config_remains_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sdk = self.make_sdk(root)
            cfg = root / 'engine' / 'win' / 'toolchain.json'
            cfg.parent.mkdir(parents=True)
            cfg.write_text('not valid json')
            with self.assertRaisesRegex(ValueError, 'Cannot read existing'):
                save_ios_sdk(root, str(sdk))
            self.assertEqual(cfg.read_text(), 'not valid json')

    def test_gui_exposes_setup_and_repair_controls(self):
        gui = (ROOT / 'win' / 'hooklink_gui.pyw').read_text(encoding='utf-8')
        self.assertIn("text='Toolchain setup…'", gui)
        self.assertIn("text='Browse…'", gui)
        self.assertIn("text='Save', command=save_sdk", gui)
        self.assertIn("text='Retry graphics setup'", gui)
        self.assertIn("'--install', '--accept-new-chain'", gui)
        self.assertIn("can_auto_prepare_translator(payload)", gui)
        self.assertIn("self._start_graphics_setup(automatic=True)", gui)
        self.assertIn("self._auto_translator_attempted = True", gui)
        self.assertIn("GUI_VERSION = 'Alpha V1.0.8'", gui)
        self.assertIn('configured_ios_sdk(ROOT)', gui)
        self.assertIn('save_ios_sdk(ROOT, sdk_var.get())', gui)


if __name__ == '__main__':
    unittest.main()
