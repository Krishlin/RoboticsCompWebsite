"""The past-events picker, each event's page, and the results band on the landing page."""

import json
from pathlib import Path

import pytest

from app import routes
from app.past_events import PAST_EVENTS, all_photos

STATIC = Path(routes.__file__).resolve().parent / "static"


def test_every_listed_photo_has_been_cut():
    # A photo listed in app/past_events.py but never run through
    # tools/cut_event_photos.py is silently dropped from the page. This is
    # what stops that shipping by accident.
    for event in PAST_EVENTS:
        folder = STATIC / "img" / "events" / event["slug"]
        manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        for photo in all_photos(event):
            entry = manifest["photos"].get(photo["src"])
            assert entry, f"{event['slug']}: {photo['src']} is listed but not cut"
            for size in entry["sizes"]:
                assert (folder / size["file"]).is_file(), size["file"]


def test_every_photo_has_alt_text():
    for event in PAST_EVENTS:
        for photo in all_photos(event):
            assert photo.get("alt", "").strip(), photo["src"]


def _event_url(event: dict) -> str:
    return f"/past-events/{event['slug']}"


def test_past_events_page_has_a_card_for_each_event(client):
    resp = client.get("/past-events")
    assert resp.status_code == 200
    page = resp.get_data(as_text=True)
    cards = page.split('class="event-cards"', 1)[1].split("</ul>", 1)[0]
    assert cards.count('class="event-card"') == len(PAST_EVENTS)
    for event in PAST_EVENTS:
        assert f'href="{_event_url(event)}"' in cards
        assert event["name"] in cards
        assert event["podium"][0]["name"] in cards
    # The picker is only the cards: the photos are on each event's page.
    assert 'class="photo"' not in page


def test_cards_are_in_the_listed_order(client):
    page = client.get("/past-events").get_data(as_text=True)
    positions = [page.index(f'href="{_event_url(e)}"') for e in PAST_EVENTS]
    assert positions == sorted(positions)


def test_a_card_shows_its_cover_photo(client):
    event = PAST_EVENTS[0]
    page = client.get("/past-events").get_data(as_text=True)
    card = page.split(f'href="{_event_url(event)}"', 1)[1].split("</a>", 1)[0]
    stem = Path(event["cover"]).stem.lower()
    assert f"img/events/{event['slug']}/{stem}-" in card


def test_a_cover_that_names_no_listed_photo_falls_back_to_the_champions(client, monkeypatch):
    event = {**PAST_EVENTS[0], "cover": "not-a-listed-photo.jpg"}
    monkeypatch.setattr(routes, "PAST_EVENTS", [event])
    page = client.get("/past-events").get_data(as_text=True)
    card = page.split(f'href="{_event_url(event)}"', 1)[1].split("</a>", 1)[0]
    champions_stem = Path(event["champions_photo"]["src"]).stem.lower()
    assert champions_stem in card


def test_event_page_shows_its_podium_and_photos(client):
    for event in PAST_EVENTS:
        resp = client.get(_event_url(event))
        assert resp.status_code == 200
        page = resp.get_data(as_text=True)
        assert f'id="{event["slug"]}"' in page
        assert f"<title>{event['name']} — Past events — Summit</title>" in page
        for winner in event["podium"]:
            assert winner["name"] in page
            assert winner["prize"] in page
        listed = sum(len(group["photos"]) for group in event["groups"])
        assert page.count('class="photo"') == listed
        # The way back to the picker.
        crumbs = page.split('class="crumbs"', 1)[1].split("</nav>", 1)[0]
        assert 'href="/past-events"' in crumbs


def test_event_page_lists_the_other_events_only_when_there_are_some(client, monkeypatch):
    first = PAST_EVENTS[0]
    page = client.get(_event_url(first)).get_data(as_text=True)
    if len(PAST_EVENTS) == 1:
        assert "More past events" not in page

    second = {**first, "slug": "older-event", "name": "Older Event"}
    monkeypatch.setattr(routes, "PAST_EVENTS", [first, second])
    page = client.get(_event_url(first)).get_data(as_text=True)
    more = page.split('id="more-title"', 1)[1]
    assert 'href="/past-events/older-event"' in more
    # Never a card for the page you are already on.
    assert f'href="{_event_url(first)}"' not in more


def test_unknown_event_is_a_404(client):
    assert client.get("/past-events/no-such-event").status_code == 404


def test_event_page_is_up_while_registration_only(app_factory):
    client = app_factory(REGISTRATION_ONLY=True).test_client()
    assert client.get(_event_url(PAST_EVENTS[0])).status_code == 200


def test_past_events_page_is_up_while_registration_only(app_factory):
    # main_bp is always registered, so the page has to work on the
    # registration-only deployment too.
    client = app_factory(REGISTRATION_ONLY=True).test_client()
    assert client.get("/past-events").status_code == 200


def _past_events_page(app_factory, registration_only: bool, path: str = "/past-events") -> str:
    client = app_factory(REGISTRATION_ONLY=registration_only).test_client()
    return client.get(path).get_data(as_text=True)


@pytest.mark.parametrize("path", ["/past-events", _event_url(PAST_EVENTS[0])])
def test_past_events_pages_have_the_whole_site_nav(app_factory, path):
    # The same nav as the landing page, not a lone way back to it: every
    # section is a link into the landing page, and Past events is marked as
    # where you are.
    page = _past_events_page(app_factory, registration_only=True, path=path)
    nav = page.split('id="nav-links"', 1)[1].split("</ul>", 1)[0]
    for section in ("game", "hill", "manual", "cost", "event"):
        assert f'href="/#{section}"' in nav
    assert 'href="/past-events" aria-current="page"' in nav
    assert "nav-toggle" in page
    assert "Back to the site" not in page
    # The full footer, which carries the organiser's mark.
    footer = page.split('class="footer band dark"', 1)[1]
    assert "Registered teams" in footer
    assert "STEMsters" in footer


def test_past_events_page_has_the_tournament_bar_on_the_full_app(app_factory):
    full = _past_events_page(app_factory, registration_only=False)
    assert 'class="app-bar band"' in full
    assert '<body class="has-app-bar">' in full

    reg_only = _past_events_page(app_factory, registration_only=True)
    assert 'class="app-bar band"' not in reg_only


def test_landing_page_section_links_stay_in_page(client):
    # The shared nav points at "/#game" from anywhere else; on the landing
    # page itself the links have to stay plain anchors.
    page = client.get("/").get_data(as_text=True)
    nav = page.split('id="nav-links"', 1)[1].split("</ul>", 1)[0]
    assert 'href="#game"' in nav
    assert 'href="/#game"' not in nav
    assert 'aria-current="page"' not in nav


def test_landing_page_shows_the_latest_results_after_the_awards(client):
    page = client.get("/").get_data(as_text=True)
    latest = PAST_EVENTS[0]
    results = page.split('id="results"', 1)[1].split("</section>", 1)[0]
    assert f"{latest['name']} champions" in results
    for winner in latest["podium"]:
        assert winner["name"] in results
    assert f'href="/past-events/{latest["slug"]}"' in results
    # The page opens on what Summit is; last time's winners come after the
    # prizes they won.
    assert page.index('class="hero band dark"') < page.index('id="results"')
    assert page.index('id="awards"') < page.index('id="results"') < page.index('id="register"')


def test_landing_page_links_to_past_events(client):
    page = client.get("/").get_data(as_text=True)
    nav = page.split('id="nav-links"', 1)[1].split("</ul>", 1)[0]
    assert 'href="/past-events"' in nav


def test_pages_survive_a_missing_manifest(client, monkeypatch):
    # The photos are a build step. Without them the results still render,
    # as an ordinary podium with no photo and no broken images.
    monkeypatch.setattr(routes, "_read_manifest", lambda *parts: None)

    picker = client.get("/past-events")
    assert picker.status_code == 200
    assert "<img" not in picker.get_data(as_text=True).split('class="event-cards"', 1)[1].split("</ul>", 1)[0]

    resp = client.get(_event_url(PAST_EVENTS[0]))
    assert resp.status_code == 200
    page = resp.get_data(as_text=True)
    assert 'class="photo"' not in page
    assert "has-photo" not in page
    for winner in PAST_EVENTS[0]["podium"]:
        assert winner["name"] in page

    home = client.get("/")
    assert home.status_code == 200
    assert PAST_EVENTS[0]["podium"][0]["name"] in home.get_data(as_text=True)


def test_a_malformed_size_is_dropped_not_rendered(client, monkeypatch):
    event = PAST_EVENTS[0]
    good = all_photos(event)[0]["src"]
    manifest = {"photos": {good: {"sizes": [
        {"file": "ok-640.webp", "width": 640, "height": 480},
        {"file": "bad.webp", "width": "wide", "height": 1},
        {"width": 1280, "height": 960},
    ]}}}
    monkeypatch.setattr(routes, "_read_manifest", lambda *parts: manifest)

    page = client.get(_event_url(event)).get_data(as_text=True)
    assert "ok-640.webp" in page
    assert "bad.webp" not in page
