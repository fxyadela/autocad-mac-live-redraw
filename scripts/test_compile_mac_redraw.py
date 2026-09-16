"""Offline tests only; no native AutoCAD assertion is made by these tests."""

from __future__ import annotations

import copy
from contextlib import redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest


COMPILER_PATH = Path(__file__).with_name("compile_mac_redraw.py")
EXAMPLE = Path(__file__).parent.parent / "references" / "sample-spec.json"
module_spec = importlib.util.spec_from_file_location("cad_mac_compile", COMPILER_PATH)
assert module_spec and module_spec.loader
compiler = importlib.util.module_from_spec(module_spec)
module_spec.loader.exec_module(compiler)


def balanced_lisp(source: str) -> bool:
    """Check generated parentheses without counting strings or line comments."""
    depth = 0
    in_string = False
    escaped = False
    in_comment = False
    for c in source:
        if in_comment:
            if c == "\n":
                in_comment = False
            continue
        if in_string:
            if escaped:
                escaped = False
            elif c == "\\":
                escaped = True
            elif c == '"':
                in_string = False
            continue
        if c == ";":
            in_comment = True
        elif c == '"':
            in_string = True
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth < 0:
                return False
    return depth == 0 and not in_string


class MacCompilerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.spec = json.loads(EXAMPLE.read_text(encoding="utf-8"))

    def test_smoke_spec_generates_native_commands(self) -> None:
        entities, layers, units = compiler.validate_spec(self.spec)
        output, expected = compiler.compile_lisp(entities, layers, units,
                                                 delay_ms=100, batch_size=2)
        self.assertEqual(expected, 13)
        self.assertTrue(balanced_lisp(output))
        for fragment in ('(entmake data)', '"_.DIMALIGNED"', '"_.DIMROTATED"',
                         '"_.DELAY"', '(redraw made 1)', '"_.ZOOM" "_Window"',
                         '"卧室"', '"测试\\\\P多行"',
                         '(defun C:CADLIVE', 'CADREDRAW DONE'):
            self.assertIn(fragment, output)
        self.assertEqual(output.count("      (cad-redraw-show pause)"), expected)
        self.assertLess(output.index('"_.ZOOM" "_Window"'), output.index('(cad-redraw-make'))
        self.assertNotIn('CADREDRAW batch:', output)
        self.assertNotIn("win32com", output)

    def test_unsupported_entity_blocks_entire_compile(self) -> None:
        spec = copy.deepcopy(self.spec)
        spec["entities"].append({"type": "table", "cells": [["must not vanish"]]})
        with self.assertRaisesRegex(ValueError, "unsupported entities: table=1"):
            compiler.validate_spec(spec)

    def test_bad_scale_and_nonfinite_numbers_block(self) -> None:
        spec = copy.deepcopy(self.spec)
        spec["metadata"]["units"] = "pixels-as-mm"
        with self.assertRaisesRegex(ValueError, "unsupported units"):
            compiler.validate_spec(spec)
        spec["metadata"]["units"] = "unitless"
        spec["entities"][0]["start"] = [float("nan"), 0]
        with self.assertRaisesRegex(ValueError, "non-finite"):
            compiler.validate_spec(spec)

    def test_explicit_missing_style_and_layer_are_rejected(self) -> None:
        spec = copy.deepcopy(self.spec)
        spec["entities"][5]["text_style"] = "CustomFont"
        with self.assertRaisesRegex(ValueError, "named text style"):
            compiler.validate_spec(spec)
        spec["entities"][5].pop("text_style")
        spec["entities"][0]["layer"] = "Bad/Layer"
        with self.assertRaisesRegex(ValueError, "invalid AutoCAD layer"):
            compiler.validate_spec(spec)

    def test_no_overwrite_and_explicit_absolute_paths(self) -> None:
        with tempfile.TemporaryDirectory(prefix="mac-cad-redraw-test-") as folder:
            directory = Path(folder)
            specfile = directory / "input.json"
            specfile.write_text(json.dumps(self.spec, ensure_ascii=False), encoding="utf-8")
            dest = directory / "native.lsp"
            argv = ["--spec", str(specfile), "--out", str(dest)]
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                self.assertEqual(compiler.main(argv), 0)
            first = dest.read_bytes()
            self.assertIn(b"(defun C:CADLIVE () (cad-redraw-run 35))", first)
            self.assertIn(f'(progn (load "{dest.as_posix()}") (C:CADLIVE))', stdout.getvalue())
            self.assertEqual(compiler.main(argv), 2)
            self.assertEqual(dest.read_bytes(), first)
            self.assertEqual(compiler.main(["--spec", "relative.json", "--out", str(directory / "bad.lsp")]), 2)


if __name__ == "__main__":
    unittest.main()
