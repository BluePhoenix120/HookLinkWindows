"""Exercise the Windows IPA packager's actual C1 table validation block."""
import ast
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class C1TableStampTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = ROOT / 'engine' / 'win' / 'build_app.py'
        tree = ast.parse(source.read_text(encoding='utf-8'))
        # Execute just the validation statements from the real packager without
        # importing its toolchain or needing Apple SDKs and shader libraries.
        for node in ast.walk(tree):
            if not isinstance(node, ast.If):
                continue
            body = node.orelse
            for i, statement in enumerate(body):
                if (isinstance(statement, ast.Assign)
                        and isinstance(statement.targets[0], ast.Name)
                        and statement.targets[0].id == 'c1'):
                    block = ast.Module(body=body[i:i+4], type_ignores=[])
                    cls.validation = compile(block, str(source), 'exec')
                    return
        raise AssertionError('Windows C1 validation block not found')

    def test_header_contract(self):
        chain, inputs = 'd4d0313539cc', 'febb14a64182'
        want = f'# chain b-{chain} inputs {inputs}'
        cases = (
            ('canonical', want + '\n', True),
            ('legacy metadata', want + ' metadata\n', True),
            ('missing', None, False),
            ('empty', '', False),
            ('wrong chain', '# chain b-deadbeef0000 inputs ' + inputs + '\n', False),
            ('wrong inputs', f'# chain b-{chain} inputs deadbeef0000\n', False),
            ('digest prefix only', want + '0\n', False),
        )
        def die(message):
            raise ValueError(message)
        for label, contents, accepted in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as td:
                gd = Path(td)
                if contents is not None:
                    (gd / 'c1_full.tsv').write_text(contents, encoding='utf-8')
                scope = dict(gd=gd, v=chain, inputs=inputs, die=die)
                if accepted:
                    exec(self.validation, scope)
                else:
                    with self.assertRaisesRegex(ValueError, 'missing or not made from these libraries'):
                        exec(self.validation, scope)


if __name__ == '__main__':
    unittest.main()
