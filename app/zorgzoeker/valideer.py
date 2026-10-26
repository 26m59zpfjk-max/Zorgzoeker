"""Validatie van een aanbiedersbestand volgens SCHEMA.md.

Draaien tegen een willekeurig bestand:
    python -m zorgzoeker.valideer pad/naar/aanbieders.json
"""

from __future__ import annotations

import json
import re
import sys
from datetime import date, datetime
from pathlib import Path

from zorgzoeker.contracten import code_sleutel, lees_datum
from zorgzoeker.config import max_wachttijd_dagen

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
    r"\b(?:ongeveer|circa|geschat|geschatte|schatting|naar schatting|rond de|naar verwachting|indicatie|indicatief|indicatieve|verwacht|verwachte|verwachting)\b|\bca\.|[±~≈]|\+\s*/\s*[-−]",
    re.IGNORECASE,
)
DATUM_IN_TEKST = re.compile(r"\b(\d{4}-\d{2}-\d{2}|\d{1,2}-\d{1,2}-\d{4})\b")
URL = re.compile(r"^https?://", re.IGNORECASE)


def peildatum_veld(veld: dict) -> str | None:
    tekst = str(veld.get("toelichting") or "")
    patroon = r"\bpeildatum\b(?:\s*\([^)]{0,30}\))?(?:\s+gelezen)?\s*:?\s*(\d{4}-\d{2}-\d{2}|\d{1,2}-\d{1,2}-\d{4})\b"
    match = re.search(patroon, tekst, re.I)
    return lees_datum(match[1]) if match else None


def indicatieve_publicatie(veld: dict) -> bool:
    """Letterlijke, gemarkeerde publicatie; nooit een actuele instroomtoezegging."""
    tekst = str(veld.get("waarde") or "")
    return veld.get("publicatie_type") == "indicatief" or bool(re.match(
        r"^\s*(?:gemiddeld|indicatie)\s*:?\s*\d+(?:\s*[-–—]\s*\d+)?\s*(?:weken|week|dagen|dag)\b", tekst, re.I))


def wachttijd_ouderdom(veld: dict, referentiedatum: date | None = None) -> int | None:
    peil = peildatum_veld(veld)
    return ((referentiedatum or date.today()) - date.fromisoformat(peil)).days if peil else None


def wachttijd_verouderd(veld: dict, referentiedatum: date | None = None) -> bool:
    dagen = wachttijd_ouderdom(veld, referentiedatum)
    return dagen is not None and dagen > max_wachttijd_dagen()


def _is_datum(waarde: object) -> bool:
    if not isinstance(waarde, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", waarde):
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
            hoofd = aanbieder["hoofdaannemer"]
            if isinstance(hoofd, dict) and hoofd.get("waarde") not in (None, "onbekend", ""):
                contract = aanbieder.get("gecontracteerd_regio") or {}
                if not isinstance(contract, dict) or contract.get("waarde") != "ja":
                    fouten.append(f"{pad}: hoofdaannemer zonder bevestigde regionale contractrelatie.")
        if "contractgemeenten" in aanbieder:
            fouten.extend(_valideer_veld(f"{pad}.contractgemeenten", "werkgebied", aanbieder["contractgemeenten"]))

        gevonden = aanbieder.get("gevonden_via")
        if not isinstance(gevonden, list) or not gevonden:
            fouten.append(f"{pad}.gevonden_via moet een niet-lege lijst bron-id's zijn.")
        else:
            for bron_id in gevonden:
                if not isinstance(bron_id, str) or bron_id not in bron_ids:
                    fouten.append(f"{pad}.gevonden_via verwijst naar onbekende bron '{bron_id}'.")

        fouten.extend(_valideer_wachttijd(pad, aanbieder))

    fouten.extend(_valideer_contractregister(document))
    from zorgzoeker.beschikbaarheid import valideer_regel
    register = document.get("beschikbaarheidsregister", [])
    if not isinstance(register, list):
        fouten.append("beschikbaarheidsregister moet een lijst zijn.")
    else:
        ids = set()
        for regel in register:
            fouten.extend(valideer_regel(regel))
            if isinstance(regel, dict):
                if not isinstance(regel.get("id"), str) or regel["id"] in ids:
                    fouten.append("Beschikbaarheidsregel-id ontbreekt of is dubbel.")
                else:
                    ids.add(regel["id"])
                if not isinstance(regel.get("aanbieder_id"), str) or regel["aanbieder_id"] not in geziene_ids:
                    fouten.append("Beschikbaarheidsregel verwijst naar onbekende aanbieder.")
    return fouten


def _valideer_veld(pad: str, sleutel: str, veld: object) -> list[str]:
    fouten: list[str] = []
    if not isinstance(veld, dict):
        return [f"{pad} is geen Veld-object."]

    label = veld.get("label")
    if not isinstance(label, str) or label not in LABELS:
        fouten.append(f"{pad}.label moet geverifieerd, afgeleid of onbekend zijn.")
        return fouten
    waarde = veld.get("waarde")
    if label != "onbekend":
        if sleutel in LIJSTVELDEN:
            if not isinstance(waarde, list):
                fouten.append(f"{pad}.waarde moet een lijst zijn.")
            elif sleutel in {"productcodes", "vestigingen"}:
                verplicht = "code" if sleutel == "productcodes" else "plaats"
                if any(not isinstance(item, dict) or not isinstance(item.get(verplicht), str) or not item[verplicht].strip() for item in waarde):
                    fouten.append(f"{pad}.waarde bevat een ongeldig {verplicht}-object.")
            elif any(not isinstance(item, str) for item in waarde):
                fouten.append(f"{pad}.waarde moet alleen teksten bevatten.")
        elif not isinstance(waarde, str) or not waarde.strip():
            fouten.append(f"{pad}.waarde moet een niet-lege tekst zijn.")

    if label in ("geverifieerd", "afgeleid"):
        bron = veld.get("bron_url")
        if not isinstance(bron, str) or not bron.strip() or not URL.match(bron):
            fouten.append(f"{pad}: label {label} zonder bruikbare bron_url.")
        if not _is_datum(veld.get("opgehaald_op")):
            fouten.append(f"{pad}: label {label} zonder opgehaald_op (YYYY-MM-DD).")
        elif veld["opgehaald_op"] > date.today().isoformat():
            fouten.append(f"{pad}: ophaaldatum ligt in de toekomst.")
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
        if not isinstance(veld.get("waarde"), str) or veld["waarde"] not in CONTRACT:
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
        if veld.get("label") != "geverifieerd":
            fouten.append(f"{waar}: alleen letterlijk geverifieerde publicaties mogen bekend zijn.")
        bron = veld.get("bron_url")
        if not isinstance(bron, str) or not bron.strip() or not URL.match(bron):
            fouten.append(f"{waar}: waarde is niet 'onbekend', maar er is geen bron_url.")
        if not _is_datum(veld.get("opgehaald_op")):
            fouten.append(f"{waar}: waarde is niet 'onbekend', maar er is geen ophaaldatum.")
        toelichting = veld.get("toelichting") if isinstance(veld.get("toelichting"), str) else ""
        peil = peildatum_veld(veld)
        if not peil:
            fouten.append(f"{waar}: toelichting moet een geldige peildatum bevatten.")
        elif _is_datum(veld.get("opgehaald_op")) and peil > veld["opgehaald_op"]:
            fouten.append(f"{waar}: peildatum ligt na de ophaaldatum.")
        waarde = veld.get("waarde")
        if isinstance(waarde, str) and SCHATTING.search(waarde) and not (sleutel == "wachttijd" and indicatieve_publicatie(veld)):
            # Een expliciet gemarkeerde, letterlijk gepubliceerde indicatie
            # mag bewaard blijven, maar is nooit actuele beschikbaarheid.
            fouten.append(f"{waar}: de tekst lijkt op een schatting. Alleen een gepubliceerd gegeven mag.")
    return fouten


def _valideer_contractregister(document: dict) -> list[str]:
    register = document.get("contractregister")
    if register is None:
        return []
    if not isinstance(register, dict):
        return ["contractregister moet een object zijn."]
    fouten = []
    if not isinstance(register.get("bron_url"), str) or not URL.match(register["bron_url"]):
        fouten.append("contractregister mist bron_url.")
    for datum in ("peildatum", "opgehaald_op"):
        if not _is_datum(register.get(datum)):
            fouten.append(f"contractregister.{datum} moet YYYY-MM-DD zijn.")
    if _is_datum(register.get("peildatum")) and _is_datum(register.get("opgehaald_op")):
        if register["peildatum"] > register["opgehaald_op"] or register["opgehaald_op"] > date.today().isoformat():
            fouten.append("contractregister bevat een onmogelijke datumvolgorde.")
    if not isinstance(register.get("regels"), list):
        return fouten + ["contractregister.regels moet een lijst zijn."]
    per_id = {a["id"]: a for a in document["aanbieders"] if isinstance(a, dict) and isinstance(a.get("id"), str)}
    for n, r in enumerate(register["regels"]):
        pad = f"contractregister.regels[{n}]"
        if not isinstance(r, dict) or not isinstance(r.get("aanbieder_id"), str) or r["aanbieder_id"] not in per_id:
            fouten.append(f"{pad}: onbekende aanbieder.")
            continue
        a = per_id[r["aanbieder_id"]]
        contract = a.get("gecontracteerd_regio") or {}
        if not isinstance(contract, dict) or contract.get("waarde") != "ja":
            fouten.append(f"{pad}: bronroute spreekt de regionale contractstatus tegen.")
        producten = (a.get("productcodes") or {}).get("waarde", [])
        codes = {code_sleutel(str(p.get("code", ""))) for p in producten if isinstance(p, dict)} if isinstance(producten, list) else set()
        if not isinstance(r.get("productcode"), str) or code_sleutel(r["productcode"]) not in codes:
            fouten.append(f"{pad}: productcode ontbreekt bij de aanbieder.")
        if not isinstance(r.get("gemeenten"), list) or not r["gemeenten"] or any(not isinstance(g, str) or not g for g in r["gemeenten"]):
            fouten.append(f"{pad}: gemeenten ontbreken of zijn ongeldig.")
        if r.get("hoofdaannemer") is not None and (not isinstance(r["hoofdaannemer"], str) or not r["hoofdaannemer"].strip()):
            fouten.append(f"{pad}: hoofdaannemer is ongeldig.")
        if not isinstance(r.get("opmerkingen"), list) or any(not isinstance(t, str) for t in r["opmerkingen"]):
            fouten.append(f"{pad}: opmerkingen moeten teksten zijn.")
        bewijs = r.get("bewijs")
        if not isinstance(bewijs, list) or not bewijs or any(not isinstance(b, dict) or not isinstance(b.get("tabblad"), str) or not isinstance(b.get("rij"), int) or b["rij"] < 3 for b in bewijs):
            fouten.append(f"{pad}: tabblad/bronrij ontbreekt.")
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
