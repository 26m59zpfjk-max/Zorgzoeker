"""Naam van de aanbieder linkt naar de eigen website (veld `website`), los van de bronlink."""

from __future__ import annotations

import json
import re
from html import unescape
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from zorgzoeker.app import maak_app
from zorgzoeker.weergave import website_url

DATASET = Path(__file__).resolve().parents[1] / "data" / "aanbieders.json"


def _w(waarde, label="geverifieerd"):
    return {"website": {"waarde": waarde, "bron_url": "https://bron.example/pagina", "opgehaald_op": "2026-10-25", "label": label}}


@pytest.mark.parametrize("waarde", ["https://voorbeeld.nl/", "http://voorbeeld.nl", "  https://voorbeeld.nl/pad?x=1  "])
def test_http_en_https_worden_geaccepteerd(waarde):
    assert website_url(_w(waarde)) == waarde.strip()


@pytest.mark.parametrize("waarde", ["javascript:alert(1)", "JAVASCRIPT:alert(1)", "data:text/html,x", "ftp://voorbeeld.nl", "//voorbeeld.nl",
                                    "voorbeeld.nl", "onbekend", "", None, 42, ["https://x.nl"], "https://", "https://voor beeld.nl", "https://x.nl/\nx", "mailto:a@b.nl"])
def test_alleen_geldige_http_urls(waarde):
    assert website_url(_w(waarde)) is None


def test_onbekend_label_of_ontbrekend_veld_geeft_geen_link():
    assert website_url(_w("https://voorbeeld.nl/", label="onbekend")) is None
    assert website_url({}) is None
    assert website_url(None) is None
    assert website_url({"website": "https://voorbeeld.nl/"}) is None


def test_bron_url_wordt_nooit_als_website_gebruikt():
    a = {"website": {"waarde": "onbekend", "bron_url": "https://bron.example/", "opgehaald_op": None, "label": "onbekend"},
         "naam": {"waarde": "X", "bron_url": "https://bron.example/x", "opgehaald_op": "2026-10-25", "label": "geverifieerd"}}
    assert website_url(a) is None


@pytest.fixture(scope="module")
def echt():
    return TestClient(maak_app(DATASET)), json.loads(DATASET.read_text(encoding="utf-8"))


def _kaart_html(html: str, naam: str) -> str:
    for blok in html.split('<article class="kaart')[1:]:
        h2 = re.search(r"<h2>(.*?)</h2>", blok, re.S)
        if h2 and naam in unescape(re.sub(r"<[^>]+>", "", h2[1])):
            return h2[1]
    raise AssertionError(f"kaart {naam} niet gevonden")


def test_zoekresultaat_naam_linkt_naar_website_in_nieuw_tabblad(echt):
    client, data = echt
    p = next(a for a in data["aanbieders"] if a["id"] == "0-tot-18")
    assert p["website"]["waarde"].startswith("https://")
    r = client.get("/", params={"q": "0 tot 18"})
    assert r.status_code == 200
    h2 = _kaart_html(r.text, "0 tot 18")
    a = re.search(r'<a class="naam-link" href="([^"]+)" target="_blank" rel="noopener noreferrer">', h2)
    assert a and unescape(a[1]) == p["website"]["waarde"]
    # De bronlink blijft afzonderlijk aanwezig.
    assert 'class="bron"' in r.text


def test_aanbieder_zonder_website_houdt_platte_naam(echt):
    client, data = echt
    zonder = next(a for a in data["aanbieders"] if website_url(a) is None)
    naam = zonder["naam"]["waarde"]
    r = client.get("/", params={"alles": "1"})
    assert r.status_code == 200
    h2 = _kaart_html(r.text, naam)
    assert "<a " not in h2
    assert "geen website bekend" in h2


def test_alle_kaarten_linken_exact_naar_datasetwebsite(echt):
    client, data = echt
    r = client.get("/", params={"alles": "1"})
    per_id = {a["id"]: website_url(a) for a in data["aanbieders"]}
    blokken = r.text.split('<article class="kaart')[1:]
    assert len(blokken) > 150
    for blok in blokken:
        kaart_id = unescape(re.search(r'name="ids" value="([^"]+)"', blok)[1])
        h2 = re.search(r"<h2>(.*?)</h2>", blok, re.S)[1]
        link = re.search(r'<a class="naam-link" href="([^"]+)" target="_blank" rel="noopener noreferrer">', h2)
        if per_id[kaart_id]:
            assert link and unescape(link[1]) == per_id[kaart_id]
            assert unescape(link[1]).split(":", 1)[0] in {"http", "https"}
        else:
            assert link is None and "geen website bekend" in h2


def test_api_levert_website(echt):
    client, data = echt
    r = client.get("/api/zoek", params={"q": "0 tot 18"}).json()
    eerste = next(t for t in r["resultaten"] if t["id"] == "0-tot-18")
    assert eerste["website"] == "https://0tot18.nl/"


def test_vergelijkpagina_linkt_namen(echt):
    client, data = echt
    met = [a for a in data["aanbieders"] if website_url(a)][:1]
    zonder = [a for a in data["aanbieders"] if not website_url(a)][:1]
    r = client.get("/vergelijken", params=[("ids", met[0]["id"]), ("ids", zonder[0]["id"])])
    assert r.status_code == 200
    assert f'href="{website_url(met[0])}" target="_blank" rel="noopener noreferrer"' in r.text
    assert "geen website bekend" in r.text
