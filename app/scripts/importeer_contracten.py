"""Importeer alleen exacte naam-/productmatches uit de openbare ROB-werkmap.

Gebruik vanuit app: python scripts/importeer_contracten.py overzicht.xlsx
Geen netwerkverkeer, fuzzy naamkoppelingen of afgeleide contractperiodes.
"""

import argparse
import hashlib
import json
from pathlib import Path
import re
import unicodedata
import xml.etree.ElementTree as ET
import zipfile

BRON = "https://robregionijmegen.nl/wp-content/uploads/2026/10/Totaaloverzicht-gecontracteerde-aanbieders-23okt26.xlsx"
NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
GEMEENTEN = ["berg en dal", "beuningen", "druten", "heumen", "mook en middelaar", "nijmegen", "wijchen"]


def sleutel(tekst):
    return re.sub(r"[^a-z0-9]", "", unicodedata.normalize("NFKD", tekst).encode("ascii", "ignore").decode().lower())


def lees_rijen(pad):
    with zipfile.ZipFile(pad) as z:
        strings = ["".join(s.itertext()) for s in ET.fromstring(z.read("xl/sharedStrings.xml"))]
        namen = {2: "Ambulant en GGZ 2026", 3: "JBJR 2026", 4: "Specialistische Jeugdhulp 2026", 8: "Onderaannemers 2026"}
        rijen = []
        for nummer, naam in namen.items():
            for row in ET.fromstring(z.read(f"xl/worksheets/sheet{nummer}.xml")).findall(".//m:row", NS):
                waarden = {}
                for cel in row.findall("m:c", NS):
                    v = cel.find("m:v", NS)
                    s = v.text if v is not None else ""
                    if cel.get("t") == "s" and s:
                        s = strings[int(s)]
                    waarden[re.sub(r"\d", "", cel.get("r"))] = (s or "").strip()
                if int(row.get("r")) > 2 and waarden.get("A") and waarden.get("C"):
                    rijen.append({**waarden, "tabblad": naam, "rij": int(row.get("r")), "sub": nummer == 8})
    return rijen


def importeer(pad, document):
    rijen = lees_rijen(pad)
    regels = []
    for a in document["aanbieders"]:
        naam = sleutel(a["naam"]["waarde"])
        codes = {sleutel(p["code"]).removeprefix("jw"): p["code"] for p in a["productcodes"]["waarde"]}
        for r in rijen:
            if sleutel(r.get("E" if r["sub"] else "A", "")) != naam:
                continue
            code = sleutel(r["C"]).removeprefix("jw")
            if code not in codes:
                continue
            opmerkingen = [r.get("F" if r["sub"] else "E", "")]
            bewijzen = [{"tabblad": r["tabblad"], "rij": r["rij"]}]
            if r["sub"]:
                for h in rijen:
                    if not h["sub"] and sleutel(h["A"]) == sleutel(r["A"]) and sleutel(h["C"]).removeprefix("jw") == code:
                        if h.get("E"):
                            opmerkingen.append(h["E"])
                            bewijzen.append({"tabblad": h["tabblad"], "rij": h["rij"]})
            regels.append({"aanbieder_id": a["id"], "productcode": codes[code],
                           "hoofdaannemer": r["A"] if r["sub"] else None,
                           "gemeenten": GEMEENTEN,
                           "opmerkingen": list(dict.fromkeys(t for t in opmerkingen if t)),
                           "bewijs": bewijzen})
    document["contractregister"] = {
        "bron_url": BRON, "peildatum": "2026-10-23", "opgehaald_op": "2026-10-25",
        "sha256": hashlib.sha256(Path(pad).read_bytes()).hexdigest(),
        "gemeenten_bron": "https://robregionijmegen.nl/over-ons/",
        "toelichting": "Exacte naam- en productmatches. Peildatum is de publicatiedatum van dit overzicht, geen contractperiode. Ontbrekende routes blijven onbekend.",
        "regels": regels,
    }
    return document


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("werkmap", type=Path)
    parser.add_argument("--dataset", type=Path, default=Path(__file__).resolve().parents[1] / "data/aanbieders.json")
    args = parser.parse_args()
    doc = importeer(args.werkmap, json.loads(args.dataset.read_text()))
    args.dataset.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n")
    print(f"{len(doc['contractregister']['regels'])} bronregels geïmporteerd.")
