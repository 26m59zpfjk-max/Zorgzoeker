"""Tekst voor de interface. Wachttijd blijft 'onbekend' zolang de bron dat zegt."""

from __future__ import annotations

from zorgzoeker.valideer import _valideer_veld, _valideer_wachttijd, peildatum_veld

MAANDEN = (
    "",
    "januari",
    "februari",
    "maart",
    "april",
    "mei",
    "juni",
    "juli",
    "augustus",
    "september",
    "oktober",
    "november",
    "december",
)

VELD_LABELS = {
    "naam": "Naam",
    "kvk_nummer": "KvK-nummer",
    "vestigingen": "Vestigingen",
    "website": "Website",
    "type_aanbod": "Type aanbod",
    "gecontracteerd_regio": "Gecontracteerd door de regio",
    "productcodes": "Productcodes",
    "expertise": "Expertise",
    "doelgroepen": "Doelgroepen",
    "werkgebied": "Werkgebied",
    "wachttijd": "Wachttijd",
    "beschikbaarheid": "Beschikbaarheid",
}

KAART_VELDEN = (
    "gecontracteerd_regio",
    "wachttijd",
    "beschikbaarheid",
    "expertise",
    "doelgroepen",
    "vestigingen",
    "werkgebied",
    "type_aanbod",
    "productcodes",
    "website",
    "kvk_nummer",
)

VERGELIJK_VELDEN = ("naam",) + KAART_VELDEN


def format_datum(iso: str | None) -> str | None:
    if not iso or len(iso) != 10:
        return None
    try:
        jaar, maand, dag = (int(deel) for deel in iso.split("-"))
    except ValueError:
        return None
    if not 1 <= maand <= 12:
        return None
    return f"{dag} {MAANDEN[maand]} {jaar}"


def veilige_url(url: object) -> str | None:
    if isinstance(url, str) and url.startswith(("https://", "http://")):
        return url
    return None


def is_onbekend(sleutel: str, veld: dict | None) -> bool:
    if not isinstance(veld, dict):
        return True
    if veld.get("label") == "onbekend":
        return True
    if sleutel in {"wachttijd", "beschikbaarheid"} and (
        _valideer_veld(sleutel, sleutel, veld) or _valideer_wachttijd("weergave", {sleutel: veld})
    ):
        return True
    waarde = veld.get("waarde")
    if sleutel in ("wachttijd", "beschikbaarheid"):
        return waarde in ("onbekend", "", None, [])
    return waarde in ("onbekend", None, [])


def formateer_waarde(sleutel: str, waarde: object) -> str:
    if waarde in (None, "", "onbekend", []):
        return "onbekend"
    if sleutel == "productcodes" and isinstance(waarde, list):
        regels = []
        for product in waarde:
            if not isinstance(product, dict):
                continue
            code = str(product.get("code") or "").strip()
            omschrijving = str(product.get("omschrijving") or "").strip()
            if code and omschrijving:
                regels.append(f"{code} — {omschrijving}")
            elif code:
                regels.append(code)
        return "\n".join(regels) or "onbekend"
    if sleutel == "vestigingen" and isinstance(waarde, list):
        regels = []
        for vestiging in waarde:
            if not isinstance(vestiging, dict):
                continue
            plaats = str(vestiging.get("plaats") or "").strip()
            adres = str(vestiging.get("adres") or "").strip()
            postcode = str(vestiging.get("postcode") or "").strip()
            if adres and postcode and plaats:
                regels.append(f"{adres}, {postcode} {plaats}")
            elif plaats:
                regels.append(plaats)
        return "\n".join(regels) or "onbekend"
    if isinstance(waarde, list):
        return ", ".join(str(item) for item in waarde) if waarde else "onbekend"
    return str(waarde)


def toon_veld(sleutel: str, veld: dict | None) -> dict:
    """Eén veld, klaar voor de kaart of de vergelijking."""
    bron = veld if isinstance(veld, dict) else {}
    onbekend = is_onbekend(sleutel, bron if isinstance(veld, dict) else None)
    tekst = "onbekend" if onbekend else formateer_waarde(sleutel, bron.get("waarde"))
    if sleutel == "gecontracteerd_regio" and bron.get("waarde") == "nee" and bron.get("label") == "afgeleid":
        tekst = "Niet aangetroffen in contractlijst"
    if sleutel in ("wachttijd", "beschikbaarheid") and onbekend:
        tekst = "onbekend"
    return {
        "sleutel": sleutel,
        "label_nl": VELD_LABELS.get(sleutel, sleutel),
        "tekst": tekst,
        "label": "onbekend" if onbekend else bron.get("label") or "onbekend",
        "bron_url": None if onbekend else veilige_url(bron.get("bron_url")),
        "datum": None if onbekend else format_datum(bron.get("opgehaald_op")),
        "peildatum": None if onbekend else peildatum_veld(bron),
        "toelichting": None if onbekend else (bron.get("toelichting") or None),
        "onbekend": onbekend or tekst == "onbekend",
    }


def onderaannemer_zin(aanbieder: dict, contracttoets: dict | None = None) -> str | None:
    """Naam van de hoofdaannemer, als dit veld er is."""
    if contracttoets and contracttoets.get("routes"):
        routes = contracttoets["routes"]
        if any(r.get("hoofdaannemer") is None for r in routes):
            return None  # er is ook een rechtstreekse contractroute
        namen = sorted({r["hoofdaannemer"] for r in routes})
        return "Gecontracteerd als onderaannemer van " + "; ".join(namen)
    veld = aanbieder.get("hoofdaannemer")
    if not isinstance(veld, dict):
        return None
    contract = aanbieder.get("gecontracteerd_regio") or {}
    if contract.get("waarde") != "ja" or contract.get("label") not in {"geverifieerd", "afgeleid"}:
        return None
    if veld.get("label") not in {"geverifieerd", "afgeleid"} or not veilige_url(veld.get("bron_url")) or not format_datum(veld.get("opgehaald_op")):
        return None
    naam = veld.get("waarde")
    if not isinstance(naam, str):
        return None
    naam = naam.strip()
    if not naam or naam.lower() == "onbekend":
        return None
    return f"Gecontracteerd als onderaannemer van {naam}"


def vergelijk_rijen(aanbieders: list[dict], contracttoetsen: list[dict] | None = None) -> list[dict]:
    rijen = []
    for sleutel in VERGELIJK_VELDEN:
        cellen = [toon_veld(sleutel, aanbieder.get(sleutel)) for aanbieder in aanbieders]
        if sleutel == "gecontracteerd_regio":
            for aanbieder, cel in zip(aanbieders, cellen):
                zin = onderaannemer_zin(aanbieder)
                if zin:
                    cel["tekst"] = zin
                    cel["label"] = "onderaannemer"
                    cel["toelichting"] = None
            if contracttoetsen:
                for aanbieder, cel, toets in zip(aanbieders, cellen, contracttoetsen):
                    if toets["status"] == "onbekend":
                        cel.update(tekst="Contract voor deze vraag onbekend", label="onbekend", onbekend=True)
                    elif toets["status"] == "nee":
                        cel["tekst"] = "Niet aangetroffen in contractlijst" if cel["label"] == "afgeleid" else "Niet gecontracteerd"
                    elif (zin := onderaannemer_zin(aanbieder, toets)):
                        cel["tekst"] = zin
                    cel["toelichting"] = "Bronpeildatum: " + str(toets.get("peildatum") or "onbekend") + ". Geen bewezen geldigheidsperiode. " + " ".join(toets["waarschuwingen"])
                    cel["bron_url"] = veilige_url(toets.get("bron_url"))
        teksten = [cel["tekst"] for cel in cellen]
        rijen.append(
            {
                "sleutel": sleutel,
                "label_nl": VELD_LABELS.get(sleutel, sleutel),
                "cellen": cellen,
                "verschilt": len(set(teksten)) > 1,
            }
        )
    return rijen
