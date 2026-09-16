#!/usr/bin/env python3
"""Compile an evidence-backed 2D redraw spec to native AutoCAD for Mac AutoLISP.

No AutoCAD installation or Windows COM module is needed for this offline step.
The generated CADLIVE command must be loaded and validated in a blank native drawing.
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
import math
from pathlib import Path
import re
import shlex
import sys


UNITS = {"unitless": 0, "in": 1, "ft": 2, "mm": 4, "cm": 5, "m": 6}
SUPPORTED = {
    "line", "polyline", "rectangle", "circle", "arc", "text", "mtext",
    "leader", "linear_dimension", "aligned_dimension", "center_mark",
}
BAD_LAYER_CHARS = re.compile(r'[<>/\\":;?*|=,]')


def number(value: object, where: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{where}: expected a number")
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"{where}: non-finite number")
    return value


def positive(value: object, where: str) -> float:
    result = number(value, where)
    if result <= 0:
        raise ValueError(f"{where}: must be positive")
    return result


def point(value: object, where: str) -> tuple[float, float]:
    if not isinstance(value, (list, tuple)) or len(value) not in (2, 3):
        raise ValueError(f"{where}: expected [x, y] or [x, y, 0]")
    x, y = number(value[0], where + ".x"), number(value[1], where + ".y")
    if len(value) == 3 and number(value[2], where + ".z") != 0:
        raise ValueError(f"{where}: only model-space z=0 is supported")
    return x, y


def layer_name(value: object, where: str) -> str:
    if not isinstance(value, str) or not value.strip() or BAD_LAYER_CHARS.search(value):
        raise ValueError(f"{where}: invalid AutoCAD layer name: {value!r}")
    if len(value) > 255:
        raise ValueError(f"{where}: layer name too long")
    return value


def color(value: object, where: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 255:
        raise ValueError(f"{where}: expected AutoCAD indexed color 1..255")
    return value


def linetype(value: object, where: str) -> None:
    if not isinstance(value, str) or value.lower() != "continuous":
        raise ValueError(f"{where}: this Mac compiler only supports Continuous")


def text(value: object, where: str, *, multiline: bool = False) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{where}: nonempty text required")
    if "\x00" in value or (not multiline and ("\n" in value or "\r" in value)):
        raise ValueError(f"{where}: invalid control character in text")
    if multiline and len(value.encode("utf-8")) > 240:
        raise ValueError(f"{where}: MTEXT over 240 UTF-8 bytes needs chunk support")
    return value


def validate_entity(entity: object, index: int) -> dict:
    where = f"entity #{index}"
    if not isinstance(entity, dict):
        raise ValueError(f"{where}: expected an object")
    kind = entity.get("type")
    if kind not in SUPPORTED:
        raise ValueError(f"{where}: unsupported {kind!r}; do not discard this content")
    e = dict(entity)
    e["layer"] = layer_name(e.get("layer", "0"), where + ".layer")
    if "color" in e:
        color(e["color"], where + ".color")
    if "linetype" in e:
        linetype(e["linetype"], where + ".linetype")
    if "text_style" in e and e["text_style"] not in (None, "Standard"):
        raise ValueError(f"{where}: named text style requires native font/style support")
    for styling in ("lineweight", "transparency", "text_width", "dimstyle", "plot_style"):
        if styling in e and e[styling] is not None:
            raise ValueError(f"{where}: {styling} requires further Mac adapter support")
    if e.get("space", "model") != "model":
        raise ValueError(f"{where}: only model space is supported")

    if kind == "line":
        a, b = point(e.get("start"), where + ".start"), point(e.get("end"), where + ".end")
        if a == b:
            raise ValueError(f"{where}: zero-length line")
    elif kind == "polyline":
        pts = e.get("points")
        if not isinstance(pts, list) or len(pts) < (3 if e.get("closed") else 2):
            raise ValueError(f"{where}: polyline has too few vertices")
        for j, p in enumerate(pts):
            point(p, f"{where}.points[{j}]")
        if e.get("closed") and point(pts[0], where + ".points[0") == point(pts[-1], where + ".points[-1") and len(pts) < 4:
            raise ValueError(f"{where}: closed polyline needs three distinct vertices")
        if "closed" in e and not isinstance(e["closed"], bool):
            raise ValueError(f"{where}: closed must be boolean")
    elif kind == "rectangle":
        if "p1" in e and "p2" in e:
            a, b = point(e["p1"], where + ".p1"), point(e["p2"], where + ".p2")
            if a[0] == b[0] or a[1] == b[1]:
                raise ValueError(f"{where}: degenerate rectangle")
        else:
            for key in ("x", "y"):
                number(e.get(key), where + "." + key)
            for key in ("width", "height"):
                positive(e.get(key), where + "." + key)
            if not math.isfinite(float(e["x"]) + float(e["width"])) or not math.isfinite(float(e["y"]) + float(e["height"])):
                raise ValueError(f"{where}: rectangle coordinates overflow")
    elif kind in ("circle", "arc"):
        point(e.get("center"), where + ".center")
        positive(e.get("radius"), where + ".radius")
        if kind == "arc":
            a = number(e.get("start_angle"), where + ".start_angle")
            b = number(e.get("end_angle"), where + ".end_angle")
            if (a - b) % 360 == 0:
                raise ValueError(f"{where}: arc endpoints coincide; use circle for a full turn")
    elif kind in ("text", "mtext"):
        text(e.get("text"), where + ".text", multiline=kind == "mtext")
        point(e.get("point"), where + ".point")
        positive(e.get("height", 3.5), where + ".height")
        number(e.get("rotation", 0), where + ".rotation")
        if kind == "mtext":
            positive(e.get("width"), where + ".width")
    elif kind == "leader":
        pts = e.get("points")
        if not isinstance(pts, list) or len(pts) < 2:
            raise ValueError(f"{where}: leader needs two or more points")
        for j, p in enumerate(pts):
            point(p, f"{where}.points[{j}]")
        text(e.get("text"), where + ".text")
        point(e.get("text_point", pts[-1]), where + ".text_point")
        positive(e.get("text_height", e.get("height", 3.5)), where + ".text_height")
        if "text_layer" in e:
            layer_name(e["text_layer"], where + ".text_layer")
        if "text_rotation" in e:
            number(e["text_rotation"], where + ".text_rotation")
    elif kind.endswith("_dimension"):
        a = point(e.get("p1"), where + ".p1")
        b = point(e.get("p2"), where + ".p2")
        point(e.get("dimline"), where + ".dimline")
        if a == b:
            raise ValueError(f"{where}: dimension endpoints coincide")
        if kind == "linear_dimension":
            number(e.get("angle", 0), where + ".angle")
        if "text" in e:
            text(e["text"], where + ".text")
        if "color" in e:
            raise ValueError(f"{where}: explicit dimension color is not supported; set its layer color")
    elif kind == "center_mark":
        point(e.get("center"), where + ".center")
        positive(e.get("size", 10), where + ".size")
    return e


def validate_spec(raw: object) -> tuple[list[dict], dict[str, int], int]:
    if not isinstance(raw, dict):
        raise ValueError("spec root must be a JSON object")
    metadata = raw.get("metadata", {})
    if not isinstance(metadata, dict):
        raise ValueError("metadata must be an object")
    unit = metadata.get("units", raw.get("units", "unitless"))
    if isinstance(unit, dict):
        unit = unit.get("name", unit.get("unit"))
    if not isinstance(unit, str) or unit.lower() not in UNITS:
        raise ValueError(f"unsupported units {unit!r}; do not invent physical scale")
    declared = raw.get("layers", [])
    if not isinstance(declared, list):
        raise ValueError("layers must be a list")
    layers: dict[str, int] = {"0": 7}
    for i, item in enumerate(declared, 1):
        if not isinstance(item, dict):
            raise ValueError(f"layer #{i}: expected an object")
        name = layer_name(item.get("name"), f"layer #{i}")
        if name in layers:
            raise ValueError(f"layer #{i}: duplicate layer {name}")
        if "linetype" in item:
            linetype(item["linetype"], f"layer #{i}.linetype")
        layers[name] = color(item.get("color", 7), f"layer #{i}.color")
    entries = raw.get("entities")
    if not isinstance(entries, list) or not entries:
        raise ValueError("entities must be a nonempty list")
    unsupported = Counter(str(item.get("type")) for item in entries if isinstance(item, dict) and item.get("type") not in SUPPORTED)
    if unsupported:
        raise ValueError("unsupported entities: " + ", ".join(f"{kind}={count}" for kind, count in sorted(unsupported.items())) + "; use full DXF or extend adapter")
    entities = [validate_entity(item, index) for index, item in enumerate(entries, 1)]
    for e in entities:
        layers.setdefault(e["layer"], 7)
        if e["type"] == "leader" and "text_layer" in e:
            layers.setdefault(e["text_layer"], 7)
    return entities, layers, UNITS[unit.lower()]


def fmt(value: float) -> str:
    return f"{value:.14g}" if value else "0.0"


def q(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"').replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\\n") + '"'


def p(value: object, where: str) -> str:
    x, y = point(value, where)
    return f"(list {fmt(x)} {fmt(y)} 0.0)"


def pair(code: int, value: str) -> str:
    return f"(cons {code} {value})"


def common(e: dict) -> list[str]:
    data = [pair(8, q(e["layer"]))]
    if "color" in e:
        data.append(pair(62, str(e["color"])))
    return data


def make(kind: str, fields: list[str], e: dict, index: int) -> str:
    rows = [pair(0, q(kind)), *common(e), *fields]
    return f"(cad-redraw-make (list {' '.join(rows)}) {q(f'entity #{index} {kind}')})"


def coords_rect(e: dict) -> list[tuple[float, float]]:
    if "p1" in e and "p2" in e:
        x1, y1 = point(e["p1"], "rectangle.p1")
        x2, y2 = point(e["p2"], "rectangle.p2")
    else:
        x1, y1 = number(e["x"], "rectangle.x"), number(e["y"], "rectangle.y")
        x2, y2 = x1 + number(e["width"], "rectangle.width"), y1 + number(e["height"], "rectangle.height")
    return [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]


def entity_view_points(e: dict) -> list[tuple[float, float]]:
    """Return conservative points used to frame the drawing before creation."""
    kind = e["type"]
    if kind == "line":
        return [point(e["start"], "line.start"), point(e["end"], "line.end")]
    if kind == "polyline":
        return [point(value, "polyline.points") for value in e["points"]]
    if kind == "rectangle":
        return coords_rect(e)
    if kind in ("circle", "arc"):
        x, y = point(e["center"], kind + ".center")
        radius = number(e["radius"], kind + ".radius")
        return [(x - radius, y - radius), (x + radius, y + radius)]
    if kind in ("text", "mtext"):
        x, y = point(e["point"], kind + ".point")
        height = number(e.get("height", 3.5), kind + ".height")
        if kind == "mtext":
            width = number(e["width"], "mtext.width")
        else:
            width = max(height, min(len(e["text"]), 24) * height * 0.65)
        pad = max(height, width)
        return [(x - pad, y - pad), (x + pad, y + pad)]
    if kind == "leader":
        values = [point(value, "leader.points") for value in e["points"]]
        values.append(point(e.get("text_point", e["points"][-1]), "leader.text_point"))
        return values
    if kind.endswith("_dimension"):
        return [point(e["p1"], kind + ".p1"), point(e["p2"], kind + ".p2"),
                point(e["dimline"], kind + ".dimline")]
    if kind == "center_mark":
        x, y = point(e["center"], "center_mark.center")
        half = number(e.get("size", 10), "center_mark.size") / 2
        return [(x - half, y - half), (x + half, y + half)]
    raise AssertionError(kind)


def drawing_view_window(entities: list[dict]) -> tuple[float, float, float, float]:
    points = [value for entity in entities for value in entity_view_points(entity)]
    xs = [value[0] for value in points]
    ys = [value[1] for value in points]
    xmin, xmax, ymin, ymax = min(xs), max(xs), min(ys), max(ys)
    span = max(xmax - xmin, ymax - ymin, 1.0)
    margin = span * 0.04
    return xmin - margin, ymin - margin, xmax + margin, ymax + margin


def polyline(e: dict, index: int, pts: list[tuple[float, float]], closed: bool) -> str:
    if closed and pts[-1] == pts[0]:
        pts = pts[:-1]
    fields = [pair(100, q("AcDbEntity")), *common(e), pair(100, q("AcDbPolyline")),
              pair(90, str(len(pts))), pair(70, str(int(closed)))]
    fields.extend(pair(10, f"(list {fmt(x)} {fmt(y)})") for x, y in pts)
    return f"(cad-redraw-make (list {pair(0, q('LWPOLYLINE'))} {' '.join(fields)}) {q(f'entity #{index} LWPOLYLINE')})"


def emit_entity(e: dict, index: int) -> list[str]:
    kind = e["type"]
    if kind == "line":
        return [make("LINE", [pair(10, p(e["start"], "start")), pair(11, p(e["end"], "end"))], e, index)]
    if kind in ("polyline", "rectangle"):
        pts = ([point(v, "polyline.points") for v in e["points"]] if kind == "polyline" else coords_rect(e))
        return [polyline(e, index, pts, bool(e.get("closed", kind == "rectangle")))]
    if kind in ("circle", "arc"):
        fields = [pair(10, p(e["center"], "center")), pair(40, fmt(number(e["radius"], "radius")))]
        if kind == "arc":
            fields += [pair(50, fmt(math.radians(number(e["start_angle"], "start_angle")))),
                       pair(51, fmt(math.radians(number(e["end_angle"], "end_angle"))))]
        return [make(kind.upper(), fields, e, index)]
    if kind in ("text", "mtext"):
        content = e["text"].replace("\r\n", "\n").replace("\r", "\n")
        if kind == "mtext":
            content = content.replace("\n", "\\P")
        fields = [pair(10, p(e["point"], "point")), pair(40, fmt(number(e.get("height", 3.5), "height")))]
        if kind == "mtext":
            fields = [pair(100, q("AcDbEntity")), *common(e), pair(100, q("AcDbMText")),
                      *fields, pair(41, fmt(number(e["width"], "width"))), pair(71, "1"),
                      pair(1, q(content))]
            fields.append(pair(50, fmt(math.radians(number(e.get("rotation", 0), "rotation")))))
            return [f"(cad-redraw-make (list {pair(0, q('MTEXT'))} {' '.join(fields)}) {q(f'entity #{index} MTEXT')})"]
        fields += [pair(1, q(content)), pair(50, fmt(math.radians(number(e.get("rotation", 0), "rotation"))))]
        return [make("TEXT", fields, e, index)]
    if kind == "leader":
        pts = e["points"]
        result = [make("LINE", [pair(10, p(a, "leader.point")), pair(11, p(b, "leader.point"))], e, index)
                  for a, b in zip(pts, pts[1:])]
        label = dict(e, type="text", point=e.get("text_point", pts[-1]),
                     height=e.get("text_height", e.get("height", 3.5)), layer=e.get("text_layer", e["layer"]))
        label["rotation"] = e.get("text_rotation", 0)
        result += emit_entity(label, index)
        return result
    if kind == "center_mark":
        x, y = point(e["center"], "center")
        half = number(e.get("size", 10), "size") / 2
        return [make("LINE", [pair(10, p(a, "center_mark.start")), pair(11, p(b, "center_mark.end"))], e, index)
                for a, b in [((x - half, y), (x + half, y)), ((x, y - half), (x, y + half))]]
    if kind.endswith("_dimension"):
        cmd = "_.DIMROTATED" if kind == "linear_dimension" else "_.DIMALIGNED"
        args = ([q(fmt(number(e.get("angle", 0), "dimension.angle")))] if kind == "linear_dimension" else [])
        args += [p(e["p1"], "p1"), p(e["p2"], "p2"), p(e["dimline"], "dimline")]
        override = q(e["text"]) if "text" in e else "nil"
        return [f"(cad-redraw-dim {q(cmd)} {q(e['layer'])} (list {' '.join(args)}) {override} {q(f'entity #{index} dimension')})"]
    raise AssertionError(kind)


def compile_lisp(entities: list[dict], layers: dict[str, int], insunits: int,
                 *, delay_ms: int, batch_size: int) -> tuple[str, int]:
    expected = sum(len(emit_entity(e, index)) for index, e in enumerate(entities, 1))
    xmin, ymin, xmax, ymax = drawing_view_window(entities)
    lines = [
        "; AutoCAD for Mac native editables; generated from checked JSON, NOT an image preview.",
        "; Run only in a newly created blank model-space drawing. Load this file, then CADLIVE.",
        "(defun cad-redraw-abort (msg)",
        "  (princ (strcat \"\\nCADREDRAW FAILED: \" msg \". Discard unsaved partial drawing.\"))",
        "  (if cad-redraw-undo (command-s \"_.UNDO\" \"_End\"))",
        "  (setq cad-redraw-undo nil cad-redraw-success nil)",
        "  (quit))",
        "(defun cad-redraw-make (data label)",
        "  (if (not (entmake data)) (cad-redraw-abort label))",
        "  (setq cad-redraw-count (1+ cad-redraw-count)))",
        "(defun cad-redraw-dim (cmd layer args override label / before made data)",
        "  (setq before (entlast))",
        "  (setvar \"CLAYER\" layer)",
        "  (apply 'command-s (cons cmd args))",
        "  (setq made (entlast))",
        "  (if (or (null made) (eq made before)) (cad-redraw-abort label))",
        "  (if override",
        "    (progn (setq data (entget made))",
        "      (if (assoc 1 data)",
        "        (setq data (subst (cons 1 override) (assoc 1 data) data))",
        "        (setq data (append data (list (cons 1 override)))))",
        "      (if (not (entmod data)) (cad-redraw-abort (strcat label \" text override\")))))",
        "  (setq cad-redraw-count (1+ cad-redraw-count)))",
        "(defun cad-redraw-show (pause / made)",
        "  (if (> pause 0)",
        "    (progn",
        "      (setq made (entlast))",
        "      (if made (redraw made 1))",
        "      (command-s \"_.DELAY\" (itoa pause)))))",
        "(defun cad-redraw-run (pause / existing model)",
        "  (setq existing (ssget \"_X\" '((410 . \"Model\"))))",
        "  (if existing",
        "    (princ \"\\nCADREDRAW refused: model space is not blank; create a new empty drawing.\")",
        "    (progn",
        "      (setq cad-redraw-count 0 cad-redraw-undo T cad-redraw-success nil)",
        "      (command-s \"_.UNDO\" \"_Begin\")",
        f"      (setvar \"INSUNITS\" {insunits})",
    ]
    for name, index_color in layers.items():
        if name == "0":
            continue
        definition = f"(list {pair(0, q('LAYER'))} {pair(100, q('AcDbSymbolTableRecord'))} {pair(100, q('AcDbLayerTableRecord'))} {pair(2, q(name))} {pair(70, '0')} {pair(62, str(index_color))} {pair(6, q('Continuous'))})"
        lines.append(f"      (if (not (tblsearch \"LAYER\" {q(name)})) (if (not (entmake {definition})) (cad-redraw-abort {q('layer ' + name)})))")
    lines.append(
        f"      (command-s \"_.ZOOM\" \"_Window\" (list {fmt(xmin)} {fmt(ymin)} 0.0) "
        f"(list {fmt(xmax)} {fmt(ymax)} 0.0))"
    )
    native_index = 0
    for index, e in enumerate(entities, 1):
        for command in emit_entity(e, index):
            lines.append("      " + command)
            lines.append("      (cad-redraw-show pause)")
            native_index += 1
        if index % batch_size == 0 or index == len(entities):
            progress_message = f"\nCADREDRAW progress: {index}/{len(entities)} source entries"
            lines.append(f"      (princ {q(progress_message)})")
    assert native_index == expected
    lines += [
        "      (command-s \"_.ZOOM\" \"_Extents\")",
        "      (command-s \"_.UNDO\" \"_End\")",
        "      (setq cad-redraw-undo nil)",
        "      (setq model (ssget \"_X\" '((410 . \"Model\"))))",
        f"      (setq cad-redraw-success (and model (= (sslength model) {expected}) (= cad-redraw-count {expected})))",
        f"      (if (/= cad-redraw-count {expected}) (princ \"\\nCADREDRAW FAILED: internal count mismatch.\"))",
        f"      (if (or (null model) (/= (sslength model) {expected})) (princ \"\\nCADREDRAW FAILED: native model-space count mismatch. Do not save.\"))",
        "      (if cad-redraw-success",
        f"        (princ {q(chr(10) + 'CADREDRAW DONE: ' + str(len(entities)) + ' source entries, ' + str(expected) + ' native model-space objects. Leave this drawing open and unsaved unless the user explicitly asks to save.')}) )",
        "    ))",
        "  (princ))",
        "(defun C:0 () (command-s \"_.QNEW\") (princ))",
        f"(defun C:1 () (cad-redraw-run {delay_ms}))",
        f"(defun C:CADLIVE () (cad-redraw-run {delay_ms}))",
        "(defun C:CADFAST () (cad-redraw-run 0))",
        "(princ \"\\nCADREDRAW loaded. New blank drawing -> type 1, or use CADLIVE/CADFAST.\")",
        "(princ)",
    ]
    return "\n".join(lines) + "\n", expected


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", required=True, type=Path, help="Absolute path to evidence-backed JSON spec")
    parser.add_argument("--out", required=True, type=Path, help="New absolute .lsp file; never overwrites")
    parser.add_argument("--delay-ms", type=int, default=35, help="Visible delay after every native object (0..3000)")
    parser.add_argument("--batch-size", type=int, default=25, help="Source entries per progress message (1..100); drawing is always object-by-object")
    args = parser.parse_args(argv)
    try:
        if not args.spec.is_absolute() or not args.out.is_absolute() or args.out.suffix.lower() != ".lsp":
            raise ValueError("spec and out must be absolute paths; out must end in .lsp")
        if not 0 <= args.delay_ms <= 3000 or not 1 <= args.batch_size <= 100:
            raise ValueError("delay-ms must be 0..3000 and batch-size must be 1..100")
        raw = json.loads(args.spec.read_text(encoding="utf-8"))
        entities, layers, insunits = validate_spec(raw)
        source, expected = compile_lisp(entities, layers, insunits,
                                        delay_ms=args.delay_ms, batch_size=args.batch_size)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("x", encoding="utf-8", newline="\n") as output:
            output.write(source)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"CADREDRAW compile FAILED: {exc}", file=sys.stderr)
        return 2
    counts = Counter(e["type"] for e in entities)
    print(f"Generated {args.out}: {len(entities)} source entries -> {expected} native model-space objects; units={insunits}; types={dict(counts)}")
    print("Next terminal step: python3 scripts/deploy_autocad_bundle.py --lsp " +
          shlex.quote(str(args.out)))
    print("Offline compile only. Native bundle/CADLIVE and source-image QA remain unverified. Saving is intentionally not requested by this compile step.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
