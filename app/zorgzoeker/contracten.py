"""Brongebonden contracttoets per gemeente, product, route en peildatum.

Een lijst op één peildatum bewijst geen begin- of einddatum van een contract.
Onbekende periodes worden nooit met een kalenderjaar aangevuld.
"""

from datetime import date
import re
import unicodedata

from zorgzoeker.synoniemen import KERN_NAAR_GEMEENTE


ROB_GEMEENTEN = frozenset({"berg en dal", "beuningen", "druten", "heumen", "mook en middelaar", "nijmegen", "wijchen"})
MAANDEN = {m: n for n, m in enumerate(("januari", "februari", "maart", "april", "mei", "juni", "juli", "augustus", "september", "oktober", "november", "december"), 1)}


def sleutel(tekst: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", unicodedata.normalize("NFKD", tekst).encode("ascii", "ignore").decode().lower()).split())


def code_sleutel(code: str) -> str:
    return re.sub(r"[^a-z0-9]", "", code.lower()).removeprefix("jw")


def lees_datum(tekst: str) -> str | None:
    """Een expliciete Nederlandse of ISO-datum; een los jaar blijft een jaar."""
    for patroon, volgorde in [(r"\b(20\d{2})-(\d{1,2})-(\d{1,2})\b", (1, 2, 3)),
                               (r"\b(\d{1,2})[-/](\d{1,2})[-/](20\d{2})\b", (3, 2, 1))]:
        m = re.search(patroon, tekst)
        if m:
            try:
                return date(*(int(m[g]) for g in volgorde)).isoformat()
            except ValueError:
                return None
    m = re.search(r"\b(\d{1,2})\s+(" + "|".join(MAANDEN) + r")\s+(20\d{2})\b", tekst.lower())
    if m:
        try:
            return date(int(m[3]), MAANDEN[m[2]], int(m[1])).isoformat()
        except ValueError:
            return None
    return None


def zoekdatum(tekst: str) -> str | None:
    if not re.search(r"\b(?:contract\w*|gecontracteerd|peildatum|per|vanaf)\b", tekst, re.I):
        return None
    return lees_datum(tekst) or next(iter(re.findall(r"\b20\d{2}\b", tekst)), None)


def _stop(tekst: str, gemeente: str | None, peildatum: str) -> bool:
    laag = tekst.lower()
    laag = re.sub(r"\b(?:geen|zonder)\s+(?:toeleidingsstop|aanmeldstop|cliëntenstop)\b", "", laag)
    if "toeleidingsstop" not in laag and "aanmeldstop" not in laag and "cliëntenstop" not in laag:
        return False
    gemeenten = {KERN_NAAR_GEMEENTE[g] for g in KERN_NAAR_GEMEENTE if re.search(rf"\b{re.escape(g)}\b", laag)}
    gemeente = KERN_NAAR_GEMEENTE.get(sleutel(gemeente), sleutel(gemeente)) if gemeente else None
    if "hele regio" not in laag and gemeenten and (not gemeente or sleutel(gemeente) not in gemeenten):
        return False
    tot = re.search(r"\btot( en met)?\s+((?:\d{4}-\d{1,2}-\d{1,2})|(?:\d{1,2}-\d{1,2}-\d{4})|(?:\d{1,2}\s+(?:" + "|".join(MAANDEN) + r")\s+20\d{2}))", laag)
    if tot and (einde := lees_datum(tot[2])):
        if peildatum > einde or (peildatum == einde and not tot[1]):
            return False
    vanaf = lees_datum(laag[:tot.start()] if tot else laag)
    return not vanaf or vanaf <= peildatum


class Contractregister:
    def __init__(self, document: dict):
        self.register = document.get("contractregister") or {}
        self.per_id: dict[str, list[dict]] = {}
        for regel in self.register.get("regels", []):
            self.per_id.setdefault(regel["aanbieder_id"], []).append(regel)

    def oordeel(self, aanbieder: dict, *, gemeente: str | None = None,
                codes: list[str] = (), op_datum: str | None = None) -> dict:
        gemeente = KERN_NAAR_GEMEENTE.get(sleutel(gemeente), sleutel(gemeente)) if gemeente else None
        bron = aanbieder.get("gecontracteerd_regio") or {}
        peil = self.register.get("peildatum") or bron.get("opgehaald_op")
        resultaat = {"status": "onbekend", "toeleiding": "onbekend", "peildatum": peil,
                     "bron_url": self.register.get("bron_url") or bron.get("bron_url"),
                     "routes": [], "waarschuwingen": []}
        # Brondatum is géén geldigheidsperiode. Geen terug- of vooruitprojectie.
        datum_onbevestigd = bool(op_datum and op_datum != peil)
        if datum_onbevestigd:
            resultaat["waarschuwingen"].append(f"Contractgeldigheid op {op_datum} niet vastgesteld; beschikbare bron heeft peildatum {peil or 'onbekend'}.")
        regels = self.per_id.get(aanbieder["id"], [])
        if self.register:
            if not regels:
                if not datum_onbevestigd and bron.get("waarde") == "nee" and bron.get("label") == "afgeleid" and bron.get("bron_url"):
                    resultaat["status"] = "nee"
                    resultaat["waarschuwingen"].append("Niet aangetroffen in de gebruikte contractlijst; dit bewijst niet dat er geen contract bestaat.")
                resultaat["waarschuwingen"].append("Geen productgebonden contractroute in de gecontroleerde bron vastgesteld.")
                return resultaat
            gezocht = {code_sleutel(c.removeprefix("code_")) for c in codes}
            regels = [r for r in regels if (not gezocht or code_sleutel(r["productcode"]) in gezocht)
                      and (not gemeente or gemeente in {KERN_NAAR_GEMEENTE.get(sleutel(g), sleutel(g)) for g in r["gemeenten"]})]
            if not regels or (gezocht and not gezocht.issubset({code_sleutel(r["productcode"]) for r in regels})):
                return resultaat
            resultaat["status"] = "onbekend" if datum_onbevestigd else "ja"
            open_codes = set()
            for r in regels:
                opmerkingen = r.get("opmerkingen", [])
                # Een onbevestigd contract wist een bekende stop niet. Zonder
                # aantoonbare einddatum/opheffing blijft de beperking gelden.
                toetsdatum = op_datum if op_datum and len(op_datum) == 10 else date.today().isoformat()
                dicht = any(_stop(t, gemeente, toetsdatum) for t in opmerkingen)
                if not dicht:
                    open_codes.add(code_sleutel(r["productcode"]))
                resultaat["routes"].append({**r, "toeleiding": "geblokkeerd" if dicht else "niet als gestopt vermeld"})
                resultaat["waarschuwingen"].extend(opmerkingen)
            geblokkeerd = (gezocht and not gezocht.issubset(open_codes)) or not open_codes
            resultaat["toeleiding"] = "geblokkeerd" if geblokkeerd else ("onbekend" if datum_onbevestigd else "niet als gestopt vermeld")
            # Afwezigheid van een stop bewijst geen vrije plek.
            resultaat["waarschuwingen"] = list(dict.fromkeys(resultaat["waarschuwingen"]))
            return resultaat
        # Legacy/fictieve bestanden: alleen het algemene bronlabel, nooit
        # productgebonden contractgeldigheid of de route uit een losse naam.
        if not datum_onbevestigd and bron.get("label") in {"geverifieerd", "afgeleid"} and bron.get("bron_url") and peil:
            resultaat["status"] = str(bron.get("waarde") or "onbekend")
        resultaat["waarschuwingen"].append("Productgebonden contractvoorwaarden ontbreken; bevestig de route bij gemeente of aanbieder.")
        return resultaat


def algemene_stop(aanbieder: dict, gemeente: str | None, op_datum: str | None = None,
                  leeftijd: int | float | None = None, codes: list[str] = ()) -> bool:
    """Alleen een expliciete algemene aanmeldstop, geen productgebonden stop."""
    veld = aanbieder.get("beschikbaarheid") or {}
    wacht = aanbieder.get("wachttijd") or {}
    wachttekst = str(wacht.get("waarde") or "")
    # Een expliciet gemelde 18+-aanmeldstop in de wachttijdtekst geldt
    # uitsluitend voor die leeftijdsgroep, niet voor alle jeugdigen.
    if leeftijd is not None and leeftijd >= 18 and re.search(r"18\s*\+\s*:\s*aanmeldstop", wachttekst, re.I):
        if wacht.get("label") == "geverifieerd" and wacht.get("bron_url"):
            if not op_datum or op_datum >= wacht.get("opgehaald_op", ""):
                toetsdatum = op_datum if op_datum and len(op_datum) == 10 else date.today().isoformat()
                return _stop(wachttekst, gemeente, toetsdatum)
    if veld.get("label") != "geverifieerd" or not veld.get("bron_url"):
        return False
    tekst = str(veld.get("waarde") or "")
    if leeftijd is not None and leeftijd < 18 and re.search(r"(?:<\s*18|onder de 18|onder 18).*niet meer aangenomen", tekst, re.I):
        if not op_datum or op_datum >= veld.get("opgehaald_op", ""):
            return True
    productcodes = re.findall(r"\bJW\s*(\d{2}[A-Z]\d{2})\b", tekst, re.I)
    if productcodes and not ({code_sleutel(c) for c in codes} & {code_sleutel(c) for c in productcodes}):
        return False
    peil = op_datum if op_datum and len(op_datum) == 10 else date.today().isoformat()
    if not peil or len(peil) != 10:
        return False
    # Vóór de waarneming is een ongedateerde stop niet bewezen. Na de
    # waarneming verdwijnt hij pas bij een expliciete einddatum/opheffing.
    if op_datum and op_datum < veld.get("opgehaald_op", "") and not lees_datum(tekst):
        return False
    return _stop(tekst, gemeente, peil)
