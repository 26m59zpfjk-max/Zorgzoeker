"""Validatie van een aanbiedersbestand volgens SCHEMA.md.

Draaien tegen een willekeurig bestand:
    python -m zorgzoeker.valideer pad/naar/aanbieders.json
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

VELDEN = (
    "naam",
    "kvk_nummer",
    "vestigingen",
    "website",
    "type_aanbod",
    "gecontracteerd_regio",
    "productcodes",
    "expertise",
    "doelgroepen",
    "werkgebied",
    "wachttijd",
    "beschikbaarheid",
)

LIJSTVELDEN = {
    "vestigingen",
    "type_aanbod",
    "productcodes",
    "expertise",
    "doelgroepen",
    "werkgebied",
}

LABELS = {"geverifieerd", "afgeleid", "onbekend"}
CONTRACT = {"ja", "nee", "onbekend"}

# Woorden die een schatting verraden. Een gepubliceerd getal ("8 weken") mag wel.
SCHATTING = re.compile(
    r"\b(ongeveer|circa|ca\.|geschat|geschatte|schatting|naar schatting|rond de|naar verwachting)\b",
    re.IGNORECASE,
)
DATUM_IN_TEKST = re.compile(r"\b(\d{4}-\d{2}-\d{2}|\d{1,2}-\d{1,2}-\d{4})\b")
URL = re.compile(r"^https?://", re.IGNORECASE)


def _is_datum(waarde: object) -> bool:
    if not isinstance(waarde, str):
        return False
    try:
        datetime.strptime(waarde, "%Y-%m-%d")
    except ValueError:
        return False
    return True


def _lege_onbekende_waarde(sleutel: str, waarde: object) -> bool:
    if sleutel in LIJSTVELDEN:
        return waarde == [] or waarde == "onbekend"
    return waarde == "onbekend"


def _onbekende_wachttijd(veld: dict) -> bool:
    waarde = veld.get("waarde")
    if veld.get("label") == "onbekend":
        return True
    if waarde in ("onbekend", "", None, []):
        return True
    return False


def valideer_document(document: object) -> list[str]:
    """Geef een lijst fouten terug. Leeg betekent: het bestand voldoet."""
    fouten: list[str] = []
    if not isinstance(document, dict):
        return ["Het bestand moet een JSON-object zijn."]

    meta = document.get("meta")
    if not isinstance(meta, dict):
        fouten.append("meta ontbreekt of is geen object.")
    else:
        if not meta.get("schema_versie"):
            fouten.append("meta.schema_versie ontbreekt.")
        if not meta.get("regio"):
            fouten.append("meta.regio ontbreekt.")

    bronnen = document.get("bronnen")
    bron_ids: set[str] = set()
    if not isinstance(bronnen, list) or not bronnen:
        fouten.append("bronnen moet een niet-lege lijst zijn.")
    else:
        for index, bron in enumerate(bronnen):
            pad = f"bronnen[{index}]"
            if not isinstance(bron, dict):
                fouten.append(f"{pad} is geen object.")
                continue
            bron_id = bron.get("id")
            if not isinstance(bron_id, str) or not bron_id.strip():
                fouten.append(f"{pad}.id ontbreekt.")
            elif bron_id in bron_ids:
                fouten.append(f"{pad}.id '{bron_id}' komt vaker voor.")
            else:
                bron_ids.add(bron_id)
            if not isinstance(bron.get("url"), str) or not URL.match(bron.get("url", "")):
                fouten.append(f"{pad}.url moet een http(s)-adres zijn.")
            if not _is_datum(bron.get("opgehaald_op")):
                fouten.append(f"{pad}.opgehaald_op moet YYYY-MM-DD zijn.")

    aanbieders = document.get("aanbieders")
    if not isinstance(aanbieders, list):
        fouten.append("aanbieders moet een lijst zijn.")
        return fouten

    geziene_ids: set[str] = set()
    for index, aanbieder in enumerate(aanbieders):
        pad = f"aanbieders[{index}]"
        if not isinstance(aanbieder, dict):
            fouten.append(f"{pad} is geen object.")
            continue
        aanbieder_id = aanbieder.get("id")
        if not isinstance(aanbieder_id, str) or not aanbieder_id.strip():
            fouten.append(f"{pad}.id ontbreekt.")
        elif aanbieder_id in geziene_ids:
            fouten.append(f"{pad}.id '{aanbieder_id}' komt vaker voor.")
        else:
            geziene_ids.add(aanbieder_id)

        for sleutel in VELDEN:
            if sleutel not in aanbieder:
                fouten.append(f"{pad}.{sleutel} ontbreekt.")
                continue
            fouten.extend(_valideer_veld(f"{pad}.{sleutel}", sleutel, aanbieder[sleutel]))

        if "hoofdaannemer" in aanbieder:
            fouten.extend(_valideer_veld(f"{pad}.hoofdaannemer", "hoofdaannemer", aanbieder["hoofdaannemer"]))

        gevonden = aanbieder.get("gevonden_via")
        if not isinstance(gevonden, list) or not gevonden:
            fouten.append(f"{pad}.gevonden_via moet een niet-lege lijst bron-id's zijn.")
        else:
            for bron_id in gevonden:
                if bron_id not in bron_ids:
                    fouten.append(f"{pad}.gevonden_via verwijst naar onbekende bron '{bron_id}'.")

        fouten.extend(_valideer_wachttijd(pad, aanbieder))

    return fouten


def _valideer_veld(pad: str, sleutel: str, veld: object) -> list[str]:
    fouten: list[str] = []
    if not isinstance(veld, dict):
        return [f"{pad} is geen Veld-object."]

    label = veld.get("label")
    if label not in LABELS:
        fouten.append(f"{pad}.label moet geverifieerd, afgeleid of onbekend zijn.")
        return fouten

    if label in ("geverifieerd", "afgeleid"):
        bron = veld.get("bron_url")
        if not isinstance(bron, str) or not bron.strip() or not URL.match(bron):
            fouten.append(f"{pad}: label {label} zonder bruikbare bron_url.")
        if not _is_datum(veld.get("opgehaald_op")):
            fouten.append(f"{pad}: label {label} zonder opgehaald_op (YYYY-MM-DD).")
        if label == "afgeleid":
            toelichting = veld.get("toelichting")
            if not isinstance(toelichting, str) or not toelichting.strip():
                fouten.append(f"{pad}: label afgeleid zonder toelichting.")
    else:
        if not _lege_onbekende_waarde(sleutel, veld.get("waarde")):
            fouten.append(
                f"{pad}: label onbekend, maar waarde is niet 'onbekend' of een lege lijst."
            )

    if sleutel == "gecontracteerd_regio" and label != "onbekend":
        if veld.get("waarde") not in CONTRACT:
            fouten.append(f"{pad}.waarde moet ja, nee of onbekend zijn.")

    return fouten


def _valideer_wachttijd(pad: str, aanbieder: dict) -> list[str]:
    """Geen verzonnen wachttijd of beschikbaarheid."""
    fouten: list[str] = []
    for sleutel in ("wachttijd", "beschikbaarheid"):
        veld = aanbieder.get(sleutel)
        if not isinstance(veld, dict):
            continue
        if _onbekende_wachttijd(veld):
            continue
        waar = f"{pad}.{sleutel}"
        bron = veld.get("bron_url")
        if not isinstance(bron, str) or not bron.strip() or not URL.match(bron):
            fouten.append(f"{waar}: waarde is niet 'onbekend', maar er is geen bron_url.")
        if not _is_datum(veld.get("opgehaald_op")):
            fouten.append(f"{waar}: waarde is niet 'onbekend', maar er is geen ophaaldatum.")
        toelichting = veld.get("toelichting") if isinstance(veld.get("toelichting"), str) else ""
        if "peildatum" not in toelichting.lower() or not DATUM_IN_TEKST.search(toelichting):
            fouten.append(f"{waar}: toelichting moet een peildatum bevatten.")
        waarde = veld.get("waarde")
        if isinstance(waarde, str) and SCHATTING.search(waarde):
            fouten.append(f"{waar}: de tekst lijkt op een schatting. Alleen een gepubliceerd gegeven mag.")
    return fouten


def valideer_pad(pad: Path) -> list[str]:
    bron = Path(pad)
    if not bron.exists():
        return [f"Bestand niet gevonden: {bron}"]
    try:
        with bron.open(encoding="utf-8") as bestand:
            document = json.load(bestand)
    except json.JSONDecodeError as fout:
        return [f"Ongeldige JSON in {bron}: {fout.msg} (regel {fout.lineno})."]
    return valideer_document(document)


def main(argv: list[str] | None = None) -> int:
    argumenten = list(sys.argv[1:] if argv is None else argv)
    if len(argumenten) != 1:
        print(
            "Gebruik: python -m zorgzoeker.valideer pad/naar/aanbieders.json",
            file=sys.stderr,
        )
        return 2
    pad = Path(argumenten[0])
    fouten = valideer_pad(pad)
    if fouten:
        print(f"FOUT: {pad}")
        for fout in fouten:
            print(f"- {fout}")
        return 1
    print(f"OK: {pad} voldoet aan het schema.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
