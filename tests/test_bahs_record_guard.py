"""Protect original NXnative BAHS record validation in the HookLinkWindows overlay.

Reproduces the descriptor-shaped false-entry issue from Ocarina's v131072
AglShader.sharcb (PR #2943 / issue #3008) without redistributing game bytes.
"""
import ast
import hashlib
import json
import struct
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPLITTER = ROOT / "engine/dm/gfx/tools/shader_split.py"
MANIFEST = ROOT / "ENGINE_PIN_FILES.json"


def record_parser():
    """Compile only the pure upstream parser to avoid platform build imports."""
    source = SPLITTER.read_text(encoding="utf-8")
    node = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == "bahs_binary_records")
    namespace = {"struct": struct}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(SPLITTER), "exec"), namespace)
    return namespace[node.name]


def fixture():
    """Two actual 0x20-byte record descriptors, plus one false candidate."""
    data = bytearray(0x180)
    array = 0x40
    struct.pack_into("<II", data, array, 0x48, 2)
    struct.pack_into("<II", data, array + 8, 0x20, 0)
    struct.pack_into("<II", data, array + 0x28, 0x20, 1)
    # The scan can mistake bytes inside a record as a third BAHS entry.
    return data, {0x58, 0x78, 0x90}


class OriginalBahsRecordGuard(unittest.TestCase):
    def test_record_array_excludes_spurious_candidate(self):
        data, candidates = fixture()
        records, end = record_parser()(data, 0x180, candidates)
        self.assertEqual(records, [(0x58, 0), (0x78, 1)])
        self.assertEqual(end, 0x88)
        candidates.intersection_update(offset for offset, _ in records)
        self.assertEqual(candidates, {0x58, 0x78})

    def test_rejects_unrecognized_descriptor_layout(self):
        data, candidates = fixture()
        struct.pack_into("<I", data, 0x48, 0x10)
        self.assertIsNone(record_parser()(data, 0x180, candidates))

    def test_rejects_out_of_bounds_descriptor_array(self):
        data, candidates = fixture()
        self.assertIsNone(record_parser()(data, 0x80, candidates))

    def test_bahs_shaders_actually_filters_to_validated_records(self):
        source = SPLITTER.read_text(encoding="utf-8")
        section = source.split("def bahs_shaders(d, label):", 1)[1].split("def sead_prim_shaders(d, label):", 1)[0]
        self.assertIn("array = bahs_binary_records(d, region, offsets)", section)
        self.assertIn("offsets.intersection_update(a for a, _ in records)", section)
        self.assertIn("return [s for a, s in candidates if a in offsets]", section)
        self.assertIn("bahs_variations(d, label, offsets, records, end)", section)

    def test_hooklink_windows_overlay_is_explicit_and_hashed(self):
        record = json.loads(MANIFEST.read_text(encoding="utf-8"))
        path = "engine/dm/gfx/tools/shader_split.py"
        raw = SPLITTER.read_bytes()
        digest = hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()
        official = {item["path"]:item["sha"] for item in record["changed_paths"]}
        self.assertEqual(official[path], "cbfbf1914da10c00cdb75ad00c80da3f16c31c34")
        if digest == official[path]:
            self.assertNotIn(path, record["integration_overrides"])
            self.assertNotIn(path, record["windows_overlays"])
        else:
            self.assertIn(path, record["windows_overlays"])
            entry = record["integration_overrides"][path]
            self.assertEqual(entry["upstream_sha"], official[path])
            self.assertEqual(digest, entry["integrated_sha"])


if __name__ == "__main__":
    unittest.main()
