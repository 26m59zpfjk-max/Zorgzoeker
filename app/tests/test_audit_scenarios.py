"""De twintig fictieve auditvragen blijven ongewijzigd; eisen komen uit de audit."""

import json
from pathlib import Path

import pytest

from zorgzoeker.laden import laad_document
from zorgzoeker.zoeken import Index, analyseer_vraag


VRAGEN = json.loads((Path(__file__).parent / "audit_scenarios.json").read_text())


@pytest.fixture(scope="module")
def index():
    return Index(laad_document(Path(__file__).resolve().parents[1] / "data/aanbieders.json"))


@pytest.mark.parametrize("scenario", VRAGEN, ids=[f"audit-{s['id']:02d}" for s in VRAGEN])
def test_onafhankelijk_auditscenario(index, scenario):
    analyse = analyseer_vraag(scenario["vraag"], index.plaatstabel, index.bekende_codes)
    treffers = index.zoek(scenario["vraag"])
    controle = scenario["controle"]
    ids = [t.id for t in treffers]
    for sleutel in ("leeftijd", "max_wachttijd", "op_datum"):
        if sleutel in controle:
            assert getattr(analyse, sleutel) == controle[sleutel]
    for sleutel in ("concepten", "ontkend", "uitgesloten"):
        if sleutel in controle:
            assert getattr(analyse, sleutel) == controle[sleutel]
    if controle.get("leeg"):
        assert not treffers
        assert index.meldingen(scenario["vraag"])
        return
    assert treffers, scenario["vraag"]
    assert not set(controle.get("verboden", [])) & set(ids)
    assert set(controle.get("aanwezig", [])) <= set(ids)
    if "alleen" in controle:
        assert set(ids) == set(controle["alleen"])
    if "eerste" in controle:
        assert ids[0] == controle["eerste"]
    if "contract" in controle:
        assert all(t.contracttoets["status"] == controle["contract"] for t in treffers)
    if "vereiste_dekking" in controle:
        assert not set(controle["vereiste_dekking"]) & set(treffers[0].ontbrekende_expertise)
    # Ook lagere resultaten mogen niet stilzwijgend volledige dekking claimen.
    gedeeltelijk_gezien = False
    for treffer in treffers:
        if treffer.ontbrekende_expertise:
            gedeeltelijk_gezien = True
            assert "Niet bevestigd in de bron" in treffer.reden
        else:
            assert not gedeeltelijk_gezien
