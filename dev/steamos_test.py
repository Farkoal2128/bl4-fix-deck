"""Offline SteamOS regression checks: python dev/steamos_test.py."""

from __future__ import annotations

import importlib.util
import json
import os
import stat
import sys
import tempfile
import types
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO / "installer"), str(REPO / "tools"), str(REPO / "mods/bl4_mod_menu")]

import build
import catalog
import manual_zip
import steamos
import updates
import repos
import undo


class SteamOSTest(unittest.TestCase):
    def setUp(self):
        scratch = REPO / "build"
        scratch.mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.game = self.root / "SD Card/steamapps/common/Borderlands 4"
        self.put(self.game / steamos.GAME_EXE, b"game")
        self.archive = self.root / "payload.zip"
        self.files = {"OakGame/Binaries/Win64/dsound.dll": b"sdk",
                      **{f"sdk_mods/{m.id}.sdkmod": m.id.encode() for m in catalog.MODS},
                      "OakGame/Content/uiresources/bl4link/boot.js": b"boot"}
        self.closed = patch.object(steamos, "ensure_closed")
        self.closed.start()
        self.addCleanup(self.closed.stop)

    def put(self, path, content):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    def payload(self, extra=None):
        with zipfile.ZipFile(self.archive, "w") as zf:
            for name, data in (self.files | (extra or {})).items():
                info = zipfile.ZipInfo(name)
                info.filename = name  # preserve hostile backslashes on Windows too
                zf.writestr(info, data)
        return self.archive

    def test_discovery_sd_flatpak_and_dedup(self):
        home = self.root / "home"
        steam = home / ".local/share/Steam"
        flatpak = home / ".var/app/com.valvesoftware.Steam/.local/share/Steam"
        library = self.game.parents[2]
        for root in (steam, flatpak):
            self.put(root / "steamapps/libraryfolders.vdf",
                     f'"libraryfolders" {{ "0" {{ "path" "{library.as_posix()}" }} }}'.encode())
        self.put(library / f"steamapps/appmanifest_{steamos.APP_ID}.acf",
                 b'"AppState" { "installdir" "Borderlands 4" }')
        self.assertEqual(steamos.find_games(home), [self.game.resolve()])

    def test_install_backup_settings_and_idempotence(self):
        loader = self.game / "OakGame/Binaries/Win64/dsound.dll"
        self.put(loader, b"old loader")
        settings = self.game / "sdk_mods/settings/bl4_minimap.json"
        self.put(settings, b'{"enabled": false}')
        backup = steamos.install(self.game, self.payload())
        self.assertEqual(loader.read_bytes(), b"sdk")
        self.assertEqual((backup / loader.relative_to(self.game)).read_bytes(), b"old loader")
        self.assertEqual(settings.read_bytes(), b'{"enabled": false}')
        again = steamos.install(self.game, self.archive)
        self.assertNotEqual(backup, again)
        self.assertEqual((again / "installed-files.txt").read_text().strip(), "")

    def test_selected_mods_repair_and_removal_preserve_user_data(self):
        self.files["OakGame/Content/uiresources/bl4weapondex/items/test.png"] = b"picture"
        self.put(self.game / "sdk_mods/another_mod.sdkmod", b"third party")
        save = self.game / "sdk_mods/settings/my-save.sav"
        self.put(save, b"user data")
        payload = self.payload()
        steamos.install(self.game, payload, {"bl4_minimap"}, log=lambda _: None)
        self.assertEqual(steamos.installed_mods(self.game), set(catalog.REQUIRED) | {"bl4_minimap"})
        self.assertFalse((self.game / "OakGame/Content/uiresources/bl4weapondex/items/test.png").exists())
        minimap = self.game / "sdk_mods/bl4_minimap.sdkmod"
        minimap.write_bytes(b"damaged")
        steamos.install(self.game, payload, {"bl4_minimap"}, log=lambda _: None)
        self.assertEqual(minimap.read_bytes(), b"bl4_minimap")
        steamos.install(self.game, payload, set(), log=lambda _: None)
        self.assertFalse(minimap.exists())
        self.assertEqual(save.read_bytes(), b"user data")
        self.assertEqual((self.game / "sdk_mods/another_mod.sdkmod").read_bytes(), b"third party")

    def test_uninstall_restores_movies_and_original_loader(self):
        loader = self.game / "OakGame/Binaries/Win64/dsound.dll"
        self.put(loader, b"previous loader")
        self.put(self.game / "OakGame/Content/Movies/2KLOGO.bk2", b"movie")
        self.put(self.game / "sdk_mods/other.sdkmod", b"third party")
        payload = self.payload()
        steamos.install(self.game, payload, {"bl4_skip_intro"}, log=lambda _: None)
        self.assertFalse((self.game / "OakGame/Content/Movies/2KLOGO.bk2").exists())
        steamos.install(self.game, payload, {"bl4_skip_intro"}, log=lambda _: None)
        steamos.uninstall(self.game, remove_sdk=True, log=lambda _: None)
        self.assertEqual(loader.read_bytes(), b"previous loader")
        self.assertEqual((self.game / "OakGame/Content/Movies/2KLOGO.bk2").read_bytes(), b"movie")
        self.assertFalse(steamos.installed_mods(self.game))
        self.assertTrue((self.game / "sdk_mods/settings/bl4_skip_intro.json").is_file())
        self.assertEqual((self.game / "sdk_mods/other.sdkmod").read_bytes(), b"third party")

    def test_uninstall_can_keep_sdk_and_refuses_changed_sdk(self):
        steamos.install(self.game, self.payload(), set(), log=lambda _: None)
        loader = self.game / "OakGame/Binaries/Win64/dsound.dll"
        loader.write_bytes(b"another loader")
        with self.assertRaisesRegex(ValueError, "changed by another"):
            steamos.uninstall(self.game, remove_sdk=True, log=lambda _: None)
        steamos.uninstall(self.game, log=lambda _: None)
        self.assertEqual(loader.read_bytes(), b"another loader")
        self.assertFalse(steamos.installed_mods(self.game))

    def test_required_mods_stay_enabled_without_losing_settings(self):
        settings = self.game / "sdk_mods/settings/bl4_direct.json"
        self.put(settings, b'{"enabled":false,"custom":42}')
        steamos.install(self.game, self.payload(), set(), log=lambda _: None)
        self.assertEqual(json.loads(settings.read_text()), {"enabled": True, "custom": 42})

    def test_paths_refused_before_writes(self):
        for name in ("../outside", "/absolute", "C:/outside", "sdk_mods/../bad",
                     "sdk_mods\\bad", "sdk_mods/settings/mine.json", "OakGame/1.sav",
                     "sdk_mods/./bad", "other/file", "sdk_mods/BL4_MOD_MENU.sdkmod"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                steamos.install(self.game, self.payload({name: b"bad"}))
        self.assertFalse((self.game / "sdk_mods/bl4_mod_menu.sdkmod").exists())
        self.assertFalse(list(self.game.glob("bl4fix-backup-*")))

    def test_incomplete_and_loose_mod_refused(self):
        self.files.pop("OakGame/Binaries/Win64/dsound.dll")
        with self.assertRaises(ValueError):
            steamos.install(self.game, self.payload())
        self.files["OakGame/Binaries/Win64/dsound.dll"] = b"sdk"
        (self.game / "sdk_mods/bl4_mod_menu").mkdir(parents=True)
        with self.assertRaisesRegex(ValueError, "loose mod"):
            steamos.install(self.game, self.payload())

    def test_archive_symlink_refused(self):
        self.payload()
        with zipfile.ZipFile(self.archive, "a") as zf:
            info = zipfile.ZipInfo("sdk_mods/link")
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            zf.writestr(info, "../../outside")
        with self.assertRaises(ValueError):
            steamos.install(self.game, self.archive)

    @unittest.skipIf(os.name == "nt", "Unix target symlinks checked on Linux CI")
    def test_existing_symlink_refused(self):
        outside = self.root / "outside"
        outside.mkdir()
        (self.game / "sdk_mods").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(ValueError):
            steamos.install(self.game, self.payload())
        self.assertEqual(list(outside.iterdir()), [])

    def test_failed_install_rolls_back(self):
        loader = self.game / "OakGame/Binaries/Win64/dsound.dll"
        self.put(loader, b"original")
        read = zipfile.ZipFile.read

        def fail(zf, member, *args, **kwargs):
            if member.filename.endswith(".sdkmod"):
                raise OSError("simulated read failure")
            return read(zf, member, *args, **kwargs)

        with patch.object(zipfile.ZipFile, "read", fail), self.assertRaises(OSError):
            steamos.install(self.game, self.payload())
        self.assertEqual(loader.read_bytes(), b"original")
        self.assertFalse((self.game / "sdk_mods/bl4_mod_menu.sdkmod").exists())

    def test_failed_file_replacement_rolls_back_prior_writes(self):
        loader = self.game / "OakGame/Binaries/Win64/dsound.dll"
        self.put(loader, b"original loader")
        replace = Path.replace
        def fail(source, target):
            if str(target).endswith("bl4_mod_menu.sdkmod"):
                raise OSError("simulated disk write failure")
            return replace(source, target)
        with patch.object(Path, "replace", fail), self.assertRaises(OSError):
            steamos.install(self.game, self.payload(), set(), log=lambda _: None)
        self.assertEqual(loader.read_bytes(), b"original loader")
        self.assertFalse((self.game / "sdk_mods/bl4_direct.sdkmod").exists())
        self.assertFalse((self.game / steamos.RECORD).exists())

    def test_process_detection_and_unavailable_proc(self):
        self.closed.stop()
        proc = self.root / "proc"
        self.put(proc / "123/comm", b"Borderlands4.ex")
        self.put(proc / "123/cmdline", b"Z:\\games\\Borderlands4.exe\0")
        with self.assertRaisesRegex(RuntimeError, "Close Borderlands"):
            steamos.ensure_closed(proc)
        self.put(proc / "123/comm", b"steam")
        self.put(proc / "123/cmdline", b"/usr/bin/steam\0")
        steamos.ensure_closed(proc)
        with self.assertRaises(RuntimeError):
            steamos.ensure_closed(self.root / "missing")

    def test_finish_replaces_and_removes_only_ui_link(self):
        target = self.game / "OakGame/Content/Paks/~mods/BL4Fix_UILink_4251_P.pak"
        self.put(target, b"old")
        self.put(target.with_name(target.name + ".next"), b"new")
        backup = steamos.finish(self.game)
        self.assertEqual((backup / target.name).read_bytes(), b"old")
        self.assertEqual(target.read_bytes(), b"new")
        self.put(target.with_name(target.name + ".remove"), b"")
        steamos.finish(self.game)
        self.assertFalse(target.exists())
        self.assertIsNone(steamos.finish(self.game))

    def test_portable_pages_from_real_catalog(self):
        mods = self.root / "mods"
        mods.mkdir()
        for info in catalog.MODS:
            build.build_sdkmod(REPO / info.source / info.id, mods / f"{info.id}.sdkmod",
                               catalog.license_files(info, REPO))
        files = manual_zip.page_files(mods)
        self.assertIn(f"OakGame/Content/Paks/~mods/{catalog.LINK_PAK}", files)
        self.assertIn("OakGame/Content/uiresources/bl4link/boot.js", files)
        self.assertIn("OakGame/Content/uiresources/bl4modmenu/menu.js", files)
        self.assertEqual(files, manual_zip.page_files(mods))
        self.assertFalse(any(n.startswith("_bl4setup_") for n in sys.modules))

    def test_steamos_updates_never_download_or_spawn(self):
        with patch.dict(os.environ, {"BL4FIX_STEAMOS": "1"}), \
                patch.object(updates, "fetch_manifest", side_effect=AssertionError("network")), \
                patch("subprocess.Popen", side_effect=AssertionError("process")):
            updates.check(self.game)
            self.assertEqual(updates.U.status, "off")
            self.assertFalse(updates.can_restart(self.game))
            self.assertFalse(updates.start_helper(self.game))
            with self.assertRaisesRegex(RuntimeError, "SteamOS"):
                updates.apply(self.game)

    def test_restore_refuses_before_creating_plan(self):
        alias = "_steamos_backup_test"
        parent = types.ModuleType(alias)
        parent.__path__ = [str(REPO / "mods/bl4_save_backup")]
        sys.modules[alias] = parent
        # Crypto and save discovery run inside Proton; this tests the restore boundary only.
        for name in ("savefile", "store"):
            sys.modules[f"{alias}.{name}"] = types.ModuleType(f"{alias}.{name}")
        try:
            import importlib
            restore = importlib.import_module(f"{alias}.restore")
            with patch.dict(os.environ, {"BL4FIX_STEAMOS": "1"}):
                with self.assertRaisesRegex(restore.RestoreError, "SteamOS"):
                    restore._add(None, [], None)
                self.assertFalse(restore.start_helper(self.root))
        finally:
            for name in list(sys.modules):
                if name == alias or name.startswith(alias + "."):
                    del sys.modules[name]

    def test_repository_mutations_refuse_before_file_or_network_work(self):
        with patch.dict(os.environ, {"BL4FIX_STEAMOS": "1"}), \
                patch.object(repos, "_say"), \
                patch.object(repos, "_find", side_effect=AssertionError("repository lookup")):
            self.assertFalse(repos.install_async("example"))
            self.assertEqual(repos.update_async(["example"]), 0)
            with self.assertRaisesRegex(RuntimeError, "SteamOS"):
                repos.remove_mod("example")
            with self.assertRaisesRegex(RuntimeError, "SteamOS"):
                undo.roll_back(self.game, "example")

    def test_steamos_firewall_never_runs_windows_tools(self):
        spec = importlib.util.spec_from_file_location("_steamos_shared", REPO / "mods/bl4_direct/shared.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        try:
            spec.loader.exec_module(module)
            with patch.dict(os.environ, {"BL4FIX_STEAMOS": "1"}), \
                    patch("subprocess.run", side_effect=AssertionError("Windows firewall")):
                self.assertEqual(module.find_rules(), [])
        finally:
            del sys.modules[spec.name]


if __name__ == "__main__":
    unittest.main(verbosity=2)
