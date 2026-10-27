"""Werkplek: gedrag en privacy, uitsluitend fictieve vragen."""
from fastapi.testclient import TestClient
from zorgzoeker.app import maak_app


def test_hoofdingang_en_klassieke_compatibiliteit(fixture_pad):
    c=TestClient(maak_app(fixture_pad))
    assert '/werkplek' in str(c.get('/').url)
    assert c.get('/klassiek').status_code==200
    assert c.get('/?q=angst').status_code==200
    assert c.get('/api/zoek?q=angst').status_code==200


def test_multi_keuze_en_afzonderlijke_routes(fixture_pad):
    c=TestClient(maak_app(fixture_pad));d={'q':'kinderen van 6 en 14 met angst'}
    r=c.post('/api/zoek',json=d).json()
    assert r['keuze_nodig'] and not r['resultaten']
    r=c.post('/api/zoek',json={**d,'zoekdoel':'afzonderlijk'}).json()
    assert len(r['deelopdrachten'])==2
    assert [x['context']['leeftijden'] for x in r['deelopdrachten']]==[[6],[14]]


def test_html_fout_en_json_fout(fixture_pad):
    c=TestClient(maak_app(fixture_pad))
    ids=list(c.app.state.index._op_id)[:2]
    r=c.post('/zoeken',data={'q':'FICTIEF angst','op_datum':'verkeerd','ids':ids})
    assert r.status_code==400 and 'text/html' in r.headers['content-type'] and 'FICTIEF angst' in r.text
    assert all('value="'+id+'" checked' in r.text for id in ids)
    r=c.post('/api/zoek',json={'q':'x'*501})
    assert r.status_code==400 and r.json()['fout']


def test_checklist_print_geen_vraag(fixture_pad):
    c=TestClient(maak_app(fixture_pad));ids=list(c.app.state.index._op_id)[:2]
    r=c.post('/bronchecklijst?weergave=print',data={'q':'FICTIEF geheimverhaal angst','ids':ids})
    assert r.status_code==200 and 'Bronchecklijst' in r.text and 'geheimverhaal' not in r.text
    assert r.headers['cache-control']=='no-store'


def test_kwaliteit_filter_export_en_alleen_lezen(fixture_pad):
    c=TestClient(maak_app(fixture_pad));naam=c.app.state.document['aanbieders'][0]['naam']['waarde']
    r=c.get('/kwaliteit',params={'q':naam});assert r.status_code==200 and naam in r.text
    assert c.get('/kwaliteit',params={'q':'NOOITBESTAAND','export':'true'}).text.count('\n')==1
    assert c.post('/kwaliteit',json={}).status_code==405


def test_wachttijdkandidaat_selectie_niet_dubbel(fixture_pad):
    from html.parser import HTMLParser
    class Keuzes(HTMLParser):
        def __init__(self):super().__init__();self.ids=[]
        def handle_starttag(self,tag,attrs):
            a=dict(attrs)
            if tag=='input' and a.get('form')=='pilot-vergelijk' and a.get('name')=='ids':self.ids.append(a['value'])
    c=TestClient(maak_app(fixture_pad));r=c.post('/api/zoek',json={'q':'angst maximaal 20 weken'}).json()
    assert r['kandidaten']
    id=r['kandidaten'][0]['id']
    h=c.post('/zoeken',json={'q':'angst maximaal 20 weken','ids':[id]});p=Keuzes();p.feed(h.text)
    assert p.ids.count(id)==1


def test_export_geen_casusafgeleide_controlepunten(fixture_pad):
    c=TestClient(maak_app(fixture_pad));ids=list(c.app.state.index._op_id)[:2]
    r=c.post('/bronchecklijst',json={'q':'FICTIEF angst en trauma','ids':ids}).json()
    assert all('Niet in bron bevestigd' not in punt for x in r for punt in x['controlepunten'])
