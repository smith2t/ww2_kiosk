import json
from pathlib import Path
from types import SimpleNamespace
import pytest

from input.category_store import CategoryStore, Node, NodeKind


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

    from network.web_interface import WebInterface
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


def test_save_updates_leaf(app_with_store):
    app, store = app_with_store
    with app.test_client() as c:
        r = c.post("/settings/catalog/3/save",
                   data={"title": "Midway 1942", "file": "midway.mp4"})
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


def test_reorder_endpoint(app_with_store):
    app, store = app_with_store
    store.add_child([1], Node(kind=NodeKind.PDF, title="Maps", file="maps.pdf"))
    with app.test_client() as c:
        r = c.post("/settings/catalog/1/reorder", json={"order": [1, 0]})
        assert r.status_code in (200, 302, 204)
    eu = store.get_root_slot(1)
    assert [c.title for c in eu.children] == ["Maps", "D-Day"]


def test_reorder_rejects_bad_permutation(app_with_store):
    app, _ = app_with_store
    with app.test_client() as c:
        r = c.post("/settings/catalog/1/reorder", json={"order": [0, 0]})
        assert r.status_code == 400


def test_pictureset_thumb_endpoint(app_with_store):
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
