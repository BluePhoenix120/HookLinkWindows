"""Dependency report contract tests; all tools simulated, no installers invoked."""
from pathlib import Path
import json
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'win'))
from hooklink_prereqs import can_auto_prepare_translator, normalize_doctor_json, run_prerequisite_check


class PrerequisiteTests(unittest.TestCase):
    def test_missing_doctor_reports_full_checkout_requirement(self):
        with tempfile.TemporaryDirectory() as td:
            result = run_prerequisite_check(Path(td), sys.executable)
            self.assertFalse(result.ready)
            self.assertIn('win/doctor.py', result.format())

    def test_normalizes_required_and_optional_items(self):
        result = normalize_doctor_json([
            {'name': 'Python 3.10+', 'ok': True, 'required': True, 'detail': '3.12.2', 'how': ''},
            {'name': '.NET SDK 10', 'ok': False, 'required': True, 'detail': 'missing', 'how': 'https://dotnet.microsoft.com/'},
            {'name': 'glslangValidator', 'ok': False, 'required': False, 'detail': 'not found', 'how': 'optional tool'},
        ])
        self.assertFalse(result.ready)
        self.assertIn('[MISSING] .NET SDK 10', result.format())
        self.assertIn('[OPTIONAL] glslangValidator', result.format())
        self.assertIn('https://dotnet.microsoft.com/', result.format())

    def test_wrong_clang_version_is_not_a_pass(self):
        result = normalize_doctor_json([
            {'name': 'LLVM clang (20+)', 'ok': True, 'required': True, 'detail': 'clang version 19.1.7', 'how': ''}
        ])
        self.assertFalse(result.ready)
        self.assertIn('LLVM 20 or later', result.format())

    def test_doctor_json_invocation_and_failure_status(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            path = root / 'win' / 'doctor.py'
            path.parent.mkdir(parents=True)
            path.write_text('import json,sys; print(json.dumps([{"name":"Python 3.10+","ok":True,"detail":"3.12","how":"","required":True}]))')
            result = run_prerequisite_check(root, sys.executable)
            self.assertTrue(result.ready)
            self.assertIn('Xcode.app', result.format())

    def test_windows_check_suppresses_console_window(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            doctor = root / 'win' / 'doctor.py'
            doctor.parent.mkdir(parents=True)
            doctor.write_text('print("placeholder")')
            payload = json.dumps([{'name': 'Python 3.10+', 'ok': True,
                                   'required': True, 'detail': '3.12', 'how': ''}])
            with patch('hooklink_prereqs.sys.platform', 'win32'), \
                 patch('hooklink_prereqs.subprocess.CREATE_NO_WINDOW', 0x08000000, create=True), \
                 patch('hooklink_prereqs.subprocess.run') as runner:
                runner.return_value.returncode = 0
                runner.return_value.stdout = payload
                runner.return_value.stderr = ''
                report = run_prerequisite_check(root, sys.executable)
                self.assertTrue(report.ready)
                self.assertEqual(runner.call_args.kwargs['creationflags'], 0x08000000)

    @staticmethod
    def _graphics_report(*, translator=False, sdk=False, dotnet=True, spirv=True, metal=True):
        values = (
            ('Windows', True), ('Python 3.10+', True),
            ('.NET SDK 10', dotnet), ('shader translator DLLs', translator),
            ('iPhoneOS SDK 26+', sdk), ('spirv-cross', spirv),
            ('Metal compiler (iphoneos)', metal), ('Metal compiler (macosx)', metal),
        )
        return normalize_doctor_json([{'name': name, 'ok': ok, 'required': True,
                                       'detail': '', 'how': ''} for name, ok in values])

    def test_graphics_setup_runs_on_missing_translator_even_without_ios_sdk(self):
        report = self._graphics_report(translator=False, sdk=False)
        self.assertFalse(report.ready)
        self.assertTrue(can_auto_prepare_translator(report))

    def test_graphics_setup_never_replaces_existing_dll_automatically(self):
        self.assertFalse(can_auto_prepare_translator(self._graphics_report(translator=True)))

    def test_graphics_setup_waits_until_required_tools_are_installed(self):
        for change in ({'dotnet': False}, {'spirv': False}, {'metal': False}):
            with self.subTest(change=change):
                self.assertFalse(can_auto_prepare_translator(self._graphics_report(**change)))

    def test_graphics_setup_respects_doctor_blockers(self):
        report = self._graphics_report()
        report.blockers.append('Invalid repository')
        self.assertFalse(can_auto_prepare_translator(report))

    def test_unstructured_doctor_output_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            path = root / 'win' / 'doctor.py'
            path.parent.mkdir(parents=True)
            path.write_text('print("looks good (unstructured)")')
            result = run_prerequisite_check(root, sys.executable)
            self.assertFalse(result.ready)
            self.assertIn('Unable to parse', result.format())

    def test_doctor_missing_import_reported_not_pretended_ok(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            path = root / 'win' / 'doctor.py'
            path.parent.mkdir(parents=True)
            path.write_text('import definitely_missing_library_98765')
            result = run_prerequisite_check(root, sys.executable)
            self.assertFalse(result.ready)
            self.assertIn('ModuleNotFoundError', result.format())

    def test_gui_has_visible_prerequisites_button_and_setup_link(self):
        source = (ROOT / 'win' / 'hooklink_gui.pyw').read_text(encoding='utf-8')
        self.assertIn("text='Check prerequisites'", source)
        self.assertIn("text='Setup guide'", source)
        self.assertIn("elif typ == 'prereqs'", source)
        self.assertTrue((ROOT / 'docs' / 'GETTING_STARTED.md').exists())


if __name__ == '__main__':
    unittest.main()
