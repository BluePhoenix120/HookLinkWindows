"""Regression checks for Windows Job Object compiler cleanup.

Mocked API checks run on CI; real Windows nested-job behavior and failure modes
must still be verified by an end-to-end build on the developer's computer.
"""
from __future__ import annotations

import ctypes
import importlib.util
from pathlib import Path
from unittest import TestCase
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('build_job', ROOT / 'engine' / 'win' / 'build_job.py')
jobmod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(jobmod)


class JobLifetimeTests(TestCase):
    def setUp(self):
        jobmod._live_job = None

    def tearDown(self):
        jobmod._live_job = None

    def test_win64_job_layout_matches_winnt(self):
        if ctypes.sizeof(ctypes.c_void_p) == 8:
            self.assertEqual(ctypes.sizeof(jobmod._BasicLimit), 64)
            self.assertEqual(ctypes.sizeof(jobmod._IoCounters), 48)
            self.assertEqual(ctypes.sizeof(jobmod._ExtendedLimits), 144)
        self.assertEqual(jobmod.KILL_ON_JOB_CLOSE, 0x2000)
        self.assertEqual(jobmod.EXTENDED_LIMIT_INFORMATION, 9)

    def test_non_windows_skips_containment(self):
        with patch.object(jobmod.os, 'name', 'posix'):
            self.assertFalse(jobmod.protect_builder_tree())

    def test_assignment_keeps_job_handle_until_process_exit(self):
        kernel = Mock()
        kernel.CreateJobObjectW.return_value = 0x8124
        kernel.SetInformationJobObject.return_value = 1
        kernel.AssignProcessToJobObject.return_value = 1
        kernel.GetCurrentProcess.return_value = 0xfeed
        with patch('builtins.print'):
            self.assertTrue(jobmod.protect_builder_tree(kernel=kernel))
            self.assertTrue(jobmod.protect_builder_tree(kernel=kernel))
        self.assertEqual(jobmod._live_job, 0x8124)
        kernel.CreateJobObjectW.assert_called_once()
        kernel.AssignProcessToJobObject.assert_called_once_with(0x8124, 0xfeed)
        self.assertEqual(kernel.SetInformationJobObject.call_args.args[1], 9)
        self.assertEqual(kernel.SetInformationJobObject.call_args.args[3], ctypes.sizeof(jobmod._ExtendedLimits))
        kernel.CloseHandle.assert_not_called()

    def test_failed_assignment_closes_job_and_reports_unavailable(self):
        kernel = Mock()
        kernel.CreateJobObjectW.return_value = 0x8173
        kernel.SetInformationJobObject.return_value = 1
        kernel.AssignProcessToJobObject.return_value = 0
        with patch('builtins.print') as prints:
            self.assertFalse(jobmod.protect_builder_tree(kernel=kernel))
        kernel.CloseHandle.assert_called_once_with(0x8173)
        self.assertIsNone(jobmod._live_job)
        self.assertIn('Warning', str(prints.call_args))

    def test_failed_configuration_closes_job(self):
        kernel = Mock()
        kernel.CreateJobObjectW.return_value = 0x8173
        kernel.SetInformationJobObject.return_value = 0
        with patch('builtins.print'):
            self.assertFalse(jobmod.protect_builder_tree(kernel=kernel))
        kernel.AssignProcessToJobObject.assert_not_called()
        kernel.CloseHandle.assert_called_once_with(0x8173)

    def test_no_job_created_when_windows_api_returns_null(self):
        kernel = Mock()
        kernel.CreateJobObjectW.return_value = 0
        with patch('builtins.print'):
            self.assertFalse(jobmod.protect_builder_tree(kernel=kernel))
        kernel.SetInformationJobObject.assert_not_called()

    def test_builder_attaches_before_pipeline_spawn(self):
        source = (ROOT / 'engine' / 'win' / 'build_ipa_windows.py').read_text(encoding='utf-8')
        self.assertIn("from build_job import protect_builder_tree", source)
        self.assertIn("        protect_builder_tree()", source)
        self.assertLess(source.index("        protect_builder_tree()"),
                        source.index("if Path(getattr(sys.modules.get('sitecustomize')"))
        self.assertLess(source.index("        protect_builder_tree()"),
                        source.index("spec = importlib.util.spec_from_file_location('build_ipa_from_nsp'"))


if __name__ == '__main__':
    from unittest import main
    main()
