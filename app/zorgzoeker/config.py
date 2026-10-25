"""Paden en instellingen. Geen netwerk, geen geheimen."""

from __future__ import annotations

import os
from pathlib import Path

# Pakket staat in <root>/zorgzoeker; data staat in <root>/data.
PROJECT_ROOT = Path(__file__).resolve().parent.parent

STANDAARD_POORT = 8741


def data_pad() -> Path:
    """Welk aanbiedersbestand geladen wordt.

    Voorrang:
    1. omgevingsvariabele ZORGZOEKER_DATA
    2. data/aanbieders.json als dat bestand bestaat (echte dataset)
    3. data/fixture_aanbieders.json (fictieve demo)
    """
    omgeving = os.environ.get("ZORGZOEKER_DATA", "").strip()
    if omgeving:
        return Path(omgeving).expanduser().resolve()
    echt = PROJECT_ROOT / "data" / "aanbieders.json"
    if echt.exists():
        return echt
    return PROJECT_ROOT / "data" / "fixture_aanbieders.json"


def poort() -> int:
    ruw = os.environ.get("ZORGZOEKER_POORT", "").strip()
    if not ruw:
        return STANDAARD_POORT
    return int(ruw)


def host() -> str:
    return os.environ.get("ZORGZOEKER_HOST", "127.0.0.1").strip() or "127.0.0.1"
