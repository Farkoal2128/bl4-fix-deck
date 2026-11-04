"""Offline SteamOS regression checks: python dev/steamos_test.py."""

from __future__ import annotations

import importlib.util
import io
import json
import os
import stat
import sys
import tempfile
import types
import unittest
import zipfile
from contextlib import redirect_stderr, redirect_stdout
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

    def health_payload(self):
        plugins = "OakGame/Binaries/Win64/Plugins/"
        self.files.update({
            **{plugins + name: name.encode() for name in (
                "unrealsdk.toml", "unrealsdk.dll", "pyunrealsdk.dll", "python3.dll",
                "python314.dll", "python314.zip", "python314._pth", "DLLs/_ssl.pyd",
            )},
            "sdk_mods/__main__.py": b"bootstrap",
            "sdk_mods/mods_base.sdkmod": b"base",
            "sdk_mods/console_mod_menu.sdkmod": b"console",
            "sdk_mods/keybinds/keybinds.pyd": b"keybinds",
            steamos.PAK_ROOT + catalog.LINK_PAK: b"UI Link",
            "BL4Fix-README.txt": b"instructions",
        })
        return self.payload()

    def assert_launch_options(self, existing, expected):
        result = steamos.compose_launch_options(existing)
        self.assertEqual(result, expected)
        self.assertEqual(steamos.compose_launch_options(result), result)

    def test_launch_empty_and_idempotent(self):
        self.payload()
        steam_config = self.root / "userdata/config/localconfig.vdf"
        self.put(steam_config, b"original launch options")
        before = {path: path.read_bytes() for path in self.root.rglob("*") if path.is_file()}
        with (patch("subprocess.Popen", side_effect=AssertionError("process")),
              patch("subprocess.run", side_effect=AssertionError("process")),
              patch("os.system", side_effect=AssertionError("shell"))):
            for existing in ("", "   ", "%command%", steamos.LAUNCH_OPTIONS):
                with self.subTest(existing=existing):
                    self.assert_launch_options(existing, steamos.LAUNCH_OPTIONS)
            with self.assertRaisesRegex(ValueError, "merge .* manually"):
                steamos.compose_launch_options("%command% && touch localconfig.vdf")
        self.assertEqual({path: path.read_bytes() for path in self.root.rglob("*") if path.is_file()}, before)

    def test_launch_lsfg_environment_and_wrapper(self):
        for prefix in ("LSFG_PROCESS=decky-lsfg-vk", "~/lsfg", '"/home/deck/LSFG wrapper" --verbose'):
            with self.subTest(prefix=prefix):
                self.assert_launch_options(
                    f"{prefix} %command%",
                    f'BL4FIX_STEAMOS=1 WINEDLLOVERRIDES="dsound=n,b" {prefix} %command% -pf_tricks=vcrun2022',
                )

    def test_launch_preserves_quotes_spacing_and_args(self):
        existing = """  EXTRA='spaces here'  BL4FIX_STEAMOS="0" ~/lsfg --path="A B"   %command%  '--label=C D'  """
        expected = ("""  WINEDLLOVERRIDES="dsound=n,b" EXTRA='spaces here'  BL4FIX_STEAMOS="1" """
                    """~/lsfg --path="A B"   %command%  '--label=C D' -pf_tricks=vcrun2022  """)
        self.assert_launch_options(existing, expected)
        existing = """  BL4FIX_STEAMOS='1' WINEDLLOVERRIDES=dsound=n,b %command%  "-pf_tricks=vcrun2022" --arg  """
        self.assert_launch_options(existing, existing)

    def test_launch_merges_dll_overrides(self):
        for original, merged in (
            ('"dxgi=n,b;dsound=b;version=n"', '"dxgi=n,b;dsound=n,b;version=n"'),
            ("dsound=b", "dsound=n,b"),
            ("dxgi=b", '"dxgi=b;dsound=n,b"'),
            ("'dxgi,d3d11=b;version='", "'dxgi,d3d11=b;version=;dsound=n,b'"),
            ("'dxgi=n; DSound.DLL = b,n;version=n'", "'dxgi=n; DSound.DLL =n,b;version=n'"),
            ('"DSOUND=NATIVE, BUILTIN;dxgi=n"', '"DSOUND=NATIVE, BUILTIN;dxgi=n"'),
            ('""', '"dsound=n,b"'),
        ):
            with self.subTest(original=original):
                self.assert_launch_options(
                    f"WINEDLLOVERRIDES={original} %command%",
                    f"BL4FIX_STEAMOS=1 WINEDLLOVERRIDES={merged} %command% -pf_tricks=vcrun2022",
                )

    def test_launch_owned_conflicts(self):
        for existing, item in (
            ("BL4FIX_STEAMOS=bad %command%", "BL4FIX_STEAMOS"),
            ("BL4FIX_STEAMOS= %command%", "BL4FIX_STEAMOS"),
            ("BL4FIX_STEAMOS+=0 %command%", "Unsupported append assignment to BL4FIX_STEAMOS"),
            ('WINEDLLOVERRIDES+="dxgi=n" %command%', "Unsupported append assignment to WINEDLLOVERRIDES"),
            ("~/lsfg BL4FIX_STEAMOS+=0 %command%", "Unsupported append assignment to BL4FIX_STEAMOS"),
            ("BL4FIX_STEAMOS=1 BL4FIX_STEAMOS=1 %command%", "Repeated BL4FIX_STEAMOS"),
            ("~/lsfg BL4FIX_STEAMOS=0 %command%", "BL4FIX_STEAMOS must be a leading"),
            ('"BL4FIX_STEAMOS=1" %command%', "BL4FIX_STEAMOS must be a leading"),
            ("%command% WINEDLLOVERRIDES=dxgi=n", "WINEDLLOVERRIDES must be a leading"),
            ("WINEDLLOVERRIDES=dxgi=n WINEDLLOVERRIDES=dsound=n,b %command%", "Repeated WINEDLLOVERRIDES"),
            ('WINEDLLOVERRIDES="dxgi,DSOUND.dll=b" %command%', "Grouped or wildcard dsound"),
            ('WINEDLLOVERRIDES="*dsound=b" %command%', "Grouped or wildcard dsound"),
            ('WINEDLLOVERRIDES="dsound=n;DSOUND.dll=b" %command%', "Repeated DLL"),
            ('WINEDLLOVERRIDES="dsound=n,n" %command%', "Repeated load mode"),
            ('WINEDLLOVERRIDES="dxgi,=b" %command%', "Malformed WINEDLLOVERRIDES"),
            ('WINEDLLOVERRIDES="bad/name=b" %command%', "Malformed WINEDLLOVERRIDES"),
            ('WINEDLLOVERRIDES="dxgi=bogus" %command%', "Malformed WINEDLLOVERRIDES"),
            ("%command% -pf_tricks=vcrun2019", "Conflicting or repeated -pf_tricks"),
            ("%command% -pf_tricks vcrun2022", "Conflicting or repeated -pf_tricks"),
            ("%command% -pf_tricks=vcrun2022 -pf_tricks=vcrun2022", "Conflicting or repeated -pf_tricks"),
        ):
            with self.subTest(existing=existing), self.assertRaisesRegex(ValueError, item + ".*merge .* manually"):
                steamos.compose_launch_options(existing)

    def test_launch_rejects_unsupported_shell(self):
        for existing in (
            "~/lsfg", "'%command%'", 'arg="%command%"', "%command% %command%", "%com'mand%'",
            "%command%\0", "%command%\n", "%command%\t", r"/path\ with\ spaces %command%",
            '"unterminated %command%', "%command% $(whoami)", "%command% `whoami`",
            "LSFG=$VAR %command%", '%command% "$VAR"', "%command% | other", "%command% && other",
            "%command% > file", "%command%; other", '%command% "a;b"', "%command% *.dll",
            "env -i %command%", '"/usr/bin/env" FOO=bar %command%', "if %command%",
            "command /usr/bin/env -i %command%", "exec /usr/bin/env -i %command%",
            "bash -c 'printf abc > result' %command%",
            """FOO=bar "/bin/bash" -c 'printf abc > result' %command%""",
            "eval 'printf abc > result' %command%", "busybox sh -c 'printf abc > result' %command%",
        ):
            with self.subTest(existing=existing), self.assertRaisesRegex(ValueError, "merge .* manually"):
                steamos.compose_launch_options(existing)

    def test_launch_rejects_runtime_trick_before_placeholder(self):
        for prefix in ("-pf_tricks=vcrun2022", "~/lsfg -pf_tricks=vcrun2022",
                       "~/lsfg '-pf_tricks=vcrun2019'", "~/lsfg -pf_tricks"):
            with self.subTest(prefix=prefix), self.assertRaisesRegex(ValueError, "-pf_tricks before %command%"):
                steamos.compose_launch_options(f"{prefix} %command%")

    def test_health_checks_sdk_dependencies(self):
        self.health_payload()
        for name, content in self.files.items():
            self.put(self.game / name, content)
        result = steamos.health(self.game, self.archive)
        self.assertEqual(result[0], f"Game: {self.game.resolve()}")
        for name in self.files.keys() - {"BL4Fix-README.txt", "OakGame/Content/uiresources/bl4link/boot.js"}:
            self.assertIn(f"Present: {name}", result)
        self.assertFalse(any("boot.js" in line or "BL4Fix-README" in line for line in result))
        self.assertIn("runtime activation unverified", result[-1])
        self.assertIn("SDK console", result[-1])
        self.assertIn("F7", result[-1])
        plugin = "OakGame/Binaries/Win64/Plugins/python314.dll"
        self.put(self.game / plugin, b"changed dll")
        (self.game / "sdk_mods/__main__.py").unlink()
        self.put(self.game / (steamos.PAK_ROOT + catalog.LINK_PAK), b"other pak")
        result = steamos.health(self.game, self.archive)
        self.assertIn(f"Changed: {plugin}", result)
        self.assertIn("Missing: sdk_mods/__main__.py", result)
        self.assertIn(f"Changed: {steamos.PAK_ROOT + catalog.LINK_PAK}", result)

    def test_health_missing_expected_mod(self):
        self.health_payload()
        record = {"files": ["sdk_mods/bl4_minimap.sdkmod"], "mods": ["bl4_minimap"]}
        self.put(self.game / steamos.RECORD, json.dumps(record).encode())
        self.put(self.game / "sdk_mods/bl4_item_cards.sdkmod", b"old mod")
        result = steamos.health(self.game, self.archive)
        self.assertIn("Missing: sdk_mods/bl4_mod_menu.sdkmod", result)
        self.assertIn("Missing: sdk_mods/bl4_minimap.sdkmod", result)
        self.assertIn("Changed: sdk_mods/bl4_item_cards.sdkmod", result)
        self.assertFalse(any("bl4_skip_intro.sdkmod" in line for line in result))

    def test_health_manual_install_and_invalid_record(self):
        self.health_payload()
        self.put(self.game / "sdk_mods/bl4_minimap.sdkmod", self.files["sdk_mods/bl4_minimap.sdkmod"])
        result = steamos.health(self.game, self.archive)
        self.assertTrue(any("Selected mod set is unknown" in line for line in result))
        self.assertIn("Present: sdk_mods/bl4_minimap.sdkmod", result)
        self.assertFalse(any("bl4_item_cards.sdkmod" in line for line in result))
        for content in (b"{bad JSON", b"[]", b'{"files":[]}', b'{"files":false,"mods":[]}',
                        b'{"files":[],"mods":"bl4_item_cards"}', b'{"files":[],"mods":["unknown"]}',
                        b'{"files":[],"mods":[{}]}', b'{"files":[],"mods":["bl4_item_cards","unknown"]}'):
            with self.subTest(content=content):
                self.put(self.game / steamos.RECORD, content)
                result = steamos.health(self.game, self.archive)
                self.assertTrue(any("Invalid or inaccessible installation record" in line for line in result))
                self.assertIn("Present: sdk_mods/bl4_minimap.sdkmod", result)
                self.assertIn("Missing: sdk_mods/bl4_mod_menu.sdkmod", result)
                self.assertIn("Missing: sdk_mods/__main__.py", result)
                self.assertFalse(any("bl4_item_cards.sdkmod" in line for line in result))

    def test_health_incomplete_payload(self):
        self.health_payload()
        for name, content in self.files.items():
            self.put(self.game / name, content)
        catalog_files = {f"sdk_mods/{m.id}.sdkmod" for m in catalog.MODS}
        anchors = [name for name in self.files if name.startswith(("OakGame/Binaries/", "sdk_mods/"))
                   and name not in catalog_files and not name.endswith("/_ssl.pyd")]
        for name in anchors:
            content = self.files.pop(name)
            self.payload()
            with self.subTest(name=name), patch.object(zipfile.ZipFile, "open", side_effect=AssertionError("member read")):
                with self.assertRaisesRegex(ValueError, "Payload incomplete") as error:
                    steamos.health(self.game, self.archive)
                self.assertIn(name, str(error.exception))
            self.files[name] = content
        for name in (steamos.PAK_ROOT + catalog.LINK_PAK, "sdk_mods/bl4_mod_menu.sdkmod"):
            del self.files[name]
        result = steamos.health(self.game, self.payload())
        self.assertIn(f"Payload incomplete. Missing member: {steamos.PAK_ROOT + catalog.LINK_PAK}", result)
        self.assertIn("Payload incomplete. Missing member: sdk_mods/bl4_mod_menu.sdkmod", result)
        self.put(self.game / "sdk_mods/__main__.py", b"bootstrap")
        self.archive.write_bytes(self.archive.read_bytes().replace(b"bootstrap", b"corrupted", 1))
        with self.assertRaisesRegex(ValueError, "Invalid payload archive.*CRC"):
            steamos.health(self.game, self.archive)
        self.archive.write_bytes(b"not a ZIP file")
        with self.assertRaisesRegex(ValueError, "Invalid payload archive"):
            steamos.health(self.game, self.archive)

    def test_health_loose_mod_and_read_only(self):
        self.health_payload()
        loose = "sdk_mods/bl4_mod_menu"
        protected = (self.game / loose / "__init__.py", self.game / "OakGame/profile.sav",
                     self.game / "sdk_mods/settings/bl4_mod_menu.json",
                     self.root / ".steam/steam/userdata/123/config/localconfig.vdf",
                     self.root / "homebrew/settings/decky-lsfg-vk.json")
        for path in protected:
            self.put(path, b"sentinel")
        paths = set(self.root.rglob("*"))
        real_open = Path.open

        def read_only(path, mode="r", *args, **kwargs):
            self.assertNotIn(path, protected)
            self.assertIn(mode, ("r", "rb"))
            return real_open(path, mode, *args, **kwargs)

        with patch.object(Path, "open", read_only), patch("subprocess.Popen", side_effect=AssertionError("process")):
            result = steamos.health(self.game, self.archive)
        self.assertIn(f"Loose catalog mod directory can shadow the packaged mod: {loose}", result)
        self.assertEqual(set(self.root.rglob("*")), paths)
        self.assertTrue(all(path.read_bytes() == b"sentinel" for path in protected))

    def test_health_unsafe_paths(self):
        self.health_payload()
        loader = self.game / "OakGame/Binaries/Win64/dsound.dll"
        self.put(loader, b"sdk")
        for name in ("../outside", "/absolute", "sdk_mods/../bad", "sdk_mods\\bad", "OakGame/save.sav"):
            self.payload({name: b"bad"})
            with self.subTest(name=name), patch.object(zipfile.ZipFile, "open", side_effect=AssertionError("member read")):
                with self.assertRaisesRegex(ValueError, "Unsafe.*path"):
                    steamos.health(self.game, self.archive)
        self.payload()
        real_open = Path.open

        def deny_loader(path, *args, **kwargs):
            if path == loader:
                raise PermissionError("simulated denial")
            return real_open(path, *args, **kwargs)

        with patch.object(Path, "open", deny_loader):
            result = steamos.health(self.game, self.archive)
        self.assertTrue(any("Inaccessible or unsafe game file:" in line and "simulated denial" in line for line in result))
        self.assertIn("Missing: sdk_mods/__main__.py", result)

    @unittest.skipIf(os.name == "nt", "Unix target symlinks checked on Linux CI")
    def test_health_symlink_paths(self):
        self.health_payload()
        outside = self.root / "outside"
        self.put(outside / "python3.dll", b"outside")
        win64 = self.game / "OakGame/Binaries/Win64"
        (win64 / "Plugins").symlink_to(outside, target_is_directory=True)
        (win64 / "dsound.dll").symlink_to(outside / "python3.dll")
        self.put(self.game / "sdk_mods/__main__.py", b"bootstrap")
        (self.game / "sdk_mods/bl4_mod_menu").symlink_to(outside, target_is_directory=True)
        self.put(outside / "install.json", b'{"files":[],"mods":["bl4_item_cards"]}')
        record = self.game / steamos.RECORD
        record.parent.mkdir()
        record.symlink_to(outside / "install.json")
        result = steamos.health(self.game, self.archive)
        self.assertTrue(any("Inaccessible or unsafe game file" in line and "Plugins/python3.dll" in line for line in result))
        self.assertTrue(any("Inaccessible or unsafe game file" in line and "dsound.dll" in line for line in result))
        self.assertTrue(any("Inaccessible or unsafe loose mod path" in line and "bl4_mod_menu" in line for line in result))
        self.assertTrue(any("Invalid or inaccessible installation record" in line for line in result))
        self.assertIn("Present: sdk_mods/__main__.py", result)
        self.assertFalse(any("bl4_item_cards.sdkmod" in line for line in result))
        exe = self.game / steamos.GAME_EXE
        exe.unlink()
        exe.symlink_to(outside / "python3.dll")
        with self.assertRaisesRegex(ValueError, "uses a link"):
            steamos.health(self.game, self.archive)

    def test_health_oversized_payload(self):
        self.health_payload()
        self.put(self.game / "OakGame/Binaries/Win64/dsound.dll", b"sdk")
        with zipfile.ZipFile(self.archive) as zf:
            members = zf.infolist()
        members[0].file_size = 1 << 30
        with patch.object(zipfile.ZipFile, "infolist", return_value=members), \
                patch.object(zipfile.ZipFile, "open", side_effect=AssertionError("member read")):
            with self.assertRaisesRegex(ValueError, "1 GiB size limit"):
                steamos.health(self.game, self.archive)

    def test_health_unsafe_member_metadata(self):
        self.health_payload()
        self.put(self.game / "OakGame/Binaries/Win64/dsound.dll", b"sdk")
        mismatched = zipfile.ZipInfo("sdk_mods/file\0hidden")
        link = zipfile.ZipInfo("sdk_mods/link")
        dir_link = zipfile.ZipInfo("sdk_mods/linked-dir/")
        link.external_attr = dir_link.external_attr = (stat.S_IFLNK | 0o777) << 16
        with zipfile.ZipFile(self.archive) as zf:
            members = zf.infolist()
        for item in (mismatched, link, dir_link, zipfile.ZipInfo("sdk_mods/BL4_MOD_MENU.sdkmod"),
                     zipfile.ZipInfo("sdk_mods/SeTtInGs/protected.json")):
            with self.subTest(item=item), patch.object(zipfile.ZipFile, "infolist", return_value=[*members, item]), \
                    patch.object(zipfile.ZipFile, "open", side_effect=AssertionError("member read")):
                with self.assertRaisesRegex(ValueError, "Unsafe or duplicate payload path"):
                    steamos.health(self.game, self.archive)

    def test_health_cli_exit_means_report_or_error(self):
        self.health_payload()
        args = ["steamos.py", "--game", str(self.game), "--archive", str(self.archive), "--check"]
        with patch.object(sys, "argv", args), patch.object(os, "geteuid", return_value=1000, create=True), \
                redirect_stdout(io.StringIO()) as stdout, redirect_stderr(io.StringIO()) as stderr:
            self.assertEqual(steamos.main(), 0)
            self.assertIn("Missing: sdk_mods/__main__.py", stdout.getvalue())
            self.archive.write_bytes(b"not a ZIP file")
            self.assertEqual(steamos.main(), 1)
            self.assertIn("Invalid payload archive", stderr.getvalue())

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
