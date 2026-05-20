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

    # ================ Tree Mutation API ================

    MAX_DEPTH = 3   # root → cat → cat → leaf

    # --------- traversal ---------

    def resolve(self, path: List[int]) -> Optional[Node]:
        """Resolve a path (list of ints) to the Node at that path, or None."""
        if not path:
            return None
        node = self._tree.get(str(path[0]))
        for idx in path[1:]:
            if node is None or node.kind is not NodeKind.CATEGORY:
                return None
            if idx < 0 or idx >= len(node.children):
                return None
            node = node.children[idx]
        return node

    def _parent_and_index(self, path: List[int]) -> tuple:
        """Returns (parent_container, child_key)."""
        if not path:
            raise ValueError("empty path has no parent")
        if len(path) == 1:
            return (self._tree, str(path[0]))
        parent = self.resolve(path[:-1])
        if parent is None or parent.kind is not NodeKind.CATEGORY:
            raise ValueError(f"parent at {format_path(path[:-1])} is not a category")
        return (parent.children, path[-1])

    # --------- depth validation ---------

    def _node_height(self, n: Optional[Node]) -> int:
        """Return the maximum depth below this node (1 for leaf, 2+ for parent)."""
        if n is None:
            return 0
        if n.kind is not NodeKind.CATEGORY or not n.children:
            return 1
        return 1 + max(self._node_height(c) for c in n.children)

    def _validate_depth(self, path: List[int], new_node: Optional[Node]) -> None:
        """Check that placing new_node at path doesn't violate MAX_DEPTH."""
        if new_node is None:
            return
        depth_at_path = len(path)
        # A category at depth MAX_DEPTH has no room for children.
        if new_node.kind is NodeKind.CATEGORY and depth_at_path >= self.MAX_DEPTH:
            raise ValueError(
                f"depth exceeded: placing a category at depth {depth_at_path} "
                f"leaves no room for children (max {self.MAX_DEPTH})")
        height = self._node_height(new_node)
        if depth_at_path + height - 1 > self.MAX_DEPTH:
            raise ValueError(
                f"depth exceeded: placing node (height={height}) at depth "
                f"{depth_at_path} would make tree {depth_at_path + height - 1} "
                f"levels (max {self.MAX_DEPTH})")

    # --------- mutations ---------

    def replace_node(self, path: List[int], node: Optional[Node]) -> None:
        """Replace the node at path with node (or None to clear)."""
        self._validate_depth(path, node)
        parent, key = self._parent_and_index(path)
        if isinstance(parent, dict):
            parent[key] = node
        else:
            if node is None:
                raise ValueError("cannot set a child to None — use delete_node")
            parent[key] = node
        self.save()

    def add_child(self, parent_path: List[int], node: Node) -> None:
        """Add a child to the category at parent_path."""
        if not parent_path:
            raise ValueError("cannot add a child at root — use replace_node on a slot")
        parent = self.resolve(parent_path)
        if parent is None or parent.kind is not NodeKind.CATEGORY:
            raise ValueError(f"target {format_path(parent_path)} is not a category")
        self._validate_depth(parent_path + [len(parent.children)], node)
        parent.children.append(node)
        self.save()

    def reorder_children(self, parent_path: List[int],
                         permutation: List[int]) -> None:
        """Reorder children of the category at parent_path."""
        parent = self.resolve(parent_path)
        if parent is None or parent.kind is not NodeKind.CATEGORY:
            raise ValueError(f"target {format_path(parent_path)} is not a category")
        n = len(parent.children)
        if sorted(permutation) != list(range(n)):
            raise ValueError(f"permutation {permutation} must be a permutation of 0..{n-1}")
        parent.children = [parent.children[i] for i in permutation]
        self.save()

    def delete_node(self, path: List[int]) -> None:
        """Delete the node at path."""
        if not path:
            raise ValueError("cannot delete root")
        parent, key = self._parent_and_index(path)
        if isinstance(parent, dict):
            parent[key] = None
        else:
            del parent[key]
        self.save()
