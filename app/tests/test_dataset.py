"""De meegeleverde dataset moet zelf door de validatie komen."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from zorgzoeker.app import maak_app
from zorgzoeker.laden import laad_document
from zorgzoeker.valideer import valideer_pad

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "data" / "aanbieders.json"


def test_definitieve_dataset_is_geldig() -> None:
    assert DATASET.exists()
    fouten = valideer_pad(DATASET)
    assert fouten == [], "\n".join(fouten)
    document = laad_document(DATASET)
    aanbieders = document["aanbieders"]
    assert len(aanbieders) == 189
    niet = sum(1 for aanbieder in aanbieders if aanbieder["gecontracteerd_regio"]["waarde"] == "nee")
    assert niet == 21
    met_expertise = sum(
        1
        for aanbieder in aanbieders
        if isinstance(aanbieder["expertise"]["waarde"], list) and aanbieder["expertise"]["waarde"]
    )
    assert met_expertise == 130
    assert (ROOT / "data" / "producten.json").exists()


def test_cli_op_definitieve_dataset() -> None:
    resultaat = subprocess.run(
        [sys.executable, "-m", "zorgzoeker.valideer", str(DATASET)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert resultaat.returncode == 0, resultaat.stdout + resultaat.stderr


def test_interface_op_definitieve_dataset() -> None:
    client = TestClient(maak_app(DATASET))
    gezondheid = client.get("/gezondheid")
    assert gezondheid.status_code == 200
    assert gezondheid.json()["aanbieders"] == 189
    antwoord = client.get("/", params={"q": "AlkaZorg"})
    assert antwoord.status_code == 200
    assert "Gecontracteerd als onderaannemer van Vooruit met zorg" in antwoord.text
    assert "onderaannemer van Vooruit met zorg · afgeleid" not in antwoord.text
    vergelijking = client.get("/vergelijken", params=[("ids", "alkazorg"), ("ids", "0-tot-18")])
    assert vergelijking.status_code == 200
    assert "Gecontracteerd als onderaannemer van Vooruit met zorg" in vergelijking.text
