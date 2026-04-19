"""Bench-mode build-along checklist.

Grouped view of the BOM by component class (resistors, caps, diodes,
transistors, ICs, pots, other). Each row has a checkbox. Tick marks a
location as soldered; untick clears it. Polarity-sensitive rows show a
warning glyph plus any orientation hint seeded per-pedal.

This is one of the two MVP differentiators (the other is the decoder panel).
"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
from typing import Callable

from app.core.hints import HintLibrary
from app.core.models import BOMItem, Project


# Order matters — this controls the suggested solder sequence (lowest
# profile first: easier to populate, less risk of bending leads).
GROUP_ORDER: list[tuple[str, str]] = [
    ("resistors",    "Resistors"),
    ("diodes",       "Diodes"),
    ("small_caps",   "Small caps (ceramic / film)"),
    ("ics",          "ICs / op-amps"),
    ("transistors",  "Transistors"),
    ("large_caps",   "Electrolytic caps"),
    ("pots",         "Pots"),
    ("other",        "Other"),
]


def _group_for(item: BOMItem) -> str:
    t = item.type.lower()
    v = item.value.lower()
    if "resistor" in t:
        return "resistors"
    if "diode" in t:
        return "diodes"
    if "transistor" in t:
        return "transistors"
    if "op-amp" in t or "opamp" in t or "ic" in t:
        return "ics"
    if "electrolytic" in t or "tantalum" in t:
        return "large_caps"
    if "cap" in t or "cer" in t or "film" in t:
        return "small_caps"
    # Pots are listed as e.g. "16mm right-angle PCB mount pot"
    if "pot" in t or item.location.isalpha() and v.startswith(("a", "b", "c")):
        return "pots"
    return "other"


class BenchView(ttk.Frame):
    """Tick components as you solder them."""

    def __init__(
        self,
        master: tk.Misc,
        project: Project,
        on_change: Callable[[], None],
        hints: HintLibrary | None = None,
    ) -> None:
        super().__init__(master, padding=12)
        self.project = project
        self.on_change = on_change
        self.hints = hints or HintLibrary({}, {})

        self._show_polarity_only = tk.BooleanVar(value=False)
        self._show_pending_only = tk.BooleanVar(value=False)
        self._row_vars: dict[str, tk.BooleanVar] = {}

        self._build_toolbar()
        self._scroll_frame = _ScrolledFrame(self)
        self._scroll_frame.pack(fill=tk.BOTH, expand=True)
        self._render()

    # ---- toolbar ---------------------------------------------------------

    def _build_toolbar(self) -> None:
        bar = ttk.Frame(self)
        bar.pack(fill=tk.X, pady=(0, 8))

        ttk.Label(
            bar,
            text="Bench Mode",
            font=("Segoe UI", 13, "bold"),
        ).pack(side=tk.LEFT)

        self._progress_label = ttk.Label(bar, foreground="#666")
        self._progress_label.pack(side=tk.LEFT, padx=(12, 0))

        ttk.Checkbutton(
            bar,
            text="Polarity-sensitive only",
            variable=self._show_polarity_only,
            command=self._render,
        ).pack(side=tk.RIGHT, padx=(4, 0))
        ttk.Checkbutton(
            bar,
            text="Pending only",
            variable=self._show_pending_only,
            command=self._render,
        ).pack(side=tk.RIGHT, padx=(4, 0))

    # ---- rendering -------------------------------------------------------

    def _render(self) -> None:
        for child in self._scroll_frame.inner.winfo_children():
            child.destroy()
        self._row_vars.clear()

        groups: dict[str, list[BOMItem]] = {k: [] for k, _ in GROUP_ORDER}
        for item in self.project.bom:
            groups.setdefault(_group_for(item), []).append(item)

        if not self.project.bom:
            ttk.Label(
                self._scroll_frame.inner,
                text=(
                    "No BOM yet. Import from a PedalPCB PDF on the "
                    "BOM tab to populate this checklist."
                ),
                foreground="#888",
                padding=20,
            ).pack(anchor=tk.W)
            self._refresh_progress()
            return

        for key, label in GROUP_ORDER:
            items = groups.get(key, [])
            if not items:
                continue
            visible = self._filter(items)
            if not visible:
                continue

            group_frame = ttk.LabelFrame(
                self._scroll_frame.inner,
                text=f"{label}  ({self._group_progress_text(items)})",
                padding=(8, 6),
            )
            group_frame.pack(fill=tk.X, pady=(0, 10), padx=4)
            for item in visible:
                self._render_row(group_frame, item)

        self._refresh_progress()

    def _group_progress_text(self, items: list[BOMItem]) -> str:
        done = sum(1 for i in items if i.location in self.project.progress.soldered_locations)
        return f"{done}/{len(items)}"

    def _filter(self, items: list[BOMItem]) -> list[BOMItem]:
        result = items
        if self._show_polarity_only.get():
            result = [i for i in result if i.polarity_sensitive]
        if self._show_pending_only.get():
            result = [
                i for i in result
                if i.location not in self.project.progress.soldered_locations
            ]
        return result

    def _render_row(self, parent: ttk.Frame, item: BOMItem) -> None:
        row = ttk.Frame(parent)
        row.pack(fill=tk.X, pady=1)

        done = item.location in self.project.progress.soldered_locations
        var = tk.BooleanVar(value=done)
        self._row_vars[item.location] = var

        cb = ttk.Checkbutton(
            row,
            variable=var,
            command=lambda loc=item.location, v=var: self._toggle(loc, v),
        )
        cb.pack(side=tk.LEFT)

        loc_lbl = ttk.Label(row, text=item.location, width=6, anchor=tk.W,
                            font=("Segoe UI", 10, "bold"))
        loc_lbl.pack(side=tk.LEFT, padx=(4, 4))

        ttk.Label(row, text=item.value, width=10, anchor=tk.W,
                  foreground="#333").pack(side=tk.LEFT)

        ttk.Label(row, text=item.type, anchor=tk.W, foreground="#555",
                  font=("Segoe UI", 9)).pack(side=tk.LEFT, padx=(4, 0))

        if item.polarity_sensitive:
            stored = item.orientation_hint
            fallback = self.hints.for_item(self.project.slug, item.location, item.type)
            # Stored (user-edited) hint wins; fall back to the library default.
            shown_hint = stored or fallback
            if shown_hint:
                warn_text = f"\u26A0 {shown_hint}"
            else:
                warn_text = "\u26A0"
            color = "#d35400" if stored else "#b07020"
            warn_lbl = ttk.Label(
                row, text=warn_text, foreground=color,
                font=("Segoe UI", 9, "bold" if stored else "normal"),
            )
            warn_lbl.pack(side=tk.RIGHT, padx=(8, 0))
            warn_lbl.bind("<Double-1>", lambda _e, it=item: self._edit_hint(it))

    # ---- actions ---------------------------------------------------------

    def _toggle(self, location: str, var: tk.BooleanVar) -> None:
        done = self.project.progress.soldered_locations
        if var.get():
            done.add(location)
        else:
            done.discard(location)
        self._refresh_progress()
        # Update the group header count cheaply by re-rendering.
        self._render()
        self.on_change()

    def _edit_hint(self, item: BOMItem) -> None:
        new_hint = simpledialog.askstring(
            "Orientation hint",
            f"Orientation hint for {item.location} ({item.value}):",
            initialvalue=item.orientation_hint or "",
            parent=self,
        )
        if new_hint is None:
            return
        item.orientation_hint = new_hint.strip() or None
        self._render()
        self.on_change()

    def _refresh_progress(self) -> None:
        total = len(self.project.bom)
        done = len(self.project.progress.soldered_locations)
        # Clamp — soldered_locations may contain stale entries after a BOM
        # re-import. Don't display >100%.
        done = min(done, total)
        if total == 0:
            self._progress_label.configure(text="")
            return
        pct = int(round(100 * done / total)) if total else 0
        self._progress_label.configure(text=f"{done}/{total} soldered ({pct}%)")


class _ScrolledFrame(ttk.Frame):
    """A vertically scrollable frame, because ttk.Frame doesn't scroll by default."""

    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master)
        self._canvas = tk.Canvas(self, highlightthickness=0)
        vsb = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=vsb.set)
        self._canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

        self.inner = ttk.Frame(self._canvas)
        self._window = self._canvas.create_window((0, 0), window=self.inner, anchor=tk.NW)

        self.inner.bind("<Configure>", self._on_inner_configure)
        self._canvas.bind("<Configure>", self._on_canvas_configure)
        # Mouse wheel scrolling (Windows).
        self._canvas.bind_all("<MouseWheel>", self._on_mousewheel, add="+")

    def _on_inner_configure(self, _event: tk.Event) -> None:
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))

    def _on_canvas_configure(self, event: tk.Event) -> None:
        self._canvas.itemconfigure(self._window, width=event.width)

    def _on_mousewheel(self, event: tk.Event) -> None:
        # Only scroll if the pointer is over our canvas.
        x, y = self._canvas.winfo_pointerxy()
        widget = self._canvas.winfo_containing(x, y)
        if widget is None:
            return
        # Walk up the widget tree — scroll if pointer is inside our subtree.
        w: tk.Misc | None = widget
        while w is not None:
            if w is self._canvas or w is self.inner:
                self._canvas.yview_scroll(int(-event.delta / 120), "units")
                return
            w = w.master


__all__ = ["BenchView"]
