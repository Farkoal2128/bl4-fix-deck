"""Native SteamOS setup window; frozen on Linux as BL4FixSetup-SteamOS."""

from __future__ import annotations

import argparse
import os
import queue
import shutil
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import catalog
import steamos

if not getattr(sys, "frozen", False):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "mods/bl4_direct"))
import shared

DOWNLOADS = "https://github.com/Farkoal2128/bl4-fix-deck/actions/workflows/steamos.yml"


def open_desktop(target: str) -> None:
    env = dict(os.environ)
    # System desktop programs must use system libraries, not the frozen app's copies.
    if "LD_LIBRARY_PATH_ORIG" in env:
        env["LD_LIBRARY_PATH"] = env["LD_LIBRARY_PATH_ORIG"]
    else:
        env.pop("LD_LIBRARY_PATH", None)
    subprocess.Popen(["xdg-open", target], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def add_shortcut(home: Path, executable: Path) -> Path:
    folder = home / ".local/share/bl4fix"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / "BL4FixSetup-SteamOS"
    if executable.resolve() != target.resolve():
        tmp = target.with_suffix(".new")
        shutil.copy2(executable, tmp)
        tmp.chmod(0o755)
        tmp.replace(target)
    command = str(target).replace("%", "%%")
    for char in ("\\", '"', "`", "$"):
        command = command.replace(char, "\\" + char)
    if any(ord(c) < 32 for c in command):
        raise ValueError("The shortcut path contains a control character.")
    desktop = home / ".local/share/applications/bl4fix.desktop"
    desktop.parent.mkdir(parents=True, exist_ok=True)
    desktop.write_text(
        '[Desktop Entry]\nType=Application\nName=BL4 Fix Setup\n'
        f'Exec="{command}"\nTerminal=false\nCategories=Game;Utility;\n', encoding="utf-8")
    return desktop


class App(tk.Tk):
    def __init__(self, archive: Path | None = None, game: Path | None = None):
        super().__init__()
        self.title("BL4 Fix Setup — SteamOS")
        self.geometry("1080x700")
        self.minsize(900, 610)
        self.option_add("*Font", "{DejaVu Sans} 11")
        self.archive = archive or steamos.payload_path()
        self.events = queue.Queue()
        self.busy = False
        self.buttons = []
        found = steamos.find_games(Path.home())
        self.game = tk.StringVar(value=str(game or (found[0] if len(found) == 1 else "")))
        self.status = tk.StringVar(value="Choose your game folder, tick your mods, then Apply.")
        self.shortcut = tk.BooleanVar(value=bool(getattr(sys, "frozen", False)))
        self.remove_sdk = tk.BooleanVar(value=False)
        self.mods = {m.id: tk.BooleanVar(value=m.id in catalog.DEFAULTS) for m in catalog.MODS}
        self.friend_name, self.friend_ip = tk.StringVar(), tk.StringVar()
        self.host_port = tk.StringVar(value="7777")
        self.friends = []
        self.protocol("WM_DELETE_WINDOW", self.close)

        header = ttk.Frame(self, padding=(16, 10))
        header.pack(fill="x")
        ttk.Label(header, text="BL4 FIX", font=("DejaVu Sans", 22, "bold")).pack(side="left")
        ttk.Label(header, text="SteamOS setup • Desktop Mode", padding=12).pack(side="left")
        self.button(header, "Open downloads", lambda: self.open(DOWNLOADS)).pack(side="right")
        row = ttk.Frame(self, padding=(16, 0, 16, 10))
        row.pack(fill="x")
        ttk.Label(row, text="Game folder").pack(side="left")
        self.folder = ttk.Combobox(row, textvariable=self.game, values=[str(p) for p in found])
        self.folder.pack(side="left", fill="x", expand=True, padx=10)
        self.folder.bind("<<ComboboxSelected>>", lambda _e: self.refresh())
        self.button(row, "Browse…", self.browse).pack(side="left")
        self.button(row, "Refresh", self.refresh).pack(side="left", padx=(8, 0))
        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=16)
        self.loadout = ttk.Frame(notebook, padding=10)
        self.coop = ttk.Frame(notebook, padding=12)
        self.system = ttk.Frame(notebook, padding=12)
        for frame, name in ((self.loadout, "Loadout"), (self.coop, "Friends & hosting"), (self.system, "System")):
            notebook.add(frame, text=name)
        self.build_loadout()
        self.build_coop()
        self.build_system()
        status = ttk.Label(self, textvariable=self.status, padding=(16, 9), wraplength=860)
        status.pack(fill="x")
        status.bind("<Configure>", lambda e: status.configure(wraplength=max(1, e.width - 32)))
        self.refresh()
        self.poll_id = self.after(50, self.drain)

    def button(self, parent, text, command):
        button = ttk.Button(parent, text=text, command=command)
        self.buttons.append(button)
        return button

    def build_loadout(self):
        ttk.Label(self.loadout, text="Select the mods to keep installed. Unticked mods are removed when you Apply.",
                  wraplength=950).pack(anchor="w", pady=(0, 8))
        canvas = tk.Canvas(self.loadout, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self.loadout, orient="vertical", command=canvas.yview)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(fill="both", expand=True)
        canvas.configure(yscrollcommand=scrollbar.set)
        grid = ttk.Frame(canvas)
        window = canvas.create_window((0, 0), window=grid, anchor="nw")
        grid.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(window, width=e.width))
        self.checks = []
        for i, info in enumerate(catalog.MODS):
            cell = ttk.Frame(grid, padding=(5, 3))
            cell.grid(row=i // 2, column=i % 2, sticky="nsew")
            label = info.name + (" (required)" if info.required else "")
            check = ttk.Checkbutton(cell, text=label, variable=self.mods[info.id])
            check.pack(anchor="w")
            if info.required:
                check.state(["disabled"])
            else:
                self.checks.append(check)
            ttk.Label(cell, text=info.blurb, wraplength=450, font=("DejaVu Sans", 9)).pack(anchor="w", padx=22)
        for col in (0, 1):
            grid.columnconfigure(col, weight=1)
        row = ttk.Frame(self.loadout, padding=(0, 8, 0, 0))
        row.pack(fill="x")
        self.button(row, "All mods", lambda: self.select(set(catalog.BY_ID))).pack(side="left")
        self.button(row, "Required only", lambda: self.select(set(catalog.REQUIRED))).pack(side="left", padx=8)
        self.button(row, "Apply selection", self.apply).pack(side="right")

    def build_coop(self):
        ttk.Label(self.coop, text="Friends are shared with Direct Connect's in-game F6 page.").pack(anchor="w")
        self.friend_list = tk.Listbox(self.coop, height=7, exportselection=False)
        self.friend_list.pack(fill="both", expand=True, pady=10)
        row = ttk.Frame(self.coop)
        row.pack(fill="x")
        for label, variable in (("Name", self.friend_name), ("IPv4 address", self.friend_ip)):
            ttk.Label(row, text=label).pack(side="left", padx=(0, 5))
            ttk.Entry(row, textvariable=variable, width=22).pack(side="left", padx=(0, 10))
        self.button(row, "Add / replace", self.add_friend).pack(side="left")
        self.button(row, "Remove selected", self.remove_friend).pack(side="left", padx=8)
        row = ttk.Frame(self.coop, padding=(0, 12))
        row.pack(fill="x")
        ttk.Label(row, text="Host UDP port").pack(side="left")
        ttk.Entry(row, textvariable=self.host_port, width=8).pack(side="left", padx=10)
        self.button(row, "Save port", self.save_port).pack(side="left")
        ttk.Label(self.coop, wraplength=940, text="Hosting: forward this UDP port on your router and configure your Linux firewall. "
                  "The friends list is not a firewall allowlist. Joining needs no incoming rule. "
                  "BL4 Fix does not change SteamOS firewall settings.").pack(anchor="w", pady=8)

    def build_system(self):
        ttk.Label(self.system, text="Steam launch options", font=("DejaVu Sans", 12, "bold")).pack(anchor="w")
        self.launch_original = tk.StringVar()
        self.launch_composed = tk.StringVar(value=steamos.compose_launch_options(""))
        ttk.Label(self.system, text="Original Steam launch options (empty = Steam currently has no options)").pack(anchor="w")
        self.launch_input = ttk.Entry(self.system, textvariable=self.launch_original)
        self.launch_input.pack(fill="x", pady=(2, 4))
        ttk.Label(self.system, text="Composed preview (read-only; cleared when original input changes)").pack(anchor="w")
        self.launch_preview = ttk.Entry(self.system, textvariable=self.launch_composed, state="readonly")
        self.launch_preview.pack(fill="x", pady=(2, 4))
        self.launch_original.trace_add("write", self.launch_edited)
        row = ttk.Frame(self.system)
        row.pack(fill="x")
        self.button(row, "Preview", self.preview_options).pack(side="left", padx=(0, 8))
        self.button(row, "Copy launch options", self.copy_options).pack(side="left")
        self.button(row, "Launch game", lambda: self.open(f"steam://rungameid/{steamos.APP_ID}")).pack(side="left", padx=8)
        ttk.Label(self.system, wraplength=810, text="Paste composed text in Steam → Borderlands 4 → Properties → Launch Options. "
                  "Unsupported syntax: keep your original text and merge manually. Wrapper environment forwarding is unverified. "
                  "Map a rear grip to F7. Automatic save restores/file updates are unavailable; use Desktop Mode.").pack(anchor="w", pady=6)
        shortcut = ttk.Checkbutton(self.system, text="Add BL4 Fix Setup to the application menu after Apply", variable=self.shortcut)
        shortcut.pack(anchor="w")
        if not getattr(sys, "frozen", False):
            shortcut.state(["disabled"])
        ttk.Checkbutton(self.system, text="Also remove the Python SDK when uninstalling", variable=self.remove_sdk).pack(anchor="w", pady=8)
        row = ttk.Frame(self.system)
        row.pack(fill="x")
        self.button(row, "Repair selected mods", self.apply).pack(side="left")
        self.button(row, "Health check", self.health).pack(side="left", padx=8)
        self.button(row, "Finish pending UI change", self.finish).pack(side="left")
        self.button(row, "Uninstall…", self.uninstall).pack(side="right")
        self.log_box = tk.Text(self.system, height=1, wrap="word", state="disabled", font=("DejaVu Sans Mono", 9))
        self.log_box.pack(fill="both", expand=True, pady=(6, 0))

    def current_game(self):
        if not self.game.get().strip():
            raise ValueError("Choose the Borderlands 4 folder containing OakGame.")
        return steamos.game_folder(Path(self.game.get()).expanduser())

    def browse(self):
        path = filedialog.askdirectory(parent=self, title="Choose the folder containing OakGame")
        if path:
            self.game.set(path)
            self.refresh()

    def select(self, ids):
        for info in catalog.MODS:
            self.mods[info.id].set(info.required or info.id in ids)

    def refresh(self):
        try:
            game = self.current_game()
            installed = steamos.installed_mods(game)
            self.select(installed if installed or steamos.read_record(game) else set(catalog.DEFAULTS))
            config = shared.Config.load(game / "sdk_mods/settings" / shared.FRIENDS_FILE_NAME)
            self.friends = config.friends
            self.host_port.set(str(config.host_port))
            self.render_friends()
            self.status.set(f"{len(installed)} mods installed. Ready to apply your selection.")
        except (OSError, ValueError) as ex:
            self.status.set(str(ex))

    def render_friends(self):
        self.friend_list.delete(0, "end")
        for friend in self.friends:
            self.friend_list.insert("end", f"{friend.name} — {friend.address}:{friend.port}")

    def save_config(self, edit):
        try:
            game = self.current_game()
            steamos.ensure_closed()
            path = steamos.safe_target(game, "sdk_mods/settings/" + shared.FRIENDS_FILE_NAME)
            config = shared.Config.load(path)
            edit(config)
            config.save(path)
            self.friends = config.friends
            self.render_friends()
            self.status.set("Friends and hosting settings saved.")
        except (OSError, ValueError, RuntimeError) as ex:
            messagebox.showerror("BL4 Fix", str(ex), parent=self)

    def add_friend(self):
        def edit(config):
            name = self.friend_name.get().strip()
            ip = shared.normalize_ipv4(self.friend_ip.get())
            if not name or len(name) > 48 or not name.isprintable() or ip is None:
                raise ValueError("Enter a name (up to 48 characters) and a valid IPv4 address.")
            config.friends = [f for f in config.friends if f.name.casefold() != name.casefold()]
            config.friends.append(shared.Friend(name, ip))
        self.save_config(edit)

    def remove_friend(self):
        selection = self.friend_list.curselection()
        if selection:
            name = self.friends[selection[0]].name
            self.save_config(lambda c: setattr(c, "friends", [f for f in c.friends if f.name != name]))

    def save_port(self):
        def edit(config):
            port = int(self.host_port.get())
            if not 1024 <= port <= 65535:
                raise ValueError("Choose a host port from 1024 to 65535.")
            config.host_port = port
        self.save_config(edit)

    def log(self, message):
        self.events.put(("log", str(message)))

    def task(self, label, action):
        if self.busy:
            return
        self.busy = True
        for button in [*self.buttons, *self.checks, self.folder]:
            button.state(["disabled"])
        self.status.set(label + "… Keep this window open.")
        def run():
            try:
                result = action()
                self.events.put(("done", str(result or label + " complete.")))
            except Exception as ex:
                self.events.put(("error", str(ex)))
        threading.Thread(target=run, daemon=True).start()

    def drain(self):
        while not self.events.empty():
            kind, message = self.events.get_nowait()
            if kind == "log":
                self.log_box.configure(state="normal")
                self.log_box.insert("end", message + "\n")
                self.log_box.see("end")
                self.log_box.configure(state="disabled")
            else:
                self.busy = False
                for button in [*self.buttons, *self.checks, self.folder]:
                    button.state(["!disabled"])
                self.refresh()
                self.status.set(message)
                if kind == "error":
                    messagebox.showerror("BL4 Fix", message, parent=self)
        self.poll_id = self.after(50, self.drain)

    def apply(self, confirm=True):
        try:
            game = self.current_game()
            chosen = {m for m, value in self.mods.items() if value.get()}
            removed = steamos.installed_mods(game) - chosen
            if confirm and removed and not messagebox.askyesno("Apply selection", "Remove these mods?\n\n" +
                    "\n".join(catalog.BY_ID[m].name for m in sorted(removed)) + "\n\nSettings and saves are kept.", parent=self):
                return
            shortcut = self.shortcut.get()
            def run():
                backup = steamos.install(game, self.archive, chosen, self.log)
                if shortcut:
                    try:
                        add_shortcut(Path.home(), Path(sys.executable))
                    except (OSError, ValueError) as ex:
                        self.log(f"Installed, but could not create the app-menu shortcut: {ex}")
                return f"Files installed. Launch setup/SDK verification pending. Backup: {backup}. Use System."
            self.task("Installing", run)
        except (OSError, ValueError) as ex:
            messagebox.showerror("BL4 Fix", str(ex), parent=self)

    def uninstall(self):
        try:
            game = self.current_game()
            remove_sdk = self.remove_sdk.get()
            if messagebox.askyesno("Uninstall BL4 Fix", "Remove BL4 Fix mods" + (" and the SDK" if remove_sdk else "") +
                    "?\n\nSaves, settings, other mods and backups are kept. Intro movies are restored.", parent=self):
                self.task("Uninstalling", lambda: f"Uninstalled. Backup: {steamos.uninstall(game, remove_sdk, self.log)}")
        except (OSError, ValueError) as ex:
            messagebox.showerror("BL4 Fix", str(ex), parent=self)

    def health(self):
        try:
            game = self.current_game()
            self.task("Checking files", lambda: self.log("File status (not runtime activation):\n" + "\n".join(steamos.health(game, self.archive))))
        except (OSError, ValueError) as ex:
            messagebox.showerror("BL4 Fix", str(ex), parent=self)

    def finish(self):
        try:
            game = self.current_game()
            self.task("Finishing UI change", lambda: f"UI change checked. Backup: {steamos.finish(game) or 'none needed'}")
        except (OSError, ValueError) as ex:
            messagebox.showerror("BL4 Fix", str(ex), parent=self)

    def launch_edited(self, *_args):
        self.launch_composed.set("")
        self.status.set("Original input changed; preview cleared. Preview or copy to validate.")

    def preview_options(self):
        try:
            composed = steamos.compose_launch_options(self.launch_original.get())
        except ValueError as ex:
            self.launch_composed.set("")
            self.status.set(str(ex))
            return None
        self.launch_composed.set(composed)
        self.status.set("Preview ready. Wrapper environment forwarding and SDK activation remain unverified.")
        return composed

    def copy_options(self):
        composed = self.preview_options()
        if composed is None:
            return
        self.clipboard_clear()
        self.clipboard_append(composed)
        self.status.set("Copied composed options. Paste into Steam Launch Options, then verify the SDK console and F7 menu.")

    def open(self, target):
        try:
            open_desktop(target)
        except OSError as ex:
            messagebox.showerror("BL4 Fix", str(ex), parent=self)

    def close(self):
        if self.busy:
            messagebox.showinfo("BL4 Fix", "Wait for the current operation to finish before closing.", parent=self)
        else:
            self.destroy()

    def destroy(self):
        if getattr(self, "poll_id", None) is not None:
            self.after_cancel(self.poll_id)
            self.poll_id = None
        super().destroy()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--game", type=Path)
    parser.add_argument("--smoke-test", action="store_true", help="check bundled payload and create the setup window, then exit")
    args = parser.parse_args()
    if hasattr(os, "geteuid") and os.geteuid() == 0 and not args.smoke_test:
        raise SystemExit("Run BL4 Fix Setup as your Steam user, without sudo.")
    app = App(args.archive, args.game)
    if args.smoke_test:
        import zipfile
        with zipfile.ZipFile(app.archive) as zf:
            assert zf.testzip() is None
            assert all(f"sdk_mods/{m.id}.sdkmod" in zf.namelist() for m in catalog.MODS)
        app.update()
        app.destroy()
        print("PASS: bundled setup window, Tk runtime and all catalog payloads")
    else:
        app.mainloop()


if __name__ == "__main__":
    main()
