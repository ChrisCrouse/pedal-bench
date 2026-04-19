"""Tkinter entry point for the DIY Pedal Build Assistant.

Run with:
    python -m app.main
"""

from __future__ import annotations

import json
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from app.core.hints import HintLibrary
from app.core.inventory_store import InventoryStore
from app.core.models import Enclosure
from app.core.project_store import ProjectStore
from app.ui.main_window import MainWindow


def _enable_hidpi() -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        pass


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _load_enclosures(path: Path) -> dict[str, Enclosure]:
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    encs: dict[str, Enclosure] = {}
    for key, entry in data.items():
        if key.startswith("_"):
            continue
        encs[key] = Enclosure.from_json(key, entry)
    return encs


def main() -> None:
    _enable_hidpi()

    root_dir = _project_root()
    project_store = ProjectStore(root_dir / "projects")
    inventory_store = InventoryStore(root_dir / "inventory.json")
    enclosures = _load_enclosures(root_dir / "app" / "data" / "enclosures.json")
    hints = HintLibrary.load(root_dir / "app" / "data" / "orientation_hints.json")

    tk_root = tk.Tk()
    tk_root.title("DIY Pedal Build Assistant")
    tk_root.geometry("1280x780")
    tk_root.minsize(960, 600)
    try:
        ttk.Style().theme_use("vista" if sys.platform == "win32" else "clam")
    except tk.TclError:
        pass

    # Report unexpected errors in a dialog rather than silently dying.
    def _on_tk_error(exc, val, tb) -> None:
        messagebox.showerror(
            "Unexpected error",
            f"{exc.__name__}: {val}",
        )
    tk_root.report_callback_exception = _on_tk_error  # type: ignore[assignment]

    MainWindow(
        tk_root,
        project_store=project_store,
        inventory_store=inventory_store,
        enclosures=enclosures,
        hints=hints,
    )
    tk_root.mainloop()


if __name__ == "__main__":
    main()
