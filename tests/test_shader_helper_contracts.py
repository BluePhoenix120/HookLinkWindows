"""Shader builder and merged helper module contracts: no game or Metal SDK required."""
import ast
import sys
from pathlib import Path
import unittest

TOOLS = Path(__file__).resolve().parents[1] / 'engine' / 'dm' / 'gfx' / 'tools'
sys.path.insert(0, str(TOOLS))
import dmsh_rewrite


class ShaderHelperContractTests(unittest.TestCase):
    def test_every_direct_builder_helper_call_exists(self):
        build = ast.parse((TOOLS / 'dmsh_build.py').read_text(encoding='utf-8'))
        called = {}
        for node in ast.walk(build):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and isinstance(node.func.value, ast.Name)):
                module = node.func.value.id
                if module.startswith('dmsh_'):
                    called.setdefault(module, set()).add(node.func.attr)
        self.assertTrue(called)
        missing = []
        for module, members in sorted(called.items()):
            file = TOOLS / (module + '.py')
            self.assertTrue(file.is_file(), str(file))
            tree = ast.parse(file.read_text(encoding='utf-8'))
            known = {node.name for node in tree.body
                     if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
            for node in tree.body:
                if isinstance(node, ast.Assign):
                    known.update(target.id for target in node.targets if isinstance(target, ast.Name))
                elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                    known.add(node.target.id)
            missing += [f'{module}.{member}' for member in members if member not in known]
        self.assertEqual(missing, [], 'Builder calls missing merged helper APIs')

    def test_mem_barrier_replaced_with_device_fence(self):
        mem_barrier = 'threadgroup_barrier(mem_flags::mem_device | mem_flags::mem_threadgroup | mem_flags::mem_texture);'
        normal_barrier = 'threadgroup_barrier(mem_flags::mem_threadgroup);'
        result = dmsh_rewrite.membar_fence('  ' + mem_barrier + '\n  ' + normal_barrier + '\n')
        self.assertNotIn(mem_barrier, result)
        self.assertIn('atomic_thread_fence(', result)
        self.assertIn('thread_scope_device', result)
        self.assertIn('memory_order_seq_cst', result)
        self.assertIn(normal_barrier, result)
        self.assertEqual(dmsh_rewrite.membar_fence('nothing to rewrite'), 'nothing to rewrite')

    def test_adjacent_mem_bars_coalesce(self):
        barrier = 'threadgroup_barrier(mem_flags::mem_device | mem_flags::mem_threadgroup | mem_flags::mem_texture);'
        result = dmsh_rewrite.membar_fence('    ' + barrier + '\n    ' + barrier + '\n')
        self.assertEqual(result.count('atomic_thread_fence('), 1)
        self.assertNotIn(barrier, result)


if __name__ == '__main__':
    unittest.main()
