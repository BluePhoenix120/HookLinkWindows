"""Run against native Windows Job Objects."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

if os.name == 'nt':
    from nxw_proc_group import Group, stop_all

@unittest.skipUnless(os.name == 'nt', 'Windows only')
class Jobs(unittest.TestCase):
    def test_output_and_exit_code(self):
        with Group([sys.executable, '-c', "print('ready', flush=True); raise SystemExit(7)"],
                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT) as g:
            self.assertEqual(list(g.lines()), ['ready\n'])
            self.assertEqual(g.finish(), 7)
            self.assertEqual(g.stragglers, [])

    def test_straggler_killed_after_parent_exit(self):
        with tempfile.TemporaryDirectory() as d:
            marker = Path(d)/'late'
            child = "import time,pathlib;time.sleep(3);pathlib.Path(" + repr(str(marker)) + ").touch()"
            parent = "import subprocess,sys;subprocess.Popen([sys.executable,'-c'," + repr(child) + "],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)"
            with Group([sys.executable, '-c', parent], drain=.2, stdout=subprocess.PIPE) as g:
                list(g.lines())
                self.assertEqual(g.finish(), 0)
                self.assertTrue(g.stragglers)
            time.sleep(3.2)
            self.assertFalse(marker.exists())

    def test_stop_all_kills_siblings(self):
        with tempfile.TemporaryDirectory() as d:
            groups = []
            try:
                for i in range(2):
                    marker = Path(d)/str(i)
                    child = "import pathlib,time;time.sleep(3);pathlib.Path(" + repr(str(marker)) + ").touch()"
                    parent = "import subprocess,sys,time;subprocess.Popen([sys.executable,'-c'," + repr(child) + "]);print('ready',flush=True);time.sleep(30)"
                    g = Group([sys.executable, '-c', parent], stdout=subprocess.PIPE)
                    groups.append(g)
                    self.assertEqual(g.p.stdout.readline().strip(), b'ready')
                stop_all(groups)
                time.sleep(3.2)
                self.assertEqual(list(Path(d).iterdir()), [])
                self.assertTrue(all(g.done for g in groups))
            finally:
                stop_all(groups)
                for g in groups:
                    if g.p.stdout: g.p.stdout.close()

if __name__ == '__main__': unittest.main()
