from pathlib import Path
import re
import unittest

ROOT=Path(__file__).resolve().parents[1]

class NativeHostTestDependencies(unittest.TestCase):
    def test_all_primary_run_executables_have_build_dependencies(self):
        s=(ROOT/"engine/dm/host/tests/Makefile").read_text(encoding="utf-8")
        recipe=re.search(r"(?m)^run: [^\n]+\n(?:\t[^\n]*\n)+",s)
        self.assertIsNotNone(recipe)
        deps=set(re.findall(r"\$\(B\)/(t_\w+)", "\n".join(re.findall(r"(?m)^run:[^\n]*",s))))
        invoked=set(re.findall(r"\$\(B\)/(t_\w+)",recipe.group(0).split("\n",1)[1]))
        rules=set(re.findall(r"(?m)^\$\(B\)/(t_\w+):",s))
        self.assertTrue({"t_crash_diag","t_memstat"} <= invoked)
        self.assertFalse(invoked-deps)
        self.assertFalse(invoked-rules)
