"""Synoniemen en plaatsnamen voor jeugdhulp in het Rijk van Nijmegen.

Begrippen staan in data/begrippen.yaml. Plaatsnamen staan hier.
Alles blijft lokaal: een vaste lijst, geen externe dienst.
"""

from __future__ import annotations

from pathlib import Path

import yaml

_BEGIN = Path(__file__).resolve().parent.parent / "data" / "begrippen.yaml"


def _laad_begrippen() -> tuple[tuple[tuple[str, str, tuple[str, ...]], ...], dict[str, str]]:
    ruw = yaml.safe_load(_BEGIN.read_text(encoding="utf-8"))
    concepten = []
    boven: dict[str, str] = {}
    for item in ruw:
        frases = tuple(str(frase) for frase in item["frases"])
        concepten.append((str(item["id"]), str(item["label"]), frases))
        if item.get("boven"):
            boven[str(item["id"])] = str(item["boven"])
    return tuple(concepten), boven


CONCEPTEN, BOVEN = _laad_begrippen()

# Kern of gemeente -> gemeente. Langere namen worden eerst gezocht.
KERN_NAAR_GEMEENTE: dict[str, str] = {
    "berg en dal": "berg en dal",
    "groesbeek": "berg en dal",
    "ubbergen": "berg en dal",
    "beek": "berg en dal",
    "ooij": "berg en dal",
    "leuth": "berg en dal",
    "erlecom": "berg en dal",
    "kekerdom": "berg en dal",
    "persingen": "berg en dal",
    "millingen aan de rijn": "berg en dal",
    "millingen": "berg en dal",
    "breedeweg": "berg en dal",
    "de horst": "berg en dal",
    "heilig landstichting": "berg en dal",
    "heumen": "heumen",
    "malden": "heumen",
    "overasselt": "heumen",
    "nederasselt": "heumen",
    "mook en middelaar": "mook en middelaar",
    "middelaar": "mook en middelaar",
    "molenhoek": "mook en middelaar",
    "plasmolen": "mook en middelaar",
    "mook": "mook en middelaar",
    "wijchen": "wijchen",
    "alverna": "wijchen",
    "balgoij": "wijchen",
    "batenburg": "wijchen",
    "bergharen": "wijchen",
    "hernen": "wijchen",
    "niftrik": "wijchen",
    "woezik": "wijchen",
    "leur": "wijchen",
    "beuningen": "beuningen",
    "ewijk": "beuningen",
    "winssen": "beuningen",
    "weurt": "beuningen",
    "druten": "druten",
    "afferden": "druten",
    "deest": "druten",
    "horssen": "druten",
    "puiflijk": "druten",
    "nijmegen-noord": "nijmegen",
    "nijmegen noord": "nijmegen",
    "nijmegen": "nijmegen",
    "lent": "nijmegen",
    "elst": "overbetuwe",
    "arnhem": "arnhem",
    "dukenburg": "nijmegen",
    "lindenholt": "nijmegen",
    "hatert": "nijmegen",
    "bottendaal": "nijmegen",
    "oosterhout": "nijmegen",
}

STOPWOORDEN = {
    "de",
    "het",
    "een",
    "van",
    "met",
    "in",
    "voor",
    "en",
    "of",
    "op",
    "te",
    "die",
    "dat",
    "aan",
    "bij",
    "tot",
    "naar",
    "uit",
    "is",
    "zijn",
    "wordt",
    "als",
    "ook",
    "om",
    "maar",
    "over",
    "per",
    "na",
    "wel",
    "deze",
    "dit",
    "er",
    "al",
    "dan",
    "nog",
    "door",
    "onder",
    "zonder",
    "binnen",
    "naast",
    "tussen",
    "via",
    "niet",
    "geen",
    "haar",
    "hun",
    "ons",
    "onze",
    "jaar",
    "jarige",
    "jarigen",
    "leeftijd",
    "jongen",
    "jongens",
    "meisje",
    "meisjes",
    "kind",
    "kinderen",
    "jongere",
    "jongeren",
    "regio",
    "hulp",
    "jeugdhulp",
    "zorg",
    "zorgvraag",
    "aanbieder",
    "aanbieders",
    "fictief",
    "productcode",
    "product",
    "code",
    "graag",
    "nodig",
    "moet",
    "kan",
    "passend",
    "passende",

    "puber",
    "pubers",
    "tiener",
    "tieners",
    "peuter",
    "peuters",
    "kleuter",
    "kleuters",
    "baby",
    "babys",
    "dreumes",
    "zoon",
    "dochter",
    "moeder",
    "vader",
    "ouders",
    "ouder",
    "zich",
    "heeft",
    "hebben",
    "bijna",
    "niets",
    "meer",
    "hele",
    "nacht",
    "slecht",
    "moeilijk",
    "gaat",
}


CONCEPT_LABEL = {cid: label for cid, label, _frases in CONCEPTEN}


def concept_frases() -> list[tuple[str, str]]:
    """(frase, concept-id), langste frase eerst."""
    paren = [(frase, cid) for cid, _label, frases in CONCEPTEN for frase in frases]
    paren.extend([("medicatie", "medicatie"), ("medicamenteuze behandeling", "medicatie")])
    paren.sort(key=lambda paar: len(paar[0]), reverse=True)
    return paren
