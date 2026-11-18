"""Offline regression tests for black-screen session log export and inspection."""
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'win'))
from hooklink_iphone_logs import (
    MAX_DISPLAY_LINES, MAX_LINE_LENGTH, MAX_TAIL_BYTES, summarize_iphone_log,
)


class DeviceLogAnalyzerTests(unittest.TestCase):
    def test_missing_log_raises_clear_error(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(FileNotFoundError):
                summarize_iphone_log(Path(td) / 'log.prev.txt')

    def test_empty_log_explains_what_to_do(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / 'log.txt'
            p.write_bytes(b'')
            self.assertIn('empty', summarize_iphone_log(p))

    def test_last_game_session_and_errors_presented_without_guessing(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / 'log.prev.txt'
            p.write_text(
                'boot: game files /Documents/romfs.img\n'
                'boot: env DM_NVN_BARRIER=full (env.txt)\n'
                '[RED] metal: shader library failed to load\n'
                'renderer: a normal note\n',
                encoding='utf-8'
            )
            report = summarize_iphone_log(p)
            self.assertIn('log.prev.txt', report)
            self.assertIn('shader library failed to load', report)
            self.assertIn('DM_NVN_BARRIER=full', report)
            self.assertIn('not a confirmed root cause', report)

    def test_large_log_is_bounded_and_does_not_gather_unrelated_content(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / 'log.prev.txt'
            p.write_bytes(b'secret-from-beginning\n' + b'ordinary filler\n' * 550_000 +
                          b'[RED] last failure\n')
            self.assertGreater(p.stat().st_size, MAX_TAIL_BYTES)
            report = summarize_iphone_log(p)
            self.assertIn('[RED] last failure', report)
            self.assertNotIn('secret-from-beginning', report)
            self.assertLess(len(report), 100_000)

    def test_long_lines_are_truncated_and_binary_is_replaced(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / 'log.txt'
            p.write_bytes(b'\xff[RED] failure ' + b'X' * 1800 + b'\n')
            report = summarize_iphone_log(p)
            self.assertIn('[RED] failure', report)
            self.assertIn(' …', report)
            self.assertLess(len(report), (MAX_LINE_LENGTH + 200) * 3)

    def test_last_lines_limited_even_when_no_errors(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / 'log.txt'
            p.write_text(''.join(f'plain message {i}\n' for i in range(180)))
            report = summarize_iphone_log(p)
            self.assertIn('plain message 179', report)
            self.assertNotIn('plain message 0\n', report)
            self.assertIn(f'Last {MAX_DISPLAY_LINES} log lines', report)


class NativeIosLogExportTests(unittest.TestCase):
    def test_windows_ios_launcher_exports_previous_and_current_game_logs(self):
        src = (ROOT / 'engine/win/ios/Launcher.m').read_text(encoding='utf-8')
        self.assertIn('Export Game Logs', src)
        self.assertIn('exportGameLogsFromButton:', src)
        self.assertIn('log.prev.txt', src)
        self.assertIn('HookLink-last-game-session.txt', src)
        self.assertIn('log.txt', src)
        self.assertIn('HookLink-this-launch.txt', src)
        self.assertIn('UIActivityViewController', src)
        self.assertIn('popover.sourceView = sender', src)
        self.assertIn('No game log yet', src)
        self.assertIn('if (!items.count)', src)

    def test_launcher_uses_weak_button_reference_and_no_log_deletion(self):
        src = (ROOT / 'engine/win/ios/Launcher.m').read_text(encoding='utf-8')
        self.assertIn('__block __weak UIButton *logSource', src)
        self.assertIn('copyItemAtPath:src toPath:dst', src)
        self.assertNotIn('removeItemAtPath:src', src)

    def test_windows_gui_has_local_file_picker_for_device_log(self):
        src = (ROOT / 'win/hooklink_gui.pyw').read_text(encoding='utf-8')
        self.assertIn("GUI_VERSION = 'Alpha V1.1.1'", src)
        self.assertIn("text='iPhone log…'", src)
        self.assertIn('summarize_iphone_log(Path(path))', src)
        self.assertIn('askopenfilename(', src)


if __name__ == '__main__':
    unittest.main()
