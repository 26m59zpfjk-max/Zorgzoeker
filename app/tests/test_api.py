"""Rooktest van de pagina's en de JSON-API, tegen de fixture."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from zorgzoeker.app import maak_app
from zorgzoeker.weergave import toon_veld


def _client(pad: Path) -> TestClient:
    return TestClient(maak_app(pad))


def test_startpagina(fixture_pad: Path) -> None:
    antwoord = _client(fixture_pad).get("/")
    assert antwoord.status_code == 200
    assert "Zorgvraag" in antwoord.text
    assert 'name="q"' in antwoord.text
    assert "Gecontracteerd" in antwoord.text


def test_zoekpagina_toont_reden_en_label(fixture_pad: Path) -> None:
    antwoord = _client(fixture_pad).get(
        "/",
        params={"q": "jongen 14 met autisme en angst in Groesbeek, ambulant"},
    )
    assert antwoord.status_code == 200
    assert "FICTIEF - De Horst Ambulant" in antwoord.text
    assert "Sluit aan op" in antwoord.text
    assert "geverifieerd" in antwoord.text
    assert "onbekend" in antwoord.text


def test_onbekende_wachttijd_blijft_onbekend(fixture_pad: Path) -> None:
    antwoord = _client(fixture_pad).get(
        "/api/zoek",
        params={"q": "schoolweigering in Groesbeek"},
    )
    assert antwoord.status_code == 200
    eerste = antwoord.json()["resultaten"][0]
    assert eerste["id"] == "fictief-de-horst-ambulant"
    assert eerste["wachttijd"]["tekst"] == "onbekend"
    assert eerste["wachttijd"]["label"] == "onbekend"
    assert eerste["beschikbaarheid"]["tekst"] == "onbekend"


def test_gepubliceerde_wachttijd_heeft_bron(fixture_pad: Path) -> None:
    antwoord = _client(fixture_pad).get("/api/zoek", params={"q": "productcode JH-GGZ-09"})
    eerste = antwoord.json()["resultaten"][0]
    assert eerste["id"] == "fictief-jeugd-ggz-de-waalbrug"
    assert eerste["wachttijd"]["tekst"] == "8 weken"
    assert eerste["wachttijd"]["bron_url"]
    assert "ongeveer" not in eerste["wachttijd"]["tekst"].lower()


def test_filter_niet_gecontracteerd(fixture_pad: Path) -> None:
    antwoord = _client(fixture_pad).get(
        "/api/zoek",
        params={"q": "autisme angst", "gecontracteerd": "nee"},
    )
    ids = [item["id"] for item in antwoord.json()["resultaten"]]
    assert ids[0] == "fictief-praktijk-lichtpunt"
    assert "fictief-de-horst-ambulant" not in ids


def test_vergelijking_van_drie(fixture_pad: Path) -> None:
    antwoord = _client(fixture_pad).get(
        "/vergelijken",
        params=[
            ("ids", "fictief-de-horst-ambulant"),
            ("ids", "fictief-gezinshuis-de-waard"),
            ("ids", "fictief-zorgboerderij-de-lage-wei"),
        ],
    )
    assert antwoord.status_code == 200
    assert "De Horst Ambulant" in antwoord.text
    assert "De Waard" in antwoord.text
    assert "De Lage Wei" in antwoord.text
    assert "onbekend" in antwoord.text


def test_vergelijking_eist_twee_of_drie(fixture_pad: Path) -> None:
    antwoord = _client(fixture_pad).get("/vergelijken", params={"ids": "fictief-de-horst-ambulant"})
    assert "twee of drie" in antwoord.text


def test_lege_zoekvraag_toont_melding(fixture_pad: Path) -> None:
    antwoord = _client(fixture_pad).get("/", params={"q": "zzzqqq-geen-match-xyz"})
    assert "Geen passende aanbieders" in antwoord.text


def test_toon_veld_verzint_geen_wachttijd() -> None:
    assert toon_veld("wachttijd", {"waarde": "onbekend", "label": "onbekend", "bron_url": None, "opgehaald_op": None})["tekst"] == "onbekend"
    assert toon_veld("beschikbaarheid", {"waarde": [], "label": "onbekend", "bron_url": None, "opgehaald_op": None})["tekst"] == "onbekend"
