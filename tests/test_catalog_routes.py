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
