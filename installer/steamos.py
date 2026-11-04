"""Install the BL4 Fix payload on SteamOS, using only Python's standard library."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import sys
import tempfile
import zipfile
import zlib
from pathlib import Path, PurePosixPath

import catalog

if not getattr(sys, "frozen", False):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "mods/bl4_skip_intro"))
import movies

APP_ID = "1285190"
GAME_EXE = "OakGame/Binaries/Win64/Borderlands4.exe"
LAUNCH_OPTIONS = 'BL4FIX_STEAMOS=1 WINEDLLOVERRIDES="dsound=n,b" %command% -pf_tricks=vcrun2022'
_LAUNCH_FRAGMENT = re.compile(r"""[^ "'\\$`|&;<>()*?\[\]{}!#]+|"[^"\\$`]*"|'[^'\\$`]*'""")
_LAUNCH_WORD = re.compile(f"(?:{_LAUNCH_FRAGMENT.pattern})+")
_LAUNCH_ASSIGNMENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=")
_DLL_NAME = re.compile(r"\*?[a-z0-9_][a-z0-9_-]*(?:\.dll)?", re.IGNORECASE | re.ASCII)


def _launch_error(item: str) -> ValueError:
    return ValueError(f"{item}. Keep your original launch options and merge the BL4 Fix settings manually.")


def _merge_dll_overrides(value: str) -> str:
    if not value:
        return "dsound=n,b"
    entries = value.split(";")
    seen = set()
    for index, entry in enumerate(entries):
        names, equals, order = entry.partition("=")
        dlls = [name.strip() for name in names.split(",")]
        modes = [mode.strip().lower() for mode in order.split(",")] if order.strip() else []
        if (not equals or not all(_DLL_NAME.fullmatch(name) for name in dlls)
                or not all(mode in {"n", "native", "b", "builtin"} for mode in modes)):
            raise _launch_error("Malformed WINEDLLOVERRIDES entry")
        load_order = [mode[0] for mode in modes]
        if len(set(load_order)) != len(load_order):
            raise _launch_error("Repeated load mode in WINEDLLOVERRIDES")
        for name in dlls:
            key = name.lower().removesuffix(".dll")
            if key in seen:
                raise _launch_error(f"Repeated DLL in WINEDLLOVERRIDES ({name})")
            seen.add(key)
            if key.lstrip("*") == "dsound":
                if len(dlls) != 1 or key.startswith("*"):
                    raise _launch_error("Grouped or wildcard dsound entry in WINEDLLOVERRIDES")
                if load_order != ["n", "b"]:
                    entries[index] = names + "=n,b"
    if "dsound" not in seen:
        entries.append("dsound=n,b")
    return ";".join(entries)


def compose_launch_options(existing: str) -> str:
    """Compose BL4 settings with a bounded subset of literal Steam launch options."""
    if not existing.strip(" "):
        return LAUNCH_OPTIONS
    if not existing.isprintable():
        raise _launch_error("Unsupported control character or non-space separator")

    flag, overrides = "BL4FIX_STEAMOS", "WINEDLLOVERRIDES"
    runtime = "-pf_tricks=vcrun2022"
    edits = []
    owned = set()
    placeholder = runtime_seen = False
    leading = True
    start = len(existing) - len(existing.lstrip(" "))
    end = len(existing.rstrip(" "))
    position = start
    while position < end:
        match = _LAUNCH_WORD.match(existing, position)
        boundary = match.end() if match else position
        if not match or (boundary < end and existing[boundary] != " "):
            raise _launch_error(f"Unsupported {existing[boundary]!r} syntax at character {boundary + 1}")
        raw = match[0]
        fragments = _LAUNCH_FRAGMENT.findall(raw)
        word = "".join(part[1:-1] if part.startswith(("'", '"')) else part for part in fragments)
        assignment = _LAUNCH_ASSIGNMENT.match(raw)
        name = word.partition("=")[0]
        if raw == "%command%":
            if placeholder:
                raise _launch_error("Repeated %command% placeholder")
            placeholder = True
            leading = False
        elif "%command%" in raw or "%command%" in word:
            raise _launch_error("Quoted or embedded %command% placeholder")
        elif name in {flag + "+", overrides + "+"} and "=" in word:
            raise _launch_error(f"Unsupported append assignment to {name[:-1]}")
        elif name in {flag, overrides} and "=" in word:
            if not leading or not assignment:
                raise _launch_error(f"{name} must be a leading unquoted variable assignment")
            if name in owned:
                raise _launch_error(f"Repeated {name} assignment")
            owned.add(name)
            raw_value = raw[assignment.end():]
            quote = raw_value[0] if raw_value.startswith(("'", '"')) else ""
            if len(fragments) > (2 if quote else 1):
                raise _launch_error(f"Unsupported quoting in {name}")
            value = word[len(name) + 1:]
            if name == flag:
                if value not in {"0", "1"}:
                    raise _launch_error(f"Conflicting {flag} value")
                replacement = "1"
            else:
                replacement = _merge_dll_overrides(value)
                if ";" in replacement and not quote:
                    quote = '"'
            if replacement != value:
                edits.append((position, match.end(), f"{name}={quote}{replacement}{quote}"))
        elif ";" in word:
            raise _launch_error("Semicolons are only supported inside a quoted WINEDLLOVERRIDES value")
        elif name == "-pf_tricks":
            if not placeholder:
                raise _launch_error("-pf_tricks before %command%")
            if word != runtime or runtime_seen:
                raise _launch_error("Conflicting or repeated -pf_tricks argument")
            runtime_seen = True
        elif leading and not assignment:
            executable = word.rsplit("/", 1)[-1]
            if executable in {"env", "command", "exec", "eval", "builtin", "source", ".",
                              "sh", "bash", "dash", "ash", "zsh", "ksh", "fish", "csh", "tcsh",
                              "busybox", "sudo", "doas", "xargs"}:
                raise _launch_error(f"Unsupported shell or command-dispatch wrapper ({executable})")
            if not word or raw in {"if", "then", "else", "elif", "fi", "for", "in", "while",
                                   "until", "do", "done", "case", "esac", "select", "function", "time"}:
                raise _launch_error("Unsupported shell wrapper")
            leading = False
        position = match.end()
        while position < end and existing[position] == " ":
            position += 1

    if not placeholder:
        raise _launch_error("Missing %command% placeholder")
    prefix = [setting for name, setting in (
        (flag, f"{flag}=1"), (overrides, f'{overrides}="dsound=n,b"'),
    ) if name not in owned]
    if prefix:
        edits.append((start, start, " ".join(prefix) + " "))
    if not runtime_seen:
        edits.append((end, end, " " + runtime))
    # Apply edits from right to left so their original offsets stay valid.
    for first, last, replacement in sorted(edits, reverse=True):
        existing = existing[:first] + replacement + existing[last:]
    return existing


def find_games(home: Path) -> list[Path]:
    roots = [home / ".local/share/Steam", home / ".steam/steam",
             home / ".var/app/com.valvesoftware.Steam/.local/share/Steam"]
    libraries = set()
    for root in roots:
        if not root.is_dir():
            continue
        libraries.add(root.resolve())
        vdf = root / "steamapps/libraryfolders.vdf"
        if vdf.is_file():
            text = vdf.read_text(encoding="utf-8")
            libraries.update(Path(p.replace("\\\\", "\\")).expanduser().resolve()
                             for p in re.findall(r'"path"\s*"([^"\n]+)"', text))
    found = set()
    for library in libraries:
        manifest = library / f"steamapps/appmanifest_{APP_ID}.acf"
        if not manifest.is_file():
            continue
        match = re.search(r'"installdir"\s*"([^"\n]+)"', manifest.read_text(encoding="utf-8"))
        if match and PurePosixPath(match[1]).name == match[1] and match[1] not in (".", ".."):
            game = library / "steamapps/common" / match[1]
            if (game / GAME_EXE).is_file():
                found.add(game.resolve())
    return sorted(found)


def ensure_closed(proc: Path = Path("/proc")) -> None:
    """Fail closed if a game process is present or process inspection is unavailable."""
    if not proc.is_dir():
        raise RuntimeError("Run the installer on SteamOS/Linux with /proc available.")
    for entry in proc.iterdir():
        if not entry.name.isdecimal():
            continue
        try:
            args = (entry / "cmdline").read_bytes().split(b"\0")
            comm = (entry / "comm").read_bytes().strip().lower()
        except FileNotFoundError:
            continue  # process exited during the scan
        except PermissionError as ex:
            raise RuntimeError("Cannot check all running processes. Close the game and retry.") from ex
        if comm.startswith(b"borderlands4") or any(
            arg.replace(b"\\", b"/").rsplit(b"/", 1)[-1].lower() == b"borderlands4.exe" for arg in args
        ):
            raise RuntimeError("Close Borderlands 4 before installing or updating.")


RECORD = "sdk_mods/.bl4fix-steamos/install.json"
UI_ROOT = "OakGame/Content/uiresources/"
PAK_ROOT = "OakGame/Content/Paks/~mods/"
SDK_ANCHORS = (
    "OakGame/Binaries/Win64/dsound.dll",
    *(f"OakGame/Binaries/Win64/Plugins/{name}" for name in (
        "unrealsdk.toml", "unrealsdk.dll", "pyunrealsdk.dll", "python3.dll",
        "python314.dll", "python314.zip", "python314._pth",
    )),
    "sdk_mods/__main__.py", "sdk_mods/mods_base.sdkmod", "sdk_mods/console_mod_menu.sdkmod",
    "sdk_mods/keybinds/keybinds.pyd",
)


def payload_path() -> Path:
    path = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)) / "BL4Fix-Manual.zip"
    if not path.is_file() and not getattr(sys, "frozen", False):
        path = Path(__file__).resolve().parents[1] / "dist/BL4Fix-Manual.zip"
    return path


def _payload_path_parts(name: str) -> tuple[str, ...]:
    rel = PurePosixPath(name)
    if (not rel.parts or "\\" in name or ":" in name or rel.is_absolute() or ".." in rel.parts
            or rel.as_posix() != name or rel.parts[0] not in ("OakGame", "sdk_mods")
            and name != "BL4Fix-README.txt" or rel.suffix.lower() == ".sav"):
        raise ValueError(f"Unsafe file path: {name}")
    return rel.parts


def _unlinked_target(game: Path, name: str) -> Path:
    target = game
    for part in _payload_path_parts(name):
        target = target / part
        if target.is_symlink():
            raise ValueError(f"File path uses a link or leaves the game folder: {name}")
    if not target.resolve().is_relative_to(game):
        raise ValueError(f"File path uses a link or leaves the game folder: {name}")
    return target


def safe_target(game: Path, name: str) -> Path:
    target = _unlinked_target(game, name)
    if target.exists() and not target.is_file():
        raise ValueError(f"File target is not a file: {name}")
    return target


def game_folder(game: Path) -> Path:
    game = game.resolve(strict=True)
    if not (game / GAME_EXE).is_file():
        raise ValueError("Choose the Borderlands 4 folder containing OakGame, not the Win64 folder.")
    return game


def read_record(game: Path) -> dict:
    path = safe_target(game, RECORD)
    if not path.exists():
        return {}
    record = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(record, dict) or not isinstance(record.get("files"), list):
        raise ValueError("The SteamOS installation record is damaged; keep it and contact support.")
    for name in record["files"]:
        if not isinstance(name, str):
            raise ValueError("Invalid installation record path.")
        safe_target(game, name)
        if "settings" in PurePosixPath(name).parts or name == GAME_EXE or name == RECORD:
            raise ValueError("The installation record includes a protected user or game file.")
    sdk_files = record.get("sdk_files", [])
    if not isinstance(sdk_files, list) or any(not isinstance(n, str) or n not in record["files"] for n in sdk_files):
        raise ValueError("Invalid SDK installation record.")
    return record


def installed_mods(game: Path) -> set[str]:
    return {m.id for m in catalog.MODS if (game / f"sdk_mods/{m.id}.sdkmod").is_file()}


def _apply_changes(game: Path, changes: dict[str, bytes | None], record: dict | None, log=print) -> Path:
    targets = {name: safe_target(game, name) for name in changes}
    if record is not None:
        safe_target(game, RECORD)
    ensure_closed()
    backup = Path(tempfile.mkdtemp(prefix="bl4fix-backup-", dir=game))
    if record is not None:
        loader = "OakGame/Binaries/Win64/dsound.dll"
        old = game / loader
        if "loader_backup" not in record and old.is_file() and loader in changes and old.read_bytes() != changes[loader]:
            record["loader_backup"] = (backup.relative_to(game) / loader).as_posix()
        changes[RECORD] = json.dumps(record, indent=2).encode()
        targets[RECORD] = safe_target(game, RECORD)
    written = []
    try:
        for name, data in changes.items():
            target = targets[name]
            existed = target.is_file()
            if data is None and not existed or data is not None and existed and target.read_bytes() == data:
                continue
            old = backup / name
            if existed:
                old.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, old)
            written.append((target, old if existed else None))
            if data is None:
                target.unlink()
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                tmp = None
                try:
                    with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as stream:
                        tmp = Path(stream.name)
                        stream.write(data)
                    tmp.replace(target)
                    if hashlib.sha256(target.read_bytes()).digest() != hashlib.sha256(data).digest():
                        raise OSError(f"Verification failed: {name}")
                finally:
                    if tmp is not None:
                        tmp.unlink(missing_ok=True)
            log(f"{'Removed' if data is None else 'Installed'} {name}")
        (backup / "installed-files.txt").write_text(
            "\n".join(str(t.relative_to(game)) for t, _ in written) + "\n", encoding="utf-8")
    except BaseException:
        for target, old in reversed(written):
            if old is None:
                target.unlink(missing_ok=True)
            else:
                shutil.copy2(old, target)
        log(f"Operation rolled back. Backup: {backup}")
        raise
    return backup


def _mod_files(game: Path, ids: set[str], include_link: bool = False) -> set[str]:
    names = {f"sdk_mods/{mod_id}.sdkmod" for mod_id in ids}
    folders = set()
    for mod_id in ids:
        info = catalog.BY_ID[mod_id]
        for pak in info.paks:
            names.update(PAK_ROOT + pak + suffix for suffix in ("", ".next", ".remove"))
        folders.update(info.ui_dirs)
    if include_link:
        names.update(PAK_ROOT + catalog.LINK_PAK + suffix for suffix in ("", ".next", ".remove"))
        folders.add(catalog.LINK_UI_DIR)
    for folder in folders:
        root = game / UI_ROOT / folder
        safe_target(game, UI_ROOT + folder + "/.bl4fix-check")
        # Never follow a replaced root (rglob itself does not follow child directory links).
        if root.is_symlink():
            raise ValueError(f"Move the linked UI folder aside first: {root}")
        for path in root.rglob("*"):
            if path.is_symlink():
                raise ValueError(f"Move the linked UI file aside first: {path}")
            if path.is_file():
                names.add(path.relative_to(game).as_posix())
    return names


def _movies(game: Path, enabled: bool, changes: dict) -> None:
    for name in movies.LOGOS:
        movie = game / f"OakGame/Content/Movies/{name}.bk2"
        parked = movie.with_name(movie.name + movies.SUFFIX)
        for path in (movie, parked):
            safe_target(game, path.relative_to(game).as_posix())
        if enabled and movie.is_file():
            changes[parked.relative_to(game).as_posix()] = movie.read_bytes()
            changes[movie.relative_to(game).as_posix()] = None
        elif not enabled and parked.is_file():
            if not movie.exists():
                changes[movie.relative_to(game).as_posix()] = parked.read_bytes()
            changes[parked.relative_to(game).as_posix()] = None


def _payload_entries(zf: zipfile.ZipFile, *, check_directories: bool = False) -> dict[str, zipfile.ZipInfo]:
    entries = {}
    seen = set()
    members = zf.infolist()
    if sum(item.file_size for item in members) > 1 << 30:
        raise ValueError("The payload exceeds the 1 GiB size limit.")
    for item in members:
        is_dir = item.is_dir()
        if is_dir and not check_directories:
            continue
        name = item.filename
        path = name.removesuffix("/") if is_dir else name
        parts = _payload_path_parts(path)
        if (item.orig_filename != name or path.casefold() in seen
                or stat.S_ISLNK(item.external_attr >> 16)
                or any(part.lower() == "settings" for part in parts)):
            raise ValueError(f"Unsafe or duplicate payload path: {name}")
        seen.add(path.casefold())
        if not is_dir:
            entries[name] = item
    return entries


def _catalog_mod_id(name: str) -> str | None:
    return PurePosixPath(name).stem if name.startswith("sdk_mods/") and name.endswith(".sdkmod") else None


def _is_sdk_file(name: str, mod_id: str | None) -> bool:
    return (mod_id not in catalog.BY_ID and not name.startswith((UI_ROOT, PAK_ROOT))
            and name != "BL4Fix-README.txt")


def install(game: Path, archive: Path, chosen: set[str] | None = None, log=print) -> Path:
    game = game_folder(game)
    ensure_closed()
    selected = set(catalog.DEFAULTS) if chosen is None else set(chosen)
    if selected - catalog.BY_ID.keys():
        raise ValueError("Unknown mod selected.")
    selected.update(catalog.REQUIRED)
    record = read_record(game)
    changes = {}
    sdk_files = []
    with zipfile.ZipFile(archive) as zf:
        entries = _payload_entries(zf)
        for name in entries:
            safe_target(game, name)
        seen = {name.casefold() for name in entries}
        required = {"oakgame/binaries/win64/dsound.dll", *(f"sdk_mods/{m}.sdkmod" for m in selected)}
        if not required <= seen:
            raise ValueError("Not a complete BL4 Fix payload (SDK or a selected mod is missing).")
        for mod_id in catalog.BY_ID:
            loose = game / "sdk_mods" / mod_id
            if loose.exists():
                raise ValueError(f"Move the old loose mod folder aside first: {loose}")
        for name, item in entries.items():
            mod_id = _catalog_mod_id(name)
            owners = {m.id for m in catalog.MODS for folder in m.ui_dirs
                      if name.startswith(UI_ROOT + folder + "/")}
            if mod_id in catalog.BY_ID and mod_id not in selected or owners and not owners & selected:
                continue
            changes[name] = zf.read(item)
            if _is_sdk_file(name, mod_id):
                sdk_files.append(name)
    files = list(changes)
    removed = set(catalog.BY_ID) - selected
    for name in _mod_files(game, removed):
        changes.setdefault(name, None)
    for mod_id in sorted(selected):
        name = f"sdk_mods/settings/{mod_id}.json"
        path = safe_target(game, name)
        if not path.exists() or mod_id in catalog.REQUIRED or mod_id == "bl4_skip_intro":
            data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
            if not isinstance(data, dict):
                raise ValueError(f"Settings are not a JSON object: {path}")
            data["enabled"] = True
            changes[name] = json.dumps(data, indent=4).encode()
    skip_settings = "sdk_mods/settings/bl4_skip_intro.json"
    if "bl4_skip_intro" not in selected and (path := safe_target(game, skip_settings)).is_file():
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("Skip Intro settings are damaged.")
        data["enabled"] = False
        changes[skip_settings] = json.dumps(data, indent=4).encode()
    _movies(game, "bl4_skip_intro" in selected, changes)
    record.update({"files": files, "mods": sorted(selected), "sdk_files": sdk_files,
                   "sdk_hashes": {n: hashlib.sha256(changes[n]).hexdigest() for n in sdk_files}})
    backup = _apply_changes(game, changes, record, log)
    log(f"Finished. Backup: {backup}")
    return backup


def uninstall(game: Path, remove_sdk: bool = False, log=print) -> Path:
    game = game_folder(game)
    ensure_closed()
    record = read_record(game)
    sdk_files = record.get("sdk_files", [])
    if not isinstance(sdk_files, list) or any(not isinstance(n, str) for n in sdk_files):
        raise ValueError("Invalid SDK installation record.")
    sdk_set = set(sdk_files)
    names = _mod_files(game, set(catalog.BY_ID), include_link=True)
    names.update(n for n in record.get("files", []) if n not in sdk_set)
    changes = {name: None for name in names}
    if remove_sdk:
        if not sdk_files:
            raise ValueError("No SteamOS SDK installation record. Keep the SDK or remove it manually.")
        for name in sdk_files:
            target = safe_target(game, name)
            if target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest() != record.get("sdk_hashes", {}).get(name):
                raise ValueError(f"SDK file was changed by another program; keep it or inspect it first: {name}")
            changes[name] = None
        loader_backup = record.get("loader_backup")
        if loader_backup:
            if not isinstance(loader_backup, str):
                raise ValueError("Invalid original loader backup path.")
            rel = PurePosixPath(loader_backup)
            if (rel.is_absolute() or not rel.parts[0].startswith("bl4fix-backup-") or ".." in rel.parts
                    or "\\" in loader_backup or ":" in loader_backup
                    or rel.parts[1:] != ("OakGame", "Binaries", "Win64", "dsound.dll")):
                raise ValueError("Invalid original loader backup path.")
            original = game / loader_backup
            if not original.resolve().is_relative_to(game) or original.is_symlink():
                raise ValueError("Original loader backup leaves the game folder.")
            changes["OakGame/Binaries/Win64/dsound.dll"] = original.read_bytes()
        changes[RECORD] = None
        next_record = None
    else:
        next_record = {**record, "files": sdk_files, "mods": []}
    _movies(game, False, changes)
    return _apply_changes(game, changes, next_record, log)


def _health_mods(game: Path, messages: list[str]) -> set[str]:
    expected = set(catalog.REQUIRED)
    try:
        record = read_record(game)
        if record:
            mods = record.get("mods")
            if not isinstance(mods, list) or any(not isinstance(m, str) or m not in catalog.BY_ID for m in mods):
                raise ValueError("mods must be a list of known catalog IDs")
            expected.update(mods)
        else:
            messages.append("No SteamOS installation record. Selected mod set is unknown.")
    except (OSError, ValueError, RecursionError) as ex:
        messages.append(f"Invalid or inaccessible installation record ({ex}). Using required and present catalog mods.")
    present = set()
    for mod_id in catalog.BY_ID:
        name = f"sdk_mods/{mod_id}.sdkmod"
        loose = f"sdk_mods/{mod_id}"
        try:
            if safe_target(game, name).is_file():
                present.add(mod_id)
        except (OSError, ValueError) as ex:
            messages.append(f"Inaccessible or unsafe catalog mod: {name} ({ex})")
        try:
            if _unlinked_target(game, loose).is_dir():
                messages.append(f"Loose catalog mod directory can shadow the packaged mod: {loose}")
        except (OSError, ValueError) as ex:
            messages.append(f"Inaccessible or unsafe loose mod path: {loose} ({ex})")
    messages.append(f"Installed catalog mods: {len(present)} / {len(catalog.MODS)}")
    return expected | present


def _matches_payload(path: Path, zf: zipfile.ZipFile, member: zipfile.ZipInfo) -> bool:
    with path.open("rb") as actual, zf.open(member) as expected:
        matches = True
        while chunk := expected.read(1 << 20):
            matches = matches and actual.read(len(chunk)) == chunk
        return matches and not actual.read(1)


def health(game: Path, archive: Path) -> list[str]:
    game = game.resolve(strict=True)
    safe_target(game, GAME_EXE)
    game = game_folder(game)
    messages = [f"Game: {game}"]
    try:
        with zipfile.ZipFile(archive) as zf:
            entries = _payload_entries(zf, check_directories=True)
            missing = set(SDK_ANCHORS) - entries.keys()
            if missing:
                raise ValueError(f"Payload incomplete. Missing SDK members: {', '.join(sorted(missing))}")
            mods = _health_mods(game, messages)
            names = [name for name in entries if _is_sdk_file(name, _catalog_mod_id(name))]
            names += [PAK_ROOT + catalog.LINK_PAK, *(f"sdk_mods/{m}.sdkmod" for m in sorted(mods))]
            for name in names:
                if name not in entries:
                    messages.append(f"Payload incomplete. Missing member: {name}")
                    continue
                try:
                    path = safe_target(game, name)
                    if not path.is_file():
                        messages.append(f"Missing: {name}")
                    else:
                        status = "Present" if _matches_payload(path, zf, entries[name]) else "Changed"
                        messages.append(f"{status}: {name}")
                except (OSError, ValueError) as ex:
                    messages.append(f"Inaccessible or unsafe game file: {name} ({ex})")
    except (zipfile.BadZipFile, RuntimeError, EOFError, zlib.error) as ex:
        raise ValueError(f"Invalid payload archive: {ex}") from ex
    messages.append("SDK runtime activation unverified. Launch the game, press tilde twice to open the SDK console "
                    "and run mods, then press F7 to check the BL4 Fix menu.")
    return messages


def finish(game: Path) -> Path | None:
    """Apply only the UI Link's staged pak change, after the game has closed."""
    game = game.resolve(strict=True)
    if not (game / GAME_EXE).is_file():
        raise ValueError("Choose the game folder containing OakGame.")
    ensure_closed()
    target = game / "OakGame/Content/Paks/~mods/BL4Fix_UILink_4251_P.pak"
    replacement = target.with_name(target.name + ".next")
    removal = target.with_name(target.name + ".remove")
    for path in (target, replacement, removal):
        if not path.resolve().is_relative_to(game) or any(p.is_symlink() for p in [path, *path.parents] if p != game):
            raise ValueError(f"Refusing linked pak path: {path}")
    if not replacement.is_file() and not removal.is_file():
        return None
    backup = Path(tempfile.mkdtemp(prefix="bl4fix-backup-", dir=game))
    if target.exists():
        shutil.copy2(target, backup / target.name)
    if removal.is_file():
        target.unlink(missing_ok=True)
        replacement.unlink(missing_ok=True)
        removal.unlink()
    else:
        replacement.replace(target)
    return backup


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game", type=Path, help="game folder containing OakGame; otherwise detect Steam libraries")
    parser.add_argument("--archive", type=Path, default=payload_path())
    parser.add_argument("--list", action="store_true", help="list detected installations without changing files")
    parser.add_argument("--mods", help="comma-separated mod IDs; required mods are always installed")
    parser.add_argument("--uninstall", action="store_true")
    parser.add_argument("--remove-sdk", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--finish", action="store_true", help="apply a pending UI Link pak change, game closed")
    args = parser.parse_args()
    try:
        games = [args.game] if args.game else find_games(Path.home())
        if args.list:
            print("\n".join(map(str, games)) or "No Steam install found. Use --game with its folder.")
            return 0
        if len(games) != 1:
            raise ValueError("Use --game with one game folder (no install found, or multiple installs found).")
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            raise ValueError("Run as your normal Steam user, without sudo.")
        if args.check:
            print("\n".join(health(games[0], args.archive)))
            return 0
        if args.uninstall:
            print(f"Uninstalled. Backup: {uninstall(games[0], args.remove_sdk)}")
            return 0
        if args.finish:
            backup = finish(games[0])
            print(f"Applied pending UI Link change. Backup: {backup}" if backup else "No pending UI Link change.")
            return 0
        backup = install(games[0], args.archive, None if args.mods is None else {m for m in args.mods.split(",") if m})
        print(f"Installed. Replaced files are backed up in:\n{backup}")
        print(f"Steam > Borderlands 4 > Properties > Launch Options:\n{LAUNCH_OPTIONS}")
        print("Merge with any existing launch options. Map a rear button to F7 in Steam Input.")
        print("Updates: install a newer SteamOS package with the game closed. See STEAMOS.md for limitations.")
        return 0
    except (OSError, ValueError, RuntimeError, zipfile.BadZipFile) as ex:
        print(f"Error: {ex}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
