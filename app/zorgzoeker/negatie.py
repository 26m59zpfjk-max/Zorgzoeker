"""Begrensde Nederlandse negatieherkenning; geen diagnose-inferentie."""

import re


METHODEN = frozenset({"medicatie", "emdr", "dagbesteding", "logeer", "residentieel", "pleegzorg", "gezinshuis", "speltherapie"})


def splits_negaties(tekst: str, frases: list[tuple[str, str]]) -> tuple[str, list[str], list[str]]:
    """Verwijder ontkende begrippen uit de zoektekst, bewaar de overige woorden.

    'Geen autisme vastgesteld' is geen reden om een aanbieder die óók ASS
    behandelt uit te sluiten. Een expliciet ongewenste methode wordt wel een
    uitsluitfilter. Bij 'niet alleen' wordt niets ontkend. De langste frases
    blijven intact: 'niet meer naar school' en 'kan zich niet concentreren'
    zijn positieve zorgsignalen.
    """
    bezet: set[int] = set()
    hits = []
    for frase, cid in frases:
        for m in re.finditer(rf"\b{re.escape(frase)}\b", tekst):
            posities = set(range(m.start(), m.end()))
            if posities & bezet:
                continue
            bezet.update(posities)
            hits.append((m.start(), m.end(), cid))
    ontkend, uitgesloten = [], []
    stukken, cursor = [], 0
    for start, eind, cid in sorted(hits):
        # Negatie strekt zich uit over 'en/of', maar niet over een nieuwe
        # bijzin of een nieuwe hulpvraag ('voor trauma', 'maar angst').
        prefix = list(tekst[:start])
        for begin, einde, _ in hits:
            if einde <= start:
                prefix[begin:einde] = " " * (einde - begin)
                # 'EMDR niet gewenst' hoort bij EMDR, niet bij het volgende
                # begrip ('bij trauma', 'en angst', ...).
                achter = re.match(r"\s+(?:is\s+)?niet\s+(?:gewenst|vastgesteld|nodig|aangetoond)\b", tekst[einde:start])
                if achter:
                    prefix[einde:einde + achter.end()] = " " * achter.end()
        voor = re.split(r"[,;.!?]|\b(?:maar|echter|wel|voor|vanwege|met|bij)\b", "".join(prefix))[-1]
        voor = re.sub(r"\bniet alleen\b", "", voor)
        na = tekst[eind:eind + 45]
        negatief = bool(re.search(r"\b(?:geen|zonder|niet)\b", voor) or
                        re.match(r"\s+(?:is\s+)?niet\s+(?:gewenst|vastgesteld|nodig|aangetoond)", na))
        if not negatief:
            continue
        ontkend.append(cid)
        if cid in METHODEN and not re.match(r"\s+(?:is\s+)?(?:niet\s+)?vastgesteld", na):
            uitgesloten.append(cid)
        stukken.extend([tekst[cursor:start], " "])
        cursor = eind
    stukken.append(tekst[cursor:])
    return "".join(stukken), list(dict.fromkeys(ontkend)), list(dict.fromkeys(uitgesloten))
