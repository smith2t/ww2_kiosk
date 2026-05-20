import pytest
from src.input.category_store import (
    Node, NodeKind, SCHEMA_VERSION,
    node_to_dict, node_from_dict,
    parse_path, format_path,
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


import json
from pathlib import Path
from types import SimpleNamespace

from src.input.category_store import CategoryStore


def _settings(tmp_path: Path) -> SimpleNamespace:
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
    assert not tmp.exists()
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
