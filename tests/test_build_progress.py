"""Standalone, no-GUI tests for build progress reporting."""
from pathlib import Path
import sys
import unittest
import ast

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'win'))
from hooklink_progress import parse_build_progress


class TestBuildProgress(unittest.TestCase):
    def test_real_shader_split_line(self):
        p = parse_build_progress('[06:33:23] [3/6] shader split A: splitting: 43%, 80,720/186,587 files, 20:31 A · ETA 14:22')
        self.assertEqual((p.stage, p.stages, p.label, p.percent, p.count, p.eta),
                         (3, 6, 'shader split A', 43, '80,720/186,587', '14:22'))

    def test_real_shader_compile_line(self):
        p = parse_build_progress('[05:47:37] [4/6] iOS shaders: compiling: 59%, 25,308/42,848 shaders, 15:22 · ETA 10:26')
        self.assertEqual((p.stage, p.label, p.percent), (4, 'iOS shaders', 59))

    def test_count_fallback_without_percent(self):
        p = parse_build_progress('[5/6] app build: compile: 150/265 objects')
        self.assertAlmostEqual(p.percent, 150 / 265 * 100)

    def test_unknown_progress_keeps_stage_but_no_percent(self):
        p = parse_build_progress('[6/6] IPA pack: listing the files ...')
        self.assertEqual((p.stage, p.label, p.percent), (6, 'IPA pack', None))

    def test_unrelated_lines_do_not_set_progress(self):
        for s in ('[CACHE] Verified identical shader-package CONTENT', 'compile 100%',
                  '[06:35:23] no progress', '[00/6] invalid', '[7/6] invalid'):
            with self.subTest(s=s):
                self.assertIsNone(parse_build_progress(s))

    def test_reject_percent_over_one_hundred(self):
        self.assertIsNone(parse_build_progress('[2/0] nope'))
        p = parse_build_progress('[2/6] extract: processing: 110% done')
        self.assertIsNone(p.percent)

    def test_subsecond_and_truncated_etas(self):
        p = parse_build_progress('[3/6] split: splitting: 0.5%, 1/200 files, ETA 1:02:03')
        self.assertEqual(p.percent, 0.5)
        self.assertEqual(p.eta, '1:02:03')

    def test_no_false_percentage_from_timestamps(self):
        p = parse_build_progress('[6/6] IPA pack (10:19): listing files')
        self.assertEqual(p.label, 'IPA pack (10:19)')
        self.assertIsNone(p.percent)

    def test_source_has_ui_wiring_and_stage_label(self):
        s = (ROOT / 'win' / 'hooklink_gui.pyw').read_text(encoding='utf-8')
        self.assertIn('parse_build_progress', s)
        self.assertIn('self._update_progress_from_log(str(payload))', s)
        self.assertIn("mode='determinate'", s)
        self.assertIn("textvariable=self.progress_var", s)


    def test_gui_switches_from_numeric_to_activity_on_next_stage(self):
        # Exercise the actual GUI method without requiring a display server.
        source = (ROOT / 'win' / 'hooklink_gui.pyw').read_text(encoding='utf-8')
        tree = ast.parse(source)
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'App')
        node = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == '_update_progress_from_log')
        namespace = {'parse_build_progress': parse_build_progress}
        exec(compile(ast.Module(body=[node], type_ignores=[]), '<GUI-progress-method>', 'exec'), namespace)

        class FakeVar:
            value = None
            def set(self, value): self.value = value
        class FakeProgress:
            mode = 'indeterminate'
            value = 0
            running = True
            def stop(self): self.running = False
            def start(self, interval): self.running = True
            def configure(self, **kwargs): self.__dict__.update(kwargs)
        class FakeApp:
            _last_progress_stage = None
            _last_progress_percent = None
            progress = FakeProgress()
            progress_var = FakeVar()
            state_var = FakeVar()
        app = FakeApp()
        update = namespace['_update_progress_from_log']
        update(app, '[3/6] shader split A: splitting: 43%, 80,720/186,587 files')
        self.assertEqual((app.progress.mode, app.progress.value), ('determinate', 43))
        self.assertIn('43.0% of this stage', app.progress_var.value)
        self.assertIn('Stage 3 of 6', app.state_var.value)
        update(app, '[3/6] shader split A: some status without a number')
        self.assertEqual(app.progress.value, 43)   # do not forget measured percentage
        update(app, '[4/6] iOS shaders: preparing Metal libraries')
        self.assertEqual(app.progress.mode, 'indeterminate')
        self.assertTrue(app.progress.running)
        self.assertIn('stage percentage not reported', app.progress_var.value)
        update(app, '[4/6] iOS shaders: compiling: 20%, 8,568/42,848 shaders')
        self.assertEqual((app.progress.mode, app.progress.value), ('determinate', 20))
        self.assertFalse(app.progress.running)

    def test_stages_do_not_invent_overall_completion(self):
        p = parse_build_progress('[3/6] shader split A: splitting: 50%')
        self.assertEqual(p.percent, 50)
        self.assertNotEqual(p.percent, (2 + .5) / 6 * 100)


if __name__ == '__main__':
    unittest.main()
