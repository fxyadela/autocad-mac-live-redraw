"""Offline tests for ordered multi-drawing LSP compilation."""

from __future__ import annotations

from contextlib import redirect_stdout
import importlib.util
from io import StringIO
import json
from pathlib import Path
import sys
import tempfile
import unittest


SCRIPTS = Path(__file__).parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
SCRIPT = SCRIPTS / "compile_mac_batch.py"
EXAMPLE = SCRIPTS.parent / "references" / "sample-spec.json"
module_spec = importlib.util.spec_from_file_location("cad_mac_batch", SCRIPT)
assert module_spec and module_spec.loader
batch = importlib.util.module_from_spec(module_spec)
module_spec.loader.exec_module(batch)


def balanced_lisp(source: str) -> bool:
    depth = 0
    in_string = False
    escaped = False
    in_comment = False
    for char in source:
        if in_comment:
            if char == "\n":
                in_comment = False
            continue
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == ";":
            in_comment = True
        elif char == '"':
            in_string = True
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth < 0:
                return False
    return depth == 0 and not in_string


class MacBatchCompilerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.spec = json.loads(EXAMPLE.read_text(encoding="utf-8"))

    def test_two_drawings_share_dispatcher_and_keep_distinct_state(self) -> None:
        source, counts = batch.compile_batch(
            [self.spec, self.spec], delay_ms=35, batch_size=25,
            batch_id="TESTBATCH01"
        )
        self.assertEqual(counts, [(11, 13), (11, 13)])
        self.assertIn("; CADREDRAW BATCH COUNT: 2", source)
        self.assertEqual(source.count("(defun C:0 "), 1)
        self.assertIn("(defun C:1 () (cad-redraw-batch-run 35))", source)
        self.assertEqual(source.count("(defun C:1 "), 1)
        self.assertNotIn("(defun C:2 ", source)
        self.assertIn("(cad-redraw-1-run pause)", source)
        self.assertIn("(cad-redraw-2-run pause)", source)
        self.assertIn('(getenv "AutoCADMacLiveRedrawTESTBATCH01")', source)
        self.assertIn('(setenv "AutoCADMacLiveRedrawTESTBATCH01" "2")', source)
        self.assertIn('(setenv "AutoCADMacLiveRedrawTESTBATCH01" "3")', source)
        self.assertIn('(getenv "AutoCADMacLiveRedrawTESTBATCH01LastDoc")', source)
        self.assertIn('(setenv "AutoCADMacLiveRedrawTESTBATCH01LastDoc" (cad-redraw-batch-doc-id))', source)
        self.assertIn('(and (> step 1) (<= step 2) (cad-redraw-batch-same-doc-p))', source)
        self.assertIn("refused: still in the completed drawing", source)
        self.assertIn("CADREDRAW DRAWING 1/2 DONE", source)
        self.assertIn("CADREDRAW DRAWING 2/2 DONE", source)
        self.assertNotIn('"_.SAVE', source)
        self.assertNotIn('"_.QSAVE', source)
        self.assertTrue(balanced_lisp(source))

    def test_batch_size_limits_are_strict(self) -> None:
        with self.assertRaisesRegex(ValueError, "2..9"):
            batch.compile_batch([self.spec], delay_ms=35, batch_size=25,
                                batch_id="TESTBATCH01")
        with self.assertRaisesRegex(ValueError, "2..9"):
            batch.compile_batch([self.spec] * 10, delay_ms=35, batch_size=25,
                                batch_id="TESTBATCH01")

    def test_three_drawings_keep_progress_across_two_tab_changes(self) -> None:
        source, counts = batch.compile_batch(
            [self.spec, self.spec, self.spec], delay_ms=25, batch_size=20,
            batch_id="THREETABS01"
        )
        self.assertEqual(len(counts), 3)
        for index in range(1, 4):
            self.assertIn(f"(cad-redraw-{index}-run pause)", source)
        for next_step in range(2, 5):
            self.assertIn(
                f'(setenv "AutoCADMacLiveRedrawTHREETABS01" "{next_step}")',
                source,
            )
        self.assertEqual(source.count("Type 0 for a new blank drawing"), 2)
        self.assertIn("all 3 drawings are open and unsaved", source)
        self.assertTrue(balanced_lisp(source))

    def test_cli_never_overwrites(self) -> None:
        with tempfile.TemporaryDirectory(prefix="mac-cad-batch-test-") as folder:
            root = Path(folder)
            first = root / "first.json"
            second = root / "second.json"
            out = root / "batch.lsp"
            first.write_text(json.dumps(self.spec, ensure_ascii=False), encoding="utf-8")
            second.write_text(json.dumps(self.spec, ensure_ascii=False), encoding="utf-8")
            argv = ["--spec", str(first), "--spec", str(second), "--out", str(out),
                    "--batch-id", "TESTBATCH01"]
            stdout = StringIO()
            with redirect_stdout(stdout):
                self.assertEqual(batch.main(argv), 0)
            original = out.read_bytes()
            self.assertIn("drawing 1", stdout.getvalue())
            self.assertEqual(batch.main(argv), 2)
            self.assertEqual(out.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
