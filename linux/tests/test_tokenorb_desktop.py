import configparser
import unittest
from pathlib import Path


DESKTOP_FILE = Path(__file__).parents[1] / "TokenOrb.desktop"


class TokenOrbDesktopTests(unittest.TestCase):
    def test_linux_desktop_entry_declares_installable_icon_and_launcher(self):
        self.assertTrue(DESKTOP_FILE.is_file(), "Linux desktop entry has not been added")
        parser = configparser.ConfigParser(interpolation=None, strict=False)
        parser.read(DESKTOP_FILE, encoding="utf-8")
        entry = parser["Desktop Entry"]

        self.assertEqual(entry["Exec"], "tokenorb")
        self.assertEqual(entry["TryExec"], "tokenorb")
        self.assertEqual(entry["Icon"], "tokenorb")
        self.assertEqual(entry["StartupWMClass"], "TokenOrb")


if __name__ == "__main__":
    unittest.main()
