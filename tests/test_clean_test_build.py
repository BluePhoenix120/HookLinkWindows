"""Clean-build GUI regression tests; no actual build or external tool needed."""
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'win'))
from hooklink_clean_build import new_clean_test_work_dir


class CleanBuildTests(unittest.TestCase):
    def test_creates_empty_sibling_and_preserves_existing_cache(self):
        with tempfile.TemporaryDirectory() as td:
            parent = Path(td)
            prev = parent / 'HookLinkWindowsBuild-200'
            prev.mkdir()
            (prev / 'shader.img').write_text('do not touch')
            fresh = new_clean_test_work_dir(prev)
            self.assertEqual(fresh, parent / 'HookLinkWindowsBuild-112-Clean')
            self.assertTrue(fresh.is_dir())
            self.assertEqual(list(fresh.iterdir()), [])
            self.assertEqual((prev / 'shader.img').read_text(), 'do not touch')

    def test_second_click_uses_separate_directory(self):
        with tempfile.TemporaryDirectory() as td:
            prev = Path(td) / 'previous'
            prev.mkdir()
            first = new_clean_test_work_dir(prev)
            (first / 'marker').write_text('keep')
            second = new_clean_test_work_dir(first)
            self.assertEqual(second.name, 'HookLinkWindowsBuild-112-Clean-2')
            self.assertEqual((first / 'marker').read_text(), 'keep')
            self.assertEqual(list(second.iterdir()), [])

    def test_missing_parent_cannot_create_implicit_directories(self):
        with tempfile.TemporaryDirectory() as td:
            prev = Path(td) / 'not-created' / 'previous'
            with self.assertRaises(FileNotFoundError):
                new_clean_test_work_dir(prev)
            self.assertFalse(prev.parent.exists())

    def test_does_not_delete_or_modify_existing_target(self):
        with tempfile.TemporaryDirectory() as td:
            prev = Path(td) / 'original'
            prev.mkdir()
            busy = Path(td) / 'HookLinkWindowsBuild-112-Clean'
            busy.mkdir()
            (busy / 'shader-cache').write_text('important')
            created = new_clean_test_work_dir(prev)
            self.assertNotEqual(created, busy)
            self.assertEqual((busy / 'shader-cache').read_text(), 'important')

    def test_invalid_workspace_name_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            prev = Path(td) / 'original'
            prev.mkdir()
            for name in ('../other', 'bad/path', '', '.', '..'):
                with self.subTest(name=name), self.assertRaises(ValueError):
                    new_clean_test_work_dir(prev, name=name)

    def test_gui_resets_previous_reuse_and_output_ipa_location(self):
        gui = (ROOT / 'win/hooklink_gui.pyw').read_text(encoding='utf-8')
        self.assertIn("text='New clean…'", gui)
        self.assertIn('new_clean_test_work_dir(Path(self.work_var.get().strip()))', gui)
        self.assertIn("self.reuse_var.set('')", gui)
        self.assertIn('self.output_auto = True', gui)
        self.assertIn('self.work_var.set(native_display_path(folder))', gui)
        self.assertIn("GUI_VERSION = 'Alpha V1.1.2'", gui)


if __name__ == '__main__':
    unittest.main()
