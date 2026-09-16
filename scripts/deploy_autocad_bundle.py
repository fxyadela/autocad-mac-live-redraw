#!/usr/bin/env python3
"""Deploy one generated live-redraw LSP as an AutoCAD for Mac command bundle.

The bundle registers one-key K plus CADLIVE and CADFAST with AutoCAD's command
autoloader, so an agent affected by truncated text entry never needs a long
command, AutoLISP expression, APPLOAD, or an in-task AutoCAD restart.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import tempfile


BUNDLE_NAME = "AutoCADMacLiveRedraw.bundle"
PRODUCT_CODE = "{A8F2BE99-8B9D-4F56-8A46-41D1B4553190}"
PACKAGE_VERSION = "1.2.0"
PACKAGE_XML = f"""<?xml version="1.0" encoding="utf-8"?>
<ApplicationPackage SchemaVersion="1.0" AppVersion="{PACKAGE_VERSION}"
  ProductCode="{PRODUCT_CODE}"
  Name="AutoCAD Mac Live Redraw"
  Description="Loads the current native live-redraw script when K or CADLIVE is invoked."
  Author="fxyadela">
  <CompanyDetails Name="fxyadela" />
  <Components>
    <ComponentEntry
      AppName="AutoCADMacLiveRedraw"
      AppDescription="Current native live-redraw commands"
      ModuleName="./Contents/cadlive-current.lsp"
      AppType="Lisp"
      PerDocument="True">
      <Commands GroupName="AutoCADMacLiveRedrawCommands">
        <Command Global="K" Local="K" />
        <Command Global="CADLIVE" Local="CADLIVE" />
        <Command Global="CADFAST" Local="CADFAST" />
      </Commands>
    </ComponentEntry>
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


def deployment_mode(bundle_dir: Path) -> str:
    """Return installed, upgraded, or updated without changing the bundle."""
    if bundle_dir.is_symlink():
        raise ValueError("bundle-dir must not be a symlink")
    package = bundle_dir / "PackageContents.xml"
    if not package.is_file():
        return "installed"
    text = package.read_text(encoding="utf-8")
    if PRODUCT_CODE not in text:
        raise ValueError(f"refusing to modify an unrelated bundle: {bundle_dir}")
    return "updated" if text == PACKAGE_XML else "upgraded"


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
    for required in ("(defun C:K", "(defun C:CADLIVE", "(defun C:CADFAST"):
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
        mode = deployment_mode(args.bundle_dir)
        target = deploy_bundle(args.lsp, args.bundle_dir)
    except (OSError, ValueError) as exc:
        print(f"CADREDRAW bundle deploy FAILED: {exc}")
        return 2
    print(f"Deployed current redraw: {target}")
    if mode == "updated":
        print("BUNDLE_UPDATED: command manifest unchanged. Do not quit or restart AutoCAD.")
    else:
        print(f"BUNDLE_{mode.upper()}: command manifest changed.")
        print("If AutoCAD is already open, run _APPAUTOLOADER and choose _Reload once; do not quit or restart AutoCAD.")
        print("If AutoCAD is closed, its next normal launch will discover the bundle.")
    print("Create a NEW blank drawing, verify the command line is idle, then press K and Return once.")
    print("Do not type CADLIVE through unreliable long-text UI input; a lone C starts CIRCLE.")
    print("Never open APPLOAD, Help/F1, or a browser. If K is unknown, stop and report it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
