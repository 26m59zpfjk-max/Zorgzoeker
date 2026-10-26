"""Optioneel, brongebonden beschikbaarheidsregister en offline reviewworkflow.

Geen netwerk, verzendfunctie of publiek endpoint. Functies veranderen hun invoer
niet. Alleen een expliciet beoordeeld voorstel levert een nieuw document op.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import hashlib
import hmac
import json
import secrets
from urllib.parse import urlsplit

from zorgzoeker.contracten import code_sleutel, sleutel
from zorgzoeker.synoniemen import KERN_NAAR_GEMEENTE

VERIFICATIES = {"aanbieder_bevestigd", "gepubliceerd", "historisch"}
VELDEN = {"id", "aanbieder_id", "dienst", "locatie", "productcode", "intake_weken", "start_behandeling_weken",
          "nieuwe_clienten", "capaciteit", "leeftijd_van", "leeftijd_tot", "regios", "stop",
          "bevestigd_op", "herbevestigen_op", "bron_url", "verificatie", "gepubliceerd_op"}


def _datum(v):
    try:
        return date.fromisoformat(v) if isinstance(v, str) else None
    except ValueError:
        return None


def valideer_regel(r: object, vandaag: date | None = None) -> list[str]:
    vandaag = vandaag or date.today()
    if not isinstance(r, dict):
        return ["Beschikbaarheidsregel moet een object zijn."]
    fouten = []
    if set(r) != VELDEN:
        fouten.append("Beschikbaarheidsregel mist velden of bevat onbekende velden.")
    for k in ("id", "aanbieder_id"):
        if not isinstance(r.get(k), str) or not r[k].strip():
            fouten.append(f"{k} ontbreekt.")
    for k in ("dienst", "locatie", "productcode"):
        if r.get(k) is not None and (not isinstance(r[k], str) or not r[k].strip()):
            fouten.append(f"{k} moet tekst of null zijn.")
    for k in ("intake_weken", "start_behandeling_weken", "leeftijd_van", "leeftijd_tot"):
        v = r.get(k)
        if v is not None and (isinstance(v, bool) or not isinstance(v, (int, float)) or not 0 <= v <= (120 if k.startswith("leeftijd") else 520)):
            fouten.append(f"{k} moet een niet-negatief, begrensd getal of null zijn.")
    if r.get("leeftijd_van") is not None and r.get("leeftijd_tot") is not None:
        try:
            if r["leeftijd_van"] > r["leeftijd_tot"]:
                fouten.append("Leeftijdsgrenzen staan omgekeerd.")
        except TypeError:
            pass
    if not isinstance(r.get("nieuwe_clienten"), str) or r["nieuwe_clienten"] not in {"ja", "nee", "onbekend"}:
        fouten.append("nieuwe_clienten moet ja, nee of onbekend zijn.")
    c = r.get("capaciteit")
    if c is not None and (type(c) is not int or c < 0):
        fouten.append("capaciteit moet een niet-negatief geheel getal of null zijn.")
    if not isinstance(r.get("regios"), list) or any(not isinstance(g, str) or not g.strip() for g in r.get("regios", [])):
        fouten.append("regios moet een lijst plaatsnamen zijn.")
    v = r.get("verificatie")
    if not isinstance(v, str) or v not in VERIFICATIES:
        fouten.append("Onbekend verificatietype.")
    try:
        url = urlsplit(r.get("bron_url") or "")
        if url.scheme not in {"https", "http"} or not url.hostname or any(c.isspace() for c in r.get("bron_url", "")):
            fouten.append("Een openbare bron of intern vastgelegde bewijsverwijzing via https/http is vereist.")
    except (ValueError, TypeError):
        fouten.append("Ongeldige bron_url.")
    for k in ("bevestigd_op", "herbevestigen_op", "gepubliceerd_op"):
        if r.get(k) is not None and not _datum(r[k]):
            fouten.append(f"{k} is geen ISO-datum.")
    for k in ("bevestigd_op", "gepubliceerd_op"):
        if _datum(r.get(k)) and _datum(r[k]) > vandaag:
            fouten.append(f"{k} ligt in de toekomst.")
    if v == "aanbieder_bevestigd":
        b, h = _datum(r.get("bevestigd_op")), _datum(r.get("herbevestigen_op"))
        if not b or not h or h <= b:
            fouten.append("Aanbiederbevestiging vereist bevestigings- en latere herbevestigingsdatum.")
    elif not _datum(r.get("gepubliceerd_op")):
        fouten.append("Publicatie/historie vereist een publicatiedatum.")
    stop = r.get("stop")
    if stop is not None:
        if not isinstance(stop, dict) or set(stop) != {"soort", "vanaf", "tot", "toelichting"}:
            fouten.append("stop moet soort, vanaf, tot en toelichting bevatten.")
        else:
            if not isinstance(stop["soort"], str) or stop["soort"] not in {"aanmeldstop", "toeleidingsstop"} or not _datum(stop["vanaf"]):
                fouten.append("Stopsoort/startdatum ongeldig.")
            if stop["tot"] is not None and (not _datum(stop["tot"]) or (_datum(stop["vanaf"]) and _datum(stop["tot"]) < _datum(stop["vanaf"]))):
                fouten.append("Stopeinddatum ongeldig.")
            if not isinstance(stop["toelichting"], str) or not stop["toelichting"].strip():
                fouten.append("Stop vereist een toelichting.")
    return fouten


def actueel(r: dict, vandaag: date | None = None) -> bool:
    d = vandaag or date.today()
    return not valideer_regel(r, d) and r["verificatie"] == "aanbieder_bevestigd" and _datum(r["bevestigd_op"]) <= d < _datum(r["herbevestigen_op"])


def stop_actief(r: dict, op: date | None = None) -> bool:
    s = r.get("stop")
    d = op or date.today()
    return bool(s and _datum(s.get("vanaf")) and _datum(s["vanaf"]) <= d and
                (s.get("tot") is None or d <= _datum(s["tot"])))


def relevante_regels(document: dict, aanbieder_id: str, *, gemeente=None, codes=(), leeftijden=(), locatie=None) -> list[dict]:
    def canon(g):
        return KERN_NAAR_GEMEENTE.get(sleutel(g), sleutel(g))
    regels = []
    for r in document.get("beschikbaarheidsregister", []):
        if r["aanbieder_id"] != aanbieder_id:
            continue
        # Een beperkte scope is alleen toepasbaar met een overeenkomende vraag.
        if r["regios"] and (not gemeente or canon(gemeente) not in {canon(g) for g in r["regios"]}):
            continue
        if r["productcode"] and (not codes or code_sleutel(r["productcode"]) not in {code_sleutel(c.removeprefix("code_")) for c in codes}):
            continue
        if r["locatie"] and (not locatie or sleutel(locatie) != sleutel(r["locatie"])):
            continue
        if (r["leeftijd_van"] is not None or r["leeftijd_tot"] is not None) and (not leeftijden or
                not all((r["leeftijd_van"] or 0) <= n <= (r["leeftijd_tot"] if r["leeftijd_tot"] is not None else 120) for n in leeftijden)):
            continue
        regels.append(r)
    return regels


def verouderde_regels(document: dict, vandaag: date | None = None) -> list[dict]:
    return [deepcopy(r) for r in document.get("beschikbaarheidsregister", []) if not actueel(r, vandaag)]


def conceptverzoek(document: dict, regel_id: str) -> dict:
    r = next(r for r in document.get("beschikbaarheidsregister", []) if r["id"] == regel_id)
    return {"status": "concept_niet_verstuurd", "regel_id": regel_id,
            "tekst": f"Wilt u voor {r['dienst'] or 'de genoemde zorg'} op {r['locatie'] or 'de betreffende locatie'} intakewachttijd, behandelwachttijd, nieuwe aanmeldingen, capaciteit en eventuele stops bevestigen? Vermeld datum en scope. Deel geen cliëntgegevens.",
            "toestemming": None}


def keur_verzoek_goed(concept: dict, *, beoordelaar: str, expliciet: bool = False) -> dict:
    if not expliciet or not beoordelaar.strip() or concept.get("status") != "concept_niet_verstuurd":
        raise ValueError("Expliciete toestemming en beoordelaar vereist.")
    nieuw = deepcopy(concept)
    nieuw.update(status="goedgekeurd_niet_verstuurd", toestemming={"door": beoordelaar, "op": date.today().isoformat()})
    return nieuw  # Opzettelijk geen verzending, ook niet na goedkeuring.


def _hash(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def voorstel(document: dict, regel: dict) -> dict:
    fouten = valideer_regel(regel)
    if fouten:
        raise ValueError("; ".join(fouten))
    if regel["aanbieder_id"] not in {a["id"] for a in document["aanbieders"]}:
        raise ValueError("Onbekende aanbieder.")
    return {"status": "ter_controle", "basis": _hash(document), "regel": deepcopy(regel)}


def neem_op(document: dict, wijziging: dict, *, beoordelaar: str, expliciet: bool = False) -> dict:
    if not expliciet or not beoordelaar.strip() or wijziging.get("status") != "ter_controle":
        raise ValueError("Expliciete inhoudelijke controle vereist.")
    if wijziging.get("basis") != _hash(document):
        raise ValueError("Bron gewijzigd: maak en controleer een nieuw voorstel.")
    regel = wijziging["regel"]
    voorstel(document, regel)  # Hervalideer, ook na eventuele aanpassing van een concept.
    nieuw = deepcopy(document)
    register = nieuw.setdefault("beschikbaarheidsregister", [])
    oud = next((r for r in register if r["id"] == regel["id"]), None)
    if oud and oud["aanbieder_id"] != regel["aanbieder_id"]:
        raise ValueError("Een regel mag niet naar een andere aanbieder worden verplaatst.")
    nieuw.setdefault("beschikbaarheidshistorie", []).append({"vorige": deepcopy(oud), "nieuwe": deepcopy(regel),
                                                             "beoordelaar": beoordelaar, "op": date.today().isoformat()})
    nieuw["beschikbaarheidsregister"] = [r for r in register if r["id"] != regel["id"]] + [deepcopy(regel)]
    return nieuw


def maak_linkbewijs(aanbieder_id: str, regel_id: str, *, nu: datetime | None = None) -> tuple[str, dict]:
    """Toekomstige portaalbouwsteen: alleen de hash opslaan, nooit het token.

    Geen URL/endpoint/verzending. Een latere weblaag moet rate limits, HTTPS,
    identiteitscontrole bij uitgifte en atomair verbruik in opslag toevoegen.
    """
    nu = nu or datetime.now(timezone.utc)
    token = secrets.token_urlsafe(32)
    return token, {"hash": hashlib.sha256(token.encode()).hexdigest(), "aanbieder_id": aanbieder_id,
                   "regel_id": regel_id, "vervalt": (nu + timedelta(hours=48)).isoformat(), "verbruikt": False}


def verbruik_linkbewijs(bewijs: dict, token: str, aanbieder_id: str, regel_id: str, *, nu: datetime | None = None) -> dict:
    nu = nu or datetime.now(timezone.utc)
    if (bewijs.get("verbruikt") or bewijs["aanbieder_id"] != aanbieder_id or bewijs["regel_id"] != regel_id or
            nu >= datetime.fromisoformat(bewijs["vervalt"]) or
            not hmac.compare_digest(bewijs["hash"], hashlib.sha256(token.encode()).hexdigest())):
        raise ValueError("Ongeldig, verlopen of gebruikt linkbewijs.")
    return {**bewijs, "verbruikt": True}  # Alleen bevoegd tot voorstel, nooit directe publicatie.
