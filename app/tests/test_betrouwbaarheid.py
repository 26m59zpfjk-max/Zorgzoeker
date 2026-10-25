"""Onafhankelijke regressies met uitsluitend fictieve aanbieders en zorgvragen."""

from copy import deepcopy
from pathlib import Path

import pytest

from zorgzoeker.laden import laad_document
from zorgzoeker.contracten import Contractregister
from zorgzoeker.zoeken import Filters, Index, analyseer_vraag, leeftijd_oordeel, leeftijdsgrenzen


def veld(waarde, **extra):
    return {"waarde": waarde, "label": "geverifieerd", "bron_url": "https://example.org/zorg",
            "opgehaald_op": "2026-10-23", **extra}


def aanbieder(id, *, leeftijd="Kinderen 0-18 jaar", expertise=None, **velden):
    return {"id": id, "naam": veld("FICTIEF - " + id), "doelgroepen": veld([leeftijd]),
            "expertise": veld(expertise or ["Angst"]), **velden}


def index_van(*aanbieders):
    return Index({"meta": {"regio": "Rijk van Nijmegen"}, "aanbieders": list(aanbieders)})


@pytest.mark.parametrize("vraag,leeftijd", [
    ("14-jarige met angst", 14), ("14 jarige met angst", 14), ("14 jaar angst", 14),
    ("zoon van 10 met angst", 10), ("dochter van 7 met angst", 7),
    ("kind 0 jaar met angst", 0), ("24-jarige met angst", 24),
])
def test_leeftijdsvormen(vraag, leeftijd):
    assert analyseer_vraag(vraag, {}, set()).leeftijd == leeftijd


def test_leeftijd_sluit_ongeschikt_uit_en_behoudt_passend_en_onbekend():
    index = index_van(
        aanbieder("vijftienplus", leeftijd="Jongeren vanaf 15 jaar", vestigingen=veld([{"plaats": "Groesbeek"}])),
        aanbieder("passend", leeftijd="Kinderen 8-14 jaar"),
        aanbieder("onbekend", leeftijd="Kinderen en jongeren"),
    )
    for vraag in ("14-jarige met angst in Groesbeek", "meisje van 14 jaar angst Groesbeek"):
        rs = index.zoek(vraag)
        assert {t.id for t in rs} == {"passend", "onbekend"}
        assert "leeftijd niet te controleren" in next(t.reden for t in rs if t.id == "onbekend")
    assert "vijftienplus" in {t.id for t in index.zoek("15-jarige met angst")}


def test_grens_voor_andere_dienst_is_geen_algemene_uitsluiting():
    assert leeftijd_oordeel(9, 9, [
        ("Kinderen, jongeren en gezinnen", []), ("Jongeren vanaf 18 jaar (wonen)", [(18, 120)])
    ])[0] == "onbekend"
    assert leeftijdsgrenzen("Jongeren vanaf 15 jaar") == [(15, 120)]
    import math
    assert leeftijdsgrenzen("jongeren tot 18 jaar") == [(0, math.nextafter(18.0, -math.inf))]
    assert leeftijdsgrenzen("jongeren tot en met 18 jaar") == [(0, math.nextafter(19.0, -math.inf))]


def test_echte_vijftienplus_praktijk_niet_voor_veertien():
    index = Index(laad_document(Path(__file__).resolve().parents[1] / "data/aanbieders.json"))
    for vraag in ("14-jarige met angst in Groesbeek", "meisje 14 jaar angst in Groesbeek"):
        ids = {t.id for t in index.zoek(vraag)}
        assert "psycholoog-groesbeek" not in ids
        assert "0-tot-18" in ids


@pytest.mark.parametrize("vraag", ["trauma, geen EMDR gewenst", "trauma zonder EMDR", "EMDR niet gewenst, wel trauma"])
def test_ongewenste_methode_geen_positieve_match(vraag):
    index = index_van(aanbieder("met-emdr", expertise=["Trauma", "EMDR"]),
                      aanbieder("zonder-emdr", expertise=["Trauma"]))
    assert [t.id for t in index.zoek(vraag)] == ["zonder-emdr"]


def test_ontkende_diagnose_verdringt_echte_hulpvraag_niet():
    index = index_van(aanbieder("school", expertise=["Schoolweigering", "Autisme"]),
                      aanbieder("alleen-ass", expertise=["Autisme"]))
    a = analyseer_vraag("schoolweigering; geen autisme vastgesteld", {}, set())
    assert a.concepten == ["school"]
    assert a.ontkend == ["ass"]
    assert not a.uitgesloten
    assert index.zoek("schoolweigering; geen autisme vastgesteld")[0].id == "school"


def test_negatiescope_en_positieve_niet_frases():
    assert analyseer_vraag("geen EMDR of dagbesteding, wel trauma", {}, set()).concepten == ["trauma"]
    assert analyseer_vraag("niet alleen EMDR, ook trauma", {}, set()).concepten == ["emdr", "trauma"]
    assert analyseer_vraag("kind kan zich niet concentreren en gaat niet meer naar school", {}, set()).concepten == ["adhd", "school"]
    index = index_van(aanbieder("ontkennend", expertise=["Geen EMDR, wel trauma"]),
                      aanbieder("bevestigd", expertise=["EMDR"]))
    assert "emdr" not in index._op_id["ontkennend"].bewijzen


def test_contractdekking_is_geen_vestigingsplaats():
    index = index_van(
        aanbieder("regionaal", gecontracteerd_regio=veld("ja"), vestigingen=veld([{"plaats": "Arnhem"}])),
        aanbieder("ander-contract", gecontracteerd_regio=veld("ja"), contractgemeenten=veld(["Arnhem"]), vestigingen=veld([{"plaats": "Nijmegen"}])),
        aanbieder("onbekend", gecontracteerd_regio=veld("onbekend")),
    )
    assert {t.id for t in index.zoek("", Filters(gemeente="Nijmegen", gecontracteerd="ja"))} == {"regionaal"}
    assert {t.id for t in index.zoek("", Filters(vestigingsplaats="Nijmegen"))} == {"ander-contract"}
    assert {t.id for t in index.zoek("", Filters(gemeente="Groesbeek", gecontracteerd="ja"))} == {"regionaal"}
    assert not index.zoek("", Filters(gemeente="Arnhem", gecontracteerd="ja", vestigingsplaats="Arnhem"))


def test_contractdatum_is_geen_jaarprojectie():
    index = index_van(aanbieder("actueel", gecontracteerd_regio=veld("ja")))
    assert index.zoek("angst", Filters(gecontracteerd="ja", op_datum="2026-10-23"))
    for datum in ("2027-01-01", "2025-10-23", "2027"):
        assert not index.zoek("angst", Filters(gecontracteerd="ja", op_datum=datum))
    a = analyseer_vraag("EMDR gecontracteerd per 1 januari 2027", {}, set())
    assert a.op_datum == "2027-01-01"
    assert not index.zoek("angst gecontracteerd 2027")
    assert "niet vastgesteld" in index.meldingen("angst gecontracteerd 2027")[0]
    rs = index.zoek("angst", Filters(gecontracteerd="onbekend", op_datum="2027-01-01"))
    assert [t.id for t in rs] == ["actueel"]
    assert rs[0].contracttoets["status"] == "onbekend"


@pytest.fixture(scope="module")
def echte_index():
    return Index(laad_document(Path(__file__).resolve().parents[1] / "data/aanbieders.json"))


@pytest.mark.parametrize("id", ["alkazorg", "apollis-zorg"])
def test_onderaannemer_stop_is_product_en_gemeentegebonden(echte_index, id):
    p = echte_index.op_id(id)
    register = echte_index.contractregister
    toets = register.oordeel(p, gemeente="nijmegen", codes=["JW 45A04"])
    assert toets["status"] == "ja"  # contract en toelating zijn aparte feiten
    assert toets["toeleiding"] == "geblokkeerd"
    assert toets["routes"][0]["hoofdaannemer"]
    assert not echte_index.zoek(id.replace("-", " "), Filters(gemeente="Nijmegen", productcode="JW 45A04", gecontracteerd="ja"))
    assert id in {t.id for t in echte_index.zoek(id.replace("-", " "), Filters(gemeente="Berg en Dal", productcode="JW 45A04", gecontracteerd="ja"))}
    if id == "apollis-zorg":
        assert id in {t.id for t in echte_index.zoek("Apollis Zorg", Filters(gemeente="Nijmegen", productcode="JW 45A55", gecontracteerd="ja"))}


def test_alternatieve_hoofdaannemerroute_blijft_beschikbaar():
    p = aanbieder("twee-routes", gecontracteerd_regio=veld("ja"))
    regels = [{"aanbieder_id": p["id"], "productcode": "JW 45A04", "gemeenten": ["nijmegen"],
               "hoofdaannemer": h, "opmerkingen": notes, "bewijs": [{"tabblad": "FICTIEF", "rij": 3}]}
              for h, notes in [("FICTIEF - Hoofd A", ["Toeleidingsstop voor gemeente Nijmegen per 1-1-2026"]),
                               ("FICTIEF - Hoofd B", [])]]
    register = Contractregister({"contractregister": {"peildatum": "2026-10-23", "regels": regels}})
    toets = register.oordeel(p, gemeente="nijmegen", codes=["JW 45A04"])
    assert toets["status"] == "ja"
    assert toets["toeleiding"] != "geblokkeerd"
    assert len(toets["routes"]) == 2
    assert register.oordeel(p, gemeente="arnhem", codes=["JW 45A04"])["status"] == "onbekend"
    assert register.oordeel(p, gemeente="nijmegen", codes=["JW 54001"])["status"] == "onbekend"


def test_regionale_aanbieders_niet_verdwenen_door_vestigingsplaats(echte_index):
    rs = echte_index.zoek("", Filters(gemeente="Nijmegen", gecontracteerd="ja"))
    assert {"1-1-vier", "stichting-pro-persona-ggz"} <= {t.id for t in rs}
    assert "alkazorg" not in {t.id for t in rs}  # bekende stop telt nu ook bij alleen filters
    assert "0-tot-18" not in {t.id for t in rs}


def test_losse_hoofdaannemernaam_bewijst_geen_contract():
    from zorgzoeker.weergave import onderaannemer_zin
    p = aanbieder("onbewezen", gecontracteerd_regio=veld("nee"), hoofdaannemer=veld("FICTIEF - Hoofd"))
    assert onderaannemer_zin(p) is None
    p["gecontracteerd_regio"] = veld("ja")
    p["hoofdaannemer"]["label"] = "onbekend"
    assert onderaannemer_zin(p) is None


def test_leeftijd_en_plaats_verzinnen_geen_expertise():
    index = index_van(
        aanbieder("alleen-ggz-code", expertise=["Algemene begeleiding"], gecontracteerd_regio=veld("ja"),
                  productcodes=veld([{"code": "JW 54001", "omschrijving": "Behandeling basis jeugd ggz"}]),
                  vestigingen=veld([{"plaats": "Nijmegen"}])),
        aanbieder("dwang-specialist", expertise=["Dwangstoornissen"]),
    )
    assert [t.id for t in index.zoek("kind 11 jaar met OCD in Nijmegen gecontracteerd")] == []
    assert [t.id for t in index.zoek("kind 11 jaar met OCD in Nijmegen")] == ["dwang-specialist"]


def test_volledige_dekking_gaat_voor_plaats_en_leeftijd():
    index = index_van(
        aanbieder("dichtbij", expertise=["Autisme"], vestigingen=veld([{"plaats": "Groesbeek"}])),
        aanbieder("volledig", leeftijd="Kinderen en jongeren", expertise=["Autisme", "Angst"]),
        aanbieder("irrelevant", expertise=["Dagbesteding"], vestigingen=veld([{"plaats": "Groesbeek"}])),
    )
    rs = index.zoek("14-jarige met autisme en angst in Groesbeek")
    assert [t.id for t in rs] == ["volledig", "dichtbij"]
    assert not rs[0].ontbrekende_expertise
    assert rs[1].ontbrekende_expertise == ["angst"]
    assert "Niet bevestigd in de bron: angst" in rs[1].reden
    assert not index.zoek("14-jarige in Groesbeek")


def test_maximale_wachttijd_is_geen_schatting():
    goed = veld("2 weken", toelichting="Peildatum: 2026-10-23")
    index = index_van(
        aanbieder("kort", expertise=["EMDR"], wachttijd=goed),
        aanbieder("lang", expertise=["EMDR"], wachttijd={**goed, "waarde": "8 weken"}),
        aanbieder("onbekend", expertise=["EMDR"]),
        aanbieder("complex", expertise=["EMDR"], wachttijd={**goed, "waarde": "Intake: 1 week; behandeling: 8 weken"}),
    )
    assert [t.id for t in index.zoek("EMDR maximaal twee weken wachttijd")] == ["kort"]


@pytest.mark.parametrize("wijziging", [
    {"bron_url": None}, {"opgehaald_op": None}, {"label": "afgeleid"},
    {"waarde": 2}, {"toelichting": "Peildatum 2026-02-31"},
    {"toelichting": "Peildatum 2026-10-26"}, {"toelichting": "Geen peildatum vermeld, opgehaald 2026-10-23"},
])
def test_onbewezen_wachttijd_niet_als_geverifieerd(wijziging, tmp_path):
    import json
    from fastapi.testclient import TestClient
    from zorgzoeker.app import maak_app
    from zorgzoeker.weergave import toon_veld
    from zorgzoeker.valideer import valideer_document
    doc = laad_document(Path(__file__).resolve().parents[1] / "data/fixture_aanbieders.json")
    wacht = veld("2 weken", toelichting="Peildatum: 2026-10-23")
    wacht.update(wijziging)
    doc["aanbieders"][0]["wachttijd"] = wacht
    assert valideer_document(doc)
    weergave = toon_veld("wachttijd", wacht)
    assert weergave["tekst"] == "onbekend"
    assert weergave["label"] == "onbekend"
    pad = tmp_path / "FICTIEF-invalid.json"
    pad.write_text(json.dumps(doc))
    client = TestClient(maak_app(pad))
    assert client.get("/gezondheid").json()["status"] == "fout"
    antwoord = client.get("/api/zoek", params={"q": "angst"})
    assert antwoord.status_code == 500
    assert antwoord.json()["validatiefouten"]
    assert client.get("/", params={"q": "angst"}).status_code == 500


def test_geldige_wachttijd_blijft_beschikbaar():
    from zorgzoeker.weergave import toon_veld
    wacht = veld("2 weken", toelichting="Peildatum: 2026-10-23")
    resultaat = toon_veld("wachttijd", wacht)
    assert resultaat["tekst"] == "2 weken"
    assert resultaat["label"] == "geverifieerd"
    assert resultaat["peildatum"] == "2026-10-23"


def test_naamzoekactie_blijft_werken_na_geschiktheidsfilter(echte_index):
    assert echte_index.zoek("AlkaZorg")[0].id == "alkazorg"
    assert echte_index.zoek("Apollis Zorg")[0].id == "apollis-zorg"


def test_aanmeldstop_achttienplus_sluit_geen_kinderen_uit(echte_index):
    assert "ambulatorium-nijmegen" not in {t.id for t in echte_index.zoek("18-jarige zoekt jeugd-ggz in Nijmegen")}
    assert "ambulatorium-nijmegen" in {t.id for t in echte_index.zoek("14-jarige zoekt jeugd-ggz in Nijmegen")}


@pytest.mark.parametrize("vraag,positief", [("rouwverwerking", "Rouwverwerking kind"), ("verslavingszorg", "Verslavingszorg GGZ jeugdkliniek")])
def test_specifieke_zorgvorm_is_bewijs_generieke_ggz_niet(vraag, positief):
    index = index_van(aanbieder("specifiek", expertise=["Algemene begeleiding"], type_aanbod=veld([positief])),
                      aanbieder("algemeen", expertise=["Algemene begeleiding"], type_aanbod=veld(["Behandeling specialistische jeugd ggz"])))
    assert [t.id for t in index.zoek(vraag)] == ["specifiek"]


@pytest.fixture(scope="module")
def echte_client():
    from fastapi.testclient import TestClient
    from zorgzoeker.app import maak_app
    return TestClient(maak_app(Path(__file__).resolve().parents[1] / "data/aanbieders.json"))


def test_api_gemeente_en_vestiging_zijn_apart(echte_client):
    r = echte_client.get("/api/zoek", params={"gemeente": "Nijmegen", "gecontracteerd": "ja"})
    assert r.status_code == 200
    assert {"1-1-vier", "stichting-pro-persona-ggz"} <= {t["id"] for t in r.json()["resultaten"]}
    assert "alkazorg" not in {t["id"] for t in r.json()["resultaten"]}
    r = echte_client.get("/api/zoek", params={"vestigingsplaats": "Nijmegen"})
    ids = {t["id"] for t in r.json()["resultaten"]}
    assert "0-tot-18" in ids
    assert "alkazorg" not in ids  # vestiging onbekend, contractroute wel bekend


def test_api_toekomst_claimt_geen_contract(echte_client):
    r = echte_client.get("/api/zoek", params={"q": "EMDR", "op_datum": "2027-01-01", "gecontracteerd": "ja"})
    assert r.status_code == 200
    assert r.json()["aantal"] == 0
    assert "niet vastgesteld" in " ".join(r.json()["waarschuwingen"])
    r = echte_client.get("/api/zoek", params={"q": "EMDR", "op_datum": "2027-01-01", "gecontracteerd": "onbekend"})
    assert r.json()["resultaten"]
    assert all(t["contracttoets"]["status"] == "onbekend" for t in r.json()["resultaten"])


@pytest.mark.parametrize("datum", ["2026-02-31", "morgen"])
def test_api_ongeldige_contractdatum(echte_client, datum):
    assert echte_client.get("/api/zoek", params={"op_datum": datum}).status_code == 400


def test_api_en_pagina_markeren_ontbrekende_expertise(echte_client):
    vraag = "14-jarige met autisme en angst in Groesbeek"
    r = echte_client.get("/api/zoek", params={"q": vraag})
    assert r.status_code == 200
    rs = r.json()["resultaten"]
    assert "psycholoog-groesbeek" not in {t["id"] for t in rs}
    gedeeltelijk = [t for t in rs if not t["volledige_match"]]
    assert gedeeltelijk
    assert all(t["ontbrekende_expertise"] for t in gedeeltelijk)
    assert "gedeeltelijke match" in echte_client.get("/", params={"q": vraag}).text


def test_contractstop_in_andere_gemeente_of_na_einddatum():
    from zorgzoeker.contracten import _stop
    tekst = "Toeleidingsstop voor gemeente Heumen per 1-10-2026 tot 23-10-2026"
    assert _stop(tekst, "heumen", "2026-10-22")
    assert not _stop(tekst, "nijmegen", "2026-10-22")
    assert not _stop(tekst, "heumen", "2026-10-23")
    assert not _stop(tekst, "heumen", "2026-09-30")


def test_onjuiste_productkoppeling_in_contractregister_wordt_afgekeurd():
    from zorgzoeker.valideer import valideer_document
    doc = laad_document(Path(__file__).resolve().parents[1] / "data/aanbieders.json")
    doc["contractregister"]["regels"][0]["productcode"] = "FICTIEF-ONBEKEND-99"
    assert any("productcode ontbreekt" in fout for fout in valideer_document(doc))


def test_vergelijking_behoudt_contractdatum_en_onzekerheid(echte_client):
    r = echte_client.get("/vergelijken", params=[("ids", "alkazorg"), ("ids", "apollis-zorg"), ("op_datum", "2027-01-01")])
    assert r.status_code == 200
    assert "Contract voor deze vraag onbekend" in r.text
    assert "Contractgeldigheid op 2027-01-01 niet vastgesteld" in r.text
    r = echte_client.get("/", params={"q": "EMDR", "op_datum": "2027-01-01"})
    assert 'name="op_datum" value="2027-01-01"' in r.text

