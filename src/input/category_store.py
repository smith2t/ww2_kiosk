"""Curator-managed catalog of media items, organized into 4 categories.

Each physical button corresponds to a category (1=Blue, 2=Green, 3=Yellow,
4=Red). Each category has a human-readable title and an ordered list of
items. Each item is a media file (video or PDF) with a display title.

JSON schema (config/categories.json):
    {
      "categories": {
        "1": {
          "title": "European Theater",
          "items": [
            {"file": "dday.mp4",      "title": "D-Day Normandy"},
            {"file": "stalingrad.pdf","title": "Stalingrad: Maps"}
          ]
        },
        "2": {"title": "...", "items": [...]},
        "3": {"title": "...", "items": [...]},
        "4": {"title": "...", "items": [...]}
      }
    }

Auto-migration: if categories.json is missing but the legacy
button_mappings.json exists, each old button becomes a single-item
category seeded with the old description as the category title.
"""

import json
import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 2


class NodeKind(str, Enum):
    CATEGORY = "category"
    VIDEO = "video"
    PDF = "pdf"
    PICTURESET = "pictureset"


@dataclass
class Node:
    """Tree node. The set of populated fields depends on `kind`:
      - CATEGORY   : title, children
      - VIDEO/PDF  : title, file
      - PICTURESET : title, files, captions, interval_sec
    """
    kind: NodeKind
    title: str = ""
    children: List["Node"] = field(default_factory=list)
    file: str = ""
    files: List[str] = field(default_factory=list)
    captions: List[str] = field(default_factory=list)
    interval_sec: int = 6


def node_to_dict(n: Node) -> dict:
    base = {"kind": n.kind.value, "title": n.title}
    if n.kind is NodeKind.CATEGORY:
        base["children"] = [node_to_dict(c) for c in n.children]
    elif n.kind in (NodeKind.VIDEO, NodeKind.PDF):
        base["file"] = n.file
    elif n.kind is NodeKind.PICTURESET:
        base["files"] = list(n.files)
        base["captions"] = list(n.captions)
        base["interval_sec"] = n.interval_sec
    return base


def node_from_dict(d: dict) -> Node:
    raw_kind = d.get("kind")
    try:
        kind = NodeKind(raw_kind)
    except ValueError as e:
        raise ValueError(f"unknown kind: {raw_kind!r}") from e

    title = str(d.get("title", ""))

    if kind is NodeKind.CATEGORY:
        children = [node_from_dict(c) for c in (d.get("children") or [])]
        return Node(kind=kind, title=title, children=children)

    if kind in (NodeKind.VIDEO, NodeKind.PDF):
        return Node(kind=kind, title=title, file=str(d.get("file", "")))

    # PICTURESET
    files = [str(f) for f in (d.get("files") or [])]
    captions = [str(c) for c in (d.get("captions") or [])]
    interval = int(d.get("interval_sec", 6))
    if len(files) < 1:
        raise ValueError("pictureset requires at least one file")
    if len(captions) != len(files):
        raise ValueError(
            f"pictureset captions length ({len(captions)}) "
            f"must equal files length ({len(files)})")
    if not (3 <= interval <= 60):
        raise ValueError(f"pictureset interval_sec must be 3-60, got {interval}")
    return Node(kind=kind, title=title, files=files, captions=captions,
                interval_sec=interval)

def parse_path(s: str) -> List[int]:
    """Parse a slash-separated path into a list of ints.

    Returns [] for the root (the tree as a whole).
    First component must be a root slot in 1..4 if present.
    Deeper components are 0-based child indices.
    """
    parts = [p for p in s.strip("/").split("/") if p]
    if not parts:
        return []
    out = []
    for i, p in enumerate(parts):
        try:
            n = int(p)
        except ValueError as e:
            raise ValueError(f"path component {p!r} is not an integer") from e
        if n < 0:
            raise ValueError(f"path component {n} is negative")
        if i == 0 and not (1 <= n <= 4):
            raise ValueError(f"root slot must be 1-4, got {n}")
        out.append(n)
    return out


def format_path(path: List[int]) -> str:
    """Format a path (list of ints) as a slash-separated string."""
    return "/".join(str(p) for p in path)


DEFAULT_CATEGORY_TITLES = {
    "1": "Category 1 — Blue",
    "2": "Category 2 — Green",
    "3": "Category 3 — Yellow",
    "4": "Category 4 — Red",
}


@dataclass
class Item:
    file: str
    title: str = ""

    def to_dict(self) -> dict:
        return {"file": self.file, "title": self.title}

    @classmethod
    def from_dict(cls, d: dict) -> "Item":
        return cls(file=str(d.get("file", "")), title=str(d.get("title", "")))


@dataclass
class Category:
    cat_id: str
    title: str
    items: List[Item] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"title": self.title, "items": [i.to_dict() for i in self.items]}


class CategoryStore:
    """v2 catalog store. Holds the tree in `_tree` (dict slot→Node|None)."""

    def __init__(self, settings):
        self.settings = settings
        cfg_dir = Path(settings.config.button_mappings_file).parent
        self.path = cfg_dir / "categories.json"
        self.legacy_path = Path(settings.config.button_mappings_file)
        self._tree: dict[str, Optional[Node]] = {"1": None, "2": None,
                                                 "3": None, "4": None}
        self.load()

    # ----------------- public read API -----------------

    def get_root_slot(self, slot) -> Optional[Node]:
        return self._tree.get(str(slot))

    def root_slots(self) -> dict[str, Optional[Node]]:
        return {s: self._tree[s] for s in ("1", "2", "3", "4")}

    # ----------------- persistence -----------------

    def load(self) -> None:
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text())
                if data.get("version") == SCHEMA_VERSION:
                    self._load_v2(data)
                    return
                self._load_legacy(data)
                return
            except Exception as e:
                logger.error(f"Failed to load {self.path}: {e}")
                self._tree = {s: None for s in ("1","2","3","4")}
                return

        if self.legacy_path.exists():
            try:
                self._load_button_mappings()
                return
            except Exception as e:
                logger.error(f"Legacy button_mappings migration failed: {e}")

        self._tree = {s: None for s in ("1", "2", "3", "4")}
        logger.info("No catalog on disk; started with empty tree")

    def _load_v2(self, data: dict) -> None:
        tree = data.get("tree") or {}
        new: dict[str, Optional[Node]] = {}
        for slot in ("1", "2", "3", "4"):
            raw = tree.get(slot)
            new[slot] = node_from_dict(raw) if raw is not None else None
        self._tree = new
        logger.info(f"Loaded v2 catalog from {self.path}")

    def _load_legacy(self, data: dict) -> None:
        """Migrate v1 categories.json (flat items per category) -> v2 tree."""
        backup = self.path.parent / "categories.v1.bak.json"
        try:
            backup.write_text(self.path.read_text())
        except Exception as e:
            logger.warning(f"Could not write v1 backup: {e}")

        v1_cats = (data or {}).get("categories", {}) or {}
        new: dict[str, Optional[Node]] = {}
        for slot in ("1", "2", "3", "4"):
            raw = v1_cats.get(slot) or {}
            items = raw.get("items") or []
            if not items:
                new[slot] = None
                continue
            children = []
            for it in items:
                f = str(it.get("file", ""))
                if not f:
                    continue
                kind = NodeKind.PDF if f.lower().endswith(".pdf") else NodeKind.VIDEO
                children.append(Node(kind=kind, title=str(it.get("title", "")),
                                     file=f))
            if not children:
                new[slot] = None
            else:
                new[slot] = Node(kind=NodeKind.CATEGORY,
                                 title=str(raw.get("title", f"Category {slot}")),
                                 children=children)
        self._tree = new
        self.save()
        logger.info(f"Migrated v1 categories.json -> v2 (backup at {backup})")

    def _load_button_mappings(self) -> None:
        """Migrate the very-old button_mappings.json to v2."""
        data = json.loads(self.legacy_path.read_text())
        mappings = data.get("mappings", {}) or {}
        descriptions = data.get("descriptions", {}) or {}
        new: dict[str, Optional[Node]] = {}
        for slot in ("1", "2", "3", "4"):
            f = (mappings.get(slot) or "").strip()
            desc = (descriptions.get(slot) or "").strip()
            if not f:
                new[slot] = None
                continue
            kind = NodeKind.PDF if f.lower().endswith(".pdf") else NodeKind.VIDEO
            leaf = Node(kind=kind, title=desc, file=f)
            new[slot] = Node(kind=NodeKind.CATEGORY,
                             title=desc or f"Category {slot}",
                             children=[leaf])
        self._tree = new
        self.save()
        logger.info("Migrated button_mappings.json -> v2 categories.json")

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": SCHEMA_VERSION,
            "tree": {
                s: (node_to_dict(n) if n is not None else None)
                for s, n in self._tree.items()
            },
        }
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=2))
        os.replace(tmp, self.path)
        logger.info(f"Saved {self.path}")
