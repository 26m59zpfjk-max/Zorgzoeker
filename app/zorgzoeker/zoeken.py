"""Zoeken in gewoon Nederlands.

De rangschikking combineert een lokale BM25-score met signalen die uit de
zoekvraag worden gelezen: leeftijd, plaats of gemeente, productcode en
contractstatus. Synoniemen staan in synoniemen.py. Er is geen netwerk en
geen taalmodel. De functie verzint geen wachttijd en schrijft geen expertise
bij een aanbieder bij.

Een treffer op expertise van de eigen website weegt zwaarder dan een treffer
op type aanbod of op de omschrijving van een productcode (data/producten.json).
Vraagbegrippen als autisme of angst staan zelden in die omschrijving. Een
gecontracteerde jeugd-ggz-code (JW 54) telt dan als zwakkere zoekmatch; de
reden noemt de code en de omschrijving, niet een verzonnen expertise.
"""

from __future__ import annotations

import json
import math
import re
import unicodedata
from dataclasses import dataclass, field, replace

from zorgzoeker.config import PROJECT_ROOT
from zorgzoeker.negatie import splits_negaties
from zorgzoeker.beschikbaarheid import relevante_regels, actueel, stop_actief
from datetime import date
from zorgzoeker.contracten import Contractregister, ROB_GEMEENTEN, algemene_stop, zoekdatum
from zorgzoeker.valideer import _valideer_veld, _valideer_wachttijd, wachttijd_verouderd, indicatieve_publicatie
from zorgzoeker.synoniemen import (
    BOVEN,
    CONCEPT_LABEL,
    KERN_NAAR_GEMEENTE,
    STOPWOORDEN,
    concept_frases,
)

# Klinische vraagbegrippen die het regionale productenboek niet bij naam noemt.
# Alleen een jeugd-ggz-product (code JW 54 of omschrijving met ggz) mag ze dragen,
# en alleen in de reden als productcode — niet als expertise.
GGZ_VRAAG = frozenset({"ass", "angst", "trauma", "depressie", "adhd"})
EXPERTISE_WEGING = 3.4
AANBOD_WEGING = 2.6
# Een zeldzamer begrip weegt extra, zodat een specifieke term (EMDR) niet
# onder een algemenere (trauma) zakt door een langere tekst.
ZELDZAAMHEID = 1.2
KLINISCH = frozenset({"angst", "dwang", "depressie", "zelfbeschadiging", "adhd", "ass", "trauma", "eet", "hechting", "gedrag", "lvb", "verslaving", "gamen", "school", "echtscheiding", "kopp", "gezin", "dyslexie", "dyscalculie", "opvoed", "slaap", "psychose", "rouw", "hoogbegaafd"})
BEHANDELMETHODEN = frozenset({"medicatie", "emdr", "speltherapie", "reflexintegratie"})

TOKEN_RE = re.compile(r"c_[a-z0-9_]+|p_[a-z0-9_]+|code_[a-z0-9]+|[a-z0-9]+")
CODE_RE = re.compile(r"\b(?=[a-z0-9-]*\d)[a-z]{2,8}(?:-[a-z0-9]{1,8})+\b")
LEEFTIJD_JAAR = re.compile(r"\b(\d{1,3}(?:decimal\d+)?)\s*(?:jaar|jr|[- ]?jarig(?:e|en)?)\b")
LEEFTIJD_PERSOON = re.compile(
    r"\b(?:jongen|meisje|kind|jongere|zoon|dochter|puber|tiener|leeftijd)\s+(?:van\s+)?(\d{1,3}(?:decimal\d+)?)\b"
)
LEEFTIJD_RANGE = re.compile(r"\b(\d{1,3})\s*(?:-|tot en met|tot)\s*(\d{1,3})\s*jaar\b")
VANAF = re.compile(r"\bvanaf\s+(\d{1,2})\b")
TOT_LEEFTIJD = re.compile(r"\btot\s+(\d{1,2})\s*jaar\b")
MEISJE_RE = re.compile(r"\b(meisje|meisjes|dochter|dochters)\b")
JONGEN_RE = re.compile(r"\b(jongen|jongens|zoon|zonen)\b")
JAAR_IN_TEKST = re.compile(r"\b(19|20)\d{2}\b")

CONTRACT_PATRONEN: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bniet[-\s]?gecontracteerd\b"), "nee"),
    (re.compile(r"\bongecontracteerd\b"), "nee"),
    (re.compile(r"\bzonder contract\b"), "nee"),
    (re.compile(r"\bgeen contract\b"), "nee"),
    (re.compile(r"\bcontract(?:status)?\s+onbekend\b"), "onbekend"),
    (re.compile(r"\bwel gecontracteerd\b"), "ja"),
    (re.compile(r"\bgecontracteerd\b"), "ja"),
)


def normaliseer(tekst: str) -> str:
    """Kleine letters, zonder accenten, leestekens weg."""
    tekst = unicodedata.normalize("NFKD", tekst or "")
    tekst = "".join(teken for teken in tekst if not unicodedata.combining(teken))
    tekst = re.sub(r"\bad\s*\(\s*h\s*\)\s*d\b", "adhd", tekst, flags=re.I)
    tekst = tekst.lower().replace("/", " ")
    tekst = re.sub(r"[^a-z0-9+\-\s]", " ", tekst)
    return re.sub(r"\s+", " ", tekst).strip()


def mooie_plaats(sleutel: str) -> str:
    klein = {"en", "aan", "de", "het", "van"}
    woorden = []
    for index, woord in enumerate(sleutel.split()):
        if index and woord in klein:
            woorden.append(woord)
        elif "-" in woord:
            woorden.append("-".join(deel.capitalize() for deel in woord.split("-")))
        else:
            woorden.append(woord.capitalize())
    return " ".join(woorden)


def _uniek(items: list[str]) -> list[str]:
    gezien: list[str] = []
    for item in items:
        if item not in gezien:
            gezien.append(item)
    return gezien


def _code_token(code: str) -> str:
    return "code_" + re.sub(r"[^a-z0-9]", "", normaliseer(code))


def _code_sleutel(code: str) -> str:
    return re.sub(r"[^a-z0-9]", "", normaliseer(code))


def _concepten_in(tekst: str) -> list[str]:
    """Concept-ids in een tekst, langste frase eerst, zonder overlap."""
    positief, _, _ = splits_negaties(normaliseer(re.sub(r"[,;.!?]", " maar ", tekst)), concept_frases())
    _, tokens = _vervang(positief, concept_frases())
    return _uniek(tokens)


def _productcatalogus() -> dict[str, dict]:
    """Regionale productcodes, sleutel is de genormaliseerde code."""
    pad = PROJECT_ROOT / "data" / "producten.json"
    if not pad.is_file():
        return {}
    try:
        document = json.loads(pad.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    catalogus: dict[str, dict] = {}
    for product in document.get("producten") or []:
        if not isinstance(product, dict):
            continue
        sleutel = normaliseer(str(product.get("code") or ""))
        if sleutel:
            catalogus[sleutel] = product
    return catalogus


_VELD_RANG = {"expertise": 0, "doelgroepen": 1, "type_aanbod": 2, "naam": 3, "productcodes": 4}


def _bewijzen_uit(
    naam: str,
    expertise: list[str],
    doelgroepen: list[str],
    types: list[str],
    producten: list[dict],
    catalogus: dict | None = None,
) -> dict[str, Bewijs]:
    """Per categorie het sterkste veld dat een synoniem echt bevat."""
    gekozen: dict[str, tuple[int, Bewijs]] = {}

    def overweeg(rang: int, veld: str, tekst: str, code: str = "") -> None:
        schoon = (tekst or "").strip()
        if not schoon or schoon == "onbekend":
            return
        for cid in _concepten_in(schoon):
            huidig = gekozen.get(cid)
            if huidig is not None and huidig[0] <= rang:
                continue
            gekozen[cid] = (rang, Bewijs(cid, veld, schoon, code))

    overweeg(_VELD_RANG["naam"], "naam", naam)
    for tekst in expertise:
        overweeg(_VELD_RANG["expertise"], "expertise", tekst)
    for tekst in doelgroepen:
        overweeg(_VELD_RANG["doelgroepen"], "doelgroepen", tekst)
    for tekst in types:
        overweeg(_VELD_RANG["type_aanbod"], "type_aanbod", tekst)
    for product in producten:
        code = str(product.get("code") or "").strip()
        catalogus_item = (catalogus or {}).get(normaliseer(code), {}) if code else {}
        omschrijving = str(product.get("omschrijving") or catalogus_item.get("omschrijving") or "").strip()
        overweeg(_VELD_RANG["productcodes"], "productcodes", omschrijving, code)
    return {cid: paar[1] for cid, paar in gekozen.items()}


def _is_ggz_code(code: str, omschrijving: str) -> bool:
    if _code_sleutel(code).startswith("jw54"):
        return True
    return "ggz" in _concepten_in(omschrijving)


def _plaats_token(naam: str) -> str:
    return "p_" + re.sub(r"[^a-z0-9]+", "_", naam).strip("_")


def plaats_match(links: str, rechts: str) -> bool:
    """Zelfde plaats, ook 'Millingen' tegenover 'Millingen aan de Rijn'."""
    links, rechts = normaliseer(links), normaliseer(rechts)
    if not links or not rechts:
        return False
    if links == rechts:
        return True
    korter, langer = (links, rechts) if len(links) <= len(rechts) else (rechts, links)
    if len(korter) < 4:
        return False
    return re.search(rf"\b{re.escape(korter)}\b", langer) is not None


def maak_plaatstabel(extra: set[str] | None = None) -> dict[str, str]:
    """Statische kernen, aangevuld met plaatsen uit de dataset."""
    tabel = dict(KERN_NAAR_GEMEENTE)
    for naam in extra or ():
        sleutel = normaliseer(naam)
        if len(sleutel) < 3 or sleutel in {"rijk van nijmegen", "regio", "landelijk"}:
            continue
        if "rijk van nijmegen" in sleutel or "contractgebied" in sleutel or sleutel.startswith("onbekend"):
            continue
        tabel.setdefault(sleutel, sleutel)
    return tabel


def _vervang(tekst: str, frases: list[tuple[str, str]]) -> tuple[str, list[str]]:
    """Vervang niet-overlappende frases. Langste frase eerst aanleveren."""
    if not tekst:
        return tekst, []
    bezet = [False] * len(tekst)
    gevonden: list[tuple[int, int, str]] = []
    for frase, token in frases:
        if not frase:
            continue
        patroon = re.compile(rf"\b{re.escape(frase)}\b")
        for match in patroon.finditer(tekst):
            if any(bezet[match.start() : match.end()]):
                continue
            for positie in range(match.start(), match.end()):
                bezet[positie] = True
            gevonden.append((match.start(), match.end(), token))
    if not gevonden:
        return tekst, []
    gevonden.sort()
    delen: list[str] = []
    tokens: list[str] = []
    cursor = 0
    for start, einde, token in gevonden:
        delen.append(tekst[cursor:start])
        delen.append(f" {token} ")
        tokens.append(token)
        cursor = einde
    delen.append(tekst[cursor:])
    return "".join(delen), tokens


def _strip_regio(tekst: str) -> tuple[str, bool]:
    regio = False
    if "rijk van nijmegen" in tekst:
        regio = True
        tekst = tekst.replace("rijk van nijmegen", " ")
    if re.search(r"\bregio\s+nijmegen\b", tekst):
        regio = True
        tekst = re.sub(r"\bregio\s+nijmegen\b", " ", tekst)
    return re.sub(r"\s+", " ", tekst).strip(), regio


def _tokeniseer(tekst: str, plaatstabel: dict[str, str], bekende_codes: set[str]) -> list[str]:
    tekst = normaliseer(tekst)
    tekst, _ = _strip_regio(tekst)
    tekst, _ = _vervang_codes(tekst, bekende_codes)
    plaats_frases = [(_naam, _plaats_token(_naam)) for _naam in sorted(plaatstabel, key=len, reverse=True)]
    tekst, _ = _vervang(tekst, plaats_frases)
    concept_tokens = [(frase, f"c_{cid}") for frase, cid in concept_frases()]
    tekst, _ = _vervang(tekst, concept_tokens)
    tokens = []
    for token in TOKEN_RE.findall(tekst):
        if token.startswith(("c_", "p_", "code_")):
            tokens.append(token)
        elif token not in STOPWOORDEN and len(token) > 2 and not token.isdigit():
            tokens.append(token)
    return tokens


def _vervang_codes(tekst: str, bekende_codes: set[str]) -> tuple[str, list[str]]:
    tokens: list[str] = []
    for code in sorted(bekende_codes, key=len, reverse=True):
        patroon = re.compile(rf"\b{re.escape(code)}\b")

        def _vervanger(match: re.Match[str], code: str = code) -> str:
            token = _code_token(code)
            tokens.append(token)
            return f" {token} "

        tekst = patroon.sub(_vervanger, tekst)
    losse: list[str] = []

    def _generiek(match: re.Match[str]) -> str:
        token = _code_token(match.group(0))
        losse.append(token)
        return f" {token} "

    tekst = CODE_RE.sub(_generiek, tekst)
    return tekst, tokens + losse


_BEREIK = re.compile(r"\b(\d{1,3})\s*(?:-|tot en met|t m|tot)\s*(\d{1,3})\b")
_TOT_ALLEEN = re.compile(r"\b(?:tot en met|tot)\s+(\d{1,3})\b")

# Levensfase is een leeftijdsband, geen woord dat in de tekst hoeft te staan.
_LEVEN: tuple[tuple[re.Pattern[str], tuple[int, int], str], ...] = (
    (re.compile(r"\b(?:baby|babys|dreumes)\b"), (0, 2), "baby"),
    (re.compile(r"\bpeuters?\b"), (1, 4), "peuter"),
    (re.compile(r"\bkleuters?\b"), (4, 6), "kleuter"),
    (re.compile(r"\b(?:pubers?|tieners?)\b"), (12, 18), "puber"),
)


def leeftijdsgrenzen(tekst: str) -> list[tuple[int, int]]:
    """Lees leeftijdsgrenzen uit één doelgroeptekst. Lege lijst = niet vast te stellen."""
    ruw = (tekst or "").replace("–", "-").replace("—", "-")
    tekst = normaliseer(ruw)
    grenzen: list[tuple[int, int]] = []
    for m in _BEREIK.finditer(tekst):
        laag, hoog = int(m[1]), int(m[2])
        if tekst[m.end():].startswith("+"):
            hoog = 120
        elif re.search(r"\b(?:tot en met|t m)\b", m[0]):
            hoog = math.nextafter(float(hoog + 1), -math.inf)
        elif re.search(r"\btot\b", m[0]) and "tot en met" not in m[0]:
            hoog = math.nextafter(float(hoog), -math.inf)
        if 0 <= laag <= hoog <= 120 and laag <= 30:
            grenzen.append((laag, hoog))
    if grenzen:
        return grenzen
    vanaf = VANAF.search(tekst) or re.search(r"\b(\d{1,2})\s*\+", tekst)
    if vanaf:
        # Geen verzonnen bovengrens van 23 voor 'vanaf 15' of '18+'.
        return [(int(vanaf.group(1)), 120)]
    tot = _TOT_ALLEEN.search(tekst)
    if tot and int(tot.group(1)) <= 120:
        bovengrens = int(tot.group(1))
        bovengrens = math.nextafter(float(bovengrens + (1 if tot.group(0).startswith("tot en met") else 0)), -math.inf)
        return [(0, bovengrens)]
    return grenzen


def leeftijd_oordeel(
    laag: int,
    hoog: int,
    bereiken: list[tuple[str, list[tuple[int, int]]]],
) -> tuple[str, str]:
    """binnen, buiten of onbekend. Het citaat is een echte doelgroeptekst.

    Een leeftijd mag alleen 'binnen' heten als het geciteerde bereik die leeftijd echt dekt.
    """
    met_bereik = [(tekst, reeksen) for tekst, reeksen in bereiken if reeksen]
    if not met_bereik:
        return "onbekend", ""

    def dekt(begin: int, eind: int) -> bool:
        if laag == hoog:
            return begin <= laag <= eind
        return begin <= laag and hoog <= eind

    def overlapt(reeksen: list[tuple[int, int]]) -> bool:
        return any(dekt(begin, eind) for begin, eind in reeksen)

    passend = [(tekst, reeksen) for tekst, reeksen in met_bereik if overlapt(reeksen)]
    if not passend:
        if any(max(laag, begin) <= min(hoog, eind) for _, reeksen in met_bereik for begin, eind in reeksen):
            return "onbekend", ""  # slechts gedeeltelijke overlap, geen volledige dekking
        # Een grens voor bijvoorbeeld wonen zegt niets over onbegrensde
        # kinder-/gezinsbehandeling in een ander doelgroepveld.
        if any(not reeksen and re.search(r"\b(kinderen|jongeren|jeugd|gezinnen)\b", normaliseer(tekst))
               for tekst, reeksen in bereiken):
            return "onbekend", ""
        return "buiten", met_bereik[0][0]

    def breedte(reeksen: list[tuple[int, int]]) -> int:
        maten = [eind - begin for begin, eind in reeksen if dekt(begin, eind)]
        return min(maten) if maten else 999

    tekst, _reeksen = min(passend, key=lambda paar: (breedte(paar[1]), len(paar[0])))
    return "binnen", tekst


def _gender(tekst: str) -> str | None:
    tekst = normaliseer(tekst)
    meisje = MEISJE_RE.search(tekst) is not None
    jongen = JONGEN_RE.search(tekst) is not None
    if meisje and jongen:
        return "beide"
    if meisje:
        return "meisjes"
    if jongen:
        return "jongens"
    return None


def _lijst(veld: dict) -> list:
    waarde = veld.get("waarde") if isinstance(veld, dict) else None
    return waarde if isinstance(waarde, list) else []


def _tekst_van(veld: dict) -> str:
    waarde = veld.get("waarde") if isinstance(veld, dict) else ""
    if isinstance(waarde, str):
        return waarde
    if isinstance(waarde, list):
        delen = []
        for item in waarde:
            if isinstance(item, str):
                delen.append(item)
            elif isinstance(item, dict):
                delen.append(" ".join(str(deel) for deel in item.values() if deel))
        return " ".join(delen)
    return ""


@dataclass
class Filters:
    gecontracteerd: str | None = None
    productcode: str | None = None
    doelgroep: str | None = None
    gemeente: str | None = None
    vestigingsplaats: str | None = None
    op_datum: str | None = None

    @classmethod
    def van(cls, **ruw: str | None) -> Filters:
        def schoon(waarde: str | None) -> str | None:
            if waarde is None:
                return None
            tekst = str(waarde).strip()
            return tekst or None

        return cls(
            gecontracteerd=schoon(ruw.get("gecontracteerd")),
            productcode=schoon(ruw.get("productcode")),
            doelgroep=schoon(ruw.get("doelgroep")),
            gemeente=schoon(ruw.get("gemeente")),
            vestigingsplaats=schoon(ruw.get("vestigingsplaats")),
            op_datum=schoon(ruw.get("op_datum")),
        )

    def actief(self) -> bool:
        return any((self.gecontracteerd, self.productcode, self.doelgroep, self.gemeente, self.vestigingsplaats, self.op_datum))


@dataclass
class Vraag:
    tekst: str
    leeftijd: int | float | None = None
    plaatsen: list[str] = field(default_factory=list)
    gemeenten: list[str] = field(default_factory=list)
    contract: str | None = None
    codes: list[str] = field(default_factory=list)
    concepten: list[str] = field(default_factory=list)
    gender: str | None = None
    regio_nijmegen: bool = False
    tokens: list[str] = field(default_factory=list)
    leeftijdsband: tuple[int, int] | None = None
    leeftijd_label: str = ""
    ontkend: list[str] = field(default_factory=list)
    uitgesloten: list[str] = field(default_factory=list)
    op_datum: str | None = None
    max_wachttijd: int | None = None
    leeftijden: list[int | float] = field(default_factory=list)
    interpretatiefragmenten: list[dict] = field(default_factory=list)

    def leeg(self) -> bool:
        return not any(
            (
                self.leeftijd is not None,
                self.leeftijdsband,
                self.plaatsen,
                self.contract,
                self.codes,
                self.concepten,
                self.gender,
                self.regio_nijmegen,
                self.tokens,
                self.ontkend,
                self.op_datum,
                self.max_wachttijd is not None,
            )
        )


@dataclass
class Profiel:
    ruw: dict
    id: str
    naam: str
    contract: str
    code_tokens: set[str]
    producten: list[dict]
    concepten: set[str]
    vestiging_plaatsen: set[str]
    alle_plaatsen: set[str]
    gemeenten: set[str]
    leeftijden: list[tuple[int, int]]
    leeftijd_tekst: str
    gender: str | None
    tokens: list[str]
    doelgroepen: list[str]
    types: list[str]
    expertise: list[str]
    bewijzen: dict = field(default_factory=dict)
    doel_bereiken: list = field(default_factory=list)
    expertise_concepten: set[str] = field(default_factory=set)
    product_voor_concept: dict = field(default_factory=dict)
    type_concepten: set[str] = field(default_factory=set)
    ggz_product: dict | None = None
    contract_gemeenten: set[str] = field(default_factory=set)


@dataclass
class Bewijs:
    categorie: str
    veld: str
    tekst: str
    code: str = ""


@dataclass
class Treffer:
    id: str
    naam: str
    score: float
    reden: str
    rang: int
    aanbieder: dict
    breder: bool = False
    contracttoets: dict = field(default_factory=dict)
    ontbrekende_expertise: list[str] = field(default_factory=list)


def interpretatiefragmenten(tekst: str, concepten: list[str], ontkend: list[str], uitgesloten: list[str]) -> list[dict]:
    """Literal original-text evidence only; no diagnosis or semantic invention."""
    fragmenten = []
    bezet = set()
    for frase, cid in concept_frases():
        if cid not in set(concepten + ontkend + uitgesloten):continue
        for m in re.finditer(r"\b" + re.escape(frase) + r"\b", tekst, re.I):
            plekken = set(range(m.start(), m.end()))
            if plekken & bezet:continue
            bezet.update(plekken)
            mogelijk = bool(re.search(r"\b(?:vermoed\w*|mogelijk\w*)\s*$", tekst[:m.start()], re.I))
            fragmenten.append({'soort': 'hulpvraag', 'begrip': cid, 'tekst': m[0],
                              'begin': m.start(), 'einde': m.end(),
                              'polariteit': 'uitgesloten' if cid in uitgesloten else 'ontkend' if cid in ontkend else 'genoemd',
                              'zekerheid': 'mogelijk' if mogelijk else 'genoemd'})
    return sorted(fragmenten, key=lambda f: f['begin'])


def analyseer_vraag(tekst: str, plaatstabel: dict[str, str], bekende_codes: set[str]) -> Vraag:
    origineel = normaliseer(tekst)
    # Bewaar zinsgrenzen voor negatie; normalisatie zou ze anders wissen.
    # Bescherm numerieke decimalen vóór komma/punt als zinsgrens dient.
    beschermd = re.sub(r"(?<=\d)[,.](?=\d)", "decimal", tekst)
    werk = normaliseer(re.sub(r"[,;.!?]", " maar ", beschermd))
    werk = JAAR_IN_TEKST.sub(" ", werk)
    contract = None
    for patroon, status in CONTRACT_PATRONEN:
        if patroon.search(werk):
            contract = status
            werk = patroon.sub(" ", werk)
            break
    werk, regio = _strip_regio(werk)
    werk, ontkend, uitgesloten = splits_negaties(werk, concept_frases())

    leeftijd = None
    band = None
    leeftijd_label = ""
    leeftijden = []
    # First isolate ranges; they are not two separate children. Then collect
    # every person/age span, rather than stopping at the first singular match.
    bereik = LEEFTIJD_RANGE.search(werk)
    if bereik and 0 <= int(bereik[1]) <= int(bereik[2]) <= 120:
        band = (int(bereik[1]), int(bereik[2]))
        leeftijd_label = f"{band[0]}-{band[1]} jaar"
        werk = werk[:bereik.start()] + " " + werk[bereik.end():]
    else:
        nummer = r"\d{1,3}(?:decimal\d+)?"
        meervoud = re.compile(r"\b(?:kinderen|jongeren|pubers)\s+(?:van\s+|maar\s+)?(" + nummer +
                             r"(?:\s*(?:en|maar)\s*" + nummer + r")+)(?:\s*(?:jaar|jr))?\b")
        spans = []
        for m in meervoud.finditer(werk):
            ns = [float(n.replace("decimal", ".")) for n in re.findall(nummer, m[1])]
            if all(0 <= n <= 120 for n in ns):spans.append((m.start(), m.end(), ns))
        for patroon in (LEEFTIJD_PERSOON, LEEFTIJD_JAAR):
            for m in patroon.finditer(werk):
                if any(m.start() < eind and m.end() > begin for begin, eind, _ in spans):continue
                n = float(m[1].replace("decimal", "."))
                if 0 <= n <= 120:spans.append((m.start(), m.end(), [n]))
        for begin, eind, ns in sorted(spans):leeftijden.extend(ns)
        for begin, eind, _ in sorted(spans, reverse=True):werk = werk[:begin] + " " + werk[eind:]
        if leeftijden:
            band = (min(leeftijden), max(leeftijden))
            leeftijd = leeftijden[0] if len(leeftijden) == 1 else None
            leeftijd_label = " en ".join(f"{n:g}".replace(".", ",") for n in leeftijden) + " jaar"
    for patroon, grens, naam in _LEVEN:
        if not patroon.search(werk):
            continue
        if band is None:
            band = grens
            leeftijd_label = naam
        werk = patroon.sub(" ", werk)

    werk, codes = _vervang_codes(werk, bekende_codes)
    plaats_frases = [(naam, naam) for naam in sorted(plaatstabel, key=len, reverse=True)]
    _, plaats_hits = _vervang(werk, plaats_frases)
    plaatsen = _uniek(plaats_hits)
    gemeenten = _uniek([plaatstabel[naam] for naam in plaatsen if naam in plaatstabel])
    tokens = _uniek(codes + _tokeniseer(werk, plaatstabel, set()))
    concepten = _uniek([token[2:] for token in tokens if token.startswith("c_")])
    maximum = re.search(r"\b(?:maximaal|max|binnen|hooguit)\s+(\d+|een|twee|drie|vier)\s+(?:week|weken)\b", origineel)
    getallen = {"een": 1, "twee": 2, "drie": 3, "vier": 4}
    return Vraag(
        tekst=origineel,
        interpretatiefragmenten=interpretatiefragmenten(tekst, concepten, ontkend, uitgesloten),
        leeftijd=leeftijd,
        leeftijden=leeftijden or ([leeftijd] if leeftijd is not None else []),
        plaatsen=plaatsen,
        gemeenten=gemeenten,
        contract=contract,
        codes=codes,
        concepten=concepten,
        gender=_gender(origineel),
        regio_nijmegen=regio,
        tokens=tokens,
        leeftijdsband=band,
        leeftijd_label=leeftijd_label,
        ontkend=ontkend,
        uitgesloten=uitgesloten,
        op_datum=zoekdatum(tekst),
        max_wachttijd=(int(maximum[1]) if maximum[1].isdigit() else getallen[maximum[1]]) if maximum else None,
    )


class Index:
    """Zoekindex over één geladen document. Klein genoeg om bij elke start te bouwen."""

    def __init__(self, document: dict):
        self.bron_document = document
        from zorgzoeker.bewijs import Kwaliteitslezing
        document = Kwaliteitslezing(document).indexdocument(document)
        self.document = document
        self.contractregister = Contractregister(document)
        self.aanbieders = document.get("aanbieders") or []
        extra: set[str] = set()
        codes: set[str] = set()
        for aanbieder in self.aanbieders:
            for vestiging in _lijst(aanbieder.get("vestigingen", {})):
                if isinstance(vestiging, dict) and vestiging.get("plaats"):
                    extra.add(str(vestiging["plaats"]))
            for gebied in _lijst(aanbieder.get("werkgebied", {})):
                # Alleen echte plaatsnamen toevoegen, niet de vaste regiogzin.
                if isinstance(gebied, str):
                    sleutel = normaliseer(gebied)
                    if (
                        "rijk van nijmegen" in sleutel
                        or "contractgebied" in sleutel
                        or sleutel.startswith("onbekend")
                        or sleutel in {"landelijk", ""}
                    ):
                        continue
                    extra.add(gebied)
            for product in _lijst(aanbieder.get("productcodes", {})):
                if isinstance(product, dict) and product.get("code"):
                    codes.add(normaliseer(str(product["code"])))
        self.plaatstabel = maak_plaatstabel(extra)
        self.bekende_codes = codes
        self.catalogus = _productcatalogus()
        self.profielen = [self._profiel(aanbieder) for aanbieder in self.aanbieders]
        self._op_id = {profiel.id: profiel for profiel in self.profielen}
        self._concept_df: dict[str, int] = {}
        for profiel in self.profielen:
            for cid in profiel.bewijzen:
                self._concept_df[cid] = self._concept_df.get(cid, 0) + 1

    def _concept_idf(self, cid: str) -> float:
        df = self._concept_df.get(cid, 0)
        aantal = len(self.profielen) or 1
        return math.log(1 + (aantal - df + 0.5) / (df + 0.5))

    def _profiel(self, aanbieder: dict) -> Profiel:
        types = [str(item) for item in _lijst(aanbieder.get("type_aanbod", {}))]
        expertise = [str(item) for item in _lijst(aanbieder.get("expertise", {}))]
        doelgroepen = [str(item) for item in _lijst(aanbieder.get("doelgroepen", {}))]
        werkgebied = [str(item) for item in _lijst(aanbieder.get("werkgebied", {}))]
        producten = [
            item for item in _lijst(aanbieder.get("productcodes", {})) if isinstance(item, dict)
        ]
        vestigingen = [
            item for item in _lijst(aanbieder.get("vestigingen", {})) if isinstance(item, dict)
        ]
        vestiging_plaatsen = {
            normaliseer(str(item.get("plaats", "")))
            for item in vestigingen
            if item.get("plaats")
        }
        gebied_tekst, _ = _strip_regio(normaliseer(" ".join(werkgebied)))
        gebied_plaatsen = set(self._vind_plaatsen(gebied_tekst))
        for plaats in vestiging_plaatsen:
            gebied_plaatsen.update(self._vind_plaatsen(plaats))
        alle = {plaats for plaats in vestiging_plaatsen | gebied_plaatsen if plaats}
        gemeenten = {self.plaatstabel[plaats] for plaats in alle if plaats in self.plaatstabel}
        # Een losse werkgebiedsnaam die zelf een gemeente is, ook meetellen.
        for naam in werkgebied:
            sleutel = normaliseer(naam)
            if sleutel in self.plaatstabel:
                alle.add(sleutel)
                gemeenten.add(self.plaatstabel[sleutel])

        contract_veld = aanbieder.get("gecontracteerd_regio") or {}
        contract = str(contract_veld.get("waarde") or "onbekend")
        if contract not in {"ja", "nee", "onbekend"}:
            contract = "onbekend"
        expliciet = aanbieder.get("contractgemeenten")
        if isinstance(expliciet, dict):
            contract_gemeenten = {normaliseer(str(p)) for p in _lijst(expliciet)}
        elif contract == "ja" and normaliseer(str((self.document.get("meta") or {}).get("regio", ""))) == "rijk van nijmegen":
            # Regionaal contract is dekking, geen bewijs van een vestiging.
            contract_gemeenten = set(ROB_GEMEENTEN)
        else:
            contract_gemeenten = set()
        if self.contractregister.register:
            contract_gemeenten = {g for r in self.contractregister.per_id.get(aanbieder["id"], []) for g in r["gemeenten"]}

        naam = str((aanbieder.get("naam") or {}).get("waarde") or aanbieder.get("id"))
        product_tekst, product_voor_concept, ggz_product = self._productkanalen(producten)
        stukken = {
            "naam": naam,
            "type": " ".join(types),
            "expertise": " ".join(expertise),
            "doel": " ".join(doelgroepen),
            "gebied": " ".join(werkgebied),
            "plaats": " ".join(sorted(vestiging_plaatsen)),
            "product": product_tekst,
        }
        # Type en product wegen lager dan expertise van de eigen website.
        gewichten = {"naam": 1, "type": 1, "expertise": 3, "doel": 2, "gebied": 2, "plaats": 2, "product": 1}
        tokens: list[str] = []
        for sleutel, gewicht in gewichten.items():
            tokens.extend(_tokeniseer(stukken[sleutel], self.plaatstabel, self.bekende_codes) * gewicht)
        concepten = {token[2:] for token in tokens if token.startswith("c_")}
        code_tokens = {token for token in tokens if token.startswith("code_")}
        expertise_concepten = set(_concepten_in(" ".join(expertise)))
        type_concepten = set(_concepten_in(" ".join(types)))
        doel_bereiken = [(deel, leeftijdsgrenzen(deel)) for deel in doelgroepen]
        grenzen = [bereik for _tekst, reeksen in doel_bereiken for bereik in reeksen]
        leeftijd_tekst = next((deel for deel, reeksen in doel_bereiken if reeksen), "")
        if not leeftijd_tekst and grenzen:
            laag, hoog = grenzen[0]
            leeftijd_tekst = f"{laag}-{hoog} jaar"
        return Profiel(
            ruw=aanbieder,
            id=str(aanbieder.get("id")),
            naam=naam,
            contract=contract,
            code_tokens=code_tokens,
            producten=producten,
            concepten=concepten,
            vestiging_plaatsen=vestiging_plaatsen,
            alle_plaatsen=alle,
            gemeenten=gemeenten,
            leeftijden=grenzen,
            leeftijd_tekst=leeftijd_tekst,
            gender=_gender(" ".join(doelgroepen)),
            tokens=tokens,
            doelgroepen=doelgroepen,
            types=types,
            expertise=expertise,
            bewijzen=_bewijzen_uit(naam, expertise, doelgroepen, types, producten, self.catalogus),
            doel_bereiken=doel_bereiken,
            expertise_concepten=expertise_concepten,
            product_voor_concept=product_voor_concept,
            type_concepten=type_concepten,
            ggz_product=ggz_product,
            contract_gemeenten=contract_gemeenten,
        )

    def _productkanalen(self, producten: list[dict]) -> tuple[str, dict, dict | None]:
        """Omschrijving per code (eigen veld, anders de catalogus) en de ggz-code."""
        delen: list[str] = []
        per_concept: dict[str, dict] = {}
        ggz: list[dict] = []
        for product in producten:
            code = str(product.get("code") or "").strip()
            if not code:
                continue
            catalogus = self.catalogus.get(normaliseer(code)) or {}
            omschrijving = str(product.get("omschrijving") or catalogus.get("omschrijving") or "").strip()
            delen.append(f"{code} {omschrijving}")
            kaart = {"code": code, "omschrijving": omschrijving}
            for cid in _concepten_in(omschrijving):
                per_concept.setdefault(cid, kaart)
            if _is_ggz_code(code, omschrijving):
                ggz.append(kaart)
        gekozen = min(ggz, key=_ggz_rang) if ggz else None
        return " ".join(delen), per_concept, gekozen

    def _vind_plaatsen(self, tekst: str) -> list[str]:
        frases = [(naam, naam) for naam in sorted(self.plaatstabel, key=len, reverse=True)]
        _, hits = _vervang(normaliseer(tekst), frases)
        return hits

    def zoek(self, vraag: str, filters: Filters | None = None) -> list[Treffer]:
        filters = filters or Filters()
        analyse = analyseer_vraag(vraag, self.plaatstabel, self.bekende_codes)
        treffers = self._zoek_geanalyseerd(analyse, filters)
        if treffers or not analyse.concepten:
            return treffers
        kind_naar_ouder = {
            cid: BOVEN[cid] for cid in analyse.concepten if cid in BOVEN and BOVEN[cid] not in analyse.concepten
        }
        if not kind_naar_ouder:
            return []
        tokens: list[str] = []
        for token in analyse.tokens:
            if token.startswith("c_") and token[2:] in kind_naar_ouder:
                tokens.append("c_" + kind_naar_ouder[token[2:]])
            else:
                tokens.append(token)
        concepten = _uniek([token[2:] for token in tokens if token.startswith("c_")])
        boven = replace(analyse, tokens=_uniek(tokens), concepten=concepten)
        treffers = self._zoek_geanalyseerd(boven, filters)
        kinderen = _uniek([CONCEPT_LABEL.get(cid, cid) for cid in kind_naar_ouder])
        ouders = _uniek([CONCEPT_LABEL.get(cid, cid) for cid in kind_naar_ouder.values()])
        voorvoegsel = (
            f"Breder resultaat: geen treffer op {_opsomming(kinderen)}. "
            f"Gebruikt is de bovencategorie {_opsomming(ouders)}."
        )
        for treffer in treffers:
            treffer.breder = True
            treffer.reden = f"{voorvoegsel} {treffer.reden}"
        return treffers

    def meldingen(self, vraag: str, filters: Filters | None = None) -> list[str]:
        analyse = analyseer_vraag(vraag, self.plaatstabel, self.bekende_codes)
        meldingen = []
        if analyse.ontkend:
            meldingen.append("Niet als zorgwens gebruikt: " + ", ".join(CONCEPT_LABEL.get(c, c) for c in analyse.ontkend) + ".")
        if analyse.uitgesloten:
            meldingen.append("Aanbieders die de uitgesloten methode of zorgvorm noemen worden verborgen; andere mogelijkheden bij hen zijn niet vastgesteld.")
        if analyse.max_wachttijd is not None:
            meldingen.append(f"Alleen resultaten met een eenduidig gepubliceerde wachttijd van maximaal {analyse.max_wachttijd} weken. Onbekende of dienstafhankelijke wachttijden worden niet geschat; een publicatie is geen garantie op actuele instroom.")
        datum = (filters or Filters()).op_datum or analyse.op_datum
        peil = self.contractregister.register.get("peildatum")
        if datum and datum != peil:
            meldingen.append(f"Contractgeldigheid op {datum} niet vastgesteld. Een bron op {peil or 'onbekende datum'} bewijst geen geldigheidsperiode.")
        return meldingen

    def _contracttoets(self, profiel: Profiel, analyse: Vraag, filters: Filters) -> dict:
        plaats = filters.gemeente
        gemeente = self.plaatstabel.get(normaliseer(plaats), normaliseer(plaats)) if plaats else None
        codes = list(analyse.codes) + ([filters.productcode] if filters.productcode else [])
        toets = self.contractregister.oordeel(profiel.ruw, gemeente=gemeente, codes=codes,
                                            op_datum=filters.op_datum or analyse.op_datum)
        toets["gemeente"] = gemeente
        toets["op_datum"] = filters.op_datum or analyse.op_datum
        toets["beschikbaarheidsregels"] = relevante_regels(self.document, profiel.id, gemeente=gemeente,
            codes=codes, leeftijden=analyse.leeftijden, locatie=filters.vestigingsplaats)
        toets["alle_beschikbaarheidsregels"] = [r for r in self.document.get("beschikbaarheidsregister", []) if r["aanbieder_id"] == profiel.id]
        from zorgzoeker.beslissen import Beslisservice,Zoekcontext
        if not hasattr(self,'_beslisservice'):self._beslisservice=Beslisservice(self.bron_document,self)
        service=self._beslisservice
        context=Zoekcontext(gemeente,analyse.leeftijden,analyse.concepten,analyse.uitgesloten,filters.productcode,filters.op_datum or analyse.op_datum or date.today().isoformat(),service.versie,max_wachttijd=analyse.max_wachttijd,genoemde_plaatsen=analyse.plaatsen,gemeente_bevestigd=bool(filters.gemeente))
        toets['beoordeling']=service.beoordeel(profiel.id,filters=filters,analyse=analyse,context=context)
        return toets

    def contracttoets_voor(self, aanbieder_id: str, vraag: str = "", filters: Filters | None = None) -> dict:
        analyse = analyseer_vraag(vraag, self.plaatstabel, self.bekende_codes)
        return self._contracttoets(self._op_id[aanbieder_id], analyse, filters or Filters())

    def _inhoudelijke_dekking(self, profiel: Profiel, analyse: Vraag) -> tuple[bool, list[str]]:
        klinisch = set(analyse.concepten) & KLINISCH
        methoden = set(analyse.concepten) & BEHANDELMETHODEN
        klinisch_bewijs = {cid for cid, b in profiel.bewijzen.items() if b.veld in {"expertise", "doelgroepen", "type_aanbod"}}
        # Een generieke ggz-code of een organisatienaam bewijst geen stoornis.
        if methoden and not methoden.issubset(profiel.bewijzen):
            return False, []
        if klinisch and not methoden and not (klinisch & klinisch_bewijs):
            return False, []
        if analyse.concepten and not (set(analyse.concepten) & profiel.bewijzen.keys()):
            return False, []
        if analyse.codes and not set(analyse.codes).issubset(profiel.code_tokens):
            return False, []
        if not analyse.concepten and not analyse.codes:
            woorden = {t for t in analyse.tokens if not t.startswith("p_")}
            if not woorden.intersection(profiel.tokens):
                return False, []
        ontbreekt = [cid for cid in analyse.concepten
                     if cid not in (klinisch_bewijs if cid in KLINISCH | BEHANDELMETHODEN else profiel.bewijzen)]
        return True, ontbreekt

    def _zoek_geanalyseerd(self, analyse: Vraag, filters: Filters) -> list[Treffer]:
        namen = {p.id for p in self.profielen if self._naamvraag(analyse, p)}
        kandidaten = [profiel for profiel in self.profielen if self._past(profiel, filters)]
        kandidaten = [profiel for profiel in kandidaten
                      if not set(analyse.uitgesloten).intersection(profiel.bewijzen)]
        if analyse.leeftijdsband is not None:
            kandidaten = [profiel for profiel in kandidaten
                          if (all(leeftijd_oordeel(n, n, profiel.doel_bereiken)[0] != "buiten" for n in analyse.leeftijden)
                              if analyse.leeftijden else leeftijd_oordeel(*analyse.leeftijdsband, profiel.doel_bereiken)[0] != "buiten")]
        toetsen = {p.id: self._contracttoets(p, analyse, filters) for p in kandidaten}
        if analyse.max_wachttijd is not None:
            def wachtpast(p):
                regels = toetsen[p.id]["beschikbaarheidsregels"]
                if regels:
                    # Intake is geen start behandeling. Tegenstrijdige of oude
                    # bevestigingen worden niet vervangen door een gunstige publicatie.
                    return len(regels) == 1 and actueel(regels[0]) and regels[0]["start_behandeling_weken"] is not None and regels[0]["start_behandeling_weken"] <= analyse.max_wachttijd
                return _past_wachttijd(p.ruw.get("wachttijd"), analyse.max_wachttijd)
            kandidaten = [p for p in kandidaten if wachtpast(p)]
        contractwens = normaliseer(filters.gecontracteerd or analyse.contract or "").replace(" ", "_")
        if contractwens:
            def contractpast(p):
                toets = toetsen[p.id]
                bron = p.ruw.get("gecontracteerd_regio") or {}
                if contractwens == "bevestigd_nee":
                    return toets["status"] == "nee" and bron.get("label") == "geverifieerd"
                if contractwens == "niet_aangetroffen":
                    return toets["status"] == "nee" and bron.get("label") == "afgeleid"
                return toets["status"] == contractwens
            kandidaten = [p for p in kandidaten if contractpast(p)]
        contextplaats = filters.gemeente
        if contextplaats:
            contextplaats = self.plaatstabel.get(normaliseer(contextplaats), normaliseer(contextplaats))
        # Informatie op naam blijft opvraagbaar, maar een expliciet gestopte
        # route mag geen zorginhoudelijke aanbeveling worden.
        for p in kandidaten:
            toets = toetsen[p.id]
            algemeen = any(algemene_stop(p.ruw, contextplaats, filters.op_datum or analyse.op_datum, n, [] if toets["routes"] else list(analyse.codes) + ([filters.productcode] if filters.productcode else []))
                          for n in (analyse.leeftijden or [analyse.leeftijd]))
            toets["algemene_stop"] = algemeen
            toets["gemeente"] = contextplaats
            datum = filters.op_datum or analyse.op_datum
            stopdatum = date.fromisoformat(datum) if datum and len(datum) == 10 else date.today()
            registerstop = any(stop_actief(r, stopdatum) or (actueel(r, stopdatum) and r["nieuwe_clienten"] == "nee") for r in toets["beschikbaarheidsregels"])
            toets["stop_actief"] = algemeen or toets["toeleiding"] == "geblokkeerd" or registerstop
            if registerstop:
                toets["waarschuwingen"].append("Aanmeld-/toeleidingsstop of geen nieuwe cliënten in het beschikbaarheidsregister.")
            if algemeen:
                toets["waarschuwingen"].append("Aanmeldstop: nieuwe aanmeldingen zijn voor deze vraag niet mogelijk; controleer de bron.")
        kandidaten = [p for p in kandidaten if analyse.leeg() or p.id in namen or not toetsen[p.id]["stop_actief"]]
        if analyse.leeg():
            kandidaten.sort(key=lambda profiel: profiel.naam.lower())
            reden = (
                "Geen zoektekst. Dit zijn de aanbieders die aan de filters voldoen, op naam."
                if filters.actief()
                else "Geen zoektekst. Dit is het hele bestand, op naam."
            )
            return [
                Treffer(profiel.id, profiel.naam, 0.0, reden, rang, profiel.ruw, contracttoets=toetsen[profiel.id])
                for rang, profiel in enumerate(kandidaten, start=1)
            ]

        dekkingen = {p.id: ((True, []) if p.id in namen else self._inhoudelijke_dekking(p, analyse)) for p in kandidaten}
        kandidaten = [p for p in kandidaten if dekkingen[p.id][0]]

        # Gebruik één vaste corpusbasis. Anders maakt een toelatingsfilter
        # een unieke naam tot een te zwak zoekwoord zodra één kandidaat rest.
        scores = _bm25([p.tokens for p in self.profielen], analyse.tokens)
        per_id_score = {p.id: score for p, score in zip(self.profielen, scores)}
        treffers: list[Treffer] = []
        for profiel in kandidaten:
            tekstscore = per_id_score[profiel.id]
            score, reden = self._beoordeel(analyse, profiel, tekstscore, filters)
            if profiel.id in namen:
                score = max(score, 100.0)
                reden = "Gevonden op naam; dit is geen beoordeling van geschiktheid."
            toets = toetsen[profiel.id]
            if toets["status"] == "onbekend":
                reden += " Contractgeldigheid voor deze vraag is onbekend."
            if toets["waarschuwingen"]:
                reden += " Let op: controleer de vermelde contractvoorwaarden en bron."
            ontbreekt = dekkingen[profiel.id][1]
            if ontbreekt:
                reden += " Niet bevestigd in de bron: " + _opsomming([CONCEPT_LABEL.get(c, c) for c in ontbreekt]) + ". Dit is een gedeeltelijke match."
            treffers.append(Treffer(profiel.id, profiel.naam, score, reden, 0, profiel.ruw,
                                   contracttoets=toets, ontbrekende_expertise=ontbreekt))
        # Volledige dekking gaat ALTIJD vóór gedeeltelijke dekking: leeftijd,
        # plaats, gender en BM25 kunnen ontbrekende expertise niet compenseren.
        treffers.sort(key=lambda t: (bool(t.ontbrekende_expertise), len(t.ontbrekende_expertise), -round(t.score, 6), t.naam.lower()))
        # Zwakke teksttreffers verbergen. Een lege zoekvraag toont wel het hele bestand.
        treffers = [treffer for treffer in treffers if treffer.score >= 2.5][:40]
        for rang, treffer in enumerate(treffers, start=1):
            treffer.rang = rang
        return treffers

    @staticmethod
    def _naamvraag(analyse: Vraag, profiel: Profiel) -> bool:
        # Alleen een expliciete naam, nooit een willekeurige vrije tekstmatch.
        naam = normaliseer(profiel.naam).removeprefix("fictief - ").strip()
        vraag = analyse.tekst.removeprefix("fictief - ").strip()
        return bool(naam and (vraag == naam or vraag == normaliseer(profiel.id).replace("-", " ")))

    def op_id(self, aanbieder_id: str) -> dict | None:
        profiel = self._op_id.get(aanbieder_id)
        return profiel.ruw if profiel else None

    def filteropties(self) -> dict:
        plaatsen: set[str] = set()
        doelgroepen: set[str] = set()
        producten: dict[str, str] = {}
        for profiel in self.profielen:
            for plaats in profiel.alle_plaatsen | profiel.gemeenten:
                if plaats and plaats != "rijk van nijmegen":
                    plaatsen.add(plaats)
            doelgroepen.update(profiel.doelgroepen)
            for product in profiel.producten:
                code = str(product.get("code") or "").strip()
                if code:
                    producten[code] = str(product.get("omschrijving") or "")
        return {
            "plaatsen": sorted({mooie_plaats(self.plaatstabel.get(plaats, plaats)) for plaats in plaatsen | ROB_GEMEENTEN}, key=str.lower),
            "vestigingsplaatsen": sorted({mooie_plaats(p) for profiel in self.profielen for p in profiel.vestiging_plaatsen}),
            "doelgroepen": sorted(doelgroepen, key=str.lower),
            "productcodes": [
                {"code": code, "omschrijving": producten[code]}
                for code in sorted(producten, key=str.lower)
            ],
            "contracten": ["ja", "nee", "onbekend"],
        }

    def _past(self, profiel: Profiel, filters: Filters) -> bool:
        # Contractstatus wordt ná de gemeente/product/datumtoets gefilterd.
        # Een historisch 'ja' kan op een andere datum juist onbekend zijn.
        if filters.productcode and _code_token(filters.productcode) not in profiel.code_tokens:
            return False
        if filters.doelgroep:
            gezocht = normaliseer(filters.doelgroep)
            if not any(gezocht == normaliseer(deel) or gezocht in normaliseer(deel) for deel in profiel.doelgroepen):
                return False
        if filters.gemeente and not self._plaatsfilter(profiel, filters.gemeente):
            return False
        if filters.vestigingsplaats and not any(plaats_match(filters.vestigingsplaats, p) for p in profiel.vestiging_plaatsen):
            return False
        return True

    def _plaatsfilter(self, profiel: Profiel, naam: str) -> bool:
        sleutel = normaliseer(naam)
        gemeente = self.plaatstabel.get(sleutel, sleutel)
        if profiel.contract == "ja":
            return gemeente in profiel.contract_gemeenten
        # Een niet-gecontracteerde aanbieder kan wel een aantoonbaar werkgebied
        # hebben. Dit wordt nergens als contractdekking gepresenteerd.
        if any(plaats_match(sleutel, plaats) for plaats in profiel.alle_plaatsen):
            return True
        canon = self.plaatstabel.get(sleutel, sleutel)
        return canon in profiel.gemeenten or any(self.plaatstabel.get(p, p) == canon for p in profiel.alle_plaatsen)

    def _beoordeel(
        self,
        vraag: Vraag,
        profiel: Profiel,
        bm25: float,
        filters: Filters,
    ) -> tuple[float, str]:
        score = bm25
        # Alleen een categorie waarvan een synoniem echt in een veld staat.
        gevonden = [profiel.bewijzen[cid] for cid in vraag.concepten if cid in profiel.bewijzen]
        hoog = [bewijs for bewijs in gevonden if bewijs.veld in {"expertise", "doelgroepen", "naam"}]
        laag = [bewijs for bewijs in gevonden if bewijs.veld in {"type_aanbod", "productcodes"}]
        score += EXPERTISE_WEGING * len(hoog)
        if laag:
            score += AANBOD_WEGING
        for bewijs in gevonden:
            score += ZELDZAAMHEID * self._concept_idf(bewijs.categorie)

        product = next(
            (
                product
                for product in profiel.producten
                if _code_token(str(product.get("code", ""))) in vraag.codes
            ),
            None,
        )
        if product:
            score += 16

        exacte_plaats = None
        for gevraagd in vraag.plaatsen:
            for vestiging in profiel.vestiging_plaatsen:
                if plaats_match(gevraagd, vestiging):
                    exacte_plaats = gevraagd
                    break
            if exacte_plaats:
                break
        softe_plaats = None
        if exacte_plaats is None:
            for gevraagd in vraag.plaatsen:
                if any(plaats_match(gevraagd, plaats) for plaats in profiel.alle_plaatsen):
                    softe_plaats = gevraagd
                    break
                if gevraagd in vraag.gemeenten and self.plaatstabel.get(gevraagd, gevraagd) in profiel.gemeenten:
                    softe_plaats = gevraagd
                    break
            if softe_plaats is None:
                for gemeente in vraag.gemeenten:
                    if gemeente in profiel.gemeenten:
                        softe_plaats = gemeente
                        break
        if exacte_plaats:
            score += 8
        elif softe_plaats:
            score += 4.5
        if vraag.regio_nijmegen and "nijmegen" in profiel.gemeenten and not exacte_plaats:
            score += 2.2

        leeftijd_status = ""
        leeftijd_citaat = ""
        if vraag.leeftijdsband is not None:
            laag, hoog = vraag.leeftijdsband
            leeftijd_status, leeftijd_citaat = leeftijd_oordeel(laag, hoog, profiel.doel_bereiken)
            if len(vraag.leeftijden) > 1:
                oordelen = [leeftijd_oordeel(n, n, profiel.doel_bereiken) for n in vraag.leeftijden]
                leeftijd_status = "binnen" if all(s == "binnen" for s, _ in oordelen) else "onbekend"
                leeftijd_citaat = "; ".join(dict.fromkeys(c for _, c in oordelen if c))
            if leeftijd_status == "binnen":
                # Een expliciete jeugddoelgroep weegt zwaarder dan een
                # algemene vermelding 'alle leeftijden (0 tot 100+)'.
                passende = [eind - begin for _, reeksen in profiel.doel_bereiken
                            for begin, eind in reeksen if begin <= laag and hoog <= eind]
                score += 3.0 if passende and min(passende) > 30 else 4.5
            elif leeftijd_status == "buiten":
                score -= 9

        contract_match = False
        if vraag.contract:
            if profiel.contract == vraag.contract:
                contract_match = True
                score += 7
            elif profiel.contract != "onbekend":
                score -= 6

        # Een treffer die geen enkel gevraagd begrip dekt, mag niet winnen op alleen een plaats.
        if vraag.concepten and not gevonden and product is None:
            score -= 9

        gender_match = False
        if vraag.gender:
            if profiel.gender == vraag.gender:
                gender_match = True
                score += 4.5
            elif profiel.gender == "beide":
                gender_match = True
                score += 3.2
            elif profiel.gender:
                score -= 4

        reden = _reden(
            bewijzen=gevonden,
            product=product,
            leeftijd_status=leeftijd_status,
            leeftijd_citaat=leeftijd_citaat,
            leeftijd_label=vraag.leeftijd_label,
            exacte_plaats=exacte_plaats,
            softe_plaats=softe_plaats,
            plaatstabel=self.plaatstabel,
            regio=vraag.regio_nijmegen and "nijmegen" in profiel.gemeenten and not exacte_plaats,
            contract_match=contract_match,
            contract=("niet_aangetroffen" if profiel.contract == "nee" and (profiel.ruw.get("gecontracteerd_regio") or {}).get("label") == "afgeleid" else profiel.contract) if contract_match else None,
            gender_match=gender_match,
            gender=vraag.gender,
            filters=filters.actief(),
            bm25=bm25,
        )
        return score, reden


def _past_wachttijd(veld: dict | None, maximum: int) -> bool:
    if not isinstance(veld, dict) or _valideer_veld("wachttijd", "wachttijd", veld) or _valideer_wachttijd("zoek", {"wachttijd": veld}):
        return False
    if indicatieve_publicatie(veld) or wachttijd_verouderd(veld):
        return False
    tekst = normaliseer(str(veld.get("waarde", "")))
    if tekst == "geen wachtlijst":
        return True
    match = re.fullmatch(r"(?:\d+\s*-\s*)?(\d+)\s*(week|weken|dag|dagen)", tekst)
    if not match:
        return False
    weken = int(match[1]) / (7 if match[2].startswith("dag") else 1)
    return weken <= maximum


def _ggz_rang(product: dict) -> tuple:
    """Liever een JW 54-code, en daarvan de basisbehandeling, niet de groep."""
    sleutel = _code_sleutel(str(product.get("code") or ""))
    omschrijving = normaliseer(str(product.get("omschrijving") or ""))
    basis = 0 if "basis" in omschrijving and "groep" not in omschrijving else 1
    return (0 if sleutel.startswith("jw54") else 1, basis, sleutel)


def _unieke_producten(concepten: list[str], per_concept: dict) -> list[dict]:
    gezien: list[dict] = []
    codes: set[str] = set()
    for cid in concepten:
        product = per_concept.get(cid)
        if not product:
            continue
        code = str(product.get("code") or "")
        if code in codes:
            continue
        codes.add(code)
        gezien.append(product)
    return gezien


def _productzin(product: dict) -> str:
    code = product.get("code", "")
    omschrijving = str(product.get("omschrijving") or "").strip()
    if omschrijving:
        return f"Past via productcode {code} ({omschrijving})."
    return f"Past via productcode {code}."


def _bewijszin(bewijs: Bewijs) -> str:
    label = CONCEPT_LABEL.get(bewijs.categorie, bewijs.categorie)
    tekst = bewijs.tekst.strip()
    if bewijs.veld == "productcodes" and bewijs.code:
        if tekst:
            return f"Past via productcode {bewijs.code} ({tekst})."
        return f"Past via productcode {bewijs.code}."
    if bewijs.veld == "type_aanbod":
        return f"Sluit aan op {label}. Past via type aanbod: \"{tekst}\"."
    if bewijs.veld == "naam":
        return f"Sluit aan op {label}. Gevonden in de naam: \"{tekst}\"."
    veldnaam = "doelgroep" if bewijs.veld == "doelgroepen" else "expertise"
    return f"Sluit aan op {label}, gevonden in {veldnaam}: \"{tekst}\"."


def _reden(
    *,
    bewijzen: list[Bewijs],
    product: dict | None,
    leeftijd_status: str,
    leeftijd_citaat: str,
    leeftijd_label: str,
    exacte_plaats: str | None,
    softe_plaats: str | None,
    plaatstabel: dict[str, str],
    regio: bool,
    contract_match: bool,
    contract: str | None,
    gender_match: bool,
    gender: str | None,
    filters: bool,
    bm25: float,
) -> str:
    delen: list[str] = []
    for bewijs in bewijzen:
        delen.append(_bewijszin(bewijs))
    if product:
        code = product.get("code", "")
        omschrijving = product.get("omschrijving") or ""
        if omschrijving:
            delen.append(f"Heeft productcode {code} ({omschrijving}).")
        else:
            delen.append(f"Heeft productcode {code}.")
    if leeftijd_status == "binnen" and leeftijd_citaat:
        delen.append(f"Leeftijd {leeftijd_label} valt binnen de doelgroep ({leeftijd_citaat}).")
    elif leeftijd_status == "buiten" and leeftijd_citaat:
        delen.append(f"Let op: leeftijd {leeftijd_label} valt buiten de doelgroep ({leeftijd_citaat}).")
    elif leeftijd_status == "onbekend":
        delen.append("Let op: leeftijd niet te controleren.")
    if exacte_plaats:
        delen.append(f"Vestiging in {mooie_plaats(exacte_plaats)}.")
    elif softe_plaats:
        gemeente = plaatstabel.get(softe_plaats, softe_plaats)
        plaatsnaam = mooie_plaats(softe_plaats)
        gemeentenaam = mooie_plaats(gemeente)
        if gemeentenaam.lower() != plaatsnaam.lower():
            delen.append(f"Werkgebied omvat {plaatsnaam} (gemeente {gemeentenaam}).")
        else:
            delen.append(f"Werkgebied omvat de gemeente {plaatsnaam}.")
    elif regio:
        delen.append("Vestiging in de gemeente Nijmegen, binnen de gevraagde regio.")
    if contract_match and contract:
        if contract == "ja":
            delen.append("Staat als gecontracteerd door de regio.")
        elif contract == "nee":
            delen.append("Staat als niet gecontracteerd door de regio.")
        elif contract == "niet_aangetroffen":
            delen.append("Niet aangetroffen in de gebruikte contractlijst; contractstatus niet definitief vastgesteld.")
        else:
            delen.append("Contractstatus met de regio is onbekend.")
    if gender_match and gender in {"meisjes", "jongens"}:
        delen.append(f"Doelgroep noemt {gender}.")
    if filters:
        delen.append("Voldoet aan de gekozen filters.")
    if not delen:
        if bm25 > 0:
            delen.append("Beperkte tekstuele overeenkomst met de zoekvraag.")
        else:
            delen.append("Weinig overeenkomst met de zoekvraag.")
    return " ".join(delen)


def _opsomming(items: list[str]) -> str:
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} en {items[1]}"
    return ", ".join(items[:-1]) + " en " + items[-1]


def _bm25(documenten: list[list[str]], vraag: list[str], k1: float = 1.4, b: float = 0.65) -> list[float]:
    """BM25 over tokens. Lege vraag geeft nullen."""
    if not documenten:
        return []
    if not vraag:
        return [0.0] * len(documenten)
    aantal = len(documenten)
    documentfrequentie: dict[str, int] = {}
    for tokens in documenten:
        for token in set(tokens):
            documentfrequentie[token] = documentfrequentie.get(token, 0) + 1
    gem_lengte = sum(len(tokens) for tokens in documenten) / aantal or 1.0
    scores: list[float] = []
    for tokens in documenten:
        frequentie: dict[str, int] = {}
        for token in tokens:
            frequentie[token] = frequentie.get(token, 0) + 1
        lengte = len(tokens) or 1
        score = 0.0
        for token in dict.fromkeys(vraag):
            if token not in frequentie:
                continue
            df = documentfrequentie.get(token, 0)
            idf = math.log(1 + (aantal - df + 0.5) / (df + 0.5))
            tf = frequentie[token]
            score += idf * (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * lengte / gem_lengte))
        scores.append(score)
    return scores


def zoek(document: dict, vraag: str, filters: Filters | None = None) -> list[Treffer]:
    return Index(document).zoek(vraag, filters)
