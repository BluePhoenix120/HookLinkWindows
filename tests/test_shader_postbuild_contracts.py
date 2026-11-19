"""Regression tests for the original-NXnative shader post-build analysis interface."""
import ast
from pathlib import Path
import sys
import unittest

TOOLS = Path(__file__).resolve().parents[1] / 'engine' / 'dm' / 'gfx' / 'tools'
sys.path.insert(0, str(TOOLS))
from c1_guard import memo_reflection


class ShaderPostbuildContractTests(unittest.TestCase):
    def test_cb_extent_named_imports_exist_in_c1_guard(self):
        c1 = ast.parse((TOOLS / 'c1_guard.py').read_text(encoding='utf-8'))
        cb = ast.parse((TOOLS / 'cb_extent.py').read_text(encoding='utf-8'))
        names = set()
        for node in c1.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                names.add(node.name)
            elif isinstance(node, ast.Assign):
                names.update(target.id for target in node.targets if isinstance(target, ast.Name))
            elif isinstance(node, ast.ImportFrom):
                names.update(alias.asname or alias.name for alias in node.names)
        required = {alias.name for node in cb.body
                    if isinstance(node, ast.ImportFrom) and node.module == 'c1_guard'
                    for alias in node.names if alias.name != '*'}
        self.assertTrue(required)
        self.assertEqual(required - names, set(), 'cb_extent.py imports missing guard functions')

    def test_memo_reflection_ignores_only_shader_chain_metadata(self):
        old = b'{"chain":"old","bindings":[{"kind":2}],"c1":"aabb"}'
        updated = b'{"chain":"new","bindings":[{"kind":2}],"c1":"aabb"}'
        changed = b'{"chain":"new","bindings":[{"kind":3}],"c1":"aabb"}'
        self.assertEqual(memo_reflection(old), memo_reflection(updated))
        self.assertNotEqual(memo_reflection(old), memo_reflection(changed))
        self.assertIn(b'"bindings":[{"kind":2}]', memo_reflection(old))
        self.assertIsNone(memo_reflection(None))


if __name__ == '__main__':
    unittest.main()
