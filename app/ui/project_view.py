"""Project detail view: name, status, enclosure, notes, attach PDF."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable

from app.core.models import Project, VALID_STATUS


class ProjectView(ttk.Frame):
    """Edit the metadata for a single project.

    Auto-saves on focus-out / combobox change. Notes commit on focus-out.
    The `on_change` callback is invoked after each persisted change so the
    parent (MainWindow) can refresh the sidebar and recompute derived views.
    """

    def __init__(
        self,
        master: tk.Misc,
        project: Project,
        enclosure_keys: list[str],
        on_change: Callable[[], None],
        on_attach_pdf: Callable[[Path], Path],
        on_delete: Callable[[], None],
    ) -> None:
        super().__init__(master, padding=16)
        self.project = project
        self.enclosure_keys = enclosure_keys
        self.on_change = on_change
        self.on_attach_pdf = on_attach_pdf
        self.on_delete_cb = on_delete

        self._name_var = tk.StringVar(value=project.name)
        self._status_var = tk.StringVar(value=project.status)
        self._enclosure_var = tk.StringVar(value=project.enclosure)
        self._source_pdf_var = tk.StringVar(value=project.source_pdf or "(none)")

        self._build()

    # ---- UI layout -------------------------------------------------------

    def _build(self) -> None:
        row = 0

        ttk.Label(self, text="Project", font=("Segoe UI", 16, "bold")).grid(
            row=row, column=0, columnspan=3, sticky=tk.W, pady=(0, 12)
        )
        row += 1

        ttk.Label(self, text="Name").grid(row=row, column=0, sticky=tk.W, pady=4)
        name_entry = ttk.Entry(self, textvariable=self._name_var, width=40)
        name_entry.grid(row=row, column=1, sticky=tk.EW, pady=4)
        name_entry.bind("<FocusOut>", self._commit_name)
        name_entry.bind("<Return>", self._commit_name)
        row += 1

        ttk.Label(self, text="Slug").grid(row=row, column=0, sticky=tk.W, pady=4)
        self._slug_label = ttk.Label(self, text=self.project.slug, foreground="#666")
        self._slug_label.grid(row=row, column=1, sticky=tk.W, pady=4)
        row += 1

        ttk.Label(self, text="Status").grid(row=row, column=0, sticky=tk.W, pady=4)
        status_combo = ttk.Combobox(
            self,
            textvariable=self._status_var,
            values=list(VALID_STATUS),
            state="readonly",
            width=20,
        )
        status_combo.grid(row=row, column=1, sticky=tk.W, pady=4)
        status_combo.bind("<<ComboboxSelected>>", self._commit_status)
        row += 1

        ttk.Label(self, text="Enclosure").grid(row=row, column=0, sticky=tk.W, pady=4)
        enclosure_combo = ttk.Combobox(
            self,
            textvariable=self._enclosure_var,
            values=self.enclosure_keys,
            width=20,
        )
        enclosure_combo.grid(row=row, column=1, sticky=tk.W, pady=4)
        enclosure_combo.bind("<<ComboboxSelected>>", self._commit_enclosure)
        enclosure_combo.bind("<FocusOut>", self._commit_enclosure)
        row += 1

        ttk.Label(self, text="Source PDF").grid(row=row, column=0, sticky=tk.W, pady=4)
        pdf_frame = ttk.Frame(self)
        pdf_frame.grid(row=row, column=1, sticky=tk.EW, pady=4)
        self._pdf_label = ttk.Label(pdf_frame, textvariable=self._source_pdf_var, foreground="#444")
        self._pdf_label.pack(side=tk.LEFT)
        ttk.Button(pdf_frame, text="Attach PDF\u2026", command=self._attach_pdf).pack(
            side=tk.LEFT, padx=(8, 0)
        )
        row += 1

        ttk.Label(self, text="Notes").grid(row=row, column=0, sticky=tk.NW, pady=(12, 4))
        self._notes_text = tk.Text(self, width=60, height=10, wrap=tk.WORD, font=("Segoe UI", 10))
        self._notes_text.grid(row=row, column=1, columnspan=2, sticky=tk.NSEW, pady=(12, 4))
        self._notes_text.insert("1.0", self.project.notes)
        self._notes_text.bind("<FocusOut>", self._commit_notes)
        row += 1

        # Stretch the notes row / second column.
        self.grid_rowconfigure(row - 1, weight=1)
        self.grid_columnconfigure(1, weight=1)

        ttk.Separator(self, orient=tk.HORIZONTAL).grid(
            row=row, column=0, columnspan=3, sticky=tk.EW, pady=12
        )
        row += 1

        meta_frame = ttk.Frame(self)
        meta_frame.grid(row=row, column=0, columnspan=3, sticky=tk.EW)
        ttk.Label(
            meta_frame,
            text=f"Created {self.project.created_at}  \u2022  Updated {self.project.updated_at}",
            foreground="#888",
            font=("Segoe UI", 9),
        ).pack(side=tk.LEFT)
        ttk.Button(meta_frame, text="Delete Project\u2026", command=self._delete).pack(
            side=tk.RIGHT
        )

    # ---- commit handlers -------------------------------------------------

    def _commit_name(self, _event=None) -> None:
        new = self._name_var.get().strip()
        if new and new != self.project.name:
            self.project.name = new
            self.on_change()

    def _commit_status(self, _event=None) -> None:
        new = self._status_var.get()
        if new in VALID_STATUS and new != self.project.status:
            self.project.status = new  # type: ignore[assignment]
            self.on_change()

    def _commit_enclosure(self, _event=None) -> None:
        new = self._enclosure_var.get().strip()
        if new != self.project.enclosure:
            self.project.enclosure = new
            self.on_change()

    def _commit_notes(self, _event=None) -> None:
        new = self._notes_text.get("1.0", tk.END).rstrip("\n")
        if new != self.project.notes:
            self.project.notes = new
            self.on_change()

    # ---- actions ---------------------------------------------------------

    def _attach_pdf(self) -> None:
        path = filedialog.askopenfilename(
            title="Attach PedalPCB PDF",
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            dest = self.on_attach_pdf(Path(path))
        except (OSError, FileNotFoundError) as exc:
            messagebox.showerror("Attach failed", str(exc))
            return
        # on_attach_pdf is expected to mutate project.source_pdf and save.
        self._source_pdf_var.set(self.project.source_pdf or dest.name)

    def _delete(self) -> None:
        if not messagebox.askyesno(
            "Delete project",
            f"Permanently delete project {self.project.name!r} and all its files?\n\n"
            "This removes the project folder including attached PDFs and STLs.",
        ):
            return
        self.on_delete_cb()


__all__ = ["ProjectView"]
