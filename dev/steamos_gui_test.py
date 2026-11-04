"""Setup window checks; run under xvfb-run on Linux CI, or directly on Windows."""

from __future__ import annotations

import sys
import tempfile
import threading
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
            for name in steamos.SDK_ANCHORS:
                zf.writestr(name, b"sdk fixture")
            for mod in catalog.MODS:
                zf.writestr(f"sdk_mods/{mod.id}.sdkmod", mod.id.encode())
            zf.writestr(steamos.PAK_ROOT + catalog.LINK_PAK, b"UI Link fixture")
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
        with patch.object(steamos, "ensure_closed"), patch.object(gui.messagebox, "showerror") as errors, \
                patch.object(self.app, "refresh", wraps=self.app.refresh) as refresh:
            self.app.apply()
            self.wait_for_task()
        errors.assert_not_called()
        refresh.assert_called_once()
        self.assertEqual(steamos.installed_mods(self.game), set(catalog.REQUIRED) | {"bl4_minimap"})
        self.assertIn("Files installed. Launch setup/SDK verification pending.", self.app.status.get())
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
        with patch.object(gui.messagebox, "showerror") as errors, \
                patch.object(self.app, "refresh", wraps=self.app.refresh) as refresh:
            def failure():
                raise RuntimeError("test failure")
            self.app.task("Testing", failure)
            self.wait_for_task()
            errors.assert_called_once()
        refresh.assert_called_once()
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

    def test_copy_empty_launch_options_matches_backend(self):
        self.app.copy_options()
        self.app.update()
        self.assertEqual(self.app.clipboard_get(), steamos.compose_launch_options(""))
        self.assertEqual(self.app.launch_composed.get(), self.app.clipboard_get())
        self.assertTrue(self.app.launch_preview.instate(["readonly"]))

    def test_launch_lsfg_and_valid_edit_refresh(self):
        for existing in ("LSFG_PROCESS=decky-lsfg-vk %command%", "~/lsfg %command% --long-option=value"):
            self.app.launch_original.set(existing)
            self.assertEqual(self.app.launch_composed.get(), "")
            self.app.copy_options()
            expected = steamos.compose_launch_options(existing)
            self.assertEqual(self.app.clipboard_get(), expected)
            self.assertEqual(self.app.launch_composed.get(), expected)
            self.assertIn(existing, expected)
        self.app.launch_original.set("%command% --edited")
        self.app.preview_options()
        self.assertIn("--edited", self.app.launch_composed.get())
        self.assertNotIn("--edited", self.app.clipboard_get())

    def test_launch_invalid_preserves_input_and_clipboard_clears_preview(self):
        self.app.copy_options()
        original_clipboard = self.app.clipboard_get()
        original = "%command% && do-not-execute"
        self.app.launch_original.set(original)
        self.assertEqual(self.app.launch_composed.get(), "")
        # Copy must recompute instead of trusting an old preview.
        self.app.launch_composed.set("stale preview")
        with patch.object(gui, "open_desktop", side_effect=AssertionError("launch")):
            self.app.copy_options()
        self.assertEqual(self.app.launch_composed.get(), "")
        self.assertEqual(self.app.launch_original.get(), original)
        self.assertEqual(self.app.clipboard_get(), original_clipboard)
        self.assertIn("manually", self.app.status.get())

    def test_launch_edit_keeps_active_task_status_and_clears_preview(self):
        release = threading.Event()
        self.addCleanup(release.set)
        self.app.task("Installing", lambda: release.wait(5))
        status = self.app.status.get()
        self.app.launch_original.set("~/lsfg %command%")
        self.assertTrue(self.app.busy)
        self.assertEqual(self.app.status.get(), status)
        self.assertIn("Keep this window open.", status)
        self.assertEqual(self.app.launch_composed.get(), "")
        release.set()
        self.wait_for_task()

    def test_health_separates_files_from_activation_without_logging_launch_text(self):
        launch = "LSFG_PROCESS=private-wrapper %command%"
        self.app.launch_original.set(launch)
        with patch.object(gui.messagebox, "showerror") as errors:
            self.app.health()
            self.wait_for_task()
        errors.assert_not_called()
        text = self.app.log_box.get("1.0", "end")
        self.assertIn("File status (not runtime activation):", text)
        self.assertIn("Missing: sdk_mods/__main__.py", text)
        self.assertIn("SDK runtime activation unverified.", text)
        self.assertNotIn(launch, text)

    def test_health_preserves_pending_selection_without_loading_settings_on_success_or_error(self):
        for invalid_archive in (False, True):
            with self.subTest(invalid_archive=invalid_archive):
                self.app.select({"bl4_minimap"})
                pending = {mod: value.get() for mod, value in self.app.mods.items()}
                if invalid_archive:
                    self.archive.write_bytes(b"not a ZIP archive")
                with patch.object(self.app, "current_game", side_effect=AssertionError("unsafe root probe")), \
                        patch.object(gui.shared.Config, "load", side_effect=AssertionError("settings read")) as settings, \
                        patch.object(gui.messagebox, "showerror") as errors:
                    self.app.health()
                    self.wait_for_task()
                settings.assert_not_called()
                self.assertEqual({mod: value.get() for mod, value in self.app.mods.items()}, pending)
                self.assertEqual(errors.call_count, int(invalid_archive))
                self.assertFalse(self.app.folder.instate(["disabled"]))
                self.assertTrue(all(not button.instate(["disabled"]) for button in self.app.buttons))
                if invalid_archive:
                    self.assertIn("Invalid payload archive", self.app.status.get())
                else:
                    self.assertEqual(self.app.status.get(), "Checking files complete.")

    def test_health_uses_backend_link_safe_validation(self):
        with patch.object(steamos, "safe_target", side_effect=ValueError("selected executable uses a link")) as safe, \
                patch.object(gui.shared.Config, "load", side_effect=AssertionError("settings read")) as settings, \
                patch.object(gui.messagebox, "showerror") as errors:
            self.app.health()
            self.wait_for_task()
        safe.assert_called_once_with(self.game.resolve(), steamos.GAME_EXE)
        settings.assert_not_called()
        errors.assert_called_once()
        self.assertEqual(self.app.status.get(), "selected executable uses a link")

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
