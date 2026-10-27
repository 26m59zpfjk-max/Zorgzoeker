"""Routes berekenen alleen wat nodig is en behouden de privacygrenzen."""
from fastapi.testclient import TestClient
from zorgzoeker.app import maak_app
from zorgzoeker.beslissen import Beslisservice


def test_start_en_selectie_doen_geen_volledige_zoekopdracht(fixture_pad,monkeypatch):
    client=TestClient(maak_app(fixture_pad))
    def verboden(*a,**k):
        raise AssertionError('Onnodige volledige zoekopdracht')
    monkeypatch.setattr(Beslisservice,'zoek',verboden)
    assert client.get('/werkplek').status_code==200
    ids=list(client.app.state.index._op_id)[:2]
    assert client.post('/vergelijken',json={'q':'angst','ids':ids}).status_code==200
    r=client.post('/bronchecklijst',json={'q':'FICTIEF vertrouwelijke vrije tekst','ids':ids})
    assert r.status_code==200 and 'vertrouwelijke' not in r.text


def test_ongeldige_selectie_voordat_zoeken_start(fixture_pad,monkeypatch):
    client=TestClient(maak_app(fixture_pad))
    def verboden(*a,**k):raise AssertionError('Eerst selectie valideren')
    monkeypatch.setattr(Beslisservice,'zoek',verboden)
    assert client.post('/zoeken',json={'ids':['niet-bestaand']}).status_code==400
