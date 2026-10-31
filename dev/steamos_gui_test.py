"""Setup window checks; run under xvfb-run on Linux CI, or directly on Windows."""

from __future__ import annotations

import sys
import tempfile
import time
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "installer"))

import catalog
import steamos
import steamos_gui as gui


class WindowTest(unittest.TestCase):
    def setUp(self):
        (REPO / "build").mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=REPO / "build")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.game = self.root / "Borderlands 4"
        exe = self.game / steamos.GAME_EXE
        exe.parent.mkdir(parents=True)
        exe.write_bytes(b"fixture only")
        self.archive = self.root / "payload.zip"
        with zipfile.ZipFile(self.archive, "w") as zf:
            zf.writestr("OakGame/Binaries/Win64/dsound.dll", b"sdk")
            for mod in catalog.MODS:
                zf.writestr(f"sdk_mods/{mod.id}.sdkmod", mod.id.encode())
        with patch.object(steamos, "find_games", return_value=[]):
            self.app = gui.App(self.archive, self.game)
        self.app.withdraw()
        self.addCleanup(self.app.destroy)
        self.app.update()

    def wait_for_task(self):
        deadline = time.monotonic() + 10
        while self.app.busy and time.monotonic() < deadline:
            self.app.update()
            time.sleep(0.01)
        self.assertFalse(self.app.busy, "setup worker did not return")

    def test_window_fits_deck_and_required_mods_cannot_be_unchecked(self):
        self.assertEqual(self.app.minsize(), (900, 610))
        self.app.select(set())
        self.assertEqual({m for m, var in self.app.mods.items() if var.get()}, set(catalog.REQUIRED))
        self.assertIn("SteamOS", self.app.title())

    def test_apply_uses_real_backend_and_refreshes_mod_selection(self):
        self.app.select({"bl4_minimap"})
        with patch.object(steamos, "ensure_closed"), patch.object(gui.messagebox, "showerror") as errors:
            self.app.apply()
            self.wait_for_task()
        errors.assert_not_called()
        self.assertEqual(steamos.installed_mods(self.game), set(catalog.REQUIRED) | {"bl4_minimap"})
        self.assertIn("Installed. Backup:", self.app.status.get())
        self.assertFalse(self.app.folder.instate(["disabled"]))

    def test_uninstall_can_cancel_and_runs_with_sdk_choice(self):
        with patch.object(gui.messagebox, "askyesno", return_value=False), patch.object(steamos, "uninstall") as remove:
            self.app.uninstall()
            remove.assert_not_called()
        self.app.remove_sdk.set(True)
        with patch.object(gui.messagebox, "askyesno", return_value=True), \
                patch.object(steamos, "uninstall", return_value=self.root) as remove:
            self.app.uninstall()
            self.wait_for_task()
            self.assertEqual(remove.call_args.args[:2], (self.game.resolve(), True))

    def test_worker_error_reenables_controls(self):
        with patch.object(gui.messagebox, "showerror") as errors:
            def failure():
                raise RuntimeError("test failure")
            self.app.task("Testing", failure)
            self.wait_for_task()
            errors.assert_called_once()
        self.assertEqual(self.app.status.get(), "test failure")
        self.assertFalse(self.app.folder.instate(["disabled"]))

    def test_friend_and_port_edits_use_shared_config(self):
        with patch.object(steamos, "ensure_closed"), patch.object(gui.messagebox, "showerror") as errors:
            self.app.friend_name.set("Deck friend")
            self.app.friend_ip.set("192.168.1.5")
            self.app.add_friend()
            self.app.host_port.set("7788")
            self.app.save_port()
            errors.assert_not_called()
            path = self.game / "sdk_mods/settings" / gui.shared.FRIENDS_FILE_NAME
            config = gui.shared.Config.load(path)
            self.assertEqual((config.friends[0].address, config.host_port), ("192.168.1.5", 7788))
            self.app.friend_ip.set("not an IP")
            self.app.add_friend()
            errors.assert_called_once()
            self.assertEqual(len(gui.shared.Config.load(path).friends), 1)

    def test_copy_launch_options(self):
        self.app.copy_options()
        self.app.update()
        self.assertEqual(self.app.clipboard_get(), steamos.LAUNCH_OPTIONS)

    def test_shortcut_copies_executable_and_quotes_home(self):
        source = self.root / "fixture-binary"
        source.write_bytes(b"fixture only; never executed")
        home = self.root / "home with spaces %"
        path = gui.add_shortcut(home, source)
        self.assertIn('Exec="', path.read_text())
        self.assertIn("%%", path.read_text())
        self.assertEqual((home / ".local/share/bl4fix/BL4FixSetup-SteamOS").read_bytes(), source.read_bytes())


if __name__ == "__main__":
    unittest.main(verbosity=2)
