"""Offline tests for the AutoCAD for Mac bundle deployer."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest


SCRIPT = Path(__file__).with_name("deploy_autocad_bundle.py")
module_spec = importlib.util.spec_from_file_location("cad_bundle_deploy", SCRIPT)
assert module_spec and module_spec.loader
deployer = importlib.util.module_from_spec(module_spec)
module_spec.loader.exec_module(deployer)


def generated_lsp(marker: str = "one") -> bytes:
    return (f"; {marker}\n"
            "(defun C:CADLIVE () (princ))\n"
            "(defun C:CADFAST () (princ))\n").encode("utf-8")


class BundleDeployTest(unittest.TestCase):
    def test_deploy_and_update_owned_bundle(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cad-bundle-test-") as folder:
            root = Path(folder)
            source = root / "source.lsp"
            bundle = root / deployer.BUNDLE_NAME
            source.write_bytes(generated_lsp())
            target = deployer.deploy_bundle(source, bundle)
            self.assertEqual(target.read_bytes(), generated_lsp())
            package = bundle / "PackageContents.xml"
            self.assertIn(deployer.PRODUCT_CODE, package.read_text(encoding="utf-8"))
            self.assertIn('PerDocument="True"', package.read_text(encoding="utf-8"))

            source.write_bytes(generated_lsp("two"))
            self.assertEqual(deployer.deploy_bundle(source, bundle).read_bytes(),
                             generated_lsp("two"))

    def test_rejects_unrelated_or_invalid_input(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cad-bundle-test-") as folder:
            root = Path(folder)
            source = root / "source.lsp"
            source.write_text("(princ)\n", encoding="utf-8")
            bundle = root / deployer.BUNDLE_NAME
            with self.assertRaisesRegex(ValueError, "missing"):
                deployer.deploy_bundle(source, bundle)

            source.write_bytes(generated_lsp())
            bundle.mkdir()
            (bundle / "PackageContents.xml").write_text("unrelated", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "unrelated bundle"):
                deployer.deploy_bundle(source, bundle)


if __name__ == "__main__":
    unittest.main()
