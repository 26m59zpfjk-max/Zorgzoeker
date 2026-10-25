"""Geen verzonnen wachttijden of beschikbaarheden."""

from __future__ import annotations

import re
from pathlib import Path

from zorgzoeker.laden import laad_document
from zorgzoeker.valideer import SCHATTING, valideer_document

PEILDATUM = re.compile(r"peildatum", re.IGNORECASE)
DATUM = re.compile(r"\b(\d{4}-\d{2}-\d{2}|\d{1,2}-\d{1,2}-\d{4})\b")


def _onbekend(veld: dict) -> bool:
    if veld.get("label") == "onbekend":
        return True
    return veld.get("waarde") in ("onbekend", "", None, [])


def test_bekende_wachttijd_heeft_bron_en_peildatum(te_valideren_pad: Path) -> None:
    document = laad_document(te_valideren_pad)
    assert valideer_document(document) == []
    for aanbieder in document["aanbieders"]:
        for sleutel in ("wachttijd", "beschikbaarheid"):
            veld = aanbieder[sleutel]
            if _onbekend(veld):
                continue
            assert veld.get("bron_url"), aanbieder["id"]
            assert veld.get("opgehaald_op"), aanbieder["id"]
            toelichting = veld.get("toelichting") or ""
            assert PEILDATUM.search(toelichting), aanbieder["id"]
            assert DATUM.search(toelichting), aanbieder["id"]
            waarde = str(veld.get("waarde"))
            assert SCHATTING.search(waarde) is None


def test_schatting_zonder_publicatie_faalt() -> None:
    document = {
        "meta": {"schema_versie": "0.1", "regio": "Rijk van Nijmegen"},
        "bronnen": [
            {
                "id": "src-x",
                "naam": "Bron",
                "url": "https://example.org/x",
                "opgehaald_op": "2026-10-25",
                "soort": "overig",
                "opmerking": "",
            }
        ],
        "aanbieders": [
            {
                "id": "voorbeeld",
                "naam": {
                    "waarde": "FICTIEF - Voorbeeld",
                    "bron_url": "https://example.org/x",
                    "opgehaald_op": "2026-10-25",
                    "label": "geverifieerd",
                },
                "kvk_nummer": {"waarde": "onbekend", "bron_url": None, "opgehaald_op": None, "label": "onbekend"},
                "vestigingen": {"waarde": [], "bron_url": None, "opgehaald_op": None, "label": "onbekend"},
                "website": {"waarde": "onbekend", "bron_url": None, "opgehaald_op": None, "label": "onbekend"},
                "type_aanbod": {"waarde": [], "bron_url": None, "opgehaald_op": None, "label": "onbekend"},
                "gecontracteerd_regio": {"waarde": "onbekend", "bron_url": None, "opgehaald_op": None, "label": "onbekend"},
                "productcodes": {"waarde": [], "bron_url": None, "opgehaald_op": None, "label": "onbekend"},
                "expertise": {"waarde": [], "bron_url": None, "opgehaald_op": None, "label": "onbekend"},
                "doelgroepen": {"waarde": [], "bron_url": None, "opgehaald_op": None, "label": "onbekend"},
                "werkgebied": {"waarde": [], "bron_url": None, "opgehaald_op": None, "label": "onbekend"},
                "wachttijd": {
                    "waarde": "ongeveer 6 weken",
                    "bron_url": "https://example.org/x",
                    "opgehaald_op": "2026-10-25",
                    "label": "geverifieerd",
                    "toelichting": "Peildatum 2026-10-01.",
                },
                "beschikbaarheid": {"waarde": "onbekend", "bron_url": None, "opgehaald_op": None, "label": "onbekend"},
                "gevonden_via": ["src-x"],
            }
        ],
    }
    fouten = valideer_document(document)
    assert any("schatting" in fout for fout in fouten)


def test_wachttijd_zonder_peildatum_faalt() -> None:
    from tests.test_validatie import _minimaal_geldig

    document = _minimaal_geldig()
    document["aanbieders"][0]["wachttijd"] = {
        "waarde": "8 weken",
        "bron_url": "https://example.org/minimaal",
        "opgehaald_op": "2026-10-25",
        "label": "geverifieerd",
        "toelichting": "Stond op de website, zonder peildatum.",
    }
    fouten = valideer_document(document)
    assert any("peildatum" in fout for fout in fouten)
