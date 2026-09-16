#!/usr/bin/env python3
"""Deploy one generated CADLIVE LSP as a per-document AutoCAD for Mac bundle.

The bundle removes the need to type a long AutoLISP expression or use APPLOAD.
After a one-time AutoCAD restart, replace the bundled LSP before opening a new
blank drawing, then enter the short command CADLIVE.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import tempfile


BUNDLE_NAME = "AutoCADMacLiveRedraw.bundle"
PRODUCT_CODE = "{A8F2BE99-8B9D-4F56-8A46-41D1B4553190}"
PACKAGE_XML = f"""<?xml version="1.0" encoding="utf-8"?>
<ApplicationPackage SchemaVersion="1.0" AppVersion="1.0.0"
  ProductCode="{PRODUCT_CODE}"
  Name="AutoCAD Mac Live Redraw"
  Description="Loads the current CADLIVE redraw script in each AutoCAD document."
  Author="fxyadela">
  <CompanyDetails Name="fxyadela" />
  <Components>
    <ComponentEntry
      AppName="AutoCADMacLiveRedraw"
      AppDescription="Current native live-redraw commands"
      ModuleName="./Contents/cadlive-current.lsp"
      AppType="Lisp"
      PerDocument="True" />
  </Components>
</ApplicationPackage>
"""


def default_bundle_dir() -> Path:
    return (Path.home() / "Library" / "Application Support" / "Autodesk" /
            "ApplicationAddins" / BUNDLE_NAME)


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def deploy_bundle(source: Path, bundle_dir: Path) -> Path:
    if not source.is_absolute() or source.suffix.lower() != ".lsp":
        raise ValueError("lsp must be an absolute .lsp path")
    if not source.is_file():
        raise ValueError(f"lsp does not exist: {source}")
    if not bundle_dir.is_absolute() or bundle_dir.name != BUNDLE_NAME:
        raise ValueError(f"bundle-dir must be an absolute path ending in {BUNDLE_NAME}")
    if bundle_dir.is_symlink():
        raise ValueError("bundle-dir must not be a symlink")

    data = source.read_bytes()
    if not data or len(data) > 20 * 1024 * 1024:
        raise ValueError("lsp must be nonempty and no larger than 20 MiB")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("lsp must be UTF-8") from exc
    for required in ("(defun C:CADLIVE", "(defun C:CADFAST"):
        if required not in text:
            raise ValueError(f"lsp is not a generated live-redraw file: missing {required}")

    package = bundle_dir / "PackageContents.xml"
    if package.exists() and PRODUCT_CODE not in package.read_text(encoding="utf-8"):
        raise ValueError(f"refusing to modify an unrelated bundle: {bundle_dir}")

    target = bundle_dir / "Contents" / "cadlive-current.lsp"
    atomic_write(target, data)
    # Publish metadata last so a running AutoCAD never observes a half-built bundle.
    atomic_write(package, PACKAGE_XML.encode("utf-8"))
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lsp", required=True, type=Path,
                        help="Absolute path to a generated CADLIVE .lsp")
    parser.add_argument("--bundle-dir", type=Path, default=default_bundle_dir(),
                        help="Testing override; normally leave at the per-user Mac default")
    args = parser.parse_args(argv)
    try:
        target = deploy_bundle(args.lsp, args.bundle_dir)
    except (OSError, ValueError) as exc:
        print(f"CADREDRAW bundle deploy FAILED: {exc}")
        return 2
    print(f"Deployed current redraw: {target}")
    print("First install: restart AutoCAD once. Each run: create a NEW blank drawing, then type CADLIVE.")
    print("Do NOT open APPLOAD or inspect its loaded-applications list; stop if CADLIVE is unknown.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
