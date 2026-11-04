# Steam Deck / SteamOS

This fork includes **BL4FixSetup-SteamOS**, a standalone graphical setup application
for SteamOS on Steam Deck and other x86-64 Linux desktops. It bundles Python and
Tcl/Tk; the Deck needs no Python installation, pip packages, sudo, pacman, or changes
to SteamOS's read-only system. The Windows game and Windows Python SDK run inside
**Proton**, while this setup app runs natively in Desktop Mode.

The package and offline checks can be built without a game installation. Actual
Steam Deck gameplay, controller navigation, hosting, and performance still need
testing on the device; this is not a claim of hardware qualification.

**Version note:** the published **steamos-v0.1.0** executable and source ZIP have
fixed **Copy launch options** output and basic file checks. **Original Steam launch
options**, **Preview**, the enhanced SDK file diagnostics and CLI `--launch-options`
below exist in the **current unreleased source**, not those downloads. Build from
this checkout using [Build from source](#build-from-source) to use them; this guide
does not announce an updated release.

## Install

1. Switch the Deck to **Desktop Mode** and fully close Borderlands 4. Let any Steam
   download or file verification finish. Back up your saves before using mods.
2. [Download **BL4FixSetup-SteamOS.tar.gz**](https://github.com/Farkoal2128/bl4-fix-deck/releases/latest/download/BL4FixSetup-SteamOS.tar.gz)
   from the [latest SteamOS release](https://github.com/Farkoal2128/bl4-fix-deck/releases/latest),
   without signing into GitHub. Its `.sha256` file is on the same release page.
   Extract the tar archive into a folder in your home directory. Double-click
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
3. On **System**, run **Health check** and compare the selected game folder with
   Steam's **Manage > Browse local files**. File results do not establish SDK
   activation. Save the complete text in **Borderlands 4 > Properties > General >
   Launch Options** in a separate note before using Copy or editing Steam.
   **On v0.1.0**, Copy replaces the clipboard with a fixed default and does not
   merge; follow [manual merge guidance](#launch-options-and-lsfg) for existing text.
   **On current source builds**, paste the saved text into **Original Steam launch
   options**. Leave this input empty only if Steam's field is empty. Press **Preview**,
   inspect **Composed preview**, then **Copy launch options**. Copy validates again;
   editing the original clears the old preview. Paste the manually merged or
   validated composed result into Steam yourself. Neither build edits Steam
   configuration or executes pasted launch text.
4. Launch through Steam, press tilde twice for the SDK console and run `mods`, then check
   **F7** for BL4 Fix's menu. These are separate checks; see [troubleshooting](#installed-files-but-no-mods).
   Map a rear grip button to **F7** in **Steam Input**
   to open MODS, and optionally another to **F6** for Direct Connect. Use the right
   trackpad as a mouse and its click as left mouse for the HTML menus. **Steam + X**
   opens the on-screen keyboard. These menus do not yet have a tested Deck layout.

The installer checks for a running game, validates archive paths, preserves mod
settings and saves, backs up every replaced file to a unique `bl4fix-backup-*`
folder inside the game directory, and rolls back file replacements if installation
fails. Old loose `sdk_mods/bl4_*` folders must be moved aside first, since the SDK
loads those instead of the packaged mods. Replaced loaders such as `dsound.dll`
are backed up too; other loaders may be incompatible with the SDK.

**Source package:** the release also includes [BL4Fix-SteamOS.zip](https://github.com/Farkoal2128/bl4-fix-deck/releases/latest/download/BL4Fix-SteamOS.zip). Extract it
and run `python3 setup.py` for the same window if you already have Python 3.11+
and Tk installed. Its command-line fallback is `python3 install.py`; `--list` lists
installs, `--game "..."` selects one, `--mods bl4_minimap,bl4_respec` selects optional
mods, `--check` checks files, and `--uninstall [--remove-sdk]` removes the installation.
The source package uses the same backend as the standalone app.

**Current unreleased source only:** a source package built from this checkout adds
a print-only launch composer; the published v0.1.0 source ZIP does not have it.
It needs no game installation or payload and does not change Steam. From the
extracted package built from this checkout:

```sh
python3 install.py --launch-options ''
python3 install.py --launch-options 'LSFG_PROCESS=decky-lsfg-vk %command%'
python3 install.py --launch-options '~/lsfg %command%'
```

The outer shell quotes pass the whole input literally; they are not part of the
Steam field. Empty input selects the empty-field default. Unsupported input returns
an error instead of a composed line. Do not combine `--launch-options` with `--game`,
`--archive`, `--mods`, `--list`, `--check`, `--finish`, `--uninstall` or `--remove-sdk`.

**Manual extraction:** for a file-only install, open the inner
`BL4Fix-Manual.zip` in Ark and extract its contents into the game folder with the
game closed, then set the same launch options. This method does not create the
installer's backup or validate existing files; copy conflicting files aside first.

## Launch options and lsfg

**Published v0.1.0 / manual merging:** before pressing its fixed **Copy launch
options** button, save Steam's complete original text in a separate note, since
Copy overwrites the clipboard. It copies only the default below; it neither reads
nor merges your current options. Paste that default unchanged only when Steam's
field was empty. For existing options, manually reconcile using the rules below
and inspect the merged line before applying it in Steam. Keep your lsfg setup and
other DLL overrides. To undo, restore your saved original exactly with the game closed.

**Current unreleased source:** paste the complete original into the new input and
use Preview/Copy. For an **empty Steam field only**, its preview is the same default:

```text
BL4FIX_STEAMOS=1 WINEDLLOVERRIDES="dsound=n,b" %command% -pf_tricks=vcrun2022
```

`BL4FIX_STEAMOS=1` selects this fork's SteamOS behavior; retain it even if the SDK
already loads. The dsound override and runtime argument follow the
[SDK's Proton instructions](https://bl-sdk.github.io/oak2-mod-db/).

Always paste your actual complete options. These two examples come from the
[Decky fork README](https://github.com/jbragado/decky-lossless-scaling-vk) and the
[experimental fork's public-plugin examples](https://github.com/PacificSilent/decky-lsfg-vk-experimental/blob/main/README.md).
They do not identify your installed plugin/version or prove compatibility. The
right column is current source composer output, also usable as manual merge
examples for v0.1.0; that release does not generate these merged lines:

| Original input | Composed preview |
|---|---|
| `LSFG_PROCESS=decky-lsfg-vk %command%` | `BL4FIX_STEAMOS=1 WINEDLLOVERRIDES="dsound=n,b" LSFG_PROCESS=decky-lsfg-vk %command% -pf_tricks=vcrun2022` |
| `~/lsfg %command%` | `BL4FIX_STEAMOS=1 WINEDLLOVERRIDES="dsound=n,b" ~/lsfg %command% -pf_tricks=vcrun2022` |
| `WINEDLLOVERRIDES="dxgi=n,b;dsound=b;version=n" %command%` | `BL4FIX_STEAMOS=1 WINEDLLOVERRIDES="dxgi=n,b;dsound=n,b;version=n" %command% -pf_tricks=vcrun2022` |

The composer keeps supported literal leading environment assignments, a wrapper
and its arguments, one unquoted standalone `%command%`, and game arguments. It
preserves unrelated spacing, quotes, tilde paths and non-dsound DLL overrides.
It adds or normalizes `BL4FIX_STEAMOS=1`, merges only `dsound=n,b` into one Wine
override, and keeps/adds one `-pf_tricks=vcrun2022` after `%command%`. Repeating
composition leaves the result unchanged. Preserving a wrapper does not verify
that it forwards these environment settings to the game or that lsfg stays active.

The composer refuses ambiguous input: shell operators, expansion such as `$VAR`
or `$(...)`, backticks, multiline/control characters, `env`/shell wrappers,
quoted/multiple/missing `%command%`, duplicate or conflicting BL4/Wine settings,
grouped dsound entries, and other/repeated `-pf_tricks` arguments (or any before
`%command%`). On refusal it keeps the original input and clipboard unchanged and
clears the preview. Preserve your saved original; **do not paste the empty-field
default over it**. Reconcile manually: keep unrelated assignments and your lsfg
wrapper, use one leading `BL4FIX_STEAMOS=1` and one leading `WINEDLLOVERRIDES`,
retain its other DLL entries while setting dsound to `n,b`, keep one `%command%`,
and place one `-pf_tricks=vcrun2022` after it. Resolve conflicting runtime tricks
using their documentation before changing them; complex shell forms need manual
review. The composer is not a general shell parser.

To undo a change, close the game, restore the saved original launch text **exactly**
in Steam and relaunch. If you choose a temporary test without lsfg, preserve the
complete original first, change only the lsfg environment assignment/wrapper for
that test, then close the game and restore the original exactly before relaunching.
This is a user-performed comparison, not an installer action or a diagnosis.

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

## Installed files but no mods

1. **Check the root and files.** Compare Steam's **Manage > Browse local files**
   with the selected game folder, then use **Health check** (or source CLI `--check`).
   Published v0.1.0 has basic checks. The enhanced **current source** check reports
   the root and compares expected SDK dependencies, selected/required mods and the UI Link
   against the package, and reports missing, changed or inaccessible files and
   loose-folder shadowing. Inspect a changed file before replacing it; another
   tool may own it. Installed counts or `Present` results are file evidence only.
2. **Check launch setup and runtime separately.** Preserve the complete current
   options, then use the manual merge guidance for v0.1.0 or Preview on current
   source builds. Note the selected Proton version
   and lsfg plugin/version. The
   [SDK FAQ](https://bl-sdk.github.io/oak2-mod-db/faq/#can-i-use-this-on-steam-decklinuxmac)
   says compatible Proton builds vary; `-pf_tricks=vcrun2022` does not prove that
   the chosen build supplied the runtime. Runtime setup or Proton changes need
   a separate, informed user decision. The installer does not install a runtime,
   switch Proton, modify Decky or delete a prefix/saves; those are not automatic
   troubleshooting steps.
3. **Check fresh SDK activation.** Launch through Steam and press tilde twice to
   open the SDK console, inspect relevant Proton/SDK errors, and run `mods` as in
   the [SDK verification instructions](https://bl-sdk.github.io/oak2-mod-db/).
   Missing logs do not prove failure; old logs do not prove this launch worked.
   A console that does not open needs investigation, including the console key
   mapping, before concluding that the loader failed.
4. **Check BL4 Fix separately.** Once the SDK console works, check **F7** for the
   BL4 Fix menu and one harmless visible mod behavior. An absent F7 menu alone
   does not diagnose the loader. Also confirm your existing lsfg remains active.

For help, provide the **complete current launch text**, chosen **Proton version**,
Steam **Browse local files path**, lsfg plugin/version, and whether double-tilde
opens the SDK console and `mods` works. If errors are needed, share only relevant
redacted excerpts; do not send saves or complete logs. File checks and automated
Linux tests do not establish physical Deck gameplay or lsfg compatibility.

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
