"""Main application window: sidebar + notebook + decoder panel."""

from __future__ import annotations

import json
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable

from app.core.hints import HintLibrary
from app.core.inventory_store import InventoryStore
from app.core.models import BOMItem, Enclosure, Project, VALID_STATUS
from app.core.project_store import ProjectStore, slugify
from app.io.pedalpcb_pdf import BOMParseError, extract_bom
from app.io.pdf_page_image import render_page_to_png
from app.ui.bench_view import BenchView
from app.ui.bom_view import BOMView
from app.ui.decoder_panel import DecoderPanel
from app.ui.drill_view import DrillView
from app.ui.project_view import ProjectView
from app.ui.widgets import StatusBar


class MainWindow:
    """Owns top-level state and orchestrates the views."""

    def __init__(
        self,
        root: tk.Tk,
        project_store: ProjectStore,
        inventory_store: InventoryStore,
        enclosures: dict[str, Enclosure],
        hints: HintLibrary,
    ) -> None:
        self.root = root
        self.project_store = project_store
        self.inventory_store = inventory_store
        self.enclosures = enclosures
        self.hints = hints

        self.current: Project | None = None
        self._project_view: ProjectView | None = None
        self._bom_view: BOMView | None = None
        self._bench_view: BenchView | None = None
        self._drill_view: DrillView | None = None

        self._build_menu()
        self._build_layout()
        self._refresh_sidebar()

    # ---- layout ---------------------------------------------------------

    def _build_menu(self) -> None:
        menubar = tk.Menu(self.root)

        file_menu = tk.Menu(menubar, tearoff=False)
        file_menu.add_command(label="New Project\u2026", command=self._new_project, accelerator="Ctrl+N")
        file_menu.add_command(label="Import BOM from PDF\u2026", command=self._import_bom_from_pdf)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.root.destroy)
        menubar.add_cascade(label="File", menu=file_menu)

        view_menu = tk.Menu(menubar, tearoff=False)
        view_menu.add_command(label="Project", command=lambda: self._select_tab(0))
        view_menu.add_command(label="BOM", command=lambda: self._select_tab(1))
        view_menu.add_command(label="Bench Mode", command=lambda: self._select_tab(2))
        view_menu.add_command(label="Drill Template", command=lambda: self._select_tab(3))
        menubar.add_cascade(label="View", menu=view_menu)

        help_menu = tk.Menu(menubar, tearoff=False)
        help_menu.add_command(label="About", command=self._show_about)
        menubar.add_cascade(label="Help", menu=help_menu)

        self.root.config(menu=menubar)
        self.root.bind("<Control-n>", lambda _e: self._new_project())

    def _build_layout(self) -> None:
        outer = ttk.Frame(self.root)
        outer.pack(fill=tk.BOTH, expand=True)

        paned = ttk.PanedWindow(outer, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True)

        # Sidebar: projects list + New button.
        sidebar = ttk.Frame(paned, width=220)
        sidebar.pack_propagate(False)
        ttk.Label(
            sidebar, text="Projects",
            font=("Segoe UI", 11, "bold"),
        ).pack(anchor=tk.W, padx=8, pady=(8, 4))
        self._projects_list = tk.Listbox(sidebar, activestyle="dotbox", exportselection=False)
        self._projects_list.pack(fill=tk.BOTH, expand=True, padx=4, pady=(0, 4))
        self._projects_list.bind("<<ListboxSelect>>", self._on_sidebar_select)
        ttk.Button(sidebar, text="+ New Project\u2026", command=self._new_project).pack(
            fill=tk.X, padx=4, pady=(0, 8)
        )
        paned.add(sidebar, weight=0)

        # Content area: Notebook with per-project tabs.
        self._content = ttk.Frame(paned)
        self._notebook = ttk.Notebook(self._content)
        self._notebook.pack(fill=tk.BOTH, expand=True)
        self._show_placeholder()
        paned.add(self._content, weight=1)

        # Right-side decoder dock.
        self._decoder = DecoderPanel(paned)
        paned.add(self._decoder, weight=0)

        # Status bar below the paned window.
        self._status = StatusBar(outer)
        self._status.pack(side=tk.BOTTOM, fill=tk.X)
        self._status.set("Ready")
        self._status.set_hint(
            f"{len(self.enclosures)} enclosures loaded"
        )

    # ---- sidebar / project switching ------------------------------------

    def _refresh_sidebar(self) -> None:
        selected_slug = None
        sel = self._projects_list.curselection()
        if sel:
            selected_slug = self._projects_list.get(sel[0]).split("  ", 1)[0]

        self._projects_list.delete(0, tk.END)
        slugs = self.project_store.list_slugs()
        self._all_slugs = slugs
        for slug in slugs:
            try:
                p = self.project_store.load(slug)
            except Exception:
                self._projects_list.insert(tk.END, f"{slug}  (corrupted)")
                continue
            self._projects_list.insert(tk.END, f"{slug}  {_status_badge(p.status)}")

        # Restore selection if still present.
        if selected_slug and selected_slug in slugs:
            idx = slugs.index(selected_slug)
            self._projects_list.selection_set(idx)

    def _on_sidebar_select(self, _event=None) -> None:
        sel = self._projects_list.curselection()
        if not sel:
            return
        slug = self._all_slugs[sel[0]]
        try:
            project = self.project_store.load(slug)
        except Exception as exc:
            messagebox.showerror("Load failed", f"Could not open {slug!r}: {exc}")
            return
        self._open_project(project)

    def _open_project(self, project: Project) -> None:
        self.current = project
        self._rebuild_notebook()
        self._status.set(f"Loaded {project.slug}")

    def _show_placeholder(self) -> None:
        for tab_id in self._notebook.tabs():
            self._notebook.forget(tab_id)
        placeholder = ttk.Frame(self._notebook, padding=32)
        ttk.Label(
            placeholder,
            text="DIY Pedal Build Assistant",
            font=("Segoe UI", 18, "bold"),
        ).pack(anchor=tk.W)
        ttk.Label(
            placeholder,
            text="Pick a project from the sidebar, or create a new one with File \u2192 New Project.",
            foreground="#666",
        ).pack(anchor=tk.W, pady=(4, 0))
        self._notebook.add(placeholder, text="Welcome")

    def _rebuild_notebook(self) -> None:
        if self.current is None:
            self._show_placeholder()
            return

        for tab_id in self._notebook.tabs():
            self._notebook.forget(tab_id)

        self._project_view = ProjectView(
            self._notebook,
            self.current,
            enclosure_keys=sorted(self.enclosures.keys()),
            on_change=self._save_current,
            on_attach_pdf=self._attach_pdf_to_current,
            on_delete=self._delete_current,
        )
        self._notebook.add(self._project_view, text="Project")

        self._bom_view = BOMView(
            self._notebook,
            self.current,
            on_change=self._save_current,
            on_import_from_pdf=self._import_bom_for_current,
        )
        self._notebook.add(self._bom_view, text="BOM")

        self._bench_view = BenchView(
            self._notebook,
            self.current,
            on_change=self._save_current,
            hints=self.hints,
        )
        self._notebook.add(self._bench_view, text="Bench")

        encl = self.enclosures.get(self.current.enclosure)
        self._drill_view = DrillView(
            self._notebook,
            self.current,
            enclosure=encl,
            project_dir=self.project_store.project_dir(self.current.slug),
            on_change=self._save_current,
        )
        self._notebook.add(self._drill_view, text="Drill")

    def _select_tab(self, index: int) -> None:
        tabs = self._notebook.tabs()
        if 0 <= index < len(tabs):
            self._notebook.select(tabs[index])

    # ---- persistence ----------------------------------------------------

    def _save_current(self) -> None:
        if self.current is None:
            return
        try:
            self.project_store.save(self.current)
            self._status.set(f"Saved {self.current.slug}")
        except OSError as exc:
            messagebox.showerror("Save failed", str(exc))

    # ---- menu/button actions --------------------------------------------

    def _new_project(self) -> None:
        result = NewProjectDialog.ask(
            self.root,
            enclosure_keys=sorted(self.enclosures.keys()),
        )
        if result is None:
            return
        name, enclosure = result
        try:
            project = self.project_store.create(name, enclosure=enclosure)
        except FileExistsError:
            messagebox.showerror(
                "Already exists",
                f"A project with slug {slugify(name)!r} already exists.",
            )
            return
        except ValueError as exc:
            messagebox.showerror("Invalid name", str(exc))
            return
        self._refresh_sidebar()
        # Select the new project in the sidebar.
        if project.slug in self._all_slugs:
            idx = self._all_slugs.index(project.slug)
            self._projects_list.selection_clear(0, tk.END)
            self._projects_list.selection_set(idx)
            self._projects_list.see(idx)
        self._open_project(project)

    def _delete_current(self) -> None:
        if self.current is None:
            return
        slug = self.current.slug
        self.project_store.delete(slug)
        self.current = None
        self._refresh_sidebar()
        self._show_placeholder()
        self._status.set(f"Deleted {slug}")

    def _attach_pdf_to_current(self, source: Path) -> Path:
        if self.current is None:
            raise RuntimeError("No current project")
        dest = self.project_store.attach_pdf(self.current.slug, source)
        # Reload to pick up source_pdf field that attach_pdf wrote.
        self.current = self.project_store.load(self.current.slug)
        self._rebuild_notebook()
        # Cache page 4 as wiring.png for the (future) wiring viewer.
        self._try_cache_wiring_page(dest)
        return dest

    def _try_cache_wiring_page(self, pdf_path: Path) -> None:
        if self.current is None:
            return
        target = self.project_store.project_dir(self.current.slug) / "wiring.png"
        try:
            render_page_to_png(pdf_path, page_index=3, output_path=target)
        except Exception as exc:
            # Not fatal — PDFs with <4 pages just won't have a wiring viewer.
            self._status.set(f"Attached PDF (wiring page cache skipped: {exc})")

    def _import_bom_from_pdf(self) -> None:
        """Menu entry: ask for a PDF, import into the current project."""
        if self.current is None:
            messagebox.showinfo(
                "No project selected",
                "Create or select a project first, then import a BOM into it.",
            )
            return
        # If no source PDF is attached, offer to pick one.
        pdir = self.project_store.project_dir(self.current.slug)
        pdf = pdir / "source.pdf"
        if not pdf.exists():
            picked = filedialog.askopenfilename(
                title="Import BOM from PDF",
                filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")],
            )
            if not picked:
                return
            pdf = self._attach_pdf_to_current(Path(picked))

        items = self._parse_bom_with_errors(pdf)
        if items is None:
            return
        if self.current.bom and not messagebox.askyesno(
            "Replace BOM?",
            f"This project already has {len(self.current.bom)} BOM rows. "
            "Replace them with the {count} parsed from the PDF?".format(count=len(items)),
        ):
            return
        self.current.bom = items
        self._save_current()
        self._rebuild_notebook()

    def _import_bom_for_current(self) -> list[BOMItem] | None:
        """Called by BOMView's 'Import from PDF' button."""
        if self.current is None:
            return None
        pdir = self.project_store.project_dir(self.current.slug)
        pdf = pdir / "source.pdf"
        if not pdf.exists():
            picked = filedialog.askopenfilename(
                title="Import BOM from PDF",
                filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")],
            )
            if not picked:
                return None
            pdf = self._attach_pdf_to_current(Path(picked))
        return self._parse_bom_with_errors(pdf)

    def _parse_bom_with_errors(self, pdf: Path) -> list[BOMItem] | None:
        try:
            items = extract_bom(pdf)
        except BOMParseError as exc:
            messagebox.showerror("BOM parse failed", str(exc))
            return None
        except Exception as exc:
            messagebox.showerror("BOM parse failed", f"{type(exc).__name__}: {exc}")
            return None
        self._status.set(f"Parsed {len(items)} BOM items from {pdf.name}")
        return items

    def _show_about(self) -> None:
        messagebox.showinfo(
            "About",
            "DIY Pedal Build Assistant\n"
            "Bench copilot for DIY guitar pedal builds.\n"
            "Phase 1 + Phase 2 (bench mode).",
        )


def _status_badge(status: str) -> str:
    # Short visual affordance for the sidebar. Keep compact.
    return {
        "planned": "\u00B7 planned",
        "ordered": "\u00B7 ordered",
        "building": "\u00B7 building",
        "finishing": "\u00B7 finishing",
        "done": "\u2713 done",
    }.get(status, "")


class NewProjectDialog:
    """Modal dialog to capture a new project's name + enclosure."""

    def __init__(self, parent: tk.Misc, enclosure_keys: list[str]) -> None:
        self.result: tuple[str, str] | None = None

        top = tk.Toplevel(parent)
        top.title("New Project")
        top.transient(parent.winfo_toplevel())
        top.resizable(False, False)
        top.grab_set()
        self.top = top

        frame = ttk.Frame(top, padding=16)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text="Name").grid(row=0, column=0, sticky=tk.W, pady=4)
        self._name = tk.StringVar()
        name_entry = ttk.Entry(frame, textvariable=self._name, width=32)
        name_entry.grid(row=0, column=1, sticky=tk.EW, pady=4)
        name_entry.focus_set()

        ttk.Label(frame, text="Enclosure").grid(row=1, column=0, sticky=tk.W, pady=4)
        self._enclosure = tk.StringVar(value=("125B" if "125B" in enclosure_keys else (enclosure_keys[0] if enclosure_keys else "")))
        ttk.Combobox(
            frame, textvariable=self._enclosure, values=enclosure_keys,
            state="readonly", width=20,
        ).grid(row=1, column=1, sticky=tk.W, pady=4)

        buttons = ttk.Frame(frame)
        buttons.grid(row=2, column=0, columnspan=2, sticky=tk.E, pady=(12, 0))
        ttk.Button(buttons, text="Cancel", command=self._cancel).pack(side=tk.RIGHT, padx=(4, 0))
        ttk.Button(buttons, text="Create", command=self._ok).pack(side=tk.RIGHT)

        top.bind("<Return>", lambda _e: self._ok())
        top.bind("<Escape>", lambda _e: self._cancel())

        parent.winfo_toplevel().wait_window(top)

    def _ok(self) -> None:
        name = self._name.get().strip()
        if not name:
            messagebox.showwarning("Name required", "Enter a project name.")
            return
        self.result = (name, self._enclosure.get())
        self.top.destroy()

    def _cancel(self) -> None:
        self.result = None
        self.top.destroy()

    @classmethod
    def ask(cls, parent: tk.Misc, enclosure_keys: list[str]) -> tuple[str, str] | None:
        return cls(parent, enclosure_keys).result


__all__ = ["MainWindow"]
