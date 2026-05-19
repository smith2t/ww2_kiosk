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
