"""Offline workflow: schrijft uitsluitend naar een nieuw opgegeven uitvoerbestand.

Start vanuit app/: python scripts/beschikbaarheidsworkflow.py --help
Geen verzendfunctie, geen netwerk, geen automatische vervanging van brondata.
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from zorgzoeker.beschikbaarheid import conceptverzoek, keur_verzoek_goed, neem_op, voorstel, verouderde_regels
from zorgzoeker.valideer import valideer_document


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("actie", choices=["signaleer", "concept", "keur-verzoek", "voorstel", "neem-op"])
    parser.add_argument("document", type=Path)
    parser.add_argument("--regel-id")
    parser.add_argument("--invoer", type=Path, help="JSON-regel, conceptverzoek of wijzigingsvoorstel")
    parser.add_argument("--uitvoer", type=Path, required=True, help="Nieuw bestand; bestaande bestanden worden nooit overschreven")
    parser.add_argument("--beoordelaar", default="")
    parser.add_argument("--expliciet-goedgekeurd", action="store_true")
    args = parser.parse_args()
    document = json.loads(args.document.read_text())
    fouten = valideer_document(document)
    if fouten:
        parser.error("; ".join(fouten))
    invoer = json.loads(args.invoer.read_text()) if args.invoer else None
    try:
        if args.actie == "signaleer":
            resultaat = verouderde_regels(document)
        elif args.actie == "concept":
            resultaat = conceptverzoek(document, args.regel_id)
        elif args.actie == "keur-verzoek":
            resultaat = keur_verzoek_goed(invoer, beoordelaar=args.beoordelaar, expliciet=args.expliciet_goedgekeurd)
        elif args.actie == "voorstel":
            resultaat = voorstel(document, invoer)
        else:
            resultaat = neem_op(document, invoer, beoordelaar=args.beoordelaar, expliciet=args.expliciet_goedgekeurd)
            fouten = valideer_document(resultaat)
            if fouten:
                raise ValueError("; ".join(fouten))
        with args.uitvoer.open("x", encoding="utf-8") as f:
            json.dump(resultaat, f, ensure_ascii=False, indent=2)
            f.write("\n")
    except (ValueError, KeyError, TypeError, StopIteration, FileExistsError) as exc:
        parser.error(f"Geen uitvoer geschreven: {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    main()
