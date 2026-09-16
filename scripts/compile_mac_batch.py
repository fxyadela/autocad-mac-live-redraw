#!/usr/bin/env python3
"""Compile two to nine redraw specs into one sequential AutoCAD Mac batch LSP.

The generated LSP keeps one drawing command, 1, plus the internal new-drawing
helper 0. Persistent batch state selects the next uploaded drawing across AutoCAD
document tabs. No drawing is saved automatically.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import shlex
import sys
import uuid

import compile_mac_redraw as single


def namespace_source(source: str, index: int, total: int) -> str:
    """Make one generated drawing coexist with the other batch drawings."""
    source = "\n".join(
        line for line in source.splitlines()
        if not line.startswith("(defun C:")
        and not line.startswith('(princ "\\nCADREDRAW loaded.')
    ) + "\n"
    source = source.replace("cad-redraw-", f"cad-redraw-{index}-")
    source = source.replace("CADREDRAW progress:", f"CADREDRAW DRAWING {index}/{total} progress:")
    source = source.replace("CADREDRAW FAILED:", f"CADREDRAW DRAWING {index}/{total} FAILED:")
    source = source.replace("CADREDRAW refused:", f"CADREDRAW DRAWING {index}/{total} refused:")
    source = source.replace("CADREDRAW DONE:", f"CADREDRAW DRAWING {index}/{total} DONE:")
    return source


def compile_batch(raw_specs: list[object], *, delay_ms: int, batch_size: int,
                  batch_id: str) -> tuple[str, list[tuple[int, int]]]:
    if not 2 <= len(raw_specs) <= 9:
        raise ValueError("one batch requires 2..9 specs; split larger jobs into ordered groups of nine")
    if not re.fullmatch(r"[A-Z0-9]{8,32}", batch_id):
        raise ValueError("batch-id must contain 8..32 uppercase ASCII letters or digits")
    blocks: list[str] = []
    counts: list[tuple[int, int]] = []
    total = len(raw_specs)
    for index, raw in enumerate(raw_specs, 1):
        entities, layers, insunits = single.validate_spec(raw)
        source, expected = single.compile_lisp(
            entities, layers, insunits, delay_ms=delay_ms, batch_size=batch_size
        )
        blocks.append(namespace_source(source, index, total))
        counts.append((len(entities), expected))
    state_key = "AutoCADMacLiveRedraw" + batch_id
    last_doc_key = state_key + "LastDoc"
    helpers = [
        "(defun cad-redraw-batch-doc-id ()",
        '  (strcat (getvar "DWGPREFIX") (getvar "DWGNAME")))',
        "(defun cad-redraw-batch-same-doc-p (/ last)",
        f"  (setq last (getenv {single.q(last_doc_key)}))",
        "  (and last (equal last (cad-redraw-batch-doc-id))))",
        "(defun C:0 (/ raw step)",
        f"  (setq raw (getenv {single.q(state_key)}))",
        "  (setq step (if (and raw (> (strlen raw) 0)) (atoi raw) 1))",
        f"  (if (and (> step 1) (<= step {total}) (cad-redraw-batch-same-doc-p))",
        '    (command-s "_.QNEW")',
        f"    (princ {single.q(chr(10) + 'CADREDRAW BATCH refused new drawing: finish the current drawing first, or the batch is already complete.')}))",
        "  (princ))",
    ]
    dispatch = [
        "(defun cad-redraw-batch-run (pause / raw step)",
        f"  (setq raw (getenv {single.q(state_key)}))",
        "  (setq step (if (and raw (> (strlen raw) 0)) (atoi raw) 1))",
        "  (cond",
    ]
    for index in range(1, total + 1):
        next_step = index + 1
        if index < total:
            ready = f"CADREDRAW BATCH ready: drawing {index}/{total} complete. Type 0 for a new blank drawing, then type 1."
        else:
            ready = f"CADREDRAW BATCH COMPLETE: all {total} drawings are open and unsaved. Do not create another drawing."
        run = [
            f"      (cad-redraw-{index}-run pause)",
            f"      (if cad-redraw-{index}-success",
            f"        (progn (setenv {single.q(state_key)} {single.q(str(next_step))})",
            f"          (setenv {single.q(last_doc_key)} (cad-redraw-batch-doc-id))",
            f"          (princ {single.q(chr(10) + ready)})))",
        ]
        dispatch.append(f"    ((= step {index})")
        if index == 1:
            dispatch.extend(run)
        else:
            dispatch.extend([
                "      (if (cad-redraw-batch-same-doc-p)",
                f"        (princ {single.q(chr(10) + 'CADREDRAW BATCH refused: still in the completed drawing. Type 0 once, confirm a new blank drawing, then type 1.')} )",
                "        (progn",
                *["  " + line for line in run],
                "        ))",
            ])
        dispatch.append("    )")
    dispatch.extend([
        f"    ((> step {total}) (princ {single.q(chr(10) + 'CADREDRAW BATCH already complete. Do not draw again.')}))",
        f"    (T (princ {single.q(chr(10) + 'CADREDRAW BATCH FAILED: invalid batch state. Stop without saving.')})))",
        "  (princ))",
        f"(defun C:1 () (cad-redraw-batch-run {delay_ms}))",
        f"(defun C:CADLIVE () (cad-redraw-batch-run {delay_ms}))",
        "(defun C:CADFAST () (cad-redraw-batch-run 0))",
    ])
    header = [
        f"; CADREDRAW BATCH COUNT: {total}",
        f"; CADREDRAW BATCH ID: {batch_id}",
        "; Draw in upload order. Type 0 only after the current drawing is verified complete, then type 1 again.",
        "; Every drawing remains open and unsaved unless the user explicitly asks to save.",
    ]
    footer = [
        f'(princ "\\nCADREDRAW BATCH loaded: {total} drawings. Type 1 to draw; after completion type 0 then 1 for the next drawing.")',
        "(princ)",
    ]
    return ("\n".join(header) + "\n" + "\n".join(blocks) + "\n" +
            "\n".join(helpers) + "\n" +
            "\n".join(dispatch) + "\n" + "\n".join(footer) + "\n", counts)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", action="append", required=True, type=Path,
                        help="Absolute JSON spec path; repeat in upload order (2..9)")
    parser.add_argument("--out", required=True, type=Path,
                        help="New absolute batch .lsp file; never overwrites")
    parser.add_argument("--delay-ms", type=int, default=35,
                        help="Visible delay after every native object (0..3000)")
    parser.add_argument("--batch-size", type=int, default=25,
                        help="Source entries per progress message (1..100)")
    parser.add_argument("--batch-id", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    try:
        if not args.out.is_absolute() or args.out.suffix.lower() != ".lsp":
            raise ValueError("out must be an absolute .lsp path")
        if not all(path.is_absolute() for path in args.spec):
            raise ValueError("every spec path must be absolute")
        if len({path.resolve() for path in args.spec}) != len(args.spec):
            raise ValueError("duplicate spec path in batch")
        if not 0 <= args.delay_ms <= 3000 or not 1 <= args.batch_size <= 100:
            raise ValueError("delay-ms must be 0..3000 and batch-size must be 1..100")
        raw_specs = [json.loads(path.read_text(encoding="utf-8")) for path in args.spec]
        batch_id = args.batch_id or uuid.uuid4().hex[:12].upper()
        source, counts = compile_batch(raw_specs, delay_ms=args.delay_ms,
                                       batch_size=args.batch_size, batch_id=batch_id)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("x", encoding="utf-8", newline="\n") as output:
            output.write(source)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"CADREDRAW batch compile FAILED: {exc}", file=sys.stderr)
        return 2
    print(f"Generated batch {args.out}: {len(counts)} drawings")
    for index, ((entries, objects), path) in enumerate(zip(counts, args.spec), 1):
        print(f"  drawing {index}: {path} -> {entries} source entries, {objects} native objects")
    print("Next terminal step: python3 scripts/deploy_autocad_bundle.py --lsp " +
          shlex.quote(str(args.out)))
    print("Type 1 for the current drawing. After it is verified complete, type 0 then 1 for the next; leave every drawing unsaved.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
