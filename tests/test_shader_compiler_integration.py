"""Prevent incompatible shader compiler interfaces in the merged NXnative engine.

Pure source contract tests: no game inputs, SDK, Metal compiler, or GPU needed.
"""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "engine" / "dm" / "gfx" / "tools"


class ShaderCompilerIntegrationTests(unittest.TestCase):
    def test_builder_tracks_integrated_shader_chain_msl_version(self):
        source = (TOOLS / "dmsh_build.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        xc = [n for n in tree.body if isinstance(n, ast.Assign)
              and any(isinstance(target, ast.Name) and target.id == "XC"
                      for target in n.targets)]
        self.assertEqual(len(xc), 1)
        value = xc[0].value
        self.assertIsInstance(value, ast.List)
        first = value.elts[0]
        self.assertIsInstance(first, ast.Starred)
        self.assertIsInstance(first.value, ast.Attribute)
        self.assertEqual(first.value.attr, "CROSS_MSL")
        self.assertIsInstance(first.value.value, ast.Name)
        self.assertEqual(first.value.value.id, "dmsh_chain")
        self.assertIn("--msl-pad-fragment-output", source)

    def test_builder_uses_available_atomic_api(self):
        source = (TOOLS / "dmsh_build.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        import_names = set()
        for n in tree.body:
            if isinstance(n, ast.Import):
                import_names.update(alias.asname or alias.name for alias in n.names)
        self.assertIn("dmsh_atomic", import_names)
        atomics = ast.parse((TOOLS / "dmsh_atomic.py").read_text(encoding="utf-8"))
        defined = {n.name for n in atomics.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
        called = {n.func.attr for n in ast.walk(tree)
                  if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                  and isinstance(n.func.value, ast.Name) and n.func.value.id == "dmsh_atomic"}
        self.assertTrue(called, "shader builder must use atomics module")
        self.assertFalse(called - defined, "shader builder calls missing atomics functions: " + repr(called - defined))
        self.assertNotIn("cross_args", called)

    def test_worker_exception_handler_works_even_with_threads(self):
        source = (TOOLS / "dmsh_build.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        exceptions = [n for n in tree.body if isinstance(n, ast.ImportFrom)
                      and n.module == "concurrent.futures.process"]
        self.assertEqual(len(exceptions), 1)
        self.assertIn("BrokenProcessPool", [a.name for a in exceptions[0].names])
        self.assertIn("except BrokenProcessPool:", source)
        self.assertNotIn("cf.process.BrokenProcessPool", source)


if __name__ == "__main__":
    unittest.main()
