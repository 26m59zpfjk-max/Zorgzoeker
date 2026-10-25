"""Regressie: openbare ROB-toeleidingsstops bij onderaannemers blijven zichtbaar.

Bron: Totaaloverzicht-gecontracteerde-aanbieders-23okt26.xlsx,
tabblad Onderaannemers 2026, rijen 80-82 en 280-282.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from zorgzoeker.app import maak_app


@pytest.mark.parametrize("aanbieder_id", ["alkazorg", "apollis-zorg"])
def test_onderaannemer_toont_gepubliceerde_toeleidingsstop(aanbieder_id: str) -> None:
    pad = Path(__file__).resolve().parents[1] / "data" / "aanbieders.json"
    client = TestClient(maak_app(pad))
    antwoord = client.get("/api/zoek", params={"q": aanbieder_id.replace("-", " ")})
    assert antwoord.status_code == 200
    treffer = next(item for item in antwoord.json()["resultaten"] if item["id"] == aanbieder_id)
    veld = treffer["beschikbaarheid"]
    assert "toeleidingsstop" in veld["tekst"].lower()
    assert "Nijmegen" in veld["tekst"]
    for code in ("JW 45A04", "JW 45A05", "JW 45A49"):
        assert code in veld["tekst"]
    assert veld["label"] == "geverifieerd"
    assert veld["bron_url"].endswith("Totaaloverzicht-gecontracteerde-aanbieders-23okt26.xlsx")
    assert "Peildatum: 2026-10-23" in veld["toelichting"]
    pagina = client.get("/", params={"q": aanbieder_id.replace("-", " ")})
    assert "toeleidingsstop" in pagina.text.lower()

