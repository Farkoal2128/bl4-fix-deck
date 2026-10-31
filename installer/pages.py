"""Portable startup page definitions and loader shared by both installers."""

from __future__ import annotations

import sys
from pathlib import Path

PAGE_SCRIPTS: tuple[tuple[str, str, str], ...] = (
    ("bl4_mod_menu", "ui", "bl4modmenu"),
    ("bl4_instant_tabs", "ui", "bl4instanttabs"),
    # The link's boot.js must be there when the game creates its pages (before any mod runs)
    ("bl4_builds", "uilink/ui", "bl4link"),
    ("bl4_tidy_pause", "uilink/ui", "bl4link"),
    ("bl4_reroll", "uilink/ui", "bl4link"),
    ("bl4_uvh_teleport", "uilink/ui", "bl4link"),
    ("bl4_damage_meter", "uilink/ui", "bl4link"),
    ("bl4_weapondex", "uilink/ui", "bl4link"),
    ("bl4_mod_menu", "uilink/ui", "bl4link"),
    ("bl4_item_cards", "uilink/ui", "bl4link"),
    ("bl4_respec", "uilink/ui", "bl4link"),
    ("bl4_instant_tabs", "uilink/ui", "bl4link"),
    ("bl4_item_pictures", "uilink/ui", "bl4link"),
)


def load_page_module(root: Path, mod_id: str, module: str):  # noqa: ANN202
    """
    Imports `<mod>.<module>` from an unpacked copy of the mod without running the mod's own
    __init__ (which needs the game): a stand-in parent package under a private name.
    """
    import importlib  # noqa: PLC0415
    import types  # noqa: PLC0415

    alias = f"_bl4setup_{mod_id}"
    for name in [n for n in sys.modules if n == alias or n.startswith(alias + ".")]:
        del sys.modules[name]
    package = types.ModuleType(alias)
    package.__path__ = [str(root / mod_id)]  # type: ignore[attr-defined]
    sys.modules[alias] = package
    return importlib.import_module(f"{alias}.{module}")
