"""Herhaal de twintig oorspronkelijke auditvragen; rapporteer zonder cliëntdata.

Gebruik vanuit app: python scripts/evalueer_audit.py [uitvoer.json]
De formele veiligheidsasserties staan in tests/test_audit_scenarios.py.
"""

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from zorgzoeker.laden import laad_document
from zorgzoeker.zoeken import Index


def main():
    index = Index(laad_document(ROOT / "data/aanbieders.json"))
    vragen = json.loads((ROOT / "tests/audit_scenarios.json").read_text())
    uitkomsten = []
    for s in vragen:
        treffers = index.zoek(s["vraag"])
        uitkomsten.append({"id": s["id"], "vraag": s["vraag"],
                          "eerder_aantal": s["eerder_aantal"], "eerder_eerste": s["eerder_eerste"],
                          "aantal": len(treffers), "volledige_matches": sum(not t.ontbrekende_expertise for t in treffers),
                          "waarschuwingen": index.meldingen(s["vraag"]),
                          "eerste_vijf": [{"id": t.id, "reden": t.reden, "ontbrekende_expertise": t.ontbrekende_expertise,
                                           "contractstatus": t.contracttoets["status"]} for t in treffers[:5]]})
    pad = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "audit-hertest.json"
    pad.write_text(json.dumps(uitkomsten, ensure_ascii=False, indent=2) + "\n")
    print(f"20 oorspronkelijke auditvragen opnieuw uitgevoerd: {pad}")


if __name__ == "__main__":
    main()
