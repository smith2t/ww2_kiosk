# Hierarchical Menu + Topic-Slideshow Leaves — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current 2-level fixed catalog (4 colored buttons → flat item list) with a 3-level tree of mixed kinds (category / video / pdf / pictureset). Hide undefined top-level tiles. Add a new picture-set leaf that auto-advances curated pictures with captions. Give curators a drill-down admin UI with thumbnails generated on upload.

**Architecture:** Single tree document in `config/categories.json` (schema v2), kept atomic on disk. A `CategoryStore` holds the tree and exposes path-based traversal + mutation ops. The visitor menu and the curator UI both walk the tree by path. A new `TopicSlideshow` class plays picture-set leaves alongside the existing video/PDF players. A new `thumbnailer.py` module generates PNG thumbnails on upload, cached under `media/.thumbs/`.

**Tech Stack:** Python 3.11, pygame (menu + slideshow rendering), Flask (curator UI), Pillow (image ops), PyMuPDF/`fitz` (PDF rendering — existing dep), ffmpeg subprocess (video frame extraction), pytest + pytest-asyncio (tests), `SDL_VIDEODRIVER=dummy` for headless pygame tests.

**Spec:** `docs/superpowers/specs/2026-05-18-hierarchical-menu-with-picturesets-design.md`

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `src/input/category_store.py` | rewrite | v2 schema, tree dataclasses, path traversal, mutation ops, v1→v2 migration |
| `src/media/thumbnailer.py` | create | Generate + cache thumbnails (video/PDF/picture/pictureset) |
| `src/media/__init__.py` | create | Package marker (may already exist) |
| `src/display/menu.py` | modify | Kind badges on tiles, hide null slots, traverse tree by path |
| `src/display/topic_slideshow.py` | create | Picture-set playback with caption overlay |
| `src/display/display_controller.py` | modify | Route leaves by kind, add PICTURESET mode, path-based back nav |
| `src/network/web_interface.py` | modify | New `/settings/catalog/*` routes, thumbnail wiring in `/upload` |
| `src/network/templates/catalog_view.html` | create | Drill-down editor template (one template, used at every depth) |
| `src/network/templates/catalog_root.html` | create | Root view template (4 fixed slots) |
| `tests/test_category_store.py` | create | Schema/migration/path/mutation tests |
| `tests/test_thumbnailer.py` | create | Cache hit/miss, mtime invalidation, fallback to placeholder |
| `tests/test_menu_rendering.py` | create | Tile badges, null-slot hiding, button-4 back rule |
| `tests/test_catalog_routes.py` | create | Flask test-client coverage of curator endpoints |
| `.gitignore` | modify | Add `media/.thumbs/` |
| `config/categories.json` | data | Will be auto-migrated on first run |

---

## Phase 1 — Data model (`category_store.py`)

The v2 store is the foundation everything else builds on. We replace the current `Category`/`Item` dataclasses with a `Node` hierarchy and a tree-walking API.

### Task 1: v2 schema constants + Node dataclass

**Files:**
- Modify: `src/input/category_store.py`
- Test: `tests/test_category_store.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_category_store.py`:

```python
import pytest
from src.input.category_store import (
    Node, NodeKind, SCHEMA_VERSION,
    node_to_dict, node_from_dict,
)


def test_schema_version_is_2():
    assert SCHEMA_VERSION == 2


def test_video_node_roundtrip():
    n = Node(kind=NodeKind.VIDEO, title="D-Day", file="dday.mp4")
    d = node_to_dict(n)
    assert d == {"kind": "video", "title": "D-Day", "file": "dday.mp4"}
    n2 = node_from_dict(d)
    assert n2 == n


def test_pdf_node_roundtrip():
    n = Node(kind=NodeKind.PDF, title="Maps", file="maps.pdf")
    d = node_to_dict(n)
    assert d == {"kind": "pdf", "title": "Maps", "file": "maps.pdf"}
    assert node_from_dict(d) == n


def test_pictureset_node_roundtrip():
    n = Node(
        kind=NodeKind.PICTURESET, title="Paris",
        files=["a.jpg", "b.jpg"],
        captions=["Aug 1944", ""],
        interval_sec=6,
    )
    d = node_to_dict(n)
    assert d == {
        "kind": "pictureset", "title": "Paris",
        "files": ["a.jpg", "b.jpg"],
        "captions": ["Aug 1944", ""],
        "interval_sec": 6,
    }
    assert node_from_dict(d) == n


def test_category_node_roundtrip():
    leaf = Node(kind=NodeKind.VIDEO, title="X", file="x.mp4")
    n = Node(kind=NodeKind.CATEGORY, title="European", children=[leaf])
    d = node_to_dict(n)
    assert d == {
        "kind": "category", "title": "European",
        "children": [{"kind": "video", "title": "X", "file": "x.mp4"}],
    }
    assert node_from_dict(d) == n


def test_node_from_dict_rejects_unknown_kind():
    with pytest.raises(ValueError, match="unknown kind"):
        node_from_dict({"kind": "frobnicate", "title": "x"})


def test_pictureset_validates_captions_length():
    with pytest.raises(ValueError, match="captions length"):
        node_from_dict({
            "kind": "pictureset", "title": "X",
            "files": ["a.jpg", "b.jpg"],
            "captions": ["only one"],
            "interval_sec": 6,
        })


def test_pictureset_validates_interval_range():
    for bad in (0, 2, 61, 999):
        with pytest.raises(ValueError, match="interval_sec"):
            node_from_dict({
                "kind": "pictureset", "title": "X",
                "files": ["a.jpg"], "captions": [""],
                "interval_sec": bad,
            })


def test_pictureset_requires_at_least_one_file():
    with pytest.raises(ValueError, match="at least one file"):
        node_from_dict({
            "kind": "pictureset", "title": "X",
            "files": [], "captions": [], "interval_sec": 6,
        })
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/tatesmith/Documents/ww2_kiosk-main
python -m pytest tests/test_category_store.py -v
```

Expected: All tests fail with `ImportError: cannot import name 'Node' from 'src.input.category_store'`.

- [ ] **Step 3: Add the Node dataclass and serialization helpers**

Edit `src/input/category_store.py`. Add the following BEFORE the existing `Item`/`Category` classes (keep those for now — Task 4 will migrate them away):

```python
from enum import Enum

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
    # Category-only:
    children: List["Node"] = field(default_factory=list)
    # Video/PDF-only:
    file: str = ""
    # Pictureset-only:
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
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest tests/test_category_store.py -v
```

Expected: All 8 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/input/category_store.py tests/test_category_store.py
git commit -m "feat(catalog): add v2 schema Node dataclass and serialization"
```

---

### Task 2: Path parsing helpers

**Files:**
- Modify: `src/input/category_store.py`
- Test: `tests/test_category_store.py`

A path is a sequence of integers identifying a node by descent from the root. The first element is always a root slot in `1..4`; subsequent elements are 0-based child indices. The string form is `"1/2/0"`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_category_store.py`:

```python
from src.input.category_store import parse_path, format_path


def test_parse_path_root_slot():
    assert parse_path("1") == [1]
    assert parse_path("/1") == [1]
    assert parse_path("/4/") == [4]


def test_parse_path_deeper():
    assert parse_path("1/0") == [1, 0]
    assert parse_path("/2/3/1") == [2, 3, 1]


def test_parse_path_empty_is_root():
    assert parse_path("") == []
    assert parse_path("/") == []


def test_parse_path_rejects_non_integer():
    with pytest.raises(ValueError):
        parse_path("1/foo")


def test_parse_path_rejects_negative():
    with pytest.raises(ValueError):
        parse_path("1/-1")


def test_parse_path_rejects_invalid_root_slot():
    with pytest.raises(ValueError, match="root slot must be 1-4"):
        parse_path("5")
    with pytest.raises(ValueError, match="root slot must be 1-4"):
        parse_path("0/0")


def test_format_path_roundtrip():
    for s in ("1", "1/0", "3/2/1"):
        assert format_path(parse_path(s)) == s
    assert format_path([]) == ""
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_category_store.py -v -k "parse_path or format_path"
```

Expected: ImportError on `parse_path` / `format_path`.

- [ ] **Step 3: Implement the helpers**

Append to `src/input/category_store.py`:

```python
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
    return "/".join(str(p) for p in path)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest tests/test_category_store.py -v
```

Expected: All tests pass (now 15 total).

- [ ] **Step 5: Commit**

```bash
git add src/input/category_store.py tests/test_category_store.py
git commit -m "feat(catalog): add parse_path / format_path helpers"
```

---

### Task 3: CategoryStore v2 — load + atomic save (no migration yet)

**Files:**
- Modify: `src/input/category_store.py`
- Test: `tests/test_category_store.py`

We replace the body of `CategoryStore` with a v2 implementation. The old `Category`/`Item` classes and their methods stay in place for one more task so the migration test (Task 4) can compare against them; they get deleted in Task 6.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_category_store.py`:

```python
import json
from pathlib import Path
from types import SimpleNamespace

from src.input.category_store import CategoryStore


def _settings(tmp_path: Path) -> SimpleNamespace:
    """Minimal settings stub matching what CategoryStore reads."""
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir()
    media_dir = tmp_path / "media"
    (media_dir / "videos").mkdir(parents=True)
    (media_dir / "pictures").mkdir(parents=True)
    return SimpleNamespace(
        config=SimpleNamespace(
            button_mappings_file=str(cfg_dir / "button_mappings.json"),
        ),
        media=SimpleNamespace(
            videos_dir=str(media_dir / "videos"),
            pictures_dir=str(media_dir / "pictures"),
        ),
    )


def test_load_v2_file(tmp_path):
    s = _settings(tmp_path)
    cfg = Path(s.config.button_mappings_file).parent / "categories.json"
    cfg.write_text(json.dumps({
        "version": 2,
        "tree": {
            "1": {"kind": "video", "title": "D-Day", "file": "dday.mp4"},
            "2": None,
            "3": {"kind": "category", "title": "Pacific", "children": []},
            "4": None,
        },
    }))
    store = CategoryStore(s)
    assert store.get_root_slot(1).kind.value == "video"
    assert store.get_root_slot(2) is None
    assert store.get_root_slot(3).kind.value == "category"
    assert store.get_root_slot(4) is None


def test_load_missing_file_yields_all_null_slots(tmp_path):
    s = _settings(tmp_path)
    store = CategoryStore(s)
    for slot in (1, 2, 3, 4):
        assert store.get_root_slot(slot) is None


def test_save_is_atomic(tmp_path):
    s = _settings(tmp_path)
    store = CategoryStore(s)
    store._tree = {
        "1": Node(kind=NodeKind.VIDEO, title="X", file="x.mp4"),
        "2": None, "3": None, "4": None,
    }
    store.save()

    cfg = Path(s.config.button_mappings_file).parent / "categories.json"
    tmp = cfg.with_suffix(".json.tmp")
    assert cfg.exists()
    assert not tmp.exists()  # no leftover temp file
    payload = json.loads(cfg.read_text())
    assert payload["version"] == 2
    assert payload["tree"]["1"]["kind"] == "video"
    assert payload["tree"]["2"] is None


def test_save_then_load_roundtrip(tmp_path):
    s = _settings(tmp_path)
    store = CategoryStore(s)
    store._tree = {
        "1": Node(kind=NodeKind.CATEGORY, title="EU", children=[
            Node(kind=NodeKind.VIDEO, title="D-Day", file="dday.mp4"),
        ]),
        "2": None, "3": None, "4": None,
    }
    store.save()

    store2 = CategoryStore(s)
    eu = store2.get_root_slot(1)
    assert eu.title == "EU"
    assert len(eu.children) == 1
    assert eu.children[0].file == "dday.mp4"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_category_store.py -v -k "load_v2 or load_missing or save_is_atomic or save_then_load"
```

Expected: AttributeError / TypeError — `CategoryStore` doesn't yet have `_tree`, `get_root_slot`, or v2-aware save/load.

- [ ] **Step 3: Replace the CategoryStore implementation**

In `src/input/category_store.py`, REPLACE the entire `class CategoryStore` block with:

```python
class CategoryStore:
    """v2 catalog store. Holds the tree in `_tree` (dict slot→Node|None)."""

    def __init__(self, settings):
        self.settings = settings
        cfg_dir = Path(settings.config.button_mappings_file).parent
        self.path = cfg_dir / "categories.json"
        self.legacy_path = Path(settings.config.button_mappings_file)
        self.v1_path = cfg_dir / "categories.json"   # rewritten on migrate
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
                # Anything older: migration (Task 4)
                self._load_legacy(data)
                return
            except Exception as e:
                logger.error(f"Failed to load {self.path}: {e}")
                self._tree = {s: None for s in ("1","2","3","4")}
                return

        # No categories.json: try the very-old button_mappings.json (Task 4)
        if self.legacy_path.exists():
            try:
                self._load_button_mappings()
                return
            except Exception as e:
                logger.error(f"Legacy button_mappings migration failed: {e}")

        # Fresh kiosk — empty tree
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
        # Filled in by Task 4. Placeholder so load() doesn't crash mid-development.
        self._tree = {s: None for s in ("1","2","3","4")}
        logger.warning("Legacy v1 categories.json detected — migration not yet implemented")

    def _load_button_mappings(self) -> None:
        # Filled in by Task 4.
        self._tree = {s: None for s in ("1","2","3","4")}
        logger.warning("Legacy button_mappings.json detected — migration not yet implemented")

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
```

Also add at the top of the file:

```python
import os
from typing import Optional
```

(The existing `import` block already has `json`, `logging`, `dataclass`, `field`, `Path`, `List`. Add `Optional` and `os`.)

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_category_store.py -v
```

Expected: All tests pass (now 19).

- [ ] **Step 5: Commit**

```bash
git add src/input/category_store.py tests/test_category_store.py
git commit -m "feat(catalog): v2 CategoryStore with atomic save"
```

---

### Task 4: v1 → v2 auto-migration with .bak

**Files:**
- Modify: `src/input/category_store.py` (fill in `_load_legacy` and `_load_button_mappings`)
- Test: `tests/test_category_store.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_category_store.py`:

```python
def test_migrate_v1_categories_to_v2(tmp_path):
    s = _settings(tmp_path)
    cfg = Path(s.config.button_mappings_file).parent / "categories.json"
    cfg.write_text(json.dumps({
        "categories": {
            "1": {"title": "European", "items": [
                {"file": "dday.mp4", "title": "D-Day"},
                {"file": "maps.pdf", "title": "Maps"},
            ]},
            "2": {"title": "Pacific", "items": []},
            "3": {"title": "Cat3", "items": [
                {"file": "midway.mp4", "title": "Midway"}]},
            "4": {"title": "Cat4", "items": []},
        },
    }))
    store = CategoryStore(s)

    eu = store.get_root_slot(1)
    assert eu is not None
    assert eu.kind.value == "category"
    assert eu.title == "European"
    assert [c.file for c in eu.children] == ["dday.mp4", "maps.pdf"]
    assert [c.kind.value for c in eu.children] == ["video", "pdf"]

    # Slot 2 had an empty items list -> migrate to null
    assert store.get_root_slot(2) is None
    assert store.get_root_slot(3).children[0].file == "midway.mp4"
    assert store.get_root_slot(4) is None


def test_migration_writes_backup_and_v2_file(tmp_path):
    s = _settings(tmp_path)
    cfg = Path(s.config.button_mappings_file).parent / "categories.json"
    bak = Path(s.config.button_mappings_file).parent / "categories.v1.bak.json"
    cfg.write_text(json.dumps({"categories": {
        "1": {"title": "X", "items": [{"file": "a.mp4", "title": "A"}]},
    }}))

    CategoryStore(s)

    # Backup preserves the v1 content
    assert bak.exists()
    assert json.loads(bak.read_text())["categories"]["1"]["title"] == "X"
    # categories.json is now v2
    assert json.loads(cfg.read_text())["version"] == 2


def test_migrate_button_mappings_when_no_categories_file(tmp_path):
    s = _settings(tmp_path)
    legacy = Path(s.config.button_mappings_file)
    legacy.write_text(json.dumps({
        "mappings": {"1": "dday.mp4", "2": "", "3": "midway.mp4", "4": ""},
        "descriptions": {"1": "D-Day", "2": "", "3": "Midway", "4": ""},
    }))

    store = CategoryStore(s)

    s1 = store.get_root_slot(1)
    assert s1.kind.value == "category"
    assert s1.title == "D-Day"
    assert s1.children[0].file == "dday.mp4"
    assert store.get_root_slot(2) is None
    assert store.get_root_slot(3).children[0].file == "midway.mp4"
    assert store.get_root_slot(4) is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_category_store.py -v -k migrate
```

Expected: 3 failures — the migration placeholders return all-null trees.

- [ ] **Step 3: Implement the migrations**

In `src/input/category_store.py`, REPLACE `_load_legacy` and `_load_button_mappings` with:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_category_store.py -v
```

Expected: All tests pass (22 total).

- [ ] **Step 5: Commit**

```bash
git add src/input/category_store.py tests/test_category_store.py
git commit -m "feat(catalog): auto-migrate v1 categories.json -> v2 with .bak"
```

---

### Task 5: Tree mutation API + depth validation

**Files:**
- Modify: `src/input/category_store.py`
- Test: `tests/test_category_store.py`

The store needs `resolve(path) -> Node|None`, `replace_root_slot`, `replace_child`, `add_child`, `reorder_children`, `delete`, all enforcing the depth-3 rule.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_category_store.py`:

```python
def _seeded_store(tmp_path):
    s = _settings(tmp_path)
    store = CategoryStore(s)
    store._tree = {
        "1": Node(kind=NodeKind.CATEGORY, title="EU", children=[
            Node(kind=NodeKind.CATEGORY, title="Air", children=[
                Node(kind=NodeKind.VIDEO, title="BoB", file="bob.mp4"),
            ]),
            Node(kind=NodeKind.VIDEO, title="D-Day", file="dday.mp4"),
        ]),
        "2": None, "3": None, "4": None,
    }
    return store


def test_resolve_root(tmp_path):
    store = _seeded_store(tmp_path)
    assert store.resolve([1]).title == "EU"
    assert store.resolve([2]) is None


def test_resolve_deeper(tmp_path):
    store = _seeded_store(tmp_path)
    assert store.resolve([1, 0]).title == "Air"
    assert store.resolve([1, 0, 0]).title == "BoB"
    assert store.resolve([1, 1]).title == "D-Day"


def test_resolve_out_of_range(tmp_path):
    store = _seeded_store(tmp_path)
    assert store.resolve([1, 99]) is None
    assert store.resolve([1, 0, 99]) is None


def test_resolve_empty_path_is_none(tmp_path):
    """Root has no Node — the tree as a whole isn't a Node."""
    store = _seeded_store(tmp_path)
    assert store.resolve([]) is None


def test_replace_root_slot(tmp_path):
    store = _seeded_store(tmp_path)
    new = Node(kind=NodeKind.VIDEO, title="Midway", file="midway.mp4")
    store.replace_node([3], new)
    assert store.get_root_slot(3).file == "midway.mp4"


def test_replace_root_slot_with_none_clears(tmp_path):
    store = _seeded_store(tmp_path)
    store.replace_node([1], None)
    assert store.get_root_slot(1) is None


def test_add_child(tmp_path):
    store = _seeded_store(tmp_path)
    new = Node(kind=NodeKind.PDF, title="Maps", file="maps.pdf")
    store.add_child([1], new)
    eu = store.get_root_slot(1)
    assert len(eu.children) == 3
    assert eu.children[-1].file == "maps.pdf"


def test_add_child_rejects_under_leaf(tmp_path):
    store = _seeded_store(tmp_path)
    new = Node(kind=NodeKind.VIDEO, title="X", file="x.mp4")
    with pytest.raises(ValueError, match="not a category"):
        store.add_child([1, 1], new)   # 1/1 is a video, not a category


def test_depth_limit_enforced(tmp_path):
    store = _seeded_store(tmp_path)
    # 1/0 is "Air" (category). Adding a sub-category there would make a 4-deep tree.
    deep_cat = Node(kind=NodeKind.CATEGORY, title="Too Deep", children=[])
    with pytest.raises(ValueError, match="depth"):
        store.add_child([1, 0], deep_cat)
    # But a leaf at the same path is fine (depth = 3, still allowed).
    store.add_child([1, 0], Node(kind=NodeKind.VIDEO, title="X", file="x.mp4"))


def test_reorder_children(tmp_path):
    store = _seeded_store(tmp_path)
    store.add_child([1], Node(kind=NodeKind.PDF, title="C", file="c.pdf"))
    # EU now has 3 children: Air, D-Day, C
    store.reorder_children([1], [2, 0, 1])
    eu = store.get_root_slot(1)
    assert [c.title for c in eu.children] == ["C", "Air", "D-Day"]


def test_reorder_rejects_bad_permutation(tmp_path):
    store = _seeded_store(tmp_path)
    with pytest.raises(ValueError, match="permutation"):
        store.reorder_children([1], [0, 0])   # duplicate
    with pytest.raises(ValueError, match="permutation"):
        store.reorder_children([1], [0])      # missing index 1


def test_delete_child(tmp_path):
    store = _seeded_store(tmp_path)
    store.delete_node([1, 0])
    eu = store.get_root_slot(1)
    assert len(eu.children) == 1
    assert eu.children[0].title == "D-Day"


def test_delete_root_slot_is_replace_with_none(tmp_path):
    store = _seeded_store(tmp_path)
    store.delete_node([1])
    assert store.get_root_slot(1) is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_category_store.py -v -k "resolve or replace or add_child or depth or reorder or delete"
```

Expected: AttributeError — `resolve`, `replace_node`, `add_child`, `reorder_children`, `delete_node` not defined.

- [ ] **Step 3: Implement the mutation API**

Append to the `CategoryStore` class:

```python
    MAX_DEPTH = 3   # root → cat → cat → leaf

    # ----------------- traversal -----------------

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
        """Returns (parent_container, child_key) where parent_container is
        either self._tree (root slot) or a Node.children list, and child_key
        is the dict key or list index identifying the node at `path`.
        """
        if not path:
            raise ValueError("empty path has no parent")
        if len(path) == 1:
            return (self._tree, str(path[0]))
        parent = self.resolve(path[:-1])
        if parent is None or parent.kind is not NodeKind.CATEGORY:
            raise ValueError(f"parent at {format_path(path[:-1])} is not a category")
        return (parent.children, path[-1])

    # ----------------- depth validation -----------------

    def _node_height(self, n: Optional[Node]) -> int:
        """Height = 1 + max child height; leaves and None are 0."""
        if n is None or n.kind is not NodeKind.CATEGORY or not n.children:
            return 0 if n is None else 1
        return 1 + max(self._node_height(c) for c in n.children)

    def _validate_depth(self, path: List[int], new_node: Optional[Node]) -> None:
        """Ensure inserting new_node at depth len(path) keeps total tree ≤ MAX_DEPTH."""
        if new_node is None:
            return
        # path of length 1 means depth 1 (root slot); len(path)+height ≤ MAX_DEPTH.
        depth_at_path = len(path)
        height = self._node_height(new_node)
        if depth_at_path + height > self.MAX_DEPTH:
            raise ValueError(
                f"depth exceeded: placing node (height={height}) at depth "
                f"{depth_at_path} would make tree {depth_at_path + height} "
                f"levels (max {self.MAX_DEPTH})")

    # ----------------- mutations -----------------

    def replace_node(self, path: List[int], node: Optional[Node]) -> None:
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
        if not parent_path:
            raise ValueError("cannot add a child at root — use replace_node on a slot")
        parent = self.resolve(parent_path)
        if parent is None or parent.kind is not NodeKind.CATEGORY:
            raise ValueError(f"target {format_path(parent_path)} is not a category")
        # New child will sit at depth len(parent_path)+1
        self._validate_depth(parent_path + [len(parent.children)], node)
        parent.children.append(node)
        self.save()

    def reorder_children(self, parent_path: List[int],
                         permutation: List[int]) -> None:
        parent = self.resolve(parent_path)
        if parent is None or parent.kind is not NodeKind.CATEGORY:
            raise ValueError(f"target {format_path(parent_path)} is not a category")
        n = len(parent.children)
        if sorted(permutation) != list(range(n)):
            raise ValueError(f"permutation {permutation} must be a permutation of 0..{n-1}")
        parent.children = [parent.children[i] for i in permutation]
        self.save()

    def delete_node(self, path: List[int]) -> None:
        if not path:
            raise ValueError("cannot delete root")
        parent, key = self._parent_and_index(path)
        if isinstance(parent, dict):
            parent[key] = None
        else:
            del parent[key]
        self.save()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_category_store.py -v
```

Expected: All tests pass (~35 total).

- [ ] **Step 5: Commit**

```bash
git add src/input/category_store.py tests/test_category_store.py
git commit -m "feat(catalog): tree mutation API with depth validation"
```

---

### Task 6: Remove the obsolete v1 API surface

**Files:**
- Modify: `src/input/category_store.py`
- Modify: `src/display/display_controller.py` (the old call sites — see Task 17 for full rewrite; this task only adds a temporary shim so the kiosk still boots)

The old `Category`/`Item` classes and `get_category`/`all_categories`/`replace_category`/`resolve_item_path` methods are about to be removed. We delete them and confirm the kiosk still imports cleanly.

- [ ] **Step 1: Delete the old types and methods**

In `src/input/category_store.py`:

- Delete the `Item` dataclass.
- Delete the `Category` dataclass.
- Delete the `DEFAULT_CATEGORY_TITLES` constant.
- Delete the methods `get_category`, `all_categories`, `replace_category`, `resolve_item_path`, `_migrate_from_legacy` from `CategoryStore` (their replacements live in Tasks 4-5).

- [ ] **Step 2: Verify the module still imports**

```bash
python -c "from src.input.category_store import CategoryStore, Node, NodeKind"
```

Expected: no output, exit code 0.

- [ ] **Step 3: Run the full test suite**

```bash
python -m pytest tests/test_category_store.py -v
```

Expected: All tests still pass (mutation tests don't touch the deleted symbols).

- [ ] **Step 4: Confirm nothing else imports the deleted names**

```bash
grep -rn "from src.input.category_store import" src/ | grep -E "Item|Category[^S]" || echo "clean"
```

Expected: `clean` (the old `Item`/`Category` names are not imported anywhere else; menu/display_controller pull `CategoryStore` and will be rewritten in Tasks 12-17).

- [ ] **Step 5: Commit**

```bash
git add src/input/category_store.py
git commit -m "refactor(catalog): drop v1 Category/Item types"
```

---

## Phase 2 — Thumbnailer (`src/media/thumbnailer.py`)

### Task 7: Thumbnailer skeleton + Pillow path for images

**Files:**
- Create: `src/media/__init__.py` (empty marker if absent)
- Create: `src/media/thumbnailer.py`
- Test: `tests/test_thumbnailer.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_thumbnailer.py`:

```python
from pathlib import Path
from PIL import Image
import pytest

from src.media.thumbnailer import ensure_thumbnail, THUMB_SIZE


@pytest.fixture
def media_root(tmp_path, monkeypatch):
    """Point the thumbnailer's cache at a temp dir."""
    cache = tmp_path / ".thumbs"
    monkeypatch.setenv("KIOSK_THUMB_CACHE_DIR", str(cache))
    return tmp_path


def _write_image(path: Path, color=(200, 50, 50), size=(800, 450)):
    img = Image.new("RGB", size, color)
    img.save(path)


def test_image_thumbnail_generated(media_root):
    src = media_root / "pictures" / "test.jpg"
    src.parent.mkdir(parents=True)
    _write_image(src)

    thumb = ensure_thumbnail(src)
    assert thumb.exists()
    with Image.open(thumb) as t:
        assert t.size == THUMB_SIZE


def test_thumbnail_is_cached(media_root):
    src = media_root / "pictures" / "test.jpg"
    src.parent.mkdir(parents=True)
    _write_image(src)

    first = ensure_thumbnail(src)
    first_mtime = first.stat().st_mtime
    second = ensure_thumbnail(src)
    assert first == second
    assert second.stat().st_mtime == first_mtime   # not regenerated


def test_cache_invalidated_when_source_newer(media_root):
    src = media_root / "pictures" / "test.jpg"
    src.parent.mkdir(parents=True)
    _write_image(src)
    thumb = ensure_thumbnail(src)
    old_mtime = thumb.stat().st_mtime

    # Make source newer than thumb
    import os, time
    time.sleep(0.05)
    _write_image(src, color=(50, 50, 200))   # rewrite
    os.utime(src, None)

    new_thumb = ensure_thumbnail(src)
    assert new_thumb.stat().st_mtime > old_mtime
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_thumbnailer.py -v
```

Expected: ImportError — `src.media.thumbnailer` does not exist.

- [ ] **Step 3: Create the package and module**

Create `src/media/__init__.py` (empty file).

Create `src/media/thumbnailer.py`:

```python
"""Thumbnail generation + caching for kiosk media."""
import hashlib
import logging
import os
from pathlib import Path
from typing import Optional

from PIL import Image

logger = logging.getLogger(__name__)

THUMB_SIZE = (320, 180)   # 16:9


def _cache_dir(media_path: Path) -> Path:
    env = os.environ.get("KIOSK_THUMB_CACHE_DIR")
    if env:
        return Path(env)
    return media_path.parent.parent / ".thumbs"


def _cache_key(media_path: Path) -> str:
    """Stable cache key based on the absolute path."""
    return hashlib.sha1(str(media_path.resolve()).encode("utf-8")).hexdigest()


def _cache_path(media_path: Path) -> Path:
    d = _cache_dir(media_path)
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{_cache_key(media_path)}.png"


def _is_image(p: Path) -> bool:
    return p.suffix.lower() in {".jpg", ".jpeg", ".png", ".bmp", ".gif"}


def _thumbnail_image(src: Path, dst: Path) -> None:
    with Image.open(src) as img:
        img = img.convert("RGB")
        img.thumbnail(THUMB_SIZE, Image.Resampling.LANCZOS)
        # Letterbox onto a 320x180 black canvas so all thumbs share dimensions.
        canvas = Image.new("RGB", THUMB_SIZE, (0, 0, 0))
        x = (THUMB_SIZE[0] - img.size[0]) // 2
        y = (THUMB_SIZE[1] - img.size[1]) // 2
        canvas.paste(img, (x, y))
        canvas.save(dst, format="PNG")


def ensure_thumbnail(media_path: Path) -> Optional[Path]:
    """Return cached thumbnail PNG, generating it if missing or stale.

    Returns None on failure (caller may fall back to a placeholder).
    """
    media_path = Path(media_path)
    if not media_path.exists():
        logger.warning(f"thumbnail source missing: {media_path}")
        return None
    dst = _cache_path(media_path)
    if dst.exists() and dst.stat().st_mtime >= media_path.stat().st_mtime:
        return dst
    try:
        if _is_image(media_path):
            _thumbnail_image(media_path, dst)
        else:
            logger.info(f"no thumbnailer for {media_path.suffix}; "
                        "video/PDF support arrives in Task 8/9")
            return None
        return dst
    except Exception as e:
        logger.error(f"thumbnail generation failed for {media_path}: {e}")
        return None
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest tests/test_thumbnailer.py -v
```

Expected: All 3 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/media/__init__.py src/media/thumbnailer.py tests/test_thumbnailer.py
git commit -m "feat(thumbs): image thumbnail generation + sha1 disk cache"
```

---

### Task 8: PDF thumbnail via `fitz`

**Files:**
- Modify: `src/media/thumbnailer.py`
- Test: `tests/test_thumbnailer.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_thumbnailer.py`:

```python
def test_pdf_thumbnail_generated(media_root):
    import fitz
    src = media_root / "pictures" / "doc.pdf"
    src.parent.mkdir(parents=True, exist_ok=True)
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 144), "Hello world", fontsize=24)
    doc.save(src)
    doc.close()

    thumb = ensure_thumbnail(src)
    assert thumb is not None
    assert thumb.exists()
    with Image.open(thumb) as t:
        assert t.size == THUMB_SIZE
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_thumbnailer.py::test_pdf_thumbnail_generated -v
```

Expected: returns `None` from `ensure_thumbnail` for a `.pdf` source.

- [ ] **Step 3: Add PDF rendering**

In `src/media/thumbnailer.py`, add this helper near `_thumbnail_image`:

```python
def _thumbnail_pdf(src: Path, dst: Path) -> None:
    import fitz   # PyMuPDF, already a project dep
    doc = fitz.open(src)
    try:
        if doc.page_count == 0:
            raise ValueError("PDF has no pages")
        page = doc.load_page(0)
        zoom = max(1.0, THUMB_SIZE[0] / page.rect.width)
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        img.thumbnail(THUMB_SIZE, Image.Resampling.LANCZOS)
        canvas = Image.new("RGB", THUMB_SIZE, (0, 0, 0))
        x = (THUMB_SIZE[0] - img.size[0]) // 2
        y = (THUMB_SIZE[1] - img.size[1]) // 2
        canvas.paste(img, (x, y))
        canvas.save(dst, format="PNG")
    finally:
        doc.close()
```

Modify `ensure_thumbnail` to dispatch to it:

```python
def ensure_thumbnail(media_path: Path) -> Optional[Path]:
    media_path = Path(media_path)
    if not media_path.exists():
        logger.warning(f"thumbnail source missing: {media_path}")
        return None
    dst = _cache_path(media_path)
    if dst.exists() and dst.stat().st_mtime >= media_path.stat().st_mtime:
        return dst
    try:
        ext = media_path.suffix.lower()
        if _is_image(media_path):
            _thumbnail_image(media_path, dst)
        elif ext == ".pdf":
            _thumbnail_pdf(media_path, dst)
        else:
            logger.info(f"no thumbnailer yet for {ext}")
            return None
        return dst
    except Exception as e:
        logger.error(f"thumbnail generation failed for {media_path}: {e}")
        return None
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest tests/test_thumbnailer.py -v
```

Expected: All 4 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/media/thumbnailer.py tests/test_thumbnailer.py
git commit -m "feat(thumbs): PDF thumbnail via fitz page-1 render"
```

---

### Task 9: Video thumbnail via `ffmpeg`

**Files:**
- Modify: `src/media/thumbnailer.py`
- Test: `tests/test_thumbnailer.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_thumbnailer.py`:

```python
import shutil


def test_video_thumbnail_generated(media_root):
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg not installed in this environment")
    src = media_root / "videos" / "clip.mp4"
    src.parent.mkdir(parents=True, exist_ok=True)
    import subprocess
    subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=duration=1:size=320x180:rate=30",
        "-pix_fmt", "yuv420p", str(src),
    ], check=True, capture_output=True)

    thumb = ensure_thumbnail(src)
    assert thumb is not None
    assert thumb.exists()


def test_video_thumbnail_failure_returns_none(media_root):
    src = media_root / "videos" / "not_a_video.mp4"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text("this is not a valid video file")
    thumb = ensure_thumbnail(src)
    assert thumb is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_thumbnailer.py -v -k video
```

Expected: failures — `.mp4` returns `None` because no video path is wired.

- [ ] **Step 3: Add ffmpeg-based extraction**

Add to `src/media/thumbnailer.py`:

```python
import subprocess

VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".webm"}


def _thumbnail_video(src: Path, dst: Path) -> None:
    """Grab a frame ~10% into the clip, scaled to THUMB_SIZE."""
    cmd = [
        "ffmpeg", "-y",
        "-ss", "10%",
        "-i", str(src),
        "-frames:v", "1",
        "-vf", f"scale={THUMB_SIZE[0]}:{THUMB_SIZE[1]}:force_original_aspect_ratio=decrease,"
               f"pad={THUMB_SIZE[0]}:{THUMB_SIZE[1]}:(ow-iw)/2:(oh-ih)/2:color=black",
        str(dst),
    ]
    result = subprocess.run(cmd, capture_output=True, timeout=30)
    if result.returncode != 0 or not dst.exists():
        raise RuntimeError(f"ffmpeg failed: {result.stderr.decode(errors='replace')[:200]}")
```

Update `ensure_thumbnail` dispatch (in the `try` block):

```python
        if _is_image(media_path):
            _thumbnail_image(media_path, dst)
        elif ext == ".pdf":
            _thumbnail_pdf(media_path, dst)
        elif ext in VIDEO_EXTS:
            _thumbnail_video(media_path, dst)
        else:
            logger.info(f"no thumbnailer yet for {ext}")
            return None
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_thumbnailer.py -v
```

Expected: All tests pass (test_video_thumbnail_generated skips if no ffmpeg).

- [ ] **Step 5: Commit**

```bash
git add src/media/thumbnailer.py tests/test_thumbnailer.py
git commit -m "feat(thumbs): video thumbnail via ffmpeg frame extraction"
```

---

### Task 10: Picture-set 2×2 grid composer

**Files:**
- Modify: `src/media/thumbnailer.py`
- Test: `tests/test_thumbnailer.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_thumbnailer.py`:

```python
from src.media.thumbnailer import compose_pictureset_thumbnail


def test_pictureset_thumbnail_composed(media_root):
    pics_dir = media_root / "pictures"
    pics_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for i, color in enumerate([(255,0,0), (0,255,0), (0,0,255), (255,255,0)]):
        p = pics_dir / f"pic{i}.jpg"
        _write_image(p, color=color)
        paths.append(p)

    out = pics_dir / "grid.png"
    result = compose_pictureset_thumbnail(paths, out)
    assert result == out
    assert out.exists()
    with Image.open(out) as t:
        assert t.size == THUMB_SIZE


def test_pictureset_thumbnail_handles_short_list(media_root):
    pics_dir = media_root / "pictures"
    pics_dir.mkdir(parents=True, exist_ok=True)
    p = pics_dir / "only.jpg"
    _write_image(p)
    out = pics_dir / "grid_one.png"
    result = compose_pictureset_thumbnail([p], out)
    assert result == out
    assert out.exists()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_thumbnailer.py -v -k pictureset
```

Expected: ImportError — `compose_pictureset_thumbnail` not defined.

- [ ] **Step 3: Implement the composer**

Add to `src/media/thumbnailer.py`:

```python
def compose_pictureset_thumbnail(picture_paths, out_path: Path) -> Optional[Path]:
    """Compose a 2x2 mini-grid of the first 4 picture thumbnails into out_path.

    If fewer than 4 pictures, empty quadrants stay black. Returns out_path on
    success, None on failure.
    """
    out_path = Path(out_path)
    try:
        cell_w, cell_h = THUMB_SIZE[0] // 2, THUMB_SIZE[1] // 2
        canvas = Image.new("RGB", THUMB_SIZE, (0, 0, 0))
        slots = [(0,0), (cell_w,0), (0,cell_h), (cell_w,cell_h)]
        for slot_xy, src in zip(slots, list(picture_paths)[:4]):
            tile_thumb = ensure_thumbnail(Path(src))
            if tile_thumb is None:
                continue
            with Image.open(tile_thumb) as t:
                t = t.resize((cell_w, cell_h), Image.Resampling.LANCZOS)
                canvas.paste(t, slot_xy)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        canvas.save(out_path, format="PNG")
        return out_path
    except Exception as e:
        logger.error(f"pictureset thumbnail failed: {e}")
        return None
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_thumbnailer.py -v
```

Expected: All thumbnailer tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/media/thumbnailer.py tests/test_thumbnailer.py
git commit -m "feat(thumbs): picture-set 2x2 grid composer"
```

---

### Task 11: Wire thumbnailer into `/upload`

**Files:**
- Modify: `src/network/web_interface.py` (in the `/upload` POST handler)
- Modify: `.gitignore`

- [ ] **Step 1: Add `media/.thumbs/` to .gitignore**

Append to `.gitignore` (create file if missing):

```
media/.thumbs/
```

- [ ] **Step 2: Find the upload handler**

```bash
grep -n "def upload\|@.*route.*upload\|conversion-note" src/network/web_interface.py | head -10
```

Note the line numbers / function name printed.

- [ ] **Step 3: Add the thumbnail call**

In `src/network/web_interface.py`:

1. Add this import at the top of the file (with other module imports):

```python
from src.media.thumbnailer import ensure_thumbnail
```

2. After the file has been saved (and after PPTX→PDF conversion if applicable), add:

```python
# Pre-generate a thumbnail so the curator UI shows it immediately. Failure
# is non-fatal — the catalog editor falls back to a placeholder.
try:
    ensure_thumbnail(Path(saved_path))
except Exception as e:
    logger.warning(f"thumbnail pre-generation failed for {saved_path}: {e}")
```

(Replace `saved_path` with whatever variable the surrounding code uses for the final on-disk path. If a PPTX was converted, use the resulting PDF path.)

- [ ] **Step 4: Smoke-test by hand**

```bash
python -c "
from src.media.thumbnailer import ensure_thumbnail
from pathlib import Path
import glob
hits = glob.glob('media/pictures/*.jpg') + glob.glob('media/pictures/*.png')
if hits:
    out = ensure_thumbnail(Path(hits[0]))
    print('thumb:', out)
else:
    print('no test image present — skip')
"
```

Expected: prints a path under `media/.thumbs/`, file exists.

- [ ] **Step 5: Commit**

```bash
git add .gitignore src/network/web_interface.py
git commit -m "feat(thumbs): generate thumbnail on upload"
```

---

## Phase 3 — Menu rendering (`menu.py`)

### Task 12: Add `kind` argument and badge to `_draw_tile`

**Files:**
- Modify: `src/display/menu.py`
- Test: `tests/test_menu_rendering.py`

We extend the existing `_draw_tile` helper rather than replacing it.

- [ ] **Step 1: Write the failing test**

Create `tests/test_menu_rendering.py`:

```python
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame
import pytest


@pytest.fixture(autouse=True, scope="module")
def _pygame_init():
    pygame.init()
    pygame.display.set_mode((1280, 720))
    yield
    pygame.quit()


from src.display.menu import _MenuBase, BADGE_GLYPHS


def test_badge_glyph_map_complete():
    for key in ("category", "video", "pdf", "pictureset", "nav_back", "nav_next"):
        assert key in BADGE_GLYPHS, f"missing badge for {key}"


def test_draw_tile_accepts_kind_argument():
    """Smoke: passing kind doesn't crash and draws *something* in the badge area."""
    surf = pygame.display.get_surface()
    base = _MenuBase(settings=None)
    import asyncio
    asyncio.get_event_loop().run_until_complete(base.initialize(screen=surf))
    base._draw_tile(50, 50, 400, 250, (37, 99, 235), "Blue", "European Theater",
                    kind="category")
    px = surf.get_at((50 + 400 - 24, 50 + 24))
    assert px[0] > 100 or px[1] > 100 or px[2] > 100
```

- [ ] **Step 2: Run test to verify it fails**

```bash
SDL_VIDEODRIVER=dummy python -m pytest tests/test_menu_rendering.py -v
```

Expected: ImportError on `BADGE_GLYPHS`, or TypeError on the `kind` kwarg.

- [ ] **Step 3: Extend `_draw_tile` with `kind` and add the badge map**

In `src/display/menu.py`, near the top of the file, add:

```python
BADGE_GLYPHS = {
    "category":   "›",         # ›
    "video":      "▶",         # ▶
    "pdf":        "\U0001F4C4",     # 📄
    "pictureset": "\U0001F5BC",     # 🖼
    "nav_back":   "←",         # ←
    "nav_next":   "→",         # →
}
```

Extend `_MenuBase.__init__`:

```python
        self._badge_font = None   # init lazily in initialize()
```

In `_MenuBase.initialize`, after the other fonts:

```python
        self._badge_font = pygame.font.SysFont("DejaVu Sans", 30, bold=True)
```

REPLACE `_draw_tile`:

```python
    def _draw_tile(self, x, y, w, h, color, label_text, body_text, kind=None):
        rect = pygame.Rect(x, y, w, h)
        pygame.draw.rect(self.screen, color, rect, border_radius=20)
        pygame.draw.rect(self.screen, (255, 255, 255), rect, width=4, border_radius=20)

        if label_text:
            label = self.fonts['color'].render(label_text, True, (255, 255, 255))
            self.screen.blit(label, label.get_rect(midtop=(x + w // 2, y + 16)))

        pad_x = 30
        text_top = (y + 16 + 48) if label_text else (y + 24)
        text_bottom = y + h - 24
        text_w = w - 2 * pad_x
        text_h = text_bottom - text_top
        if text_h > 0 and text_w > 0:
            body_text = body_text or "—"
            font, wrapped = self._fit_text(body_text, text_w, text_h)
            line_height = font.get_linesize()
            block_h = line_height * len(wrapped)
            cur_y = text_top + max(0, (text_h - block_h) // 2)
            for line in wrapped:
                ls = font.render(line, True, (255, 255, 255))
                self.screen.blit(ls, ls.get_rect(midtop=(x + w // 2, cur_y)))
                cur_y += line_height

        # Kind badge in the top-right corner
        if kind and kind in BADGE_GLYPHS and self._badge_font is not None:
            glyph = BADGE_GLYPHS[kind]
            badge = self._badge_font.render(glyph, True, (255, 255, 255))
            self.screen.blit(badge, badge.get_rect(topright=(x + w - 14, y + 14)))
```

- [ ] **Step 4: Run test to verify it passes**

```bash
SDL_VIDEODRIVER=dummy python -m pytest tests/test_menu_rendering.py -v
```

Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/display/menu.py tests/test_menu_rendering.py
git commit -m "feat(menu): kind badges on tiles"
```

---

### Task 13: Rewrite `CategoryMenu` to read the new tree and hide null slots

**Files:**
- Modify: `src/display/menu.py`
- Test: `tests/test_menu_rendering.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_menu_rendering.py`:

```python
from types import SimpleNamespace
import asyncio
from src.display.menu import CategoryMenu
from src.input.category_store import Node, NodeKind


class _FakeStore:
    def __init__(self, slots):
        self._slots = slots

    def root_slots(self):
        return self._slots


def _settings():
    return SimpleNamespace(display=SimpleNamespace(
        fullscreen=False, width=1280, height=720,
        slideshow_interval=10, idle_timeout=30,
    ))


def test_category_menu_lit_slots_for_present_nodes():
    store = _FakeStore({
        "1": Node(kind=NodeKind.CATEGORY, title="EU", children=[]),
        "2": None,
        "3": Node(kind=NodeKind.VIDEO, title="Midway", file="midway.mp4"),
        "4": None,
    })
    menu = CategoryMenu(_settings(), store)
    asyncio.get_event_loop().run_until_complete(menu.initialize(screen=pygame.display.get_surface()))
    lit = menu.lit_slots()
    assert lit == [1, 3]


def test_category_menu_all_null_lit_is_empty():
    store = _FakeStore({s: None for s in ("1","2","3","4")})
    menu = CategoryMenu(_settings(), store)
    asyncio.get_event_loop().run_until_complete(menu.initialize(screen=pygame.display.get_surface()))
    assert menu.lit_slots() == []


def test_category_menu_draw_skips_null_tiles():
    """A null slot must leave its quadrant untouched (background color)."""
    store = _FakeStore({
        "1": Node(kind=NodeKind.CATEGORY, title="EU", children=[]),
        "2": None, "3": None, "4": None,
    })
    menu = CategoryMenu(_settings(), store)
    asyncio.get_event_loop().run_until_complete(menu.initialize(screen=pygame.display.get_surface()))
    menu.draw()
    surf = pygame.display.get_surface()
    sw, sh = surf.get_size()
    px = surf.get_at((sw - 100, 200))   # right-column / top-row of the grid
    # Background is (20, 20, 25); drawn tiles paint strong colors + white border
    assert px[0] < 50 and px[1] < 50 and px[2] < 50
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
SDL_VIDEODRIVER=dummy python -m pytest tests/test_menu_rendering.py -v -k category
```

Expected: errors — `lit_slots` undefined, draw still uses old store API.

- [ ] **Step 3: Replace `CategoryMenu`**

In `src/display/menu.py`, REPLACE the `CategoryMenu` class with:

```python
class CategoryMenu(_MenuBase):
    """Top-level menu: up to 4 colored tiles, one per root slot.
    Slots that are None are not drawn — visitors see only configured tiles.
    """

    def __init__(self, settings, store):
        super().__init__(settings)
        self.store = store

    def lit_slots(self):
        """Return the list of button ids (1-4) that have a defined node."""
        return [int(s) for s, n in self.store.root_slots().items() if n is not None]

    def draw(self):
        if self.screen is None:
            self.screen = pygame.display.get_surface()
        if self.screen is None:
            return
        sw, sh = self._draw_chrome("Choose a topic",
                                   "Press a colored button to browse")
        cells = self._layout_2x2(sw, sh)
        for slot_id_str, (x, y, w, h) in zip(("1", "2", "3", "4"), cells):
            node = self.store.root_slots().get(slot_id_str)
            if node is None:
                continue   # hide tile entirely
            button_id = int(slot_id_str)
            color = COLORS[button_id][1]
            label = COLORS[button_id][0]
            body = node.title or "(untitled)"
            kind = node.kind.value
            if kind == "category" and not node.children:
                body = f"{body}\n(no items yet)"
            self._draw_tile(x, y, w, h, color, label, body, kind=kind)
        pygame.display.flip()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
SDL_VIDEODRIVER=dummy python -m pytest tests/test_menu_rendering.py -v
```

Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/display/menu.py tests/test_menu_rendering.py
git commit -m "feat(menu): CategoryMenu honors null slots, exposes lit_slots()"
```

---

### Task 14: Generalize `ItemMenu` into `SubMenu` that walks a path

**Files:**
- Modify: `src/display/menu.py`
- Test: `tests/test_menu_rendering.py`

We replace `ItemMenu` with a `SubMenu` class that takes a path into the tree and draws that node's children.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_menu_rendering.py`:

```python
from src.display.menu import SubMenu


def _store_with(*children, parent_title="EU"):
    return _FakeStore({
        "1": Node(kind=NodeKind.CATEGORY, title=parent_title, children=list(children)),
        "2": None, "3": None, "4": None,
    })


def _resolve(store, path):
    # Minimal resolve for _FakeStore so SubMenu can find its parent node.
    if not path:
        return None
    node = store.root_slots().get(str(path[0]))
    for idx in path[1:]:
        if node is None or node.kind is not NodeKind.CATEGORY:
            return None
        if idx < 0 or idx >= len(node.children):
            return None
        node = node.children[idx]
    return node


def _menu_at(store, path):
    # Patch resolve onto the fake store for the duration of the test.
    store.resolve = lambda p: _resolve(store, p)
    m = SubMenu(_settings(), store)
    asyncio.get_event_loop().run_until_complete(
        m.initialize(screen=pygame.display.get_surface()))
    m.open(path)
    return m


def test_submenu_button4_is_back_with_three_children():
    store = _store_with(
        Node(kind=NodeKind.VIDEO, title="A", file="a.mp4"),
        Node(kind=NodeKind.VIDEO, title="B", file="b.mp4"),
        Node(kind=NodeKind.VIDEO, title="C", file="c.mp4"),
    )
    m = _menu_at(store, [1])
    items, paginated = m.visible_items()
    assert paginated is False
    assert len(items) == 3
    assert m.selection_for_button(4) == ("back",)


def test_submenu_button4_is_back_with_four_children():
    children = [Node(kind=NodeKind.VIDEO, title=f"V{i}", file=f"v{i}.mp4") for i in range(4)]
    store = _store_with(*children)
    m = _menu_at(store, [1])
    items, paginated = m.visible_items()
    assert paginated is False
    assert len(items) == 3   # 4th unreachable; tile 4 is Back
    assert m.selection_for_button(4) == ("back",)


def test_submenu_pagination_at_five_children():
    children = [Node(kind=NodeKind.VIDEO, title=f"V{i}", file=f"v{i}.mp4") for i in range(5)]
    store = _store_with(*children)
    m = _menu_at(store, [1])
    assert m.selection_for_button(4) == ("next",)
    m.next_page()
    assert m.selection_for_button(4) == ("back",)


def test_submenu_drill_into_subcategory():
    store = _store_with(
        Node(kind=NodeKind.CATEGORY, title="Air", children=[
            Node(kind=NodeKind.VIDEO, title="BoB", file="bob.mp4"),
        ]),
    )
    m = _menu_at(store, [1])
    action = m.selection_for_button(1)
    assert action[0] == "drill"
    assert action[1] == [1, 0]


def test_submenu_play_leaf():
    store = _store_with(
        Node(kind=NodeKind.VIDEO, title="X", file="x.mp4"),
    )
    m = _menu_at(store, [1])
    action = m.selection_for_button(1)
    assert action[0] == "play"
    assert action[1].file == "x.mp4"
    assert action[2] == [1, 0]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
SDL_VIDEODRIVER=dummy python -m pytest tests/test_menu_rendering.py -v -k submenu
```

Expected: ImportError on `SubMenu`.

- [ ] **Step 3: Replace `ItemMenu` with `SubMenu`**

In `src/display/menu.py`, REPLACE the `ItemMenu` class entirely with:

```python
class SubMenu(_MenuBase):
    """Menu showing children of a category node anywhere in the tree.

    Set the current location via open(path). Pagination kicks in only when a
    category has 5+ children — with ≤4 children tile 4 is reserved as Back,
    and tiles 1-3 show items. With exactly 4 children, the 4th is unreachable
    from this menu — curators should add a 5th to enable pagination (the
    curator UI surfaces this warning).
    """

    def __init__(self, settings, store):
        super().__init__(settings)
        self.store = store
        self.path: List[int] = []   # path to the parent CATEGORY node
        self.page = 0
        self.page_size = 3

    def open(self, path):
        self.path = list(path)
        self.page = 0

    def _parent_node(self):
        return self.store.resolve(self.path) if self.path else None

    def _children(self):
        n = self._parent_node()
        if n is None or n.kind is not NodeKind.CATEGORY:
            return []
        return list(n.children)

    def _is_paginated(self):
        return len(self._children()) > 4

    def _page_count(self):
        n = len(self._children())
        if n <= 4:
            return 1
        return max(1, (n + self.page_size - 1) // self.page_size)

    def _is_last_page(self):
        return self._is_paginated() and self.page >= self._page_count() - 1

    def next_page(self):
        if self._is_paginated() and self.page < self._page_count() - 1:
            self.page += 1

    def visible_items(self):
        """Return (children_for_this_page, paginated_flag).
        At most 3 children when paginated (tile 4 is Next/Back).
        When not paginated, returns 0-3 children (tile 4 is always Back).
        """
        children = self._children()
        if len(children) <= 4:
            return children[:3], False
        start = self.page * self.page_size
        return children[start:start + self.page_size], True

    def selection_for_button(self, button_id):
        """Returns one of:
          ('play', node, abs_path)   — play a leaf
          ('drill', abs_path)        — drill into a sub-category
          ('next',)                  — advance the page
          ('back',)                  — go up one level
          ('noop',)
        """
        items, paginated = self.visible_items()
        if button_id == 4:
            if paginated and not self._is_last_page():
                return ('next',)
            return ('back',)
        idx = button_id - 1
        if 0 <= idx < len(items):
            node = items[idx]
            absolute_idx = (self.page * self.page_size if paginated else 0) + idx
            abs_path = self.path + [absolute_idx]
            if node.kind is NodeKind.CATEGORY:
                return ('drill', abs_path)
            return ('play', node, abs_path)
        return ('noop',)

    def draw(self):
        if self.screen is None:
            self.screen = pygame.display.get_surface()
        if self.screen is None:
            return

        parent = self._parent_node()
        title = parent.title if parent else "(empty)"
        items, paginated = self.visible_items()
        n_total = len(self._children())

        page_info = ""
        if paginated:
            pages = self._page_count()
            page_info = f"  ({self.page + 1} / {pages})"

        sw, sh = self._draw_chrome(title + page_info,
                                   "Press the matching colored button to play")
        cells = self._layout_2x2(sw, sh)

        for slot in range(4):
            x, y, w, h = cells[slot]
            button_id = slot + 1
            label = COLORS[button_id][0]
            color = COLORS[button_id][1]

            if button_id == 4:
                if paginated and not self._is_last_page():
                    self._draw_tile(x, y, w, h, _BTN4_COLOR, label, "Next  →",
                                    kind="nav_next")
                else:
                    self._draw_tile(x, y, w, h, _BTN4_COLOR, label, "←  Back",
                                    kind="nav_back")
                continue

            if slot < len(items):
                node = items[slot]
                self._draw_tile(x, y, w, h, color, label,
                                node.title or getattr(node, "file", ""),
                                kind=node.kind.value)
            else:
                continue   # empty slot — leave hidden

        pygame.display.flip()
```

Also add at the top of the file (with other imports):

```python
from src.input.category_store import NodeKind
```

And BELOW the `SubMenu` class, add a compatibility alias so the old `display_controller.py` import path still works until Task 17:

```python
# Backwards-compat name — display_controller import switches in Task 17.
ItemMenu = SubMenu
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
SDL_VIDEODRIVER=dummy python -m pytest tests/test_menu_rendering.py -v
```

Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/display/menu.py tests/test_menu_rendering.py
git commit -m "feat(menu): SubMenu walks tree by path; button 4 always Back"
```

---

## Phase 4 — Topic-slideshow leaf

### Task 15: `TopicSlideshow` skeleton with auto-advance

**Files:**
- Create: `src/display/topic_slideshow.py`
- Create: `tests/test_topic_slideshow.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_topic_slideshow.py`:

```python
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import asyncio
from pathlib import Path
from types import SimpleNamespace
import pytest
import pygame
from PIL import Image

from src.input.category_store import Node, NodeKind


@pytest.fixture(autouse=True, scope="module")
def _pygame_init():
    pygame.init()
    pygame.display.set_mode((1280, 720))
    yield
    pygame.quit()


from src.display.topic_slideshow import TopicSlideshow


def _settings(tmp_path):
    return SimpleNamespace(
        display=SimpleNamespace(slideshow_interval=10, idle_timeout=30,
                                fullscreen=False, width=1280, height=720),
        media=SimpleNamespace(pictures_dir=str(tmp_path / "pictures")),
    )


def _make_images(tmp_path, names):
    d = tmp_path / "pictures"
    d.mkdir(parents=True, exist_ok=True)
    for i, n in enumerate(names):
        Image.new("RGB", (800, 450), (i*40 % 255, 50, 50)).save(d / n)


def test_advance_index_loops(tmp_path):
    _make_images(tmp_path, ["a.jpg", "b.jpg"])
    leaf = Node(kind=NodeKind.PICTURESET, title="Set",
                files=["a.jpg", "b.jpg"],
                captions=["", ""], interval_sec=3)
    ts = TopicSlideshow(_settings(tmp_path))
    asyncio.get_event_loop().run_until_complete(
        ts.initialize(screen=pygame.display.get_surface()))
    ts.open(leaf)
    assert ts.current_index == 0
    ts.advance()
    assert ts.current_index == 1
    ts.advance()
    assert ts.current_index == 0


def test_open_missing_file_falls_through(tmp_path):
    leaf = Node(kind=NodeKind.PICTURESET, title="Set",
                files=["nope.jpg"], captions=[""], interval_sec=3)
    ts = TopicSlideshow(_settings(tmp_path))
    asyncio.get_event_loop().run_until_complete(
        ts.initialize(screen=pygame.display.get_surface()))
    ts.open(leaf)
    ts.draw()
    assert ts.current_index == 0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
SDL_VIDEODRIVER=dummy python -m pytest tests/test_topic_slideshow.py -v
```

Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement the module**

Create `src/display/topic_slideshow.py`:

```python
"""Plays a curated picture-set leaf as an auto-advancing slideshow."""
import asyncio
import logging
from pathlib import Path

import pygame
from PIL import Image

logger = logging.getLogger(__name__)


class TopicSlideshow:
    def __init__(self, settings):
        self.settings = settings
        self.screen = None
        self._caption_font = None
        self.leaf = None              # current pictureset Node
        self.current_index = 0
        self.running = False
        self._task = None

    async def initialize(self, screen=None):
        self.screen = screen or pygame.display.get_surface()
        self._caption_font = pygame.font.SysFont("DejaVu Sans", 28, bold=False)

    def open(self, leaf):
        self.leaf = leaf
        self.current_index = 0

    def advance(self):
        if not self.leaf:
            return
        n = len(self.leaf.files)
        if n == 0:
            return
        self.current_index = (self.current_index + 1) % n

    async def start(self):
        if self.running:
            return
        self.running = True
        self.draw()
        self._task = asyncio.create_task(self._loop())

    async def _loop(self):
        try:
            while self.running and self.leaf is not None:
                await asyncio.sleep(max(3, self.leaf.interval_sec))
                if not self.running:
                    return
                self.advance()
                self.draw()
        except asyncio.CancelledError:
            return

    async def stop(self):
        self.running = False
        if self._task and not self._task.done():
            self._task.cancel()
        self._task = None

    def draw(self):
        if self.screen is None or self.leaf is None:
            return
        sw, sh = self.screen.get_size()
        self.screen.fill((0, 0, 0))

        file = self.leaf.files[self.current_index] if self.leaf.files else None
        if file:
            src = Path(self.settings.media.pictures_dir) / file
            if src.exists():
                try:
                    img = Image.open(src).convert("RGB")
                    ratio = min(sw / img.width, sh / img.height)
                    new_size = (max(1, int(img.width * ratio)),
                                max(1, int(img.height * ratio)))
                    img = img.resize(new_size, Image.Resampling.LANCZOS)
                    surf = pygame.image.fromstring(img.tobytes(), img.size, img.mode)
                    self.screen.blit(surf, surf.get_rect(center=(sw // 2, sh // 2)))
                except Exception as e:
                    logger.error(f"topic slideshow draw {src}: {e}")
            else:
                logger.warning(f"topic slideshow file missing: {src}")

        hint = self._caption_font.render("Press Red to go back", True,
                                         (180, 180, 180))
        self.screen.blit(hint, hint.get_rect(midbottom=(sw // 2, sh - 10)))

        pygame.display.flip()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
SDL_VIDEODRIVER=dummy python -m pytest tests/test_topic_slideshow.py -v
```

Expected: tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/display/topic_slideshow.py tests/test_topic_slideshow.py
git commit -m "feat(topic-slideshow): auto-advance picture-set playback"
```

---

### Task 16: Caption overlay

**Files:**
- Modify: `src/display/topic_slideshow.py`
- Test: `tests/test_topic_slideshow.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_topic_slideshow.py`:

```python
def test_caption_drawn_when_present(tmp_path):
    _make_images(tmp_path, ["a.jpg"])
    leaf = Node(kind=NodeKind.PICTURESET, title="Set",
                files=["a.jpg"], captions=["Hello caption"], interval_sec=3)
    ts = TopicSlideshow(_settings(tmp_path))
    asyncio.get_event_loop().run_until_complete(
        ts.initialize(screen=pygame.display.get_surface()))
    ts.open(leaf)
    ts.draw()
    surf = pygame.display.get_surface()
    sw, sh = surf.get_size()
    # Sample inside the caption bar band (centered at sh*0.92)
    px = surf.get_at((sw // 2, int(sh * 0.92)))
    # Caption bar is translucent dark with white text — pixel is near-black or near-white
    assert (px[0] < 80 and px[1] < 80 and px[2] < 80) or (px[0] > 200)


def test_no_caption_drawn_when_empty(tmp_path):
    _make_images(tmp_path, ["a.jpg"])
    leaf = Node(kind=NodeKind.PICTURESET, title="Set",
                files=["a.jpg"], captions=[""], interval_sec=3)
    ts = TopicSlideshow(_settings(tmp_path))
    asyncio.get_event_loop().run_until_complete(
        ts.initialize(screen=pygame.display.get_surface()))
    ts.open(leaf)
    ts.draw()
    assert ts.current_index == 0   # no crash
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
SDL_VIDEODRIVER=dummy python -m pytest tests/test_topic_slideshow.py -v -k caption
```

Expected: caption-present test may fail because the caption band isn't drawn.

- [ ] **Step 3: Add caption rendering**

In `src/display/topic_slideshow.py`, IN `draw()`, BEFORE the final `pygame.display.flip()`, add:

```python
        # Caption overlay (only when this slide has non-empty caption text)
        if (self.leaf.captions
                and self.current_index < len(self.leaf.captions)
                and self.leaf.captions[self.current_index].strip()):
            cap = self.leaf.captions[self.current_index]
            bar_h = int(sh * 0.12)
            bar = pygame.Surface((sw, bar_h), pygame.SRCALPHA)
            bar.fill((0, 0, 0, 180))
            self.screen.blit(bar, (0, sh - bar_h - 40))
            txt = self._caption_font.render(cap, True, (255, 255, 255))
            self.screen.blit(txt, txt.get_rect(center=(sw // 2,
                                                       sh - bar_h // 2 - 40)))
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
SDL_VIDEODRIVER=dummy python -m pytest tests/test_topic_slideshow.py -v
```

Expected: tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/display/topic_slideshow.py tests/test_topic_slideshow.py
git commit -m "feat(topic-slideshow): translucent caption bar"
```

---

## Phase 5 — Display controller integration

### Task 17: Wire `SubMenu` + `TopicSlideshow` into `display_controller.py`

**Files:**
- Modify: `src/display/display_controller.py`
- Modify: `src/main.py` (button-press dispatch)

This is integration; verification is the existing unit tests plus a manual smoke run.

- [ ] **Step 1: Update `DisplayController`**

In `src/display/display_controller.py`:

1. Change the import line from `from .menu import CategoryMenu, ItemMenu` to:

```python
from .menu import CategoryMenu, SubMenu
from .topic_slideshow import TopicSlideshow
from src.input.category_store import NodeKind
```

2. Extend the `DisplayMode` enum:

```python
class DisplayMode(Enum):
    SLIDESHOW = "slideshow"
    CATEGORY_MENU = "category_menu"
    SUBMENU = "submenu"
    VIDEO = "video"
    PICTURESET = "pictureset"
    IDLE = "idle"
```

3. In `DisplayController.__init__`, REPLACE the `self.item_menu = ItemMenu(...)` line with:

```python
        self.sub_menu = SubMenu(settings, store) if store else None
        self.topic_slideshow = TopicSlideshow(settings)
        # Stack of path indices so multi-level Back is one press per level.
        self._menu_stack: list = []
```

4. In `initialize()`, REPLACE the `self.item_menu` initialize block with:

```python
        if self.sub_menu:
            await self.sub_menu.initialize(screen=self.slideshow.screen)
        await self.topic_slideshow.initialize(screen=self.slideshow.screen)
```

- [ ] **Step 2: Replace `show_item_menu` with path-based `show_submenu`**

In `src/display/display_controller.py`, REPLACE `show_item_menu` with:

```python
    async def show_submenu(self, path):
        """Open the menu at `path` (e.g. [1] or [1, 0]). Pushes the path so
        Back can pop one level at a time.
        """
        if self.sub_menu is None:
            logger.warning("show_submenu called but no store available")
            return
        if self.store is not None:
            self.store.load()
        logger.info(f"Showing submenu at path {path}")
        if self.current_mode == DisplayMode.SLIDESHOW:
            await self.slideshow.stop()
        self._menu_stack = list(path)
        self.sub_menu.open(self._menu_stack)
        self.current_mode = DisplayMode.SUBMENU
        self.menu_shown_at = time.time()
        self.sub_menu.draw()

    async def go_back_one_level(self):
        """Pop one level off the menu stack. If empty, return to root menu."""
        if len(self._menu_stack) > 1:
            self._menu_stack.pop()
            self.sub_menu.open(self._menu_stack)
            self.current_mode = DisplayMode.SUBMENU
            self.menu_shown_at = time.time()
            self.sub_menu.draw()
        else:
            self._menu_stack = []
            await self.show_category_menu()
```

- [ ] **Step 3: Add the picture-set player entry points**

After `play_pdf`, ADD:

```python
    async def play_pictureset(self, leaf):
        """Begin auto-advancing picture-set playback."""
        logger.info(f"Playing pictureset: {leaf.title}")
        if self.current_mode == DisplayMode.SLIDESHOW:
            await self.slideshow.stop()
        self.current_mode = DisplayMode.PICTURESET
        self.last_activity = time.time()
        self.topic_slideshow.open(leaf)
        await self.topic_slideshow.start()

    async def stop_pictureset(self):
        await self.topic_slideshow.stop()
```

- [ ] **Step 4: Update `_pdf_play_handler` and `_video_end_handler`**

In `_pdf_play_handler`, REPLACE the trailing block:

```python
        if self.item_menu is not None and self.item_menu.cat_id is not None:
            await self.show_item_menu(self.item_menu.cat_id)
        else:
            await self.start_slideshow()
```

with:

```python
        if self._menu_stack:
            await self.show_submenu(self._menu_stack)
        else:
            await self.start_slideshow()
```

In `_video_end_handler`, do the same substitution.

- [ ] **Step 5: Update `cleanup()`**

```python
    async def cleanup(self):
        logger.info("Cleaning up display controller")
        await self.video_player.cleanup()
        await self.slideshow.cleanup()
        await self.topic_slideshow.stop()
```

- [ ] **Step 6: Update the button-press dispatch in `main.py`**

Find the dispatch:

```bash
grep -n "show_item_menu\|show_category_menu\|item_menu\|selection_for_button" src/main.py
```

For each call site, apply the following changes (the agent should read the surrounding code to place these correctly):

**Root-level press (current mode is `CATEGORY_MENU`):**

```python
button_id = pressed_button   # 1..4
if button_id in controller.category_menu.lit_slots():
    root_node = controller.store.get_root_slot(button_id)
    if root_node.kind is NodeKind.CATEGORY:
        await controller.show_submenu([button_id])
    elif root_node.kind is NodeKind.VIDEO:
        controller._menu_stack = [button_id]
        from pathlib import Path
        video_path = Path(controller.settings.media.videos_dir) / root_node.file
        await controller.play_video(str(video_path))
    elif root_node.kind is NodeKind.PDF:
        controller._menu_stack = [button_id]
        from pathlib import Path
        pdf_path = Path(controller.settings.media.pictures_dir) / root_node.file
        await controller.play_pdf(str(pdf_path))
    elif root_node.kind is NodeKind.PICTURESET:
        controller._menu_stack = [button_id]
        await controller.play_pictureset(root_node)
# else: hidden tile — ignore the press
```

**SubMenu press (current mode is `SUBMENU`):**

```python
action = controller.sub_menu.selection_for_button(button_id)
op = action[0]
if op == "play":
    node, abs_path = action[1], action[2]
    controller._menu_stack = abs_path[:-1]
    if node.kind is NodeKind.VIDEO:
        from pathlib import Path
        video_path = Path(controller.settings.media.videos_dir) / node.file
        await controller.play_video(str(video_path))
    elif node.kind is NodeKind.PDF:
        from pathlib import Path
        pdf_path = Path(controller.settings.media.pictures_dir) / node.file
        await controller.play_pdf(str(pdf_path))
    elif node.kind is NodeKind.PICTURESET:
        await controller.play_pictureset(node)
elif op == "drill":
    await controller.show_submenu(action[1])
elif op == "next":
    controller.sub_menu.next_page()
    controller.sub_menu.draw()
    controller.reset_menu_timeout()
elif op == "back":
    await controller.go_back_one_level()
# noop: ignore
```

**Picture-set playback press (current mode is `PICTURESET`):**

```python
if button_id == 4:
    await controller.stop_pictureset()
    if controller._menu_stack:
        await controller.show_submenu(controller._menu_stack)
    else:
        await controller.show_category_menu()
# buttons 1-3 ignored during picture-set playback
```

Also import `NodeKind` at the top of `main.py`:

```python
from src.input.category_store import NodeKind
```

- [ ] **Step 7: Manual smoke test**

```bash
ssh pi5 "cd /home/sysadmin/ww2_kiosk-main && git pull && sudo pkill -f 'src/main.py'"
```

Physically:
1. Press any defined top-level button → SubMenu or direct play.
2. Press Red anywhere below root → one level up.
3. From a 5+ child sub-category, press Red repeatedly → Next ... Back.

- [ ] **Step 8: Commit**

```bash
git add src/display/display_controller.py src/main.py
git commit -m "feat(controller): route SubMenu and TopicSlideshow with path-based back nav"
```

---

## Phase 6 — Curator UI

### Task 18: Catalog routes — read-only root view

**Files:**
- Modify: `src/network/web_interface.py`
- Create: `src/network/templates/catalog_root.html`
- Test: `tests/test_catalog_routes.py`

- [ ] **Step 1: Discover the existing template pattern**

```bash
grep -n "render_template\|template_folder\|templates/" src/network/web_interface.py | head -10
ls src/network/templates 2>/dev/null && echo "templates dir exists" || echo "no templates dir"
```

If `templates/` doesn't exist, create it (`mkdir -p src/network/templates`). If the Flask app isn't already configured with `template_folder="templates"`, add that arg at the `Flask()` instantiation site:

```python
self.app = Flask(__name__, template_folder="templates")
```

- [ ] **Step 2: Write the failing test**

Create `tests/test_catalog_routes.py`:

```python
import json
from pathlib import Path
from types import SimpleNamespace
import pytest

from src.input.category_store import CategoryStore, Node, NodeKind


@pytest.fixture
def app_with_store(tmp_path):
    cfg = tmp_path / "config"
    cfg.mkdir()
    media = tmp_path / "media"
    (media / "videos").mkdir(parents=True)
    (media / "pictures").mkdir(parents=True)
    settings = SimpleNamespace(
        config=SimpleNamespace(button_mappings_file=str(cfg / "button_mappings.json")),
        media=SimpleNamespace(videos_dir=str(media / "videos"),
                              pictures_dir=str(media / "pictures")),
        display=SimpleNamespace(slideshow_interval=10, idle_timeout=30,
                                fullscreen=False, width=1280, height=720),
        network=SimpleNamespace(enable_web=True, web_host="127.0.0.1", web_port=0),
    )
    store = CategoryStore(settings)
    store._tree = {
        "1": Node(kind=NodeKind.CATEGORY, title="EU", children=[
            Node(kind=NodeKind.VIDEO, title="D-Day", file="dday.mp4"),
        ]),
        "2": None,
        "3": Node(kind=NodeKind.VIDEO, title="Midway", file="midway.mp4"),
        "4": None,
    }
    store.save()

    from src.network.web_interface import WebInterface
    web = WebInterface(settings, store=store, controller=None)
    app = web.app
    app.config["TESTING"] = True
    return app, store


def test_catalog_root_renders_existing_slots(app_with_store):
    app, _ = app_with_store
    with app.test_client() as c:
        r = c.get("/settings/catalog")
        assert r.status_code == 200
        body = r.data.decode()
        assert "EU" in body
        assert "Midway" in body
        assert "Slot 2" in body
        assert "Slot 4" in body


def test_catalog_root_links_to_drilldown(app_with_store):
    app, _ = app_with_store
    with app.test_client() as c:
        r = c.get("/settings/catalog")
        body = r.data.decode()
        assert "/settings/catalog/1" in body
```

- [ ] **Step 3: Run test to verify it fails**

```bash
python -m pytest tests/test_catalog_routes.py -v
```

Expected: 404 — `/settings/catalog` not defined. Also, `WebInterface.__init__` may not yet accept `store` and `controller` kwargs — if not, add them with defaults of `None`.

- [ ] **Step 4: Create the template**

Create `src/network/templates/catalog_root.html`:

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Catalog — WW2 Kiosk</title>
  <style>
    body { font-family: -apple-system, system-ui, sans-serif; margin: 2em; }
    h1 { margin: 0 0 1em 0; }
    .slot { border: 2px solid #ccc; border-radius: 12px; padding: 1em; margin: 1em 0;
            display: flex; gap: 1em; align-items: center; }
    .slot.empty { border-style: dashed; color: #999; }
    .swatch { width: 32px; height: 32px; border-radius: 6px; flex-shrink: 0; }
    .blue { background: #2563eb; } .green { background: #16a34a; }
    .yellow { background: #ca8a04; } .red { background: #dc2626; }
    .meta { flex: 1; }
    a.btn { display: inline-block; padding: .5em .8em; background: #333; color: #fff;
            border-radius: 6px; text-decoration: none; margin-right: .5em; }
    form { display: inline; }
    .clear { background: #b00; color: #fff; border: 0; padding: .5em .8em;
             border-radius: 6px; cursor: pointer; }
  </style>
</head>
<body>
  <h1>Catalog</h1>
  <p><a href="/settings">&larr; back to settings</a></p>

  {% for slot_id, slot, color in slots %}
  <div class="slot {% if slot is none %}empty{% endif %}">
    <div class="swatch {{ color }}"></div>
    <div class="meta">
      <strong>Slot {{ slot_id }} ({{ color }})</strong>
      {% if slot is none %}
        <em>— empty (tile hidden from visitors)</em>
      {% else %}
        <div>{{ slot.title or '(untitled)' }} <small>[{{ slot.kind.value }}]</small></div>
      {% endif %}
    </div>
    <div>
      <a class="btn" href="/settings/catalog/{{ slot_id }}">Edit</a>
      {% if slot is not none %}
      <form method="post" action="/settings/catalog/{{ slot_id }}/delete"
            onsubmit="return confirm('Clear slot {{ slot_id }}? Items below it will be removed.');">
        <button class="clear" type="submit">Clear this slot</button>
      </form>
      {% endif %}
    </div>
  </div>
  {% endfor %}
</body>
</html>
```

- [ ] **Step 5: Add the route**

In `src/network/web_interface.py`, inside the route-registration block of `WebInterface`:

```python
        @self.app.route("/settings/catalog")
        def settings_catalog_root():
            from flask import render_template
            slots = []
            colors = {"1": "blue", "2": "green", "3": "yellow", "4": "red"}
            for slot_id in ("1", "2", "3", "4"):
                slots.append((slot_id, self.store.get_root_slot(slot_id),
                              colors[slot_id]))
            return render_template("catalog_root.html", slots=slots)
```

If `WebInterface.__init__` doesn't accept `store`, add it (default `None`) and assign `self.store = store`.

- [ ] **Step 6: Run test to verify it passes**

```bash
python -m pytest tests/test_catalog_routes.py -v
```

Expected: tests pass.

- [ ] **Step 7: Commit**

```bash
git add src/network/web_interface.py src/network/templates/catalog_root.html tests/test_catalog_routes.py
git commit -m "feat(curator): catalog root view"
```

---

### Task 19: Catalog drill-down view

**Files:**
- Modify: `src/network/web_interface.py`
- Create: `src/network/templates/catalog_view.html`
- Test: `tests/test_catalog_routes.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_catalog_routes.py`:

```python
def test_catalog_drilldown_shows_breadcrumb_and_children(app_with_store):
    app, _ = app_with_store
    with app.test_client() as c:
        r = c.get("/settings/catalog/1")
        assert r.status_code == 200
        body = r.data.decode()
        assert "EU" in body
        assert "D-Day" in body
        assert "Home" in body


def test_catalog_drilldown_handles_leaf_path(app_with_store):
    app, _ = app_with_store
    with app.test_client() as c:
        r = c.get("/settings/catalog/3")
        assert r.status_code == 200
        body = r.data.decode()
        assert "Midway" in body
        assert "midway.mp4" in body


def test_catalog_drilldown_invalid_path_returns_404(app_with_store):
    app, _ = app_with_store
    with app.test_client() as c:
        r = c.get("/settings/catalog/1/99")
        assert r.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_catalog_routes.py -v -k drilldown
```

Expected: 404 errors.

- [ ] **Step 3: Create the template**

Create `src/network/templates/catalog_view.html`:

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Catalog — {{ node.title or 'Edit' }}</title>
  <style>
    body { font-family: -apple-system, system-ui, sans-serif; margin: 2em; }
    nav.crumbs { margin-bottom: 1em; font-size: 1.1em; }
    nav.crumbs a { color: #2563eb; text-decoration: none; }
    nav.crumbs .sep { color: #aaa; margin: 0 .5em; }
    .child { border: 1px solid #ccc; border-radius: 10px; padding: 1em;
             margin: .8em 0; display: flex; gap: 1em; align-items: center; }
    .thumb { width: 160px; height: 90px; background: #222; object-fit: cover; border-radius: 6px; }
    .meta { flex: 1; }
    label { display: inline-block; width: 80px; color: #555; }
    input[type=text] { width: 60%; padding: .3em; }
    select { padding: .3em; }
    button, .btn { padding: .4em .8em; border-radius: 6px; border: 0; cursor: pointer;
                   text-decoration: none; }
    .primary { background: #2563eb; color: #fff; }
    .danger  { background: #b00; color: #fff; }
    .add-row { background: #f5f5f5; padding: 1em; border-radius: 8px; margin-top: 2em; }
    .empty { color: #999; font-style: italic; }
  </style>
</head>
<body>
  <nav class="crumbs">
    <a href="/settings/catalog">Home</a>
    {% for label, link in breadcrumbs %}
      <span class="sep">&rsaquo;</span>
      {% if link %}<a href="{{ link }}">{{ label }}</a>{% else %}{{ label }}{% endif %}
    {% endfor %}
  </nav>

  <h1>{{ node.title or '(untitled)' }} <small>[{{ node.kind.value }}]</small></h1>

  <form method="post" action="/settings/catalog/{{ path_str }}/save">
    <p><label>Title:</label>
      <input type="text" name="title" value="{{ node.title or '' }}"></p>
    {% if node.kind.value in ('video','pdf') %}
      <p><label>File:</label>
        <input type="text" name="file" value="{{ node.file or '' }}"></p>
    {% endif %}
    {% if node.kind.value == 'pictureset' %}
      <p><label>Interval (sec):</label>
        <input type="number" name="interval_sec" value="{{ node.interval_sec }}" min="3" max="60"></p>
      <p><label>Files (one per line):</label><br>
        <textarea name="files" rows="6" cols="50">{{ '\n'.join(node.files) }}</textarea></p>
      <p><label>Captions (one per line, blank line for none):</label><br>
        <textarea name="captions" rows="6" cols="50">{{ '\n'.join(node.captions) }}</textarea></p>
    {% endif %}
    <p><button class="primary" type="submit">Save</button></p>
  </form>

  {% if node.kind.value == 'category' %}
    <h2>Children</h2>
    {% if not node.children %}
      <p class="empty">No children yet — add one below.</p>
    {% endif %}
    {% for child, child_path in zip(node.children, child_paths) %}
      <div class="child">
        {% if child.thumb_url %}
          <img class="thumb" src="{{ child.thumb_url }}" alt="">
        {% else %}
          <div class="thumb" title="no thumbnail"></div>
        {% endif %}
        <div class="meta">
          <strong>{{ child.title or '(untitled)' }}</strong>
          <span style="color:#888">[{{ child.kind.value }}]</span><br>
          {% if child.file %}<small>{{ child.file }}</small>{% endif %}
        </div>
        <div>
          <a class="btn primary" href="/settings/catalog/{{ child_path }}">Edit</a>
          <form method="post" action="/settings/catalog/{{ child_path }}/delete"
                style="display:inline"
                onsubmit="return confirm('Delete this entry and any children?');">
            <button class="danger" type="submit">Delete</button>
          </form>
        </div>
      </div>
    {% endfor %}

    <div class="add-row">
      <form method="post" action="/settings/catalog/{{ path_str }}/add-child">
        <label>Add child:</label>
        <select name="kind">
          <option value="video">Video</option>
          <option value="pdf">PDF</option>
          <option value="pictureset">Picture-set</option>
          {% if can_add_subcategory %}<option value="category">Sub-category</option>{% endif %}
        </select>
        <input type="text" name="title" placeholder="Title" required>
        <input type="text" name="file" placeholder="filename.mp4 (for video/PDF)">
        <button class="primary" type="submit">Add</button>
      </form>
      {% if not can_add_subcategory %}
        <p><em>Sub-categories disabled at this depth (max 3 levels).</em></p>
      {% endif %}
    </div>
  {% endif %}
</body>
</html>
```

- [ ] **Step 4: Add the drill-down route and supporting helpers**

In `src/network/web_interface.py`:

```python
    def _resolve_media_path(self, basename):
        from pathlib import Path
        for d in (self.settings.media.videos_dir,
                  self.settings.media.pictures_dir):
            p = Path(d) / basename
            if p.exists():
                return p
        return None
```

```python
        @self.app.route("/settings/catalog/<path:catalog_path>")
        def settings_catalog_view(catalog_path):
            from flask import render_template, abort
            from src.input.category_store import parse_path, format_path
            from src.media.thumbnailer import ensure_thumbnail
            try:
                path = parse_path(catalog_path)
            except ValueError:
                abort(404)
            node = self.store.resolve(path)
            if node is None:
                abort(404)

            breadcrumbs = []
            for i in range(1, len(path) + 1):
                ancestor = self.store.resolve(path[:i])
                label = ancestor.title if ancestor else f"slot {path[0]}"
                link = (f"/settings/catalog/{format_path(path[:i])}"
                        if i < len(path) else None)
                breadcrumbs.append((label, link))

            child_paths = []
            for i, child in enumerate(getattr(node, 'children', []) or []):
                child_paths.append(format_path(path + [i]))
                if child.kind.value in ("video", "pdf"):
                    full = self._resolve_media_path(child.file)
                    if full:
                        ensure_thumbnail(full)
                        child.thumb_url = f"/thumb/{child.file}"
                    else:
                        child.thumb_url = None
                elif child.kind.value == "pictureset" and child.files:
                    child.thumb_url = f"/pictureset-thumb/{format_path(path + [i])}"
                else:
                    child.thumb_url = None

            return render_template(
                "catalog_view.html",
                node=node,
                path_str=format_path(path),
                breadcrumbs=breadcrumbs,
                child_paths=child_paths,
                can_add_subcategory=(len(path) < 2),
                zip=zip,
            )
```

Add a `/thumb/<file>` static-style route:

```python
        @self.app.route("/thumb/<path:basename>")
        def serve_thumb(basename):
            from flask import send_file, abort
            from src.media.thumbnailer import ensure_thumbnail
            full = self._resolve_media_path(basename)
            if full is None:
                abort(404)
            thumb = ensure_thumbnail(full)
            if thumb is None or not thumb.exists():
                abort(404)
            return send_file(thumb, mimetype="image/png")
```

- [ ] **Step 5: Run test to verify it passes**

```bash
python -m pytest tests/test_catalog_routes.py -v
```

Expected: drill-down tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/network/web_interface.py src/network/templates/catalog_view.html tests/test_catalog_routes.py
git commit -m "feat(curator): catalog drill-down view with breadcrumbs and thumbs"
```

---

### Task 20: Save / add-child / delete endpoints

**Files:**
- Modify: `src/network/web_interface.py`
- Test: `tests/test_catalog_routes.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_catalog_routes.py`:

```python
def test_save_updates_leaf(app_with_store):
    app, store = app_with_store
    with app.test_client() as c:
        r = c.post("/settings/catalog/3/save", data={"title": "Midway 1942",
                                                     "file": "midway.mp4"})
        assert r.status_code in (200, 302)
    assert store.get_root_slot(3).title == "Midway 1942"


def test_add_video_child(app_with_store):
    app, store = app_with_store
    with app.test_client() as c:
        r = c.post("/settings/catalog/1/add-child",
                   data={"kind": "video", "title": "Stalingrad",
                         "file": "stalingrad.mp4"})
        assert r.status_code in (200, 302)
    eu = store.get_root_slot(1)
    assert eu.children[-1].file == "stalingrad.mp4"


def test_delete_child(app_with_store):
    app, store = app_with_store
    with app.test_client() as c:
        r = c.post("/settings/catalog/1/0/delete")
        assert r.status_code in (200, 302)
    assert len(store.get_root_slot(1).children) == 0


def test_delete_root_slot_clears(app_with_store):
    app, store = app_with_store
    with app.test_client() as c:
        c.post("/settings/catalog/3/delete")
    assert store.get_root_slot(3) is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_catalog_routes.py -v -k "save_updates or add_video or delete"
```

Expected: 404 for these routes.

- [ ] **Step 3: Add the endpoints**

In `src/network/web_interface.py`:

```python
        @self.app.route("/settings/catalog/<path:catalog_path>/save", methods=["POST"])
        def settings_catalog_save(catalog_path):
            from flask import request, redirect, abort
            from src.input.category_store import parse_path, Node, NodeKind, format_path
            try:
                path = parse_path(catalog_path)
            except ValueError:
                abort(400)
            node = self.store.resolve(path)
            if node is None:
                abort(404)

            new_title = request.form.get("title", node.title)
            if node.kind in (NodeKind.VIDEO, NodeKind.PDF):
                new = Node(kind=node.kind, title=new_title,
                           file=request.form.get("file", node.file))
            elif node.kind is NodeKind.PICTURESET:
                files = [l.strip() for l in
                         request.form.get("files", "").splitlines() if l.strip()]
                captions = request.form.get("captions", "").splitlines()
                while len(captions) < len(files):
                    captions.append("")
                captions = captions[:len(files)]
                interval = int(request.form.get("interval_sec", node.interval_sec))
                new = Node(kind=node.kind, title=new_title, files=files,
                           captions=captions, interval_sec=interval)
            elif node.kind is NodeKind.CATEGORY:
                new = Node(kind=node.kind, title=new_title, children=node.children)
            else:
                abort(400)

            try:
                self.store.replace_node(path, new)
            except ValueError as e:
                return f"Save rejected: {e}", 400
            return redirect(f"/settings/catalog/{format_path(path)}")


        @self.app.route("/settings/catalog/<path:catalog_path>/add-child", methods=["POST"])
        def settings_catalog_add_child(catalog_path):
            from flask import request, redirect, abort
            from src.input.category_store import parse_path, Node, NodeKind, format_path
            try:
                path = parse_path(catalog_path)
            except ValueError:
                abort(400)
            kind = request.form.get("kind")
            title = request.form.get("title", "")
            file = request.form.get("file", "")
            try:
                k = NodeKind(kind)
            except ValueError:
                return f"unknown kind: {kind}", 400
            if k is NodeKind.CATEGORY:
                new = Node(kind=k, title=title, children=[])
            elif k in (NodeKind.VIDEO, NodeKind.PDF):
                new = Node(kind=k, title=title, file=file)
            elif k is NodeKind.PICTURESET:
                if not file:
                    return ("Picture-sets must be created via the dedicated form "
                            "(no files set yet)."), 400
                new = Node(kind=k, title=title, files=[file],
                           captions=[""], interval_sec=6)
            else:
                return f"unknown kind: {kind}", 400
            try:
                self.store.add_child(path, new)
            except ValueError as e:
                return f"Add rejected: {e}", 400
            return redirect(f"/settings/catalog/{format_path(path)}")


        @self.app.route("/settings/catalog/<path:catalog_path>/delete", methods=["POST"])
        def settings_catalog_delete(catalog_path):
            from flask import redirect, abort
            from src.input.category_store import parse_path, format_path
            try:
                path = parse_path(catalog_path)
            except ValueError:
                abort(400)
            try:
                self.store.delete_node(path)
            except ValueError as e:
                return f"Delete rejected: {e}", 400
            parent_path = path[:-1]
            return redirect("/settings/catalog" if not parent_path
                            else f"/settings/catalog/{format_path(parent_path)}")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_catalog_routes.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/network/web_interface.py tests/test_catalog_routes.py
git commit -m "feat(curator): save / add-child / delete endpoints"
```

---

### Task 21: Drag reorder + client-side JS

**Files:**
- Modify: `src/network/web_interface.py`
- Modify: `src/network/templates/catalog_view.html`
- Test: `tests/test_catalog_routes.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_catalog_routes.py`:

```python
def test_reorder_endpoint(app_with_store):
    app, store = app_with_store
    store.add_child([1], Node(kind=NodeKind.PDF, title="Maps", file="maps.pdf"))
    with app.test_client() as c:
        r = c.post("/settings/catalog/1/reorder",
                   json={"order": [1, 0]})
        assert r.status_code in (200, 302, 204)
    eu = store.get_root_slot(1)
    assert [c.title for c in eu.children] == ["Maps", "D-Day"]


def test_reorder_rejects_bad_permutation(app_with_store):
    app, _ = app_with_store
    with app.test_client() as c:
        r = c.post("/settings/catalog/1/reorder",
                   json={"order": [0, 0]})
        assert r.status_code == 400
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_catalog_routes.py -v -k reorder
```

Expected: 404.

- [ ] **Step 3: Add the endpoint**

In `src/network/web_interface.py`:

```python
        @self.app.route("/settings/catalog/<path:catalog_path>/reorder", methods=["POST"])
        def settings_catalog_reorder(catalog_path):
            from flask import request, abort
            from src.input.category_store import parse_path
            try:
                path = parse_path(catalog_path)
            except ValueError:
                abort(400)
            order = (request.get_json(silent=True) or {}).get("order")
            if not isinstance(order, list):
                return "order must be a list", 400
            try:
                self.store.reorder_children(path, [int(i) for i in order])
            except ValueError as e:
                return f"Reorder rejected: {e}", 400
            return "", 204
```

- [ ] **Step 4: Add drag-and-drop JS to the template**

Append to `src/network/templates/catalog_view.html`, just before `</body>`:

```html
{% if node.kind.value == 'category' and node.children %}
<script>
(function() {
  const path = "{{ path_str }}";
  const list = Array.from(document.querySelectorAll('.child'));
  list.forEach((el, i) => {
    el.draggable = true;
    el.dataset.originalIndex = i;
    el.addEventListener('dragstart', (e) => {
      e.dataTransfer.setData('text/plain', i.toString());
      el.style.opacity = '0.5';
    });
    el.addEventListener('dragend', () => { el.style.opacity = '1'; });
    el.addEventListener('dragover', (e) => e.preventDefault());
    el.addEventListener('drop', (e) => {
      e.preventDefault();
      const from = parseInt(e.dataTransfer.getData('text/plain'), 10);
      const to = parseInt(el.dataset.originalIndex, 10);
      if (from === to) return;
      const order = list.map((_, j) => j);
      const moved = order.splice(from, 1)[0];
      order.splice(to, 0, moved);
      fetch(`/settings/catalog/${path}/reorder`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ order })
      }).then(r => {
        if (r.ok) location.reload();
        else r.text().then(t => alert('Reorder failed: ' + t));
      });
    });
  });
})();
</script>
{% endif %}
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
python -m pytest tests/test_catalog_routes.py -v
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add src/network/web_interface.py src/network/templates/catalog_view.html tests/test_catalog_routes.py
git commit -m "feat(curator): drag-reorder children with /reorder endpoint"
```

---

### Task 22: Picture-set thumbnail endpoint

**Files:**
- Modify: `src/network/web_interface.py`
- Test: `tests/test_catalog_routes.py`

The catalog template references `/pictureset-thumb/<path>` for the picture-set composite thumbnail.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_catalog_routes.py`:

```python
def test_pictureset_thumb_endpoint(app_with_store, tmp_path):
    app, store = app_with_store
    pics_dir = Path(store.settings.media.pictures_dir)
    pics_dir.mkdir(parents=True, exist_ok=True)
    for i, color in enumerate([(200, 50, 50), (50, 200, 50)]):
        from PIL import Image
        Image.new("RGB", (640, 360), color).save(pics_dir / f"p{i}.jpg")
    leaf = Node(kind=NodeKind.PICTURESET, title="Set",
                files=["p0.jpg", "p1.jpg"], captions=["", ""], interval_sec=6)
    eu = store.get_root_slot(1)
    eu.children.append(leaf)
    store.save()
    idx = len(eu.children) - 1

    with app.test_client() as c:
        r = c.get(f"/pictureset-thumb/1/{idx}")
        assert r.status_code == 200
        assert r.headers["Content-Type"].startswith("image/")
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_catalog_routes.py -v -k pictureset_thumb
```

Expected: 404.

- [ ] **Step 3: Add the route**

In `src/network/web_interface.py`:

```python
        @self.app.route("/pictureset-thumb/<path:catalog_path>")
        def serve_pictureset_thumb(catalog_path):
            from flask import send_file, abort
            from pathlib import Path
            from src.input.category_store import parse_path, NodeKind
            from src.media.thumbnailer import compose_pictureset_thumbnail, _cache_dir
            import hashlib
            try:
                path = parse_path(catalog_path)
            except ValueError:
                abort(404)
            node = self.store.resolve(path)
            if node is None or node.kind is not NodeKind.PICTURESET:
                abort(404)
            pics_dir = Path(self.settings.media.pictures_dir)
            file_paths = [pics_dir / f for f in node.files]
            key = hashlib.sha1(("|".join(node.files)).encode("utf-8")).hexdigest()
            out = _cache_dir(pics_dir / "x") / f"pictureset-{key}.png"
            if not out.exists():
                if compose_pictureset_thumbnail(file_paths, out) is None:
                    abort(500)
            return send_file(out, mimetype="image/png")
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest tests/test_catalog_routes.py -v
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add src/network/web_interface.py tests/test_catalog_routes.py
git commit -m "feat(curator): pictureset composite thumbnail endpoint"
```

---

## Phase 7 — Polish & smoke test

### Task 23: Final integration smoke test

**Files:**
- No code changes — hands-on verification step.

- [ ] **Step 1: Push the branch and deploy to the Pi**

```bash
git push origin HEAD
ssh pi5 "cd /home/sysadmin/ww2_kiosk-main && git pull && sudo pkill -f 'src/main.py'"
```

(The `kiosk-session` script's `while true` loop restarts `main.py` automatically.)

- [ ] **Step 2: Run the manual smoke checklist**

| # | Action | Expected |
|---|---|---|
| 1 | Boot kiosk on a fresh Pi (no `categories.json`) | All 4 tiles hidden; button presses do nothing; idle slideshow runs |
| 2 | Upload an MP4 via `/upload` | `media/.thumbs/<hash>.png` appears |
| 3 | Add a top-level category in `/settings/catalog` | Visiting `/settings/catalog` shows it; kiosk shows the tile in its assigned color |
| 4 | Add a sub-category one level deep | Drilling on the kiosk shows the sub-category tile with the `›` badge |
| 5 | Add a video, a PDF, and a picture-set inside the sub-category | Each shows the correct badge (`▶`, `📄`, `🖼️`) |
| 6 | Press the picture-set tile | Auto-advances; captions show only when set; press Red → back to sub-menu |
| 7 | Add 5 items in one sub-category | Pagination: tile 4 is Next; last page tile 4 is Back |
| 8 | Set slot 2 to `null` via "Clear this slot" | Tile 2 disappears immediately; LED 2 off |
| 9 | Drag-reorder children in `/settings/catalog/<path>` | Order on the kiosk matches |
| 10 | Lose home wifi → AP fallback comes up | Admin can still reach `/settings/catalog` at 10.42.0.1:8080 |

- [ ] **Step 3: If any step fails, fix and re-deploy**

Open a fresh subagent for the fix or apply inline. Re-run the failing step until it passes.

- [ ] **Step 4: Commit any final tweaks**

```bash
git add -p
git commit -m "fix: post-smoke-test polish" || echo "no tweaks needed"
```

- [ ] **Step 5: Tag the feature**

```bash
git tag -a hierarchical-menu-v1 -m "3-level catalog + picture-set leaves"
git push origin hierarchical-menu-v1
```

---

## Self-review summary

- **Spec coverage** — every numbered item in the design doc is addressed: hierarchy (Tasks 1-5), hide-null-tiles (Task 13), kind badges (Task 12), pictureset leaf (Tasks 15-16), back semantics (Task 17), drill-down admin UI (Tasks 18-19), thumbnails on upload (Tasks 7-11), drag reorder (Task 21), migration (Task 4), atomic save (Task 3), tests for the three high-risk modules (Tasks 1-5, 7-10, 12-14), smoke checklist (Task 23).
- **Placeholders** — none. Each code-modifying step shows the full code.
- **Type consistency** — `Node` / `NodeKind` named consistently. `replace_node` / `add_child` / `reorder_children` / `delete_node` used identically across Tasks 5 and 20. `_menu_stack` referenced the same way in Tasks 17 + 23. `parse_path` / `format_path` used consistently.
- **One gap to flag for the implementer** — `src/main.py`'s button-press dispatch isn't visible in this plan (file wasn't read during planning). Task 17 step 6 directs the implementer to grep for call sites and apply the dispatch update. If the handler turns out more entangled than expected, that step may need decomposition into 2-3 sub-tasks during execution.

---
