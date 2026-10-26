"""Compacte beslisinformatie, met behoud van alle bronvelden in de details."""
import re

from zorgzoeker.beschikbaarheid import actueel
from zorgzoeker.weergave import KAART_VELDEN, toon_veld
from zorgzoeker.zoeken import _concepten_in, analyseer_vraag


def samenvatting(treffer, vraag="") -> dict:
    ruw, toets = treffer.aanbieder, treffer.contracttoets
    bron = ruw.get("gecontracteerd_regio") or {}
    status = toets.get("status", "onbekend")
    routes = toets.get("routes", [])
    bevestigd = bool(routes and toets.get("bron_url") and toets.get("peildatum")) or bron.get("label") == "geverifieerd"
    contract = "Contractstatus onbekend"
    if status == "ja" and bevestigd:
        contract = "Bevestigd gecontracteerd"
    elif status == "nee":
        contract = "Bevestigd niet-gecontracteerd" if bron.get("label") == "geverifieerd" else "Niet aangetroffen in beschikbare contractbronnen"
    route = "Contractroute onbekend"
    if routes:
        direct = any(not r.get("hoofdaannemer") for r in routes)
        via = any(r.get("hoofdaannemer") for r in routes)
        route = "Rechtstreeks én via hoofdaannemer" if direct and via else "Via hoofdaannemer (onderaannemer)" if via else "Rechtstreeks gecontracteerd"
        if status != "ja":
            route = route.replace("Rechtstreeks gecontracteerd", "Rechtstreekse route in bron") + " · geldigheid onbekend"
    elif ruw.get("hoofdaannemer", {}).get("label") in {"geverifieerd", "afgeleid"}:
        route = "Via hoofdaannemer · route voor deze vraag controleren"
    codes = list(dict.fromkeys(r["productcode"] for r in routes)) if status == "ja" and bevestigd else []
    wensen = set(analyseer_vraag(vraag, {}, set()).concepten)
    def lijst(k):
        v = ruw.get(k) or {}
        return v.get("waarde", []) if v.get("label") in {"geverifieerd", "afgeleid"} and isinstance(v.get("waarde"), list) else []
    expertise = lijst("expertise")
    relevant = [x for x in expertise if wensen & set(_concepten_in(x))]
    expertise = relevant or expertise
    velden = {k: toon_veld(k, ruw.get(k)) for k in KAART_VELDEN}
    stop = toets.get("stop_actief", False)
    waarschuwingen = []
    for k,v in ruw.get('_kwaliteit',{}).items():
        if v['status']=='tegenstrijdig_of_verouderd' or v.get('hash_gewijzigd'):
            waarschuwingen.append(k + ': tegenstrijdig/verouderd bewijs; niet als bevestigd gebruikt.')
    if stop:
        waarschuwingen.append("STOP — nieuwe aanmeldingen/toeleiding voor deze vraag niet mogelijk.")
    elif any(r.get("toeleiding") == "geblokkeerd" for r in routes):
        waarschuwingen.append("Toeleidingsstop op een deel van de routes; controleer de open route.")
    # Onbevestigde scope/einddatum wordt zichtbaar gehouden, ook bij naamzoeken.
    for k in ("beschikbaarheid", "wachttijd", "doelgroepen", "uitsluitingscriteria", "toelatingsvoorwaarden"):
        v = ruw.get(k) or {}
        if v.get("label") in {"geverifieerd", "afgeleid"}:
            tekst = str(v.get("waarde", ""))
            if tekst not in {"onbekend", "", "[]"} and (k in {"uitsluitingscriteria", "toelatingsvoorwaarden"} or re.search(r"stop|niet meer aangenomen|uitsluit|uitsluitend|alleen voor|niet geschikt|geen crisis", tekst, re.I)):
                waarschuwingen.append(("Bron noemt beperking (scope/periode controleren): " if not stop else "") + tekst)
    if treffer.ontbrekende_expertise:
        waarschuwingen.append("Gedeeltelijke match: niet bevestigd — " + ", ".join(treffer.ontbrekende_expertise))
    wacht = velden["wachttijd"]
    wachttijd = "Onbekend"
    if not wacht["onbekend"]:
        wachttijd = wacht["tekst"] + " · gepubliceerd, niet actueel bevestigd"
    aanname = "Onbekend; geen bevestigde actuele instroom"
    if stop:
        aanname = "Nee — relevante stop"
    regels = toets.get("beschikbaarheidsregels", [])
    actuele = [r for r in regels if actueel(r)]
    if regels:
        wachttijd = "Onbekend"  # Geen oudere publicatie als gunstig alternatief voor een verlopen bevestiging.
    # Tegenstrijdige/multiple dienstwaarnemingen nooit samenpersen tot één getal.
    if len(actuele) == 1 and len(regels) == 1:
        regel = actuele[0]
        scope = " · ".join(x for x in (regel["dienst"], regel["locatie"]) if x)
        aanname = {"ja": "Ja — door aanbieder bevestigd", "nee": "Nee — door aanbieder bevestigd", "onbekend": "Onbekend"}[regel["nieuwe_clienten"]] if not stop else aanname
        delen = []
        for k, label in (("intake_weken", "intake"), ("start_behandeling_weken", "start behandeling")):
            if regel[k] is not None:
                delen.append(f"{label}: {regel[k]:g} weken")
        if delen:
            wachttijd = "; ".join(delen) + " · bevestigd " + regel["bevestigd_op"]
        if scope:
            aanname += " · " + scope
            wachttijd += " · " + scope
    if len(regels) > 1:
        aanname = "Meerdere dienst-/locatiegegevens; controleer details" if not stop else aanname
    doelen = lijst("doelgroepen")
    numeriek = [d for d in doelen if re.search(r"\b(?:vanaf|tot|\d+\s*(?:-|jaar|jr|t/m|tot))\b|\d+\s*\+", d, re.I)]
    if numeriek:
        toelating = "; ".join(numeriek)
    else:
        groepen = [g for g in ("kinderen", "jongeren", "volwassenen", "gezinnen")
                   if any(re.search(rf"\b{g}\b", d, re.I) for d in doelen)]
        toelating = ", ".join(groepen) + " · precieze leeftijdsgrenzen onbekend" if groepen else "Leeftijdsgroep onbekend"
    return {"contract_kort": contract, "route_kort": route, "gemeente_kort": toets.get("gemeente") or "geen gemeente geselecteerd",
            "codes_kort": codes[:3], "meer_codes": len(codes) > 3,
            "expertise_kort": "; ".join(expertise[:3]) or "Expertise onbekend",
            "hulpvorm_kort": "; ".join(lijst("type_aanbod")[:2]) or "Hulpvorm onbekend",
            "leeftijd_kort": toelating, "wachttijd_kort": wachttijd, "aanname_kort": aanname,
            "waarschuwingen_kort": list(dict.fromkeys(waarschuwingen)),
            "detail_velden": [toon_veld("naam", ruw.get("naam"))] + list(velden.values()) +
                [toon_veld(k, v) for k, v in ruw.items() if k not in {"id", "naam", "gevonden_via", *KAART_VELDEN} and isinstance(v, dict) and "waarde" in v],
            "beschikbaarheidsdetails": [{**r, "actueel": actueel(r)} for r in toets.get("alle_beschikbaarheidsregels", [])]}
