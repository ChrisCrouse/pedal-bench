"""Load and save projects as JSON on disk.

Layout:
    <repo>/projects/<slug>/project.json
    <repo>/projects/<slug>/source.pdf        (optional, attached)
    <repo>/projects/<slug>/wiring.png        (optional, rendered page 4)
    <repo>/projects/<slug>/drill/holes.json  (optional, canonical holes)
    <repo>/projects/<slug>/drill/guide_<face>.stl
    <repo>/projects/<slug>/photos/

Writes are atomic: temp file in the same directory, then os.replace.
"""

from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path
from typing import Iterator

from .models import Project, now_iso

PROJECT_JSON = "project.json"
_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(name: str) -> str:
    """Produce a filesystem-safe slug.

    "Sherwood Overdrive" -> "sherwood-overdrive"
    """
    s = _SLUG_RE.sub("-", name.strip().lower()).strip("-")
    if not s:
        raise ValueError(f"Cannot slugify {name!r}")
    return s


class ProjectStore:
    """Loads and persists projects under a single root directory."""

    def __init__(self, projects_root: Path) -> None:
        self.root = Path(projects_root)
        self.root.mkdir(parents=True, exist_ok=True)

    def project_dir(self, slug: str) -> Path:
        return self.root / slug

    def exists(self, slug: str) -> bool:
        return (self.project_dir(slug) / PROJECT_JSON).exists()

    def list_slugs(self) -> list[str]:
        if not self.root.exists():
            return []
        return sorted(
            p.name for p in self.root.iterdir()
            if p.is_dir() and (p / PROJECT_JSON).exists()
        )

    def iter_projects(self) -> Iterator[Project]:
        for slug in self.list_slugs():
            try:
                yield self.load(slug)
            except (OSError, json.JSONDecodeError, KeyError):
                # Skip corrupted projects rather than fail the whole list.
                # The UI surfaces these via a reload-failed warning elsewhere.
                continue

    def load(self, slug: str) -> Project:
        path = self.project_dir(slug) / PROJECT_JSON
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        project = Project.from_dict(data)
        # Heal mismatch between folder name and stored slug.
        if project.slug != slug:
            project.slug = slug
        return project

    def save(self, project: Project) -> Path:
        project.touch()
        pdir = self.project_dir(project.slug)
        pdir.mkdir(parents=True, exist_ok=True)
        dest = pdir / PROJECT_JSON
        _atomic_write_json(dest, project.to_dict())
        return dest

    def create(self, name: str, enclosure: str = "") -> Project:
        slug = slugify(name)
        if self.exists(slug):
            raise FileExistsError(f"Project {slug!r} already exists")
        project = Project(slug=slug, name=name, enclosure=enclosure)
        self.save(project)
        return project

    def delete(self, slug: str) -> None:
        pdir = self.project_dir(slug)
        if pdir.exists():
            shutil.rmtree(pdir)

    def rename(self, slug: str, new_name: str) -> Project:
        """Rename a project. Slug follows the new name.

        If the slug changes and the new slug is taken, raises FileExistsError.
        """
        project = self.load(slug)
        new_slug = slugify(new_name)
        if new_slug != slug and self.exists(new_slug):
            raise FileExistsError(f"Project {new_slug!r} already exists")

        project.name = new_name
        if new_slug != slug:
            # Move the directory, then re-slug and save.
            src = self.project_dir(slug)
            dst = self.project_dir(new_slug)
            os.rename(src, dst)
            project.slug = new_slug
        self.save(project)
        return project

    def attach_pdf(self, slug: str, source_pdf_path: Path) -> Path:
        """Copy a PDF into the project folder and update source_pdf.

        Returns the destination path.
        """
        source_pdf_path = Path(source_pdf_path)
        if not source_pdf_path.is_file():
            raise FileNotFoundError(source_pdf_path)
        project = self.load(slug)
        pdir = self.project_dir(slug)
        pdir.mkdir(parents=True, exist_ok=True)
        dest = pdir / "source.pdf"
        shutil.copyfile(source_pdf_path, dest)
        project.source_pdf = "source.pdf"
        self.save(project)
        return dest


def _atomic_write_json(dest: Path, payload: dict) -> None:
    """Write JSON atomically: temp file in same dir, then os.replace."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    # Writing then replacing minimizes the window where dest is missing or
    # partial. os.replace is atomic on POSIX and on NTFS (within the same
    # filesystem), which is what we need.
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False, sort_keys=False)
        fh.write("\n")
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, dest)


__all__ = ["ProjectStore", "slugify", "now_iso"]
