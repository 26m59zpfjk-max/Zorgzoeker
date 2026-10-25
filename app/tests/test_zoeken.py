"""Rangschikking op de fixture. Verwachte treffers staan in zoekvragen.yaml."""

from __future__ import annotations

from pathlib import Path

import yaml

from zorgzoeker.laden import laad_document
from zorgzoeker.zoeken import Index

VERBODEN = ("ongeveer", "circa", "geschat", "schatting", "naar schatting")


def test_minstens_vijftien_zoekvragen() -> None:
    vragen = yaml.safe_load((Path(__file__).parent / "zoekvragen.yaml").read_text(encoding="utf-8"))
    assert len(vragen) >= 15


def test_verwachte_eerste_treffer(fixture_pad: Path) -> None:
    vragen = yaml.safe_load((Path(__file__).parent / "zoekvragen.yaml").read_text(encoding="utf-8"))
    index = Index(laad_document(fixture_pad))
    for vraag in vragen:
        treffers = index.zoek(vraag["vraag"])
        assert treffers, vraag["id"]
        assert treffers[0].id == vraag["verwacht_eerste"], (
            f"{vraag['id']}: verwacht {vraag['verwacht_eerste']}, "
            f"kreeg {treffers[0].id} ({treffers[0].naam})"
        )
        assert treffers[0].reden.strip()
        laag = treffers[0].reden.lower()
        assert not any(woord in laag for woord in VERBODEN)


def test_verwachte_eerste_treffer_echte_dataset() -> None:
    pad = Path(__file__).resolve().parents[1] / "data" / "aanbieders.json"
    vragen = yaml.safe_load((Path(__file__).parent / "zoekvragen_dataset.yaml").read_text(encoding="utf-8"))
    assert len(vragen) >= 15
    index = Index(laad_document(pad))
    bekende_ids = {aanbieder["id"] for aanbieder in laad_document(pad)["aanbieders"]}
    for vraag in vragen:
        assert vraag["verwacht_eerste"] in bekende_ids
        treffers = index.zoek(vraag["vraag"])
        assert treffers, vraag["id"]
        assert treffers[0].id == vraag["verwacht_eerste"], (
            f"{vraag['id']}: verwacht {vraag['verwacht_eerste']}, kreeg {treffers[0].id}"
        )
        assert treffers[0].reden.strip()


def test_smetvrees_en_dwang_in_gewone_taal() -> None:
    index = Index(laad_document(_dataset()))
    for vraag in ("smetvrees", "meisje met dwangstoornis"):
        treffers = index.zoek(vraag)
        assert treffers, vraag
        assert treffers[0].id == "stichting-pro-persona-ggz"
        assert "dwangstoornissen" in treffers[0].reden
        assert "Breder resultaat" not in treffers[0].reden


def test_meisje_is_geen_zoekwoord() -> None:
    from zorgzoeker.zoeken import analyseer_vraag

    document = laad_document(_dataset())
    index = Index(document)
    analyse = analyseer_vraag("meisje met dwangstoornis", index.plaatstabel, index.bekende_codes)
    assert "meisje" not in analyse.tokens
    treffers = index.zoek("meisje met dwangstoornis")
    assert treffers
    tekst = " ".join(treffers[0].aanbieder["expertise"]["waarde"]).lower()
    assert "meisje" not in tekst
    assert "dwangstoornissen" in treffers[0].reden


def test_leeftijd_14_valt_niet_binnen_0_12() -> None:
    from zorgzoeker.zoeken import leeftijd_oordeel

    binnen, citaat = leeftijd_oordeel(
        14,
        14,
        [("Kinderen 0-12 jaar", [(0, 12)]), ("Jongeren 12-18 jaar", [(12, 18)])],
    )
    assert binnen == "binnen"
    assert "12-18" in citaat
    assert "0-12" not in citaat
    buiten, citaat = leeftijd_oordeel(14, 14, [("Kinderen 0-12 jaar", [(0, 12)])])
    assert buiten == "buiten"
    assert "0-12" in citaat
    onbekend, _leeg = leeftijd_oordeel(14, 14, [("jongeren", [])])
    assert onbekend == "onbekend"

    index = Index(laad_document(_dataset()))
    treffers = index.zoek("meisje 14 jaar angst in Groesbeek")
    # Een bewezen leeftijdsmismatch mag niet langer als kandidaat verschijnen.
    assert "psycholoog-groesbeek" not in {treffer.id for treffer in treffers}
    for treffer in treffers:
        if "valt binnen de doelgroep" in treffer.reden and "0-12" in treffer.reden:
            raise AssertionError(treffer.id + " " + treffer.reden)


def test_kopp_is_breder_resultaat() -> None:
    index = Index(laad_document(_dataset()))
    treffers = index.zoek("KOPP")
    assert treffers
    assert all(treffer.breder for treffer in treffers)
    assert "Breder resultaat" in treffers[0].reden
    assert "geen treffer op KOPP" in treffers[0].reden
    assert "bovencategorie" in treffers[0].reden
    assert "kopp" not in treffers[0].reden.split("gevonden", 1)[-1].lower()


def _dataset() -> Path:
    return Path(__file__).resolve().parents[1] / "data" / "aanbieders.json"


def test_synoniem_ass_vindt_autisme(fixture_pad: Path) -> None:
    index = Index(laad_document(fixture_pad))
    treffers = index.zoek("ASS in Groesbeek")
    assert treffers[0].id == "fictief-de-horst-ambulant"
    assert "autisme" in treffers[0].reden.lower()
