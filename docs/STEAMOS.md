# Steam Deck / SteamOS

This fork includes **BL4FixSetup-SteamOS**, a standalone graphical setup application
for SteamOS on Steam Deck and other x86-64 Linux desktops. It bundles Python and
Tcl/Tk; the Deck needs no Python installation, pip packages, sudo, pacman, or changes
to SteamOS's read-only system. The Windows game and Windows Python SDK run inside
**Proton**, while this setup app runs natively in Desktop Mode.

The package and offline checks can be built without a game installation. Actual
Steam Deck gameplay, controller navigation, hosting, and performance still need
testing on the device; this is not a claim of hardware qualification.

## Install

1. Switch the Deck to **Desktop Mode** and fully close Borderlands 4. Let any Steam
   download or file verification finish. Back up your saves before using mods.
2. Download the **BL4Fix-SteamOS** artifact from the latest successful **main** run
   of [SteamOS package](https://github.com/Farkoal2128/bl4-fix-deck/actions/workflows/steamos.yml).
   GitHub requires sign-in for artifact downloads. Extract the artifact ZIP, then
   **BL4FixSetup-SteamOS.tar.gz** into a folder in your home directory. Double-click
   the extracted **BL4FixSetup-SteamOS** executable. Allow execution if Dolphin asks.
   Keep it on internal storage if an SD card is mounted with `noexec`.

   The app detects native and Flatpak Steam libraries, including SD card libraries
   listed in Steam's `libraryfolders.vdf`. Select your install or use **Browse** to
   choose the folder containing `OakGame`. On **Loadout**, tick your mods and press
   **Apply selection**. Mod Menu and Direct Connect stay installed. Unticked optional
   mods are removed. The app confirms removals before applying the selection.

   **System** offers Repair, Health check, Uninstall, and Finish pending UI change.
   Uninstall keeps the SDK unless you tick **Also remove the Python SDK**. It restores
   logo movies, preserves saves, settings and other mods, and backs up files before
   removing them. An SDK file replaced by another tool is kept and reported rather
   than silently deleted. A loader replaced by this installer can be restored from
   the original installation backup.

   **Friends & hosting** edits the same friends list and host port as the in-game
   Direct Connect page; close the game before changing them. Apply can copy the
   standalone app into `~/.local/share/bl4fix/` and add **BL4 Fix Setup** to the
   application menu, so you can return after deleting the download folder.
3. On **System**, press **Copy launch options**, then paste in Steam under
   **Borderlands 4 > Properties > General > Launch Options**:

   ```text
   BL4FIX_STEAMOS=1 WINEDLLOVERRIDES="dsound=n,b" %command% -pf_tricks=vcrun2022
   ```

   Keep your existing options: combine environment variables before the single
   `%command%`, and game arguments after it. Merge `dsound=n,b` into an existing
   `WINEDLLOVERRIDES` value with a semicolon. `BL4FIX_STEAMOS=1` selects this
   fork's SteamOS behavior; keep it even when the SDK already loads successfully.
   The dsound override and runtime argument follow the
   [SDK's Proton instructions](https://bl-sdk.github.io/oak2-mod-db/).
4. Run the game through Steam. Map a rear grip button to **F7** in **Steam Input**
   to open MODS, and optionally another to **F6** for Direct Connect. Use the right
   trackpad as a mouse and its click as left mouse for the HTML menus. **Steam + X**
   opens the on-screen keyboard. These menus do not yet have a tested Deck layout.

The installer checks for a running game, validates archive paths, preserves mod
settings and saves, backs up every replaced file to a unique `bl4fix-backup-*`
folder inside the game directory, and rolls back file replacements if installation
fails. Old loose `sdk_mods/bl4_*` folders must be moved aside first, since the SDK
loads those instead of the packaged mods. Replaced loaders such as `dsound.dll`
are backed up too; other loaders may be incompatible with the SDK.

**Source package:** the artifact also includes `BL4Fix-SteamOS.zip`. Extract it
and run `python3 setup.py` for the same window if you already have Python 3.11+
and Tk installed. Its command-line fallback is `python3 install.py`; `--list` lists
installs, `--game "..."` selects one, `--mods bl4_minimap,bl4_respec` selects optional
mods, `--check` checks files, and `--uninstall [--remove-sdk]` removes the installation.
The source package uses the same backend as the standalone app.

**Manual extraction:** for a file-only install, open the inner
`BL4Fix-Manual.zip` in Ark and extract its contents into the game folder with the
game closed, then set the same launch options. This method does not create the
installer's backup or validate existing files; copy conflicting files aside first.

## Updates and platform limits

- **Updates:** build or obtain a newer package from this fork and run its installer
  with the game closed. In-game official updates and automatic restart are disabled
  in SteamOS mode so an upstream Windows update cannot replace the port. Settings
  are preserved. In-game repository install, update, remove and rollback operations
  also report that files must be managed in Desktop Mode with the game closed.
  Enabling, disabling and configuring installed mods still use the in-game menu.
- **UI Link changes:** if the mod log requests it after a game patch or disabling
  the final UI mod, close the game and use **System > Finish pending UI change**.
  The source-package equivalent is `python3 install.py --finish`. This applies only
  the UI Link's pending pak replacement
  or removal, keeping the old pak in a backup folder.
- **Co-op:** the game still uses UDP, normally port **7777**. Joining is outgoing.
  Hosting across the internet requires router forwarding and a suitable Linux
  firewall rule. BL4 Fix does not change the Linux firewall or install a friend IP
  allowlist. Windows Firewall controls report this instead of trying netsh/UAC.
  An in-game friends list alone does not restrict who can reach a hosted port.
- **Save Backups:** copies can still be made in the game's Proton environment.
  Automatic in-game restores, including bank-only restores, are unavailable because
  their helper needs Windows PowerShell. A restore request reports this and creates
  no pending restore. For a manual whole-file restore, close the game, pause Steam
  Cloud for the game, copy current saves aside, then copy the desired `.sav` files
  from `Saved/BL4Fix Save Backups/<account>/<backup>/` into the corresponding
  `Saved/SaveGames/` account folder. Bank-only merging has no native replacement.
  Confirm the restored state before re-enabling Cloud and resolving any conflict.
- **Save locations:** look under the game's Proton prefix:
  `steamapps/compatdata/1285190/pfx/drive_c/users/steamuser/Documents/My Games/Borderlands 4/Saved/`.
  Check Steam libraries on internal storage and SD cards; prefix locations and the
  Documents mapping can vary. The installer never edits saves or the prefix. Launch options are
  copied for you to apply, and are not silently written into Steam configuration.
- **Windows setup features:** the WebView2 setup app, NTFS Disk Space tool, Start
  menu integration and automatic setup-app self-update are Windows-only. Run this
  fork's native setup app; do not add `BL4FixSetup.exe` as a separate non-Steam game/prefix.

If the SDK fails to load, check `dsound.dll` and `Plugins/` under
`OakGame/Binaries/Win64/`, the launch options, and the SDK's logs. The
[SDK FAQ](https://bl-sdk.github.io/oak2-mod-db/faq/#can-i-use-this-on-steam-decklinuxmac)
describes Proton build compatibility and installing `vcrun2022` with Protontricks
if the selected Proton build does not handle `-pf_tricks`. Install that runtime
into **Borderlands 4's prefix**, not into the Linux system or an unrelated prefix.

## Remove

Open **System > Uninstall** with the game closed. Choose whether to remove the SDK
first. Remove the added Steam launch options yourself. Saves, settings, other mods
and backup folders are preserved. To remove the setup app and its application-menu
entry too, delete `~/.local/share/bl4fix/` and
`~/.local/share/applications/bl4fix.desktop` after closing the setup app.

For manual installations without this setup app's SDK record, it offers mod removal
but refuses to guess which SDK files to delete; remove only the SDK files you copied.

## Build from source

Download this fork's source archive or clone it, then in that folder run:

```sh
python3 tools/build_steamos.py
python3 dev/steamos_test.py
```

The source-package build works on Linux or Windows with Python 3.11+. It downloads the pinned
oak2 SDK v0.3 from bl-sdk and checks its SHA-256 against `installer/build.py`.
It packs this checkout's mods, prepared UI pages and pictures into
`dist/BL4Fix-SteamOS.zip` and writes `BL4Fix-SteamOS.zip.sha256`. No game files,
Windows setup executable, build tools, or pip installation are required. All
included mod source and licenses are inspectable inside the `.sdkmod` zip files.

On the Deck, compare `sha256sum BL4Fix-SteamOS.zip` with the checksum supplied
alongside the package. A local checksum detects transfer damage; it is not an
independent signature or a GitHub release attestation.

To build the **standalone graphical executable**, use x86-64 Linux (PyInstaller
cannot cross-compile it from Windows), Python 3.11 with Tk, and PyInstaller:

```sh
python3 -m pip install pyinstaller==6.11.1
python3 tools/build_steamos.py --native
# On a desktop:
python3 dev/steamos_gui_test.py
# On a headless build worker:
xvfb-run -a python3 dev/steamos_gui_test.py
xvfb-run -a dist/BL4FixSetup-SteamOS --smoke-test
```

Outputs are `dist/BL4FixSetup-SteamOS`, `dist/BL4FixSetup-SteamOS.tar.gz` and its
SHA-256 file. The tar preserves executable permissions. The Linux CI builds on
Ubuntu 22.04 for a glibc 2.35 baseline, verifies the setup window and controls, and
launches the **bundled executable** under a virtual display to verify its Python,
Tk and payload are present. Build-only packages belong on the build machine, not
on the Deck. See [PyInstaller's platform guidance](https://pyinstaller.org/en/stable/usage.html).
