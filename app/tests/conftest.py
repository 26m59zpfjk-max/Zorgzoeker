"""Gedeelde paden. ZORGZOEKER_DATA wijst in tests standaard naar de fixture."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "data" / "fixture_aanbieders.json"
DATASET = ROOT / "data" / "aanbieders.json"

os.environ.setdefault("ZORGZOEKER_DATA", str(FIXTURE))


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--aanbieders",
        action="store",
        default=None,
        help="Pad naar een aanbieders.json voor de validatie- en wachttijdtests.",
    )


@pytest.fixture(scope="session")
def fixture_pad() -> Path:
    return FIXTURE


@pytest.fixture(scope="session")
def aanbieders_pad(request: pytest.FixtureRequest) -> Path:
    """Fixture, tenzij pytest --aanbieders een ander bestand meegeeft."""
    optie = request.config.getoption("--aanbieders")
    if optie:
        return Path(optie)
    return FIXTURE


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    """Validatie draait altijd tegen de fixture én de echte dataset."""
    if "te_valideren_pad" not in metafunc.fixturenames:
        return
    paden = [FIXTURE, DATASET]
    extra = metafunc.config.getoption("--aanbieders")
    if extra:
        paden.append(Path(extra))
    uniek: list[Path] = []
    for pad in paden:
        if pad not in uniek:
            uniek.append(pad)
    metafunc.parametrize("te_valideren_pad", uniek, ids=[pad.name for pad in uniek])
