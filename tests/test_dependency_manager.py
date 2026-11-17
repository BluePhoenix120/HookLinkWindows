"""Offline tests for the Windows dependency manager and its allowlisted actions."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'win'))
from hooklink_dependency_manager import XCODE_XIP_DOWNLOAD_URL, DEPENDENCIES, dependency_statuses, missing_python_packages
from hooklink_prereqs import CheckReport, normalize_doctor_json


class DependencyManagerTests(unittest.TestCase):
    @staticmethod
    def report(*items):
        return normalize_doctor_json([
            {'name': name, 'ok': ok, 'detail': detail, 'required': required, 'how': ''}
            for name, ok, detail, required in items])

    def test_official_xcode_xip_download_link(self):
        self.assertEqual(XCODE_XIP_DOWNLOAD_URL,
                         'https://download.developer.apple.com/Developer_Tools/Xcode_27.2/Xcode_27.2.xip')

    def test_unknown_is_not_misreported_as_missing(self):
        rows = dependency_statuses(None)
        self.assertEqual(len(rows), len(DEPENDENCIES))
        self.assertTrue(all(status == 'Not checked' for _, status, _ in rows))
        self.assertEqual(missing_python_packages(None), ())

    def test_actual_doctor_results_control_status(self):
        report = self.report(('Python 3.10+', True, '3.14.2', True),
                             ('iPhoneOS SDK 26+', False, 'not found', True),
                             ('glslangValidator', False, '', False))
        status = {dep.key: (state, detail) for dep, state, detail in dependency_statuses(report)}
        self.assertEqual(status['Python 3.10+'], ('Installed', '3.14.2'))
        self.assertEqual(status['iPhoneOS SDK 26+'], ('Missing', 'not found'))
        self.assertEqual(status['glslangValidator'][0], 'Optional')
        self.assertEqual(status['LLVM clang (20+)'][0], 'Not checked')

    def test_all_download_links_are_explicit_https_pages(self):
        self.assertEqual(len({d.key for d in DEPENDENCIES}), len(DEPENDENCIES))
        self.assertTrue(all(not dep.url or dep.url.startswith('https://') for dep in DEPENDENCIES))
        self.assertIn('https://developer.apple.com/metal/tools/', {d.url for d in DEPENDENCIES})

    def test_only_expected_required_missing_packages_are_installed(self):
        report = self.report(('Python 3.10+', True, '', True),
                             ('python module lz4.block', False, '', True),
                             ('python module capstone', False, '', True),
                             ('python module fontTools', True, '', True),
                             ('python zstd (compression.zstd / backports.zstd)', False, '', True),
                             ('python module PIL', False, '', False))
        self.assertEqual(missing_python_packages(report),
                         ('lz4', 'capstone', 'backports.zstd'))

    def test_never_install_packages_when_python_missing_or_blocked(self):
        report = self.report(('Python 3.10+', False, '', True),
                             ('python module lz4.block', False, '', True))
        self.assertEqual(missing_python_packages(report), ())
        report.entries[0]['ok'] = True
        report.blockers.append('Invalid repository layout')
        self.assertEqual(missing_python_packages(report), ())

    def test_gui_contains_user_confirmed_pip_and_vendor_actions(self):
        gui = (ROOT / 'win' / 'hooklink_gui.pyw').read_text(encoding='utf-8')
        self.assertIn("text='Install missing Python packages'", gui)
        self.assertIn('messagebox.askyesno(\'Install missing Python packages?\'', gui)
        self.assertIn("'--no-input', 'install', *packages]", gui)
        self.assertIn('webbrowser.open_new_tab(url)', gui)
        self.assertIn('self._render_dependency_rows()', gui)
        self.assertIn("GUI_VERSION = 'Alpha V1.1.0'", gui)
        self.assertNotIn('subprocess.run([\'powershell\'', gui)


if __name__ == '__main__':
    unittest.main()
