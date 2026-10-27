from fastapi.testclient import TestClient
from zorgzoeker.app import maak_app

def test_detail_behoudt_volledige_selectie(fixture_pad):
    c=TestClient(maak_app(fixture_pad));ids=list(c.app.state.index._op_id)[:2]
    r=c.post('/aanbieder',json={'q':'angst','ids':ids,'aanbieder_id':ids[0]})
    assert r.status_code==200 and 'Aanbieder bekijken' in r.text
    for id in ids:assert 'value="'+id+'" checked' in r.text
    assert c.post('/aanbieder',json={'ids':'geenlijst','aanbieder_id':ids[0]}).status_code==400

def test_primair_scherm_geen_beheer_of_bronadministratie(fixture_pad):
    c=TestClient(maak_app(fixture_pad));r=c.post('/zoeken',json={'q':'angst'})
    assert r.status_code==200 and 'search.css' in r.text and '5b.css' not in r.text
    assert 'href="/kwaliteit"' not in r.text
    assert 'Contract te controleren' in r.text and 'Bekijk aanbieder' in r.text
