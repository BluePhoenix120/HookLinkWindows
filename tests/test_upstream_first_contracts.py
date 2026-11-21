"""Prevent accidental replacement of newer original NXnative code by older HookLink files.

The full original-first engine integration must retain the official source
functions used by the Windows iOS pipeline, not only pass GUI packaging tests.
"""
from pathlib import Path
import ast
import json
import re
import unittest

ROOT=Path(__file__).resolve().parents[1]
ENGINE=ROOT/"engine"
PIN=json.loads((ROOT/"ENGINE_PIN.json").read_text(encoding="utf-8"))
MANIFEST=json.loads((ROOT/"ENGINE_PIN_FILES.json").read_text(encoding="utf-8"))


def all_symbols(rel):
    module=ast.parse((ENGINE/rel).read_text(encoding="utf-8"))
    names=set()
    def walk(items,prefix=""):
        for node in items:
            if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)):
                name=prefix+node.name
                names.add(name)
                if isinstance(node,ast.ClassDef):
                    walk(node.body,name+".")
    walk(module.body)
    return names


class UpstreamFirstEngineContracts(unittest.TestCase):
    def test_complete_original_snapshot_is_represented(self):
        self.assertEqual(PIN["nxnative_commit"],"3ec5b785f37f8c87d78433f152914d89c4ef93c9")
        self.assertIn("upstream-first", PIN["engine_integration_policy"])
        self.assertGreaterEqual(len(MANIFEST["changed_paths"]),3800)
        self.assertEqual(len(MANIFEST["changed_paths"]),len(set(p["path"] for p in MANIFEST["changed_paths"])))
        self.assertEqual(MANIFEST["engine_integration_commit"],PIN["engine_integration_commit"])

    def test_only_two_prebuilt_nonwindows_translators_excluded(self):
        omitted={p["path"] for p in MANIFEST["platform_binary_exclusions"]}
        self.assertEqual(omitted,{
            "engine/dm/gfx/tools/dmsh_xlate_bin/dmsh_xlate",
            "engine/dm/gfx/tools/spirv_cross_bin/spirv-cross"
        })
        for path in omitted:
            self.assertFalse((ROOT/path).exists())

    def test_hooklink_and_windows_overlap_decisions_are_recorded(self):
        self.assertGreaterEqual(len(MANIFEST["original_hooklink_conflicts"]),20)
        reviewed=set(MANIFEST["windows_reviewed_hunk_conflicts"])
        self.assertEqual(reviewed,{
            "engine/dm/gfx/nvn/dmsh_chain.h",
            "engine/dm/gfx/nvn/nvn_mtl.m",
            "engine/dm/gfx/tools/dmsh_build.py",
            "engine/dm/gfx/tools/dmsh_chain.lock",
            "engine/dm/gfx/tools/dmsh_rewrite.py",
            "engine/docs/reference/frame-rate.md"
        })
        self.assertTrue(set(MANIFEST["integration_overrides"]).issubset(set(MANIFEST["windows_overlays"])))

    def test_original_shader_split_coverage(self):
        symbols=all_symbols("dm/gfx/tools/shader_split.py")
        self.assertTrue({"bahs_binary_records","bahs_variations","bahs_shaders","kit_jobs"} <= symbols)
        s=(ENGINE/"dm/gfx/tools/shader_split.py").read_text(encoding="utf-8")
        self.assertIn("offsets.intersection_update(a for a, _ in records)",s)

    def test_original_shader_translator_coverage_with_windows_fallback(self):
        symbols=all_symbols("dm/gfx/tools/dmsh_build.py")
        self.assertTrue({"owned_output","rt_finish"} <= symbols)
        s=(ENGINE/"dm/gfx/tools/dmsh_build.py").read_text(encoding="utf-8")
        self.assertIn("BrokenProcessPool",s)
        self.assertIn("RT_PLAN",s)
        self.assertIn("hasattr(os, 'pread')",s)
        self.assertIn("dmsh_rt_build",s)

    def test_newest_nso_shader_cache_and_ipa_sources_exist(self):
        specs={
            "dm/tools/patch_nso.py":{"branch_entries","code_ok","half_pads","movie_native_color_keys"},
            "dm/tools/shader_cache.py":{"Store.forget","Store._reader","Store._close_readers"},
            "dm/mac/pack_app.py":{"seals","as_packed","as_recorded","write_key"},
            "scripts/build_ipa_from_nsp.py":{"build_sources","drop_prewarm"}
        }
        for path,expected in specs.items():
            with self.subTest(path=path):
                self.assertTrue(expected <= all_symbols(path),str(expected-all_symbols(path)))

    def test_shader_chain_is_explicit_and_windows_metal_is_recorded(self):
        h=(ENGINE/"dm/gfx/nvn/dmsh_chain.h").read_text(encoding="utf-8")
        self.assertIn('DMSH_CHAIN "'+PIN["shader_chain"]+'"',h)
        lock=(ENGINE/"dm/gfx/tools/dmsh_chain.lock").read_text(encoding="utf-8")
        self.assertIn("metalfe-custom-windows",lock)

    def test_windows_native_build_shim_preserved(self):
        self.assertTrue((ENGINE/"win/build_ipa_windows.py").is_file())
        s=(ENGINE/"dm/gfx/tools/dmsh_rewrite.py").read_text(encoding="utf-8")
        self.assertIn("def membar_fence(msl):",s)


if __name__=="__main__":
    unittest.main()
