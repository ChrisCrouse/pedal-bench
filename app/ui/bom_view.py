"""BOM editor: Treeview with inline cell edit, add/remove rows, import-from-PDF."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Callable

from app.core.models import BOMItem, Project, is_polarity_sensitive
from app.ui.widgets import EditableTreeview


class BOMView(ttk.Frame):
    """Edit a project's BOM in place."""

    COLUMNS = ("location", "value", "type", "notes", "polarity", "qty")
    EDITABLE = {"location", "value", "type", "notes", "qty"}
    POLARITY_MARK = "\u26A0"  # ⚠

    def __init__(
        self,
        master: tk.Misc,
        project: Project,
        on_change: Callable[[], None],
        on_import_from_pdf: Callable[[], list[BOMItem] | None],
    ) -> None:
        super().__init__(master, padding=12)
        self.project = project
        self.on_change = on_change
        self.on_import_from_pdf = on_import_from_pdf
        self._build()
        self._populate()

    # ---- UI layout -------------------------------------------------------

    def _build(self) -> None:
        toolbar = ttk.Frame(self)
        toolbar.pack(fill=tk.X, pady=(0, 8))

        ttk.Label(
            toolbar,
            text="Bill of Materials",
            font=("Segoe UI", 13, "bold"),
        ).pack(side=tk.LEFT)

        ttk.Button(toolbar, text="Import from PDF", command=self._do_import).pack(
            side=tk.RIGHT, padx=(4, 0)
        )
        ttk.Button(toolbar, text="Remove Selected", command=self._remove_selected).pack(
            side=tk.RIGHT, padx=(4, 0)
        )
        ttk.Button(toolbar, text="Add Row", command=self._add_row).pack(
            side=tk.RIGHT, padx=(4, 0)
        )

        tree_frame = ttk.Frame(self)
        tree_frame.pack(fill=tk.BOTH, expand=True)

        self._tree = EditableTreeview(
            tree_frame,
            columns=self.COLUMNS,
            editable_columns=self.EDITABLE,
            on_commit=self._on_cell_commit,
            selectmode="extended",
        )
        for col, label, width in [
            ("location", "Loc",       70),
            ("value",    "Value",     90),
            ("type",     "Type",     260),
            ("notes",    "Notes",    200),
            ("polarity", "\u26A0",    40),
            ("qty",      "Qty",       50),
        ]:
            self._tree.heading(col, text=label)
            anchor = tk.CENTER if col in ("polarity", "qty") else tk.W
            self._tree.column(col, width=width, anchor=anchor, stretch=(col == "type"))
        self._tree.tag_configure("polarity", foreground="#d35400")

        vsb = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        self._tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

        self._count_label = ttk.Label(self, foreground="#666")
        self._count_label.pack(fill=tk.X, pady=(8, 0))

    def _populate(self) -> None:
        self._tree.delete(*self._tree.get_children())
        for index, item in enumerate(self.project.bom):
            self._insert_row(index, item)
        self._refresh_count()

    def _insert_row(self, index: int, item: BOMItem) -> None:
        iid = str(index)
        tag = ("polarity",) if item.polarity_sensitive else ()
        self._tree.insert(
            "",
            tk.END,
            iid=iid,
            values=(
                item.location,
                item.value,
                item.type,
                item.notes,
                self.POLARITY_MARK if item.polarity_sensitive else "",
                item.quantity,
            ),
            tags=tag,
        )

    def _refresh_count(self) -> None:
        polar = sum(1 for b in self.project.bom if b.polarity_sensitive)
        self._count_label.configure(
            text=f"{len(self.project.bom)} items  \u2022  {polar} polarity-sensitive"
        )

    # ---- edit handlers ---------------------------------------------------

    def _on_cell_commit(self, iid: str, column: str, new_value: str) -> None:
        try:
            index = int(iid)
        except ValueError:
            return
        if index < 0 or index >= len(self.project.bom):
            return
        item = self.project.bom[index]

        if column == "qty":
            try:
                qty = int(new_value.strip())
                if qty < 1:
                    raise ValueError
            except ValueError:
                messagebox.showerror(
                    "Invalid quantity",
                    f"Quantity must be a positive integer. Got {new_value!r}.",
                )
                self._tree.set(iid, "qty", str(item.quantity))
                return
            item.quantity = qty
        elif column == "location":
            item.location = new_value.strip()
        elif column == "value":
            item.value = new_value.strip()
        elif column == "type":
            item.type = new_value.strip()
            # Re-tag polarity on type changes.
            was_polar = item.polarity_sensitive
            item.polarity_sensitive = is_polarity_sensitive(item.type)
            if was_polar != item.polarity_sensitive:
                tag = ("polarity",) if item.polarity_sensitive else ()
                self._tree.item(iid, tags=tag)
                self._tree.set(
                    iid, "polarity",
                    self.POLARITY_MARK if item.polarity_sensitive else "",
                )
        elif column == "notes":
            item.notes = new_value.strip()

        self._refresh_count()
        self.on_change()

    # ---- actions ---------------------------------------------------------

    def _add_row(self) -> None:
        self.project.bom.append(BOMItem(location="", value="", type=""))
        self._populate()
        self.on_change()

    def _remove_selected(self) -> None:
        selected = self._tree.selection()
        if not selected:
            return
        # Remove in reverse so indices stay valid.
        indices = sorted(
            (int(i) for i in selected if i.isdigit()),
            reverse=True,
        )
        for idx in indices:
            if 0 <= idx < len(self.project.bom):
                del self.project.bom[idx]
        self._populate()
        self.on_change()

    def _do_import(self) -> None:
        if self.project.bom:
            if not messagebox.askyesno(
                "Replace BOM?",
                f"This project already has {len(self.project.bom)} BOM rows. "
                "Importing will replace them. Continue?",
            ):
                return
        new_items = self.on_import_from_pdf()
        if new_items is None:
            return
        self.project.bom = new_items
        self._populate()
        self.on_change()


__all__ = ["BOMView"]
