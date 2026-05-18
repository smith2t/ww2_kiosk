# Hierarchical Menu + Topic-Slideshow Leaves

**Date:** 2026-05-18
**Platform:** Raspberry Pi 5 (BCM2712), Debian 12 bookworm, Python 3.11
**Status:** Approved design — ready for implementation planning

## Problem

The catalog today is two levels deep: 4 fixed colored buttons (Blue/Green/Yellow/Red) at the top, each a flat list of items, paginated when there are more than four. Curators can't group items into sub-topics, and every top-level slot must show a tile even when the museum didn't define content for it.

That limits the kiosk's educational value: a visitor sees four buttons regardless of what's there, and a category can't be subdivided (e.g., "European Theater → Air War, Ground War, D-Day"). The brainstorm also surfaced a parallel need — a way to present a curated set of pictures on a single subject as its own piece of content, distinct from the attract-loop slideshow.

## Goals

- Let curators build a 3-level catalog: root → sub-category → leaf.
- A node at any non-root level may be a sub-category **or** a playable leaf (mixed content per menu).
- Top-level slots may be left undefined; their tile is hidden and the button is a no-op.
- Add a new leaf kind, `pictureset`: a curator-chosen set of pictures that auto-advances with optional per-picture captions.
- Give the curator a drill-down admin UI with thumbnails for every node.

## Non-goals

- Depth greater than 3.
- Visitor-side captions on video/PDF leaves (only picture-sets get captions in this iteration).
- Re-ordering root slots (button-to-color mapping is physical).
- Cross-category moves / shared items (curators may duplicate entries for now).
- Search inside the admin UI.
- Multi-user admin auth.

## Visitor experience

```
ROOT (CategoryMenu)
├─ slot null → tile hidden, LED off, button = no-op
├─ slot is leaf → press → play immediately, button 4 = back
└─ slot is category → press → drill into SubMenu
       │
       SubMenu (one level down)
       ├─ 1-3 children → tiles 1-3 show them, tile 4 = "← Back"
       ├─ 4 children   → tiles 1-3 show first 3, tile 4 = "Back"
       ├─ 5+ children  → tiles 1-3 = page, tile 4 = "Next →" or "← Back" on last page
       │
       │   pressing a child:
       │   ├─ leaf     → play
       │   └─ category → drill deeper (third level uses the same SubMenu code)
```

### Back semantics

- **Root**: tile 4 is whatever slot 4 holds (a normal category, a leaf, or hidden if null). No "back" needed.
- **Any sub-level**: tile 4 is always Back. With pagination, tile 4 reads "Next →" until the last page, then "← Back to topics". One extra press always exits.
- **Idle timeout** (existing `idle_timeout: 30`) from any menu or playback → return to attract slideshow.

### Tile drawing — kind badges

`_draw_tile()` gains a `kind` argument. A small white badge (~32 px) is drawn in the top-right corner:

| kind | badge | meaning |
|---|---|---|
| `category`   | `›`        | drills in |
| `video`      | `▶`        | plays a video |
| `pdf`        | `📄`        | plays a PDF document |
| `pictureset` | `🖼️`        | plays a curated slideshow |
| `nav`        | `←` or `→` | tile-4 Back / Next |

The badge sits over the existing colored tile body so the physical-button color association stays intact.

### Topic-slideshow playback (`pictureset` leaf)

- Implemented as a new `TopicSlideshow` class in `src/display/topic_slideshow.py`, sibling to `Slideshow`.
- Renders to the same pygame surface as the menu and attract slideshow.
- Auto-advances every `interval_sec` seconds (per-set, always present; the admin UI pre-fills `6` when a new picture-set is added).
- Caption rendered in a translucent bar across the bottom 12% of the screen, drawn only when the caption string is non-empty.
- Loops continuously while open.
- Exit triggers: **button 4 press** or **idle timeout**. Buttons 1-3 are ignored (hands-off model — visitor only needs to learn one rule).
- On-screen hint along the bottom edge: "Press Red to go back".

### LED behavior

- An LED is on only for the tiles drawn on the current screen.
- Root: LED for a null slot is off.
- Sub-level: tile-4 LED is always on (it's always Back or Next).
- Leaf playback (video / PDF / picture-set): only LED 4 is on (signals "press red to return").

## Data model

`config/categories.json` schema, version 2:

```json
{
  "version": 2,
  "tree": {
    "1": {
      "kind": "category",
      "title": "European Theater",
      "children": [
        { "kind": "category", "title": "Air War", "children": [
            { "kind": "video", "file": "battle_of_britain.mp4",
              "title": "Battle of Britain" }
        ] },
        { "kind": "video", "file": "dday.mp4", "title": "D-Day" },
        { "kind": "pdf",   "file": "maps.pdf", "title": "Theater Maps" },
        { "kind": "pictureset",
          "title": "Liberation of Paris",
          "files": ["paris_01.jpg", "paris_02.jpg", "paris_03.jpg"],
          "captions": ["Aug 25 1944 — De Gaulle on the Champs-Élysées", "", ""],
          "interval_sec": 6
        }
      ]
    },
    "2": null,
    "3": { "kind": "video", "file": "midway.mp4", "title": "Midway" },
    "4": { "kind": "category", "title": "Home Front", "children": [] }
  }
}
```

### Node kinds

- `category` — has `title: str`, `children: [Node]`. Children may be any kind.
- `video` — has `title: str`, `file: str` (basename under `media/videos/`).
- `pdf` — has `title: str`, `file: str` (basename under `media/pictures/`).
- `pictureset` — has `title: str`, `files: [str]` (basenames under `media/pictures/`, ≥1), `captions: [str]` (parallel to `files`, may be empty strings), `interval_sec: int` (required, 3-60; admin UI pre-fills `6`).

### Schema rules

- Depth ≤ 3 (root → category → category → leaf).
- Root `tree` always contains exactly slots `"1".."4"`. A slot may be `null` (hidden tile) or any node kind.
- `replace_node(path, node)` enforces all of the above and rejects invalid saves.
- Files referenced by leaves must exist on disk; missing files log a warning and render a placeholder tile.

### Persistence

- Atomic write: `categories.json.tmp` → `os.replace()` over `categories.json` so power-loss can't leave a half-written file.
- On first migration, the v1 file is preserved as `categories.v1.bak.json` next to it.

## Migration (v1 → v2)

`CategoryStore.load()` reads the `version` field. Absent or `< 2` triggers `_migrate_v1_to_v2`:

```python
def _migrate_v1_to_v2(self, v1: dict) -> dict:
    """categories[1..4].items[]  ->  tree[1..4]{kind: category, children: [...]}"""
    tree = {}
    for cid in ("1","2","3","4"):
        cat = v1.get("categories", {}).get(cid)
        if not cat or not cat.get("items"):
            tree[cid] = None
            continue
        children = []
        for item in cat["items"]:
            ext = Path(item["file"]).suffix.lower()
            kind = "pdf" if ext == ".pdf" else "video"
            children.append({"kind": kind, "file": item["file"],
                             "title": item.get("title", "")})
        tree[cid] = {"kind": "category", "title": cat["title"], "children": children}
    return {"version": 2, "tree": tree}
```

Empty v1 categories migrate to `null` slots — matches the new "hide empty top-level tile" behavior.

## Curator UI

### Routes (added to `web_interface.py`)

```
GET  /settings/catalog                   # root view: 4 top-level slots
GET  /settings/catalog/<path>            # drill into a node
POST /settings/catalog/<path>/save       # update node title / leaf fields
POST /settings/catalog/<path>/add-child  # append a new child to a category
POST /settings/catalog/<path>/reorder    # reorder children of a category
POST /settings/catalog/<path>/delete     # remove a node and its subtree
```

**Path encoding**: `/1/2/0` means root slot 1 → its child at index 2 → that node's child at index 0. Root slots stay 1-4 (they map to physical buttons); deeper levels are 0-based indices.

### Page layout

Breadcrumb at the top: `Home › European Theater › Air War` — each crumb links to that level.

Body — one card per child slot, in stored order:

```
┌────────────────────────────────────────────────────────────────┐
│  ⠿  [THUMBNAIL]   Title: [_____________________]    ▼ kind     │
│                    File:  dday.mp4 ▼                            │
│                    [Edit children]   [Delete]                   │
└────────────────────────────────────────────────────────────────┘
```

- `⠿` = drag handle (vanilla HTML5 drag-and-drop, no JS library).
- Thumbnail = cached PNG from `media/.thumbs/` (see below).
- Kind dropdown — switches the form: file picker for `video`/`pdf`, file multi-select + caption rows + interval input for `pictureset`, nothing extra for `category`.
- "Edit children" only on categories — opens that node's URL.

Bottom of every page:

```
+ Add child:  [Video ▼]  [pick file ▼]  [Title _______]  [Add]
```

### Root view differences

- Exactly 4 slots, fixed positions (Blue/Green/Yellow/Red); no reorder.
- Each slot card has a **Clear this slot** button that sets it back to `null`.

### Validation surface

Server-side checks on every save:

- Depth ≤ 3.
- Node kind matches its payload (e.g., `video` must have `file`, no `children`).
- `pictureset`: `len(files) ≥ 1`, `len(captions) == len(files)`, `3 ≤ interval_sec ≤ 60`.
- Referenced files exist under the allowed media dirs.
- Atomic save (temp file + `os.replace`).

## Thumbnails

`src/media/thumbnailer.py`:

```python
def ensure_thumbnail(media_path: Path) -> Path:
    """Return cached thumbnail PNG for media_path, generating it if missing."""
```

- Cache: `media/.thumbs/<sha1-of-relpath>.png`, 320×180.
- Regenerate when source mtime > thumbnail mtime.
- `.thumbs/` is added to `.gitignore`.

| Source | Method | Tool |
|---|---|---|
| Video (`.mp4`/`.mkv`/`.avi`) | Frame at 10% in, scaled | `ffmpeg -ss 10% -i in.mp4 -frames:v 1 -vf scale=320:180:flags=lanczos out.png` |
| PDF | Page 1 rendered to 320 px wide | `fitz` (existing dep) |
| Picture (`.jpg`/`.png`/`.bmp`/`.gif`) | Resize | `Pillow` (existing dep) |
| Picture-set | 2×2 grid of first 4 pictures' thumbnails | `Pillow`, composed from cached single-image thumbs |

`ffmpeg` is already installed by `scripts/install.sh`. No new system deps.

### Upload integration

`/upload` in `web_interface.py` currently saves the file then PPTX→PDF-converts. Extend:

```python
# (existing) save the upload to media/{videos,pictures}
# (existing) if PPTX, soffice --headless --convert-to pdf, delete original
# (new)     thumbnailer.ensure_thumbnail(saved_path)
```

If ffmpeg or fitz fails, log the error and serve a generic placeholder PNG — admin UI still works.

## Code layout

```
src/
├── input/
│   └── category_store.py       (modified — v2 schema, tree ops, path traversal)
├── display/
│   ├── menu.py                 (modified — kind badges, hide null tiles, breadcrumb stack)
│   ├── topic_slideshow.py      (NEW — pictureset playback)
│   └── display_controller.py   (modified — route to topic_slideshow on pictureset leaf)
├── media/
│   └── thumbnailer.py          (NEW — generate + cache thumbnails)
└── network/
    └── web_interface.py        (modified — /settings/catalog routes + templates)
config/
└── categories.json             (schema v2)
media/
└── .thumbs/                    (NEW — cache dir, .gitignored)
docs/superpowers/specs/
└── 2026-05-18-hierarchical-menu-with-picturesets-design.md   (this file)
```

## Testing

The repo has a `tests/` directory but sparse coverage. This feature adds targeted tests for the highest-risk modules:

- `tests/test_category_store.py` — v1 → v2 migration, depth-3 validation, path traversal, atomic save (write-then-replace, mid-write crash leaves the old file intact).
- `tests/test_thumbnailer.py` — cache hit / miss, mtime invalidation, ffmpeg failure → placeholder, picture-set grid composition.
- `tests/test_menu_rendering.py` — null-slot tile hidden, badge drawn per kind, button-4-always-back at sub-levels. Uses a pygame dummy surface (`SDL_VIDEODRIVER=dummy`), no display required.

No visitor-flow E2E tests — would require a real display + GPIO. Manual smoke-test plan instead:

1. Fresh kiosk with empty `categories.json` → migration runs → all 4 tiles hidden → button presses no-op.
2. Build a 3-level tree with all 4 leaf kinds via the admin UI → each draws the right badge.
3. Play a picture-set → captions appear → button 4 returns to parent menu.
4. Slot 2 set to null → tile not drawn → LED 2 off.
5. Sub-category with 5 items → pagination: 3 + Next, last page = Back.

## What ships in v1 and what doesn't

**In:**
- 3-level tree with mixed leaves and sub-categories.
- Hide-null-root-slot, button-4 = Back at all sub-levels.
- `pictureset` leaf with auto-advance, captions, button-4 exit.
- Drill-down admin UI with breadcrumb, drag-reorder, kind dropdown.
- Thumbnails for all leaf kinds, generated on upload, cached on disk.
- v1 → v2 auto-migration with `.bak` of the old file.
- Tests for the three highest-risk modules.

**Deliberately out (YAGNI):**
- Cross-category sharing / moving of items.
- Search in the admin UI.
- Visitor-side captions for video / PDF (picture-sets only).
- Re-ordering root slots.
- Multi-user admin auth.

## Open questions

None at design time. All decisions made during the brainstorm are encoded above.
