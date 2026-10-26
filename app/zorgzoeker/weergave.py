"""Tekst voor de interface. Wachttijd blijft 'onbekend' zolang de bron dat zegt."""

from __future__ import annotations
from datetime import date
from urllib.parse import urlsplit

from zorgzoeker.valideer import _valideer_veld, _valideer_wachttijd, peildatum_veld, wachttijd_ouderdom, wachttijd_verouderd, indicatieve_publicatie

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
    "hoofdaannemer": "Hoofdaannemer",
    "aanmeldprocedure": "Aanmeldprocedure",
    "verwijzingsprocedure": "Verwijzingsprocedure",
    "contactgegevens": "Contactgegevens",
    "uitsluitingscriteria": "Uitsluitingscriteria",
    "toelatingsvoorwaarden": "Toelatingsvoorwaarden",
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


def website_url(aanbieder: dict | None) -> str | None:
    """Eigen website van de aanbieder uit het veld `website`, alleen http(s).

    Nooit een bron_url als vervanging: ontbreekt een bruikbare website, dan
    geen link.
    """
    veld = (aanbieder or {}).get("website") if isinstance(aanbieder, dict) else None
    if not isinstance(veld, dict) or veld.get("label") not in {"geverifieerd", "afgeleid"}:
        return None
    waarde = veld.get("waarde")
    if not isinstance(waarde, str):
        return None
    url = waarde.strip()
    if not url or any(teken.isspace() or ord(teken) < 32 for teken in url):
        return None
    try:
        delen = urlsplit(url)
    except ValueError:
        return None
    if delen.scheme.lower() not in {"http", "https"} or not delen.hostname:
        return None
    return url


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


def toon_veld(sleutel: str, veld: dict | None, *, referentiedatum: date | None = None) -> dict:
    """Eén veld, klaar voor de kaart of de vergelijking."""
    bron = veld if isinstance(veld, dict) else {}
    onbekend = is_onbekend(sleutel, bron if isinstance(veld, dict) else None)
    tekst = "onbekend" if onbekend else formateer_waarde(sleutel, bron.get("waarde"))
    if sleutel == "gecontracteerd_regio" and bron.get("waarde") == "nee" and bron.get("label") == "afgeleid":
        tekst = "Niet aangetroffen in contractlijst"
    if sleutel in ("wachttijd", "beschikbaarheid") and onbekend:
        tekst = "onbekend"
    geldig_gegeven = not onbekend
    verouderd = sleutel == "wachttijd" and geldig_gegeven and wachttijd_verouderd(bron, referentiedatum)
    indicatief = sleutel == "wachttijd" and geldig_gegeven and indicatieve_publicatie(bron)
    publicatie_tekst = tekst if verouderd or indicatief else None
    if verouderd or indicatief:
        tekst, onbekend = "onbekend", True
    return {
        "sleutel": sleutel,
        "label_nl": VELD_LABELS.get(sleutel, sleutel),
        "tekst": tekst,
        "label": "onbekend" if onbekend else bron.get("label") or "onbekend",
        "bron_url": veilige_url(bron.get("bron_url")) if geldig_gegeven else None,
        "datum": format_datum(bron.get("opgehaald_op")) if geldig_gegeven else None,
        "peildatum": peildatum_veld(bron) if geldig_gegeven else None,
        "toelichting": (bron.get("toelichting") or None) if geldig_gegeven else None,
        "verouderd": verouderd,
        "indicatief": indicatief,
        "actualiteit": "alleen gepubliceerd" if geldig_gegeven else "onbekend",
        "peildatum_leeftijd_dagen": wachttijd_ouderdom(bron, referentiedatum) if sleutel == "wachttijd" and geldig_gegeven else None,
        "publicatie_tekst": publicatie_tekst,
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
    if contracttoetsen and any(t.get("alle_beschikbaarheidsregels") for t in contracttoetsen):
        from zorgzoeker.beschikbaarheid import actueel, stop_actief
        for sleutel, label in (("intake_weken", "Actueel bevestigd: intake"),
                               ("start_behandeling_weken", "Actueel bevestigd: start behandeling"),
                               ("nieuwe_clienten", "Actueel bevestigd: nieuwe cliënten")):
            cellen = []
            for toets in contracttoetsen:
                regels = toets.get("beschikbaarheidsregels", [])
                r = regels[0] if len(regels) == 1 and actueel(regels[0]) else None
                waarde = r.get(sleutel) if r else None
                if sleutel == "nieuwe_clienten" and any(stop_actief(x) for x in regels):
                    waarde = "nee — relevante stop"
                tekst = f"{waarde:g} weken" if isinstance(waarde, (int, float)) else waarde or "onbekend"
                cellen.append({"tekst": tekst, "onbekend": tekst == "onbekend", "label": "geverifieerd" if r else "onbekend",
                               "bron_url": veilige_url(r.get("bron_url")) if r else None,
                               "datum": format_datum(r.get("bevestigd_op")) if r else None,
                               "toelichting": "Scope: " + "; ".join(str(r[k]) for k in ("dienst", "locatie", "productcode", "regios")) + ". Herbevestigen: " + r["herbevestigen_op"] if r else "Geen eenduidige actuele bevestiging voor deze zoekcontext."})
            rijen.append({"sleutel": sleutel, "label_nl": label, "cellen": cellen,
                          "verschilt": len({c["tekst"] for c in cellen}) > 1})
    if contracttoetsen and all(t.get('beoordeling') for t in contracttoetsen):
        for sleutel,label,lees in (
            ('beslis_inhoud','Zorginhoudelijk bronbewijs',lambda b:b['inhoud']['status']+' · '+b['inhoud']['kwaliteit']),
            ('beslis_contract','Contractbron en geldigheid',lambda b:b['contract']['bronstatus']+' · bronpeildatum '+str(b['contract']['peildatum'])+' · geldigheid '+b['contract']['geldigheid']),
            ('beslis_instroom','Aanmelden/start bevestigd',lambda b:b['instroom']['status']),
            ('beslis_versie','Bronversie',lambda b:b['context']['datasetversie'])):
            cellen=[{'tekst':lees(t['beoordeling']),'onbekend':False,'label':'afgeleid','toelichting':'Geen toewijsgarantie; controleer open punten.','bron_url':None,'datum':None} for t in contracttoetsen]
            rijen.insert(0,{'sleutel':sleutel,'label_nl':label,'cellen':cellen,'verschilt':len({c['tekst'] for c in cellen})>1})
    return rijen
