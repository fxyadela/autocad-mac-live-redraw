"""Offline tests for the AutoCAD for Mac bundle deployer."""

from __future__ import annotations

import importlib.util
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET


SCRIPT = Path(__file__).with_name("deploy_autocad_bundle.py")
module_spec = importlib.util.spec_from_file_location("cad_bundle_deploy", SCRIPT)
assert module_spec and module_spec.loader
deployer = importlib.util.module_from_spec(module_spec)
module_spec.loader.exec_module(deployer)


def generated_lsp(marker: str = "one") -> bytes:
    return (f"; {marker}\n"
            "(defun C:K () (princ))\n"
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

            root_xml = ET.fromstring(package.read_text(encoding="utf-8"))
            commands = {
                command.attrib["Global"]: command.attrib["Local"]
                for command in root_xml.findall(".//Command")
            }
            self.assertEqual(commands, {
                "K": "K", "CADLIVE": "CADLIVE", "CADFAST": "CADFAST"
            })
            self.assertEqual(root_xml.attrib["AppVersion"], deployer.PACKAGE_VERSION)

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

    def test_main_reports_install_upgrade_and_update_without_restart(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cad-bundle-test-") as folder:
            root = Path(folder)
            source = root / "source.lsp"
            bundle = root / deployer.BUNDLE_NAME
            source.write_bytes(generated_lsp())

            output = StringIO()
            with redirect_stdout(output):
                self.assertEqual(
                    deployer.main(["--lsp", str(source), "--bundle-dir", str(bundle)]),
                    0,
                )
            self.assertIn("BUNDLE_INSTALLED", output.getvalue())
            self.assertIn("_APPAUTOLOADER", output.getvalue())
            self.assertNotIn("restart AutoCAD once", output.getvalue())

            output = StringIO()
            with redirect_stdout(output):
                self.assertEqual(
                    deployer.main(["--lsp", str(source), "--bundle-dir", str(bundle)]),
                    0,
                )
            self.assertIn("BUNDLE_UPDATED", output.getvalue())
            self.assertIn("Do not quit or restart AutoCAD", output.getvalue())

            legacy = deployer.PACKAGE_XML.replace(
                f'AppVersion="{deployer.PACKAGE_VERSION}"', 'AppVersion="1.0.0"'
            ).replace("      <Commands", "      <!-- old manifest -->\n      <Commands")
            (bundle / "PackageContents.xml").write_text(legacy, encoding="utf-8")
            output = StringIO()
            with redirect_stdout(output):
                self.assertEqual(
                    deployer.main(["--lsp", str(source), "--bundle-dir", str(bundle)]),
                    0,
                )
            self.assertIn("BUNDLE_UPGRADED", output.getvalue())
            self.assertIn("_APPAUTOLOADER", output.getvalue())


if __name__ == "__main__":
    unittest.main()
