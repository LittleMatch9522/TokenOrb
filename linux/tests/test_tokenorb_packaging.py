import configparser
import unittest
from pathlib import Path


LINUX_ROOT = Path(__file__).parents[1]
PACKAGING_ROOT = LINUX_ROOT / "packaging"
DESKTOP_FILE = LINUX_ROOT / "TokenOrb.desktop"
WORKFLOW_FILE = LINUX_ROOT.parent / ".github" / "workflows" / "linux-packages.yml"
RELEASE_WORKFLOW_FILE = LINUX_ROOT.parent / ".github" / "workflows" / "release.yml"


class TokenOrbPackagingTests(unittest.TestCase):
    def test_desktop_entry_uses_installable_launcher_and_icon_names(self):
        parser = configparser.ConfigParser(interpolation=None, strict=False)
        parser.read(DESKTOP_FILE, encoding="utf-8")
        entry = parser["Desktop Entry"]

        self.assertEqual(entry["Exec"], "tokenorb")
        self.assertEqual(entry["TryExec"], "tokenorb")
        self.assertEqual(entry["Icon"], "tokenorb")
        self.assertEqual(entry["StartupWMClass"], "TokenOrb")
        self.assertNotIn("/home/", entry.get("Exec", ""))
        self.assertNotIn("/home/", entry.get("Icon", ""))

    def test_packaging_contract_files_exist(self):
        expected = {
            "TokenOrb.desktop",
            "TokenOrb.spec",
            "INSTALL.md",
            "debian/control.in",
            "tokenorb-launcher",
            "tokenorb-user-launcher.in",
            "tokenorb-appimage-launcher",
            "tokenorb-appimage-run",
            "tokenorb.spec.in",
            "build_deb.sh",
            "build_rpm.sh",
            "build_appimage.sh",
            "build_linux.sh",
        }
        actual = {
            path.relative_to(PACKAGING_ROOT).as_posix()
            for path in PACKAGING_ROOT.rglob("*")
            if path.is_file()
        }
        self.assertTrue(expected <= actual, sorted(expected - actual))

    def test_builders_declare_expected_artifact_names_and_dependencies(self):
        deb_builder = (PACKAGING_ROOT / "build_deb.sh").read_text(encoding="utf-8")
        rpm_builder = (PACKAGING_ROOT / "build_rpm.sh").read_text(encoding="utf-8")
        appimage_builder = (PACKAGING_ROOT / "build_appimage.sh").read_text(encoding="utf-8")
        linux_builder = (PACKAGING_ROOT / "build_linux.sh").read_text(encoding="utf-8")
        deb_control = (PACKAGING_ROOT / "debian/control.in").read_text(encoding="utf-8")
        rpm_spec = (PACKAGING_ROOT / "tokenorb.spec.in").read_text(encoding="utf-8")

        self.assertIn("TokenOrb-Linux-x86_64.deb", deb_builder)
        self.assertIn("TokenOrb-Linux-x86_64.rpm", rpm_builder)
        self.assertIn("TokenOrb-Linux-x86_64.AppImage", appimage_builder)
        self.assertIn('"$app_dir/TokenOrb.desktop"', appimage_builder)
        self.assertIn('"$app_dir/tokenorb.svg"', appimage_builder)
        self.assertIn("python3-pyqt5", deb_control)
        self.assertIn("python3-qt5", rpm_spec)
        self.assertIn("/usr/lib/tokenorb", rpm_spec)
        install_script = (LINUX_ROOT / "install_linux.sh").read_text(encoding="utf-8")
        self.assertIn("tokenorb-user-launcher.in", install_script)
        self.assertIn('cd "$OUTPUT_DIR"', linux_builder)
        self.assertIn("sha256sum \\", linux_builder)
        self.assertIn("TokenOrb-Linux-x86_64.deb", linux_builder)

    def test_public_packaging_files_use_codex_text(self):
        desktop = DESKTOP_FILE.read_text(encoding="utf-8").lower()
        install = (PACKAGING_ROOT / "INSTALL.md").read_text(encoding="utf-8").lower()
        deb_control = (PACKAGING_ROOT / "debian/control.in").read_text(encoding="utf-8").lower()
        rpm_spec = (PACKAGING_ROOT / "tokenorb.spec.in").read_text(encoding="utf-8").lower()

        self.assertIn("codex", desktop)
        self.assertIn("codex", install)
        self.assertIn("codex", deb_control)
        self.assertIn("codex", rpm_spec)

    def test_linux_workflow_builds_all_public_artifacts(self):
        workflow = WORKFLOW_FILE.read_text(encoding="utf-8")
        self.assertIn("build-deb", workflow)
        self.assertIn("build-rpm", workflow)
        self.assertIn("build-appimage", workflow)
        self.assertIn("TokenOrb-Linux-x86_64.deb", workflow)
        self.assertIn("TokenOrb-Linux-x86_64.rpm", workflow)
        self.assertIn("TokenOrb-Linux-x86_64.AppImage", workflow)

    def test_release_workflow_publishes_linux_artifacts(self):
        workflow = RELEASE_WORKFLOW_FILE.read_text(encoding="utf-8")
        for job in ("build-linux-deb", "build-linux-rpm", "build-linux-appimage"):
            self.assertIn(job, workflow)
        for artifact in (
            "TokenOrb-Linux-x86_64.deb",
            "TokenOrb-Linux-x86_64.rpm",
            "TokenOrb-Linux-x86_64.AppImage",
            "TokenOrb-Linux-x86_64.sha256",
        ):
            self.assertIn(artifact, workflow)

    def test_appimage_spec_keeps_qt_collection_minimal(self):
        spec = (PACKAGING_ROOT / "TokenOrb.spec").read_text(encoding="utf-8")
        self.assertNotIn("collect_submodules", spec)
        self.assertIn('"PyQt5.sip"', spec)

    def test_user_visible_linux_messages_use_codex_text(self):
        app_text = (LINUX_ROOT / "tokenorb_app.py").read_text(encoding="utf-8").lower()
        core_text = (LINUX_ROOT / "tokenorb_core.py").read_text(encoding="utf-8").lower()

        self.assertIn("codex 额度", app_text)
        self.assertIn("codex 剩余额度", app_text)
        self.assertIn("codex 刷新", core_text)
        self.assertIn("codex 实时", core_text)


if __name__ == "__main__":
    unittest.main()
