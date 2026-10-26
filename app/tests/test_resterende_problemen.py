"""Vervolgregressies: fictieve vragen/aanbieders, geen cliëntgegevens."""

from datetime import date, timedelta

import pytest

from zorgzoeker.contracten import algemene_stop
from zorgzoeker.zoeken import Filters, Index, analyseer_vraag
from tests.test_betrouwbaarheid import aanbieder, index_van, veld


def stop_index():
    p = aanbieder("gestopt", expertise=["Angst"], gecontracteerd_regio=veld("ja"),
                  productcodes=veld([{"code": "JW 45A04", "omschrijving": "Reguliere begeleiding"}]))
    vrij = aanbieder("vrij", expertise=["Angst"], gecontracteerd_regio=veld("ja"))
    regels = [{"aanbieder_id": a["id"], "productcode": "JW 45A04", "gemeenten": ["nijmegen", "heumen"],
               "hoofdaannemer": "FICTIEF - Hoofd", "opmerkingen": notes}
              for a, notes in [(p, ["Toeleidingsstop voor gemeente Nijmegen per 1-10-2026"]), (vrij, [])]]
    afleiders = [aanbieder(f"andere-praktijk-{n}", expertise=["Speltherapie"]) for n in range(80)]
    return Index({"meta": {"regio": "Rijk van Nijmegen"}, "aanbieders": [p, vrij, *afleiders],
                  "contractregister": {"peildatum": "2026-10-23", "regels": regels}})


@pytest.mark.parametrize("vraag", ["FICTIEF gestopt Nijmegen", "gestopt", "angst", ""])
def test_stop_geldt_ook_bij_vrije_tekst_en_zonder_onderwerp(vraag):
    index = stop_index()
    resultaten = index.zoek(vraag, Filters(gemeente="Nijmegen"))
    if vraag in {"gestopt", ""}:
        assert next(t for t in resultaten if t.id == "gestopt").contracttoets["stop_actief"]
    else:
        assert "gestopt" not in {t.id for t in resultaten}
    assert "gestopt" in {t.id for t in index.zoek("gestopt", Filters(gemeente="Heumen"))}


def test_onbekend_contract_wist_bekende_stop_niet():
    index = stop_index()
    toets = index.contracttoets_voor("gestopt", filters=Filters(gemeente="Nijmegen", op_datum="2026-10-26"))
    assert toets["status"] == "onbekend"
    assert toets["toeleiding"] == "geblokkeerd"
    assert toets["routes"][0]["opmerkingen"]
    rs = index.zoek("angst", Filters(gemeente="Nijmegen", op_datum="2026-10-26"))
    assert [t.id for t in rs] == ["vrij"]


def test_algemene_stop_blijft_na_peildatum_en_einddatum_wordt_gerespecteerd():
    p = aanbieder("stop", beschikbaarheid=veld("Aanmeldstop", toelichting="Peildatum 2026-10-23"))
    assert algemene_stop(p, None, "2026-10-26")
    p["beschikbaarheid"] = veld("Aanmeldstop tot 2026-11-01", toelichting="Peildatum 2026-10-23")
    assert algemene_stop(p, None, "2026-10-26")
    assert not algemene_stop(p, None, "2026-11-02")


@pytest.mark.parametrize("vraag", ["EMDR niet gewenst bij trauma", "EMDR is niet gewenst bij trauma", "EMDR niet gewenst en trauma", "trauma, EMDR niet gewenst"])
def test_postfix_negatie_schrapt_volgend_onderwerp_niet(vraag):
    a = analyseer_vraag(vraag, {}, set())
    assert a.concepten == ["trauma"]
    assert a.ontkend == ["emdr"]
    index = index_van(aanbieder("trauma", expertise=["Trauma"]), aanbieder("emdr", expertise=["EMDR", "Trauma"]))
    assert [t.id for t in index.zoek(vraag)] == ["trauma"]


@pytest.mark.parametrize("vraag,verwacht", [("17,5 jaar met angst", 17.5), ("17.5 jaar met angst", 17.5), ("zoon van 17,5 met angst", 17.5), ("14jr met angst", 14), ("14 jr. met angst", 14)])
def test_decimale_leeftijd_en_jr(vraag, verwacht):
    a = analyseer_vraag(vraag, {}, set())
    assert a.leeftijd == verwacht
    assert a.leeftijdsband == (verwacht, verwacht)
    index = index_van(aanbieder("jeugd", leeftijd="Jongeren tot 18 jaar"), aanbieder("volwassen", leeftijd="Volwassenen vanaf 18 jaar"))
    assert [t.id for t in index.zoek(vraag)] == ["jeugd"]
    assert [t.id for t in index.zoek("18jr met angst")] == ["volwassen"]


@pytest.mark.parametrize("doelgroep", ["Kinderen tot en met 17 jaar", "Kinderen 8 t/m 17 jaar"])
def test_zeventien_en_half_is_nog_zeventien_jaar_oud(doelgroep):
    index = index_van(aanbieder("jeugd", leeftijd=doelgroep))
    assert [t.id for t in index.zoek("17,5 jaar met angst")] == ["jeugd"]
    assert not index.zoek("18jr met angst")


@pytest.mark.parametrize("tekst", ["± 6 weken", "~6 weken", "verwachte wachttijd: 6 weken", "indicatieve wachttijd 6 weken", "naar verwachting 6 weken", "≈6 weken", "+/- 6 weken"])
def test_schattingswoorden_en_symbolen_worden_geweigerd(tekst):
    from zorgzoeker.valideer import _valideer_wachttijd
    from zorgzoeker.weergave import toon_veld
    v = veld(tekst, toelichting="Peildatum: 2026-10-23")
    assert any("schatting" in f for f in _valideer_wachttijd("test", {"wachttijd": v}))
    assert toon_veld("wachttijd", v)["tekst"] == "onbekend"
    assert toon_veld("wachttijd", v)["publicatie_tekst"] is None


def test_veroudering_gebruikt_peildatum_en_niet_ophaaldatum(monkeypatch):
    from zorgzoeker.weergave import toon_veld
    monkeypatch.setenv("ZORGZOEKER_WACHTTIJD_MAX_DAGEN", "30")
    v = veld("2 weken", toelichting="Peildatum: 2026-09-24")
    oud = toon_veld("wachttijd", v, referentiedatum=date(2026, 10, 25))
    assert oud["peildatum_leeftijd_dagen"] == 31
    assert oud["verouderd"]
    assert oud["tekst"] == "onbekend"
    assert oud["label"] == "onbekend"
    assert oud["publicatie_tekst"] == "2 weken"
    assert oud["bron_url"]
    grens = toon_veld("wachttijd", v, referentiedatum=date(2026, 10, 24))
    assert not grens["verouderd"]
    assert grens["tekst"] == "2 weken"
    monkeypatch.setenv("ZORGZOEKER_WACHTTIJD_MAX_DAGEN", "60")
    assert not toon_veld("wachttijd", v, referentiedatum=date(2026, 10, 25))["verouderd"]


def test_oude_wachttijd_telt_niet_voor_maximum_en_stop_veroudert_niet(monkeypatch):
    from zorgzoeker.zoeken import _past_wachttijd
    from zorgzoeker.weergave import toon_veld
    monkeypatch.setenv("ZORGZOEKER_WACHTTIJD_MAX_DAGEN", "30")
    peil = (date.today() - timedelta(days=31)).isoformat()
    oud = veld("1 week", toelichting=f"Peildatum: {peil}")
    assert not _past_wachttijd(oud, 2)
    vers = veld("1 week", toelichting=f"Peildatum: {date.today().isoformat()}", opgehaald_op=date.today().isoformat())
    assert _past_wachttijd(vers, 2)
    stop = veld("Aanmeldstop", toelichting=f"Peildatum: {peil}")
    assert toon_veld("beschikbaarheid", stop)["tekst"] == "Aanmeldstop"
    assert algemene_stop(aanbieder("gestopt", beschikbaarheid=stop), None, "2026-10-26")
