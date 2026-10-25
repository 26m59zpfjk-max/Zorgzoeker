"""Datavalidatie volgens SCHEMA.md, ook tegen een willekeurig aangeleverd bestand."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from zorgzoeker.laden import laad_document
from zorgzoeker.valideer import VELDEN, valideer_document, valideer_pad

LIJSTVELDEN = {
    "vestigingen",
    "type_aanbod",
    "productcodes",
    "expertise",
    "doelgroepen",
    "werkgebied",
}


def test_fixture_is_geldig(fixture_pad: Path) -> None:
    assert valideer_pad(fixture_pad) == []


def test_aangeleverd_bestand_is_geldig(te_valideren_pad: Path) -> None:
    """Fixture, data/aanbieders.json, en eventueel --aanbieders."""
    fouten = valideer_pad(te_valideren_pad)
    assert fouten == [], "\n".join(fouten)


def test_geverifieerd_en_afgeleid_hebben_bron_en_datum(te_valideren_pad: Path) -> None:
    document = laad_document(te_valideren_pad)
    for aanbieder in document["aanbieders"]:
        for sleutel in VELDEN:
            veld = aanbieder[sleutel]
            if veld["label"] in ("geverifieerd", "afgeleid"):
                assert veld["bron_url"], f"{aanbieder['id']}.{sleutel} mist bron_url"
                assert veld["opgehaald_op"], f"{aanbieder['id']}.{sleutel} mist opgehaald_op"


def test_onbekend_heeft_lege_waarde(te_valideren_pad: Path) -> None:
    document = laad_document(te_valideren_pad)
    for aanbieder in document["aanbieders"]:
        for sleutel in VELDEN:
            veld = aanbieder[sleutel]
            if veld["label"] != "onbekend":
                continue
            waarde = veld["waarde"]
            if sleutel in LIJSTVELDEN:
                assert waarde == [] or waarde == "onbekend"
            else:
                assert waarde == "onbekend"


def test_cli_ok_op_fixture(fixture_pad: Path) -> None:
    resultaat = subprocess.run(
        [sys.executable, "-m", "zorgzoeker.valideer", str(fixture_pad)],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )
    assert resultaat.returncode == 0, resultaat.stdout + resultaat.stderr
    assert "OK" in resultaat.stdout


def test_cli_faalt_op_ongeldig_bestand(tmp_path: Path) -> None:
    pad = tmp_path / "aanbieders.json"
    pad.write_text("{}\n", encoding="utf-8")
    resultaat = subprocess.run(
        [sys.executable, "-m", "zorgzoeker.valideer", str(pad)],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )
    assert resultaat.returncode == 1
    assert "FOUT" in resultaat.stdout


def _minimaal_geldig() -> dict:
    def bekend(waarde: object) -> dict:
        return {
            "waarde": waarde,
            "bron_url": "https://example.org/minimaal",
            "opgehaald_op": "2026-10-25",
            "label": "geverifieerd",
        }

    def leeg(lijst: bool = False) -> dict:
        return {
            "waarde": [] if lijst else "onbekend",
            "bron_url": None,
            "opgehaald_op": None,
            "label": "onbekend",
        }

    return {
        "meta": {
            "schema_versie": "0.1",
            "regio": "Rijk van Nijmegen",
            "gegenereerd_op": "2026-10-25",
        },
        "bronnen": [
            {
                "id": "src-minimaal",
                "naam": "Minimale bron",
                "url": "https://example.org/minimaal",
                "opgehaald_op": "2026-10-25",
                "soort": "overig",
                "opmerking": "Alleen voor de validatietest.",
            }
        ],
        "aanbieders": [
            {
                "id": "minimaal-voorbeeld",
                "naam": bekend("FICTIEF - Minimaal"),
                "kvk_nummer": leeg(),
                "vestigingen": leeg(lijst=True),
                "website": leeg(),
                "type_aanbod": leeg(lijst=True),
                "gecontracteerd_regio": leeg(),
                "productcodes": leeg(lijst=True),
                "expertise": leeg(lijst=True),
                "doelgroepen": leeg(lijst=True),
                "werkgebied": leeg(lijst=True),
                "wachttijd": leeg(),
                "beschikbaarheid": leeg(),
                "gevonden_via": ["src-minimaal"],
            }
        ],
    }


def test_willekeurig_geldig_document_slaagt(tmp_path: Path) -> None:
    document = _minimaal_geldig()
    assert valideer_document(document) == []
    pad = tmp_path / "aanbieders.json"
    pad.write_text(json.dumps(document), encoding="utf-8")
    assert valideer_pad(pad) == []


def test_geverifieerd_zonder_bron_faalt() -> None:
    document = _minimaal_geldig()
    document["aanbieders"][0]["naam"]["bron_url"] = None
    fouten = valideer_document(document)
    assert any("bron_url" in fout for fout in fouten)


def test_afgeleid_zonder_toelichting_faalt() -> None:
    document = _minimaal_geldig()
    document["aanbieders"][0]["werkgebied"] = {
        "waarde": ["Nijmegen"],
        "bron_url": "https://example.org/minimaal",
        "opgehaald_op": "2026-10-25",
        "label": "afgeleid",
    }
    fouten = valideer_document(document)
    assert any("toelichting" in fout for fout in fouten)


def test_onbekend_met_echte_waarde_faalt() -> None:
    document = _minimaal_geldig()
    document["aanbieders"][0]["wachttijd"] = {
        "waarde": "3 weken",
        "bron_url": None,
        "opgehaald_op": None,
        "label": "onbekend",
    }
    fouten = valideer_document(document)
    assert any("onbekend" in fout for fout in fouten)


def test_fixture_bevat_geen_persoonsgegevens(fixture_pad: Path) -> None:
    tekst = fixture_pad.read_text(encoding="utf-8")
    assert "@" not in tekst
    document = laad_document(fixture_pad)
    for aanbieder in document["aanbieders"]:
        assert str(aanbieder["naam"]["waarde"]).startswith("FICTIEF - ")
        assert str(aanbieder["kvk_nummer"]["waarde"]).startswith("FICTIEF-")
        for sleutel in VELDEN:
            bron = aanbieder[sleutel].get("bron_url")
            if bron:
                assert bron.startswith("https://example.org/"), bron
