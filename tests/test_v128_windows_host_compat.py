"""Windows compatibility for the incoming X3 / NXnative host-source API."""
import ast
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("hlw_host_source_manifest", ROOT / "engine/win/host_source_manifest.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class HostSourceManifestTests(unittest.TestCase):
    def fixture(self, files, source):
        with tempfile.TemporaryDirectory() as td:
            host = Path(td)
            for name in files:
                (host / name).touch()
            return [p.name for p in module.host_source_paths(host, "SRC=" + source + "\n")]

    def test_real_current_makefile_expands_to_existing_sources(self):
        host = ROOT / "engine/dm/host"
        files = module.host_source_paths(host, (host / "Makefile").read_text(encoding="utf-8"))
        self.assertEqual(files[0].name, "main.c")
        self.assertEqual(files[-1].name, "entry.S")
        self.assertEqual(len(files), len(set(files)))

    def test_new_upstream_audio_sources_are_not_omitted(self):
        names = ["main.c", "audio_input.c", "audio_input_mac.m",
                 "audio_input_dualsense_mac.m", "dualsense_mic_mac.c",
                 "hle_z.c", "hle_a.c", "entry.S"]
        src = "main.c audio_input.c audio_input_mac.m audio_input_dualsense_mac.m dualsense_mic_mac.c $(sort $(wildcard hle_*.c)) entry.S"
        self.assertEqual(self.fixture(names, src), names[:5] + ["hle_a.c", "hle_z.c", "entry.S"])

    def test_previous_mic_and_new_audio_sources_can_coexist(self):
        names = ["main.c", "mic_apple.m", "audio_input.c", "audio_input_mac.m", "entry.S"]
        self.assertEqual(self.fixture(names, "main.c mic_apple.m audio_input.c audio_input_mac.m $(sort $(wildcard hle_*.c)) entry.S"), names)

    def test_missing_source_and_unknown_make_syntax_fail_closed(self):
        for src in ("main.c $(sort $(wildcard hle_*.c)) missing.c",
                    "main.c $(sort $(wildcard hle_*.c)) $(MORE)",
                    "main.c $(sort $(wildcard hle_*.c)) ../foo.c",
                    "main.c $(sort $(wildcard hle_*.c)) main.c"):
            with self.subTest(src=src), self.assertRaises(ValueError):
                self.fixture(["main.c"], src)

    def test_windows_region_check_accepts_new_target_argument(self):
        source = (ROOT / "engine/win/build_ipa_windows.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        node = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "region_skip")
        self.assertEqual(node.args.args[-1].arg, "mac_only")
        self.assertIs(node.args.defaults[-1].value, False)


if __name__ == "__main__":
    unittest.main()
