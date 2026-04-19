"""Drill-template view: per-project hole list + STL export.

Holes table accepts inline edits on side/label/x/y/diameter/pc-margin.
`Paste Tayda...` pops a modal with a Text widget for Tayda-format input.
`Export STLs` generates one guide_<side>.stl per face that has holes.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Callable

from app.core.models import Enclosure, Hole, Project, VALID_SIDE
from app.io.stl_builder import export_all_face_guides
from app.io.tayda_import import TaydaParseError, parse_tayda_text
from app.ui.widgets import EditableTreeview


class DrillView(ttk.Frame):
    COLUMNS = ("side", "label", "x", "y", "diameter", "pc_margin")
    EDITABLE = {"side", "label", "x", "y", "diameter", "pc_margin"}

    def __init__(
        self,
        master: tk.Misc,
        project: Project,
        enclosure: Enclosure | None,
        project_dir: Path,
        on_change: Callable[[], None],
    ) -> None:
        super().__init__(master, padding=12)
        self.project = project
        self.enclosure = enclosure
        self.project_dir = project_dir
        self.on_change = on_change
        self._build()
        self._populate()

    # ---- layout ---------------------------------------------------------

    def _build(self) -> None:
        header = ttk.Frame(self)
        header.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(
            header, text="Drill Template",
            font=("Segoe UI", 13, "bold"),
        ).pack(side=tk.LEFT)
        self._encl_label = ttk.Label(header, foreground="#555")
        self._encl_label.pack(side=tk.LEFT, padx=(12, 0))

        toolbar = ttk.Frame(self)
        toolbar.pack(fill=tk.X, pady=(0, 8))
        ttk.Button(toolbar, text="Add Hole", command=self._add_hole).pack(side=tk.LEFT)
        ttk.Button(toolbar, text="Remove Selected", command=self._remove_selected).pack(
            side=tk.LEFT, padx=(4, 0)
        )
        ttk.Button(toolbar, text="Paste Tayda\u2026", command=self._paste_tayda).pack(
            side=tk.LEFT, padx=(4, 0)
        )
        ttk.Button(toolbar, text="Export STLs", command=self._export_stls).pack(
            side=tk.RIGHT
        )
        ttk.Button(toolbar, text="Open Drill Folder", command=self._open_drill_folder).pack(
            side=tk.RIGHT, padx=(0, 4)
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
        for col, label, width, anchor in [
            ("side",      "Side",        60,  tk.CENTER),
            ("label",     "Label",      140,  tk.W),
            ("x",         "X (mm)",      80,  tk.E),
            ("y",         "Y (mm)",      80,  tk.E),
            ("diameter",  "\u00D8 (mm)", 80,  tk.E),
            ("pc_margin", "+0.4 PC",     70,  tk.CENTER),
        ]:
            self._tree.heading(col, text=label)
            stretch = (col == "label")
            self._tree.column(col, width=width, anchor=anchor, stretch=stretch)

        vsb = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        self._tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

        self._status = ttk.Label(self, foreground="#666")
        self._status.pack(fill=tk.X, pady=(8, 0))

    def _populate(self) -> None:
        self._tree.delete(*self._tree.get_children())
        for idx, hole in enumerate(self.project.holes):
            self._insert_row(idx, hole)
        self._refresh_header()

    def _insert_row(self, idx: int, hole: Hole) -> None:
        self._tree.insert(
            "", tk.END, iid=str(idx),
            values=(
                hole.side,
                hole.label or "",
                f"{hole.x_mm:g}",
                f"{hole.y_mm:g}",
                f"{hole.diameter_mm:g}",
                "\u2713" if hole.powder_coat_margin else "",
            ),
        )

    def _refresh_header(self) -> None:
        if self.enclosure is None:
            self._encl_label.configure(
                text=f"\u2014 no enclosure set on this project \u2014",
                foreground="#c00",
            )
        else:
            self._encl_label.configure(
                text=(
                    f"{self.enclosure.name}  "
                    f"\u2022  {self.enclosure.length_mm:g} \u00D7 {self.enclosure.width_mm:g} "
                    f"\u00D7 {self.enclosure.height_mm:g} mm"
                ),
                foreground="#555",
            )
        by_side: dict[str, int] = {}
        for h in self.project.holes:
            by_side[h.side] = by_side.get(h.side, 0) + 1
        if by_side:
            summary = "  ".join(f"side {s}: {n}" for s, n in sorted(by_side.items()))
            self._status.configure(text=f"{len(self.project.holes)} holes  \u2022  {summary}")
        else:
            self._status.configure(text="No holes yet. Add rows or paste Tayda format.")

    # ---- cell edits -----------------------------------------------------

    def _on_cell_commit(self, iid: str, column: str, new_value: str) -> None:
        try:
            idx = int(iid)
        except ValueError:
            return
        if idx < 0 or idx >= len(self.project.holes):
            return
        hole = self.project.holes[idx]
        new_value = new_value.strip()

        try:
            if column == "side":
                side = new_value.upper()
                if side not in VALID_SIDE:
                    raise ValueError(f"Side must be one of {VALID_SIDE}")
                hole.side = side  # type: ignore[assignment]
            elif column == "label":
                hole.label = new_value or None
            elif column == "x":
                hole.x_mm = float(new_value)
            elif column == "y":
                hole.y_mm = float(new_value)
            elif column == "diameter":
                d = float(new_value)
                if d <= 0:
                    raise ValueError("Diameter must be > 0")
                hole.diameter_mm = d
            elif column == "pc_margin":
                hole.powder_coat_margin = new_value in ("\u2713", "1", "true", "True", "yes", "y")
        except (TypeError, ValueError) as exc:
            messagebox.showerror("Invalid value", f"{column}: {exc}")
            # Revert displayed cell.
            self._revert_cell(iid, idx, column)
            return

        # Rewrite the row to get consistent formatting.
        self._tree.delete(iid)
        self._insert_row(idx, hole)
        self._refresh_header()
        self.on_change()

    def _revert_cell(self, iid: str, idx: int, column: str) -> None:
        hole = self.project.holes[idx]
        revert_map = {
            "side": hole.side,
            "label": hole.label or "",
            "x": f"{hole.x_mm:g}",
            "y": f"{hole.y_mm:g}",
            "diameter": f"{hole.diameter_mm:g}",
            "pc_margin": "\u2713" if hole.powder_coat_margin else "",
        }
        if column in revert_map:
            self._tree.set(iid, column, revert_map[column])

    # ---- actions --------------------------------------------------------

    def _add_hole(self) -> None:
        hole = Hole(side="A", x_mm=0.0, y_mm=0.0, diameter_mm=7.2)
        self.project.holes.append(hole)
        self._populate()
        self.on_change()

    def _remove_selected(self) -> None:
        selected = self._tree.selection()
        if not selected:
            return
        indices = sorted((int(i) for i in selected if i.isdigit()), reverse=True)
        for idx in indices:
            if 0 <= idx < len(self.project.holes):
                del self.project.holes[idx]
        self._populate()
        self.on_change()

    def _paste_tayda(self) -> None:
        dlg = _PasteTaydaDialog(self.winfo_toplevel())
        if dlg.result is None:
            return
        text, replace_existing = dlg.result
        try:
            new_holes = parse_tayda_text(text)
        except TaydaParseError as exc:
            messagebox.showerror("Parse failed", str(exc))
            return
        if replace_existing:
            self.project.holes = list(new_holes)
        else:
            self.project.holes.extend(new_holes)
        self._populate()
        self.on_change()

    def _export_stls(self) -> None:
        if self.enclosure is None:
            messagebox.showerror(
                "No enclosure",
                "Set the enclosure on the Project tab first.",
            )
            return
        if not self.project.holes:
            messagebox.showinfo("No holes", "Add at least one hole before exporting.")
            return
        drill_dir = self.project_dir / "drill"

        # Warn about holes whose side isn't on this enclosure.
        unknown = sorted({h.side for h in self.project.holes if h.side not in self.enclosure.faces})
        if unknown:
            if not messagebox.askyesno(
                "Holes on missing sides",
                f"Holes reference side(s) {unknown} which the {self.enclosure.key} enclosure "
                "doesn't define. Those holes will be skipped. Continue?",
            ):
                return

        progress = _ExportProgressDialog(self.winfo_toplevel())
        progress.set_text("Generating STLs\u2026")
        results: dict[str, Path] = {}
        error: list[BaseException] = []

        def worker() -> None:
            try:
                results.update(
                    export_all_face_guides(self.enclosure, self.project.holes, drill_dir)
                )
            except BaseException as exc:  # noqa: BLE001
                error.append(exc)
            finally:
                self.after(0, progress.close)

        threading.Thread(target=worker, daemon=True).start()
        progress.wait()

        if error:
            messagebox.showerror("Export failed", f"{type(error[0]).__name__}: {error[0]}")
            return
        if not results:
            messagebox.showinfo("Nothing to export", "No holes mapped to valid faces.")
            return
        summary = "\n".join(f"  side {s}: {p.name} ({p.stat().st_size:,} bytes)" for s, p in sorted(results.items()))
        if messagebox.askyesno(
            "Export complete",
            f"Wrote {len(results)} STL file(s) to {drill_dir}:\n\n{summary}\n\n"
            "Open the folder?",
        ):
            self._open_drill_folder()

    def _open_drill_folder(self) -> None:
        drill_dir = self.project_dir / "drill"
        drill_dir.mkdir(parents=True, exist_ok=True)
        try:
            if sys.platform == "win32":
                os.startfile(str(drill_dir))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.run(["open", str(drill_dir)], check=False)
            else:
                subprocess.run(["xdg-open", str(drill_dir)], check=False)
        except OSError as exc:
            messagebox.showerror("Open failed", str(exc))


class _PasteTaydaDialog:
    """Modal dialog with a Text widget for pasting Tayda coordinate data."""

    def __init__(self, parent: tk.Misc) -> None:
        self.result: tuple[str, bool] | None = None

        top = tk.Toplevel(parent)
        top.title("Paste Tayda coordinates")
        top.transient(parent)
        top.grab_set()
        self.top = top

        frame = ttk.Frame(top, padding=12)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(
            frame,
            text=(
                "Paste CSV, TSV, or JSON from the Tayda Box Tool.\n"
                "Header row optional. Columns: side, diameter, x, y [, label]."
            ),
            foreground="#555",
        ).pack(anchor=tk.W, pady=(0, 6))

        self._text = tk.Text(frame, width=72, height=14, font=("Consolas", 10))
        self._text.pack(fill=tk.BOTH, expand=True)
        self._text.insert(
            "1.0",
            "side,diameter,x,y,label\nA,12.2,0,0,FOOTSWITCH\n",
        )
        self._text.focus_set()

        self._replace_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            frame,
            text="Replace existing holes (unchecked = append)",
            variable=self._replace_var,
        ).pack(anchor=tk.W, pady=(8, 0))

        buttons = ttk.Frame(frame)
        buttons.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(buttons, text="Cancel", command=self._cancel).pack(side=tk.RIGHT, padx=(4, 0))
        ttk.Button(buttons, text="Parse", command=self._ok).pack(side=tk.RIGHT)
        top.bind("<Escape>", lambda _e: self._cancel())

        parent.winfo_toplevel().wait_window(top)

    def _ok(self) -> None:
        self.result = (self._text.get("1.0", tk.END), self._replace_var.get())
        self.top.destroy()

    def _cancel(self) -> None:
        self.result = None
        self.top.destroy()


class _ExportProgressDialog:
    """Simple indeterminate-progress modal for long STL exports."""

    def __init__(self, parent: tk.Misc) -> None:
        top = tk.Toplevel(parent)
        top.title("Exporting STLs")
        top.transient(parent)
        top.grab_set()
        top.resizable(False, False)
        self.top = top

        frame = ttk.Frame(top, padding=16)
        frame.pack()
        self._label = ttk.Label(frame, text="Working\u2026")
        self._label.pack(anchor=tk.W, pady=(0, 8))
        self._bar = ttk.Progressbar(frame, mode="indeterminate", length=240)
        self._bar.pack()
        self._bar.start(12)

        # Disable closing the dialog while work is in flight.
        top.protocol("WM_DELETE_WINDOW", lambda: None)

    def set_text(self, text: str) -> None:
        self._label.configure(text=text)

    def close(self) -> None:
        try:
            self._bar.stop()
            self.top.grab_release()
            self.top.destroy()
        except tk.TclError:
            pass

    def wait(self) -> None:
        self.top.wait_window()


__all__ = ["DrillView"]
