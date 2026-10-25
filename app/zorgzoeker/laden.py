"""JSON-dataset inlezen. Het bestandspad komt uit de configuratie."""

from __future__ import annotations

import json
from pathlib import Path

from zorgzoeker.config import data_pad


def laad_document(pad: Path | None = None) -> dict:
    """Lees een aanbiedersbestand. Geeft het ruwe object terug."""
    bron = Path(pad) if pad is not None else data_pad()
    if not bron.exists():
        raise FileNotFoundError(f"Aanbiedersbestand niet gevonden: {bron}")
    with bron.open(encoding="utf-8") as bestand:
        inhoud = json.load(bestand)
    if not isinstance(inhoud, dict):
        raise ValueError("Het aanbiedersbestand moet een JSON-object zijn.")
    return inhoud


def aanbieders_uit(document: dict) -> list[dict]:
    lijst = document.get("aanbieders")
    if not isinstance(lijst, list):
        return []
    return lijst
