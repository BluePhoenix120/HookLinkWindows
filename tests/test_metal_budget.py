"""Concurrency and cleanup regressions without running real Metal tools."""
import ast
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import sys
import threading
import time
from types import SimpleNamespace
from unittest import TestCase, mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'engine' / 'dm' / 'gfx' / 'tools'))
sys.path.insert(0, str(ROOT / 'win'))
from metal_budget import MetalBudget
import host_process


class MetalSchedulingTests(TestCase):
    def test_retains_61_shader_workers_and_caps_only_compilers(self):
        gui = (ROOT / 'win' / 'hooklink_gui_core.py').read_text(encoding='utf-8')
        driver = (ROOT / 'engine' / 'win' / 'build_ipa_windows.py').read_text(encoding='utf-8')
        cache = (ROOT / 'engine' / 'dm' / 'gfx' / 'tools' / 'dmsh_mtlcache.py').read_text(encoding='utf-8')
        self.assertIn("env['J'] = str(c.workers)", gui)
        self.assertIn("env['NXW_METAL_J'] = str(c.metal_workers)", gui)
        self.assertIn("os.environ.setdefault('J'", driver)
        self.assertIn('with METAL_BUDGET.slot():', cache)
        self.assertIn('self.targets[target][2](msl, air, lib)', cache)

    def test_never_admits_more_than_limit(self):
        budget = MetalBudget(enabled=True, limit=2, min_available_gib=8,
                             available=lambda: 30.0, notice=lambda text: None)
        start = threading.Event()
        release = threading.Event()
        peak = [0]
        lock = threading.Lock()
        def work():
            with budget.slot():
                with lock:
                    peak[0] = max(peak[0], budget._active)
                    start.set()
                release.wait(3)
        with ThreadPoolExecutor(max_workers=6) as pool:
            futures = [pool.submit(work) for _ in range(6)]
            self.assertTrue(start.wait(2))
            time.sleep(0.08)
            self.assertLessEqual(budget._active, 2)
            release.set()
            for f in futures: f.result(timeout=5)
        self.assertEqual(peak[0], 2)
        self.assertEqual(budget._active, 0)

    def test_memory_floor_blocks_new_launches_and_times_out_cleanly(self):
        notices = []
        budget = MetalBudget(enabled=True, limit=3, min_available_gib=8,
                             available=lambda: 2.0, timeout=0.1, notice=notices.append)
        with self.assertRaisesRegex(RuntimeError, 'RAM remained below'):
            with budget.slot():
                self.fail('No compiler may launch during persistent RAM pressure')
        self.assertEqual(budget._active, 0)
        self.assertEqual(len(notices) >= 1, True)

    def test_compiler_failure_releases_token(self):
        budget = MetalBudget(enabled=True, limit=1, min_available_gib=8,
                             available=lambda: 30.0, notice=lambda _: None)
        with self.assertRaisesRegex(ValueError, 'simulated'):
            with budget.slot():
                raise ValueError('simulated')
        with budget.slot():
            self.assertEqual(budget._active, 1)

    def test_stop_uses_taskkill_descendants_first(self):
        proc = SimpleNamespace(pid=12345, poll=lambda: None)
        with mock.patch.object(host_process.os, 'name', 'nt'):
            with mock.patch.object(host_process.subprocess, 'run', return_value=SimpleNamespace(returncode=0,stderr='',stdout='')) as run:
                self.assertTrue(host_process.terminate_build_tree(proc))
        args = run.call_args.args[0]
        self.assertEqual(args, ['taskkill', '/F', '/T', '/PID', '12345'])

    def test_stop_failure_does_not_silently_kill_only_parent(self):
        proc = SimpleNamespace(pid=12345, poll=lambda: None)
        with mock.patch.object(host_process.os, 'name', 'nt'):
            with mock.patch.object(host_process.subprocess, 'run', return_value=SimpleNamespace(returncode=1,stderr='access denied',stdout='')):
                with self.assertRaisesRegex(RuntimeError, 'access denied'):
                    host_process.terminate_build_tree(proc)

    def test_gui_calls_process_tree_stop(self):
        source = (ROOT / 'win' / 'hooklink_gui.pyw').read_text(encoding='utf-8')
        self.assertIn('terminate_build_tree(proc)', source)
        self.assertNotIn('self.proc.terminate()', source)
