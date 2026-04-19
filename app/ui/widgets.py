"""Reusable tkinter widgets.

EditableTreeview — ttk.Treeview with double-click-to-edit cell overlays.
RESISTOR_BAND_HEX — color name -> hex for the decoder's visual band display.

ZoomPanCanvas lands with the wiring viewer (Phase 3.5).
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable, Iterable


# Visual colors for resistor color-code bands. "grey" uses a darker shade
# than "white"; "gold"/"silver" approximate metallic sheens.
RESISTOR_BAND_HEX: dict[str, str] = {
    "black":  "#111111",
    "brown":  "#7a4a1d",
    "red":    "#d32f2f",
    "orange": "#ef6c00",
    "yellow": "#fbc02d",
    "green":  "#388e3c",
    "blue":   "#1976d2",
    "violet": "#7b1fa2",
    "grey":   "#616161",
    "white":  "#f5f5f5",
    "gold":   "#b8860b",
    "silver": "#9e9e9e",
}

# A light-gray text color that reads against all of the above.
_BAND_FG = {
    "black": "#ffffff",
    "brown": "#ffffff",
    "red": "#ffffff",
    "orange": "#000000",
    "yellow": "#000000",
    "green": "#ffffff",
    "blue": "#ffffff",
    "violet": "#ffffff",
    "grey": "#ffffff",
    "white": "#000000",
    "gold": "#000000",
    "silver": "#000000",
}


def band_fg(color: str) -> str:
    return _BAND_FG.get(color, "#000000")


class EditableTreeview(ttk.Treeview):
    """ttk.Treeview with in-cell editing via an overlay Entry.

    Columns marked editable accept a double-click to pop a single-line
    Entry widget over the cell. Pressing Enter commits; Escape cancels.
    A commit fires the on_commit callback with (item_id, column_id, new_value).
    """

    def __init__(
        self,
        master: tk.Misc,
        *,
        columns: Iterable[str],
        editable_columns: Iterable[str] = (),
        on_commit: Callable[[str, str, str], None] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(master, columns=tuple(columns), **kwargs)
        self._editable = set(editable_columns)
        self._on_commit = on_commit
        self._edit_entry: tk.Entry | None = None
        self.bind("<Double-1>", self._on_double_click, add="+")
        # Hide the default #0 tree column by default — callers can still
        # enable it with show="tree headings".
        if "show" not in kwargs:
            self.configure(show="headings")

    def _on_double_click(self, event: tk.Event) -> None:
        region = self.identify_region(event.x, event.y)
        if region != "cell":
            return
        row = self.identify_row(event.y)
        column = self.identify_column(event.x)  # returns "#1", "#2", ...
        if not row or not column:
            return
        col_idx = int(column.replace("#", "")) - 1
        cols = self.cget("columns")
        if col_idx < 0 or col_idx >= len(cols):
            return
        col_name = cols[col_idx]
        if col_name not in self._editable:
            return
        self._begin_edit(row, column, col_name)

    def _begin_edit(self, row: str, column: str, col_name: str) -> None:
        self._cancel_edit()
        bbox = self.bbox(row, column)
        if not bbox:
            return
        x, y, w, h = bbox
        value = self.set(row, col_name)
        entry = tk.Entry(self, borderwidth=1, relief="solid")
        entry.insert(0, value)
        entry.select_range(0, tk.END)
        entry.focus_set()
        entry.place(x=x, y=y, width=w, height=h)

        def commit(_event: tk.Event | None = None) -> None:
            new_value = entry.get()
            self.set(row, col_name, new_value)
            self._cancel_edit()
            if self._on_commit is not None:
                self._on_commit(row, col_name, new_value)

        def cancel(_event: tk.Event | None = None) -> None:
            self._cancel_edit()

        entry.bind("<Return>", commit)
        entry.bind("<KP_Enter>", commit)
        entry.bind("<Escape>", cancel)
        entry.bind("<FocusOut>", commit)
        self._edit_entry = entry

    def _cancel_edit(self) -> None:
        if self._edit_entry is not None:
            try:
                self._edit_entry.destroy()
            except tk.TclError:
                pass
            self._edit_entry = None


class StatusBar(ttk.Frame):
    """A tiny status bar. Left label for messages, right label for hints."""

    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master)
        self._left = ttk.Label(self, text="", anchor=tk.W, padding=(8, 2))
        self._right = ttk.Label(self, text="", anchor=tk.E, padding=(8, 2))
        self._left.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self._right.pack(side=tk.RIGHT)

    def set(self, text: str) -> None:
        self._left.configure(text=text)

    def set_hint(self, text: str) -> None:
        self._right.configure(text=text)


__all__ = ["EditableTreeview", "StatusBar", "RESISTOR_BAND_HEX", "band_fg"]
