import json
from fastapi.testclient import TestClient
from zorgzoeker.app import maak_app
from zorgzoeker.bewijs import hashwaarde

def test_review_alleen_lezen_en_datasetgebonden(fixture_pad,tmp_path,monkeypatch):
    c=TestClient(maak_app(fixture_pad));d=c.app.state.document
    assert c.get('/beheer/verrijking').status_code==503
    p=tmp_path/'run.json';p.write_text(json.dumps({'dataset_hash':hashwaarde(d),'runs':[{'aanbieder_id':d['aanbieders'][0]['id'],'bevindingen':[],'problemen':[],'status':'ter_controle'}]}));monkeypatch.setenv('ZORGZOEKER_VERRIJKING_REVIEW',str(p))
    assert c.get('/beheer/verrijking').status_code==200
    assert c.post('/beheer/verrijking',json={}).status_code==405
    p.write_text(json.dumps({'dataset_hash':'anders','runs':[]}));assert c.get('/beheer/verrijking').status_code==400
