from pathlib import Path
import json
import pytest
from fastapi.testclient import TestClient
from zorgzoeker.app import maak_app
from zorgzoeker.beslissen import Beslisservice
from zorgzoeker.zoeken import Index,Filters
DATA=Path(__file__).resolve().parents[1]/'data/aanbieders.json'
@pytest.fixture(scope='module')
def doc():return json.loads(DATA.read_text())
@pytest.mark.parametrize('plaats',['Arnhem','Nijmegen','Berg en Dal','Groesbeek','Wijchen'])
def test_genoemde_plaats_geen_verantwoordelijkheid(doc,plaats):
 z=Beslisservice(doc);a,c=z.context('autisme 8 jaar '+plaats,Filters())
 assert c.gemeente is None and not c.gemeente_bevestigd
 assert z.index.zoek('autisme 8 jaar '+plaats)
 assert all(t.contracttoets['gemeente'] is None for t in z.index.zoek('autisme 8 jaar '+plaats))
 a,c=z.context('autisme 8 jaar '+plaats,Filters(gemeente='Berg en Dal'))
 assert c.gemeente=='berg en dal' and c.gemeente_bevestigd

def test_onbekende_gemeente_niet_omzetten(doc):
 with pytest.raises(ValueError):Beslisservice(doc).context('angst',Filters(gemeente='Onbekendedorp999'))

def test_wachttijdgroepen_en_melding(doc):
 r=Beslisservice(doc).zoek('angst maximaal 20 weken')
 assert r['kandidaten'] and not r['onderbouwd']
 assert not any('Geen resultaten' in m or 'Geen kandidaten' in m for m in r['meldingen'])
 for x in r['kandidaten']:
  assert x['resultaatstatus']=='kandidaten'
  assert next(c for c in x['beoordeling']['criteria'] if c['sleutel']=='wachttijd')['status']=='onbekend'
 sets=[{x['id'] for x in r[k]} for k in ('onderbouwd','kandidaten','uitgesloten')]
 assert all(not a&b for i,a in enumerate(sets) for b in sets[i+1:])

def test_api_schema_en_leeftijdweergave(doc):
 c=TestClient(maak_app(DATA));r=c.post('/api/zoek',json={'q':'angst maximaal 20 weken'}).json()
 assert r['schema_versie']=='5G' and r['aantallen']['kandidaten']>0
 assert all(x['resultaatstatus']==x['beoordeling']['groep'] for x in r['resultaten'])
 r=c.post('/zoeken',json={'q':'kinderen van 6 en 14 met angst','zoekdoel':'gezamenlijk','gemeente':'Berg en Dal'})
 assert r.status_code==200 and '6 en 14 jaar' in r.text and '6.0 en 14.0' not in r.text

def test_contractstatus_blijft_onbekend_bij_snapshot(doc):
 z=Beslisservice(doc);r=z.zoek('14 jaar angst',Filters(gemeente='Nijmegen'))
 assert len(r['kandidaten'])==16
 assert all(x['beoordeling']['contract']['geldigheid']=='onbekend' for x in r['kandidaten'])
 assert all('hulpvorm_niet_productgebonden_vastgesteld' in x['beoordeling']['contract']['redenen_onzeker'] for x in r['kandidaten'])


def test_scraper_interne_dns_wordt_voor_http_geweigerd(monkeypatch):
 import socket
 import urllib.request
 from zorgzoeker.verrijking import Verzamelaar
 monkeypatch.setattr(socket,'getaddrinfo',lambda *a,**k:[(socket.AF_INET,socket.SOCK_STREAM,6,'',('127.0.0.1',443))])
 monkeypatch.setattr(urllib.request,'build_opener',lambda *a: (_ for _ in ()).throw(AssertionError('HTTP mag niet starten')))
 with pytest.raises(ValueError):Verzamelaar().request('https://example.org/',{'https://example.org'})


def test_review_geen_scriptuitvoering_of_publicatie(doc,tmp_path,monkeypatch):
 from zorgzoeker.bewijs import hashwaarde
 c=TestClient(maak_app(DATA));id=doc['aanbieders'][0]['id'];p=tmp_path/'review.json'
 p.write_text(json.dumps({'dataset_hash':hashwaarde(doc),'runs':[{'aanbieder_id':id,'status':'ter_controle','problemen':[],'bevindingen':[{'veld':'expertise','citaat':'<script>alert(1)</script>','scope':'onbekend','verzameld_op':'2026-10-26','taxonomie':[],'bron_url':'https://example.org'}]}]}))
 monkeypatch.setenv('ZORGZOEKER_VERRIJKING_REVIEW',str(p));r=c.get('/beheer/verrijking')
 assert r.status_code==200 and '<script>alert(1)</script>' not in r.text and '&lt;script&gt;' in r.text
 assert c.post('/beheer/verrijking',json={}).status_code==405
 assert json.loads(DATA.read_text())==doc


def test_html_foutpagina_is_geen_robotstoestemming():
 from zorgzoeker.verrijking import Verzamelaar,BronFout
 calls=[]
 def http(url,headers):calls.append(url);return 200,{'Content-Type':'text/html'},b'<html>Pagina niet gevonden</html>'
 v=Verzamelaar(transport=http)
 with pytest.raises(BronFout):v.toegelaten('https://example.org/',{'https://example.org'})
 assert len(calls)==1


def test_mogelijke_gemeentestop_blijft_zichtbaar_zonder_harde_scope():
 from tests.test_betrouwbaarheid import aanbieder,veld
 p=aanbieder('fictief');p['beschikbaarheid']=veld('Aanmeldstop in Nijmegen')
 z=Beslisservice({'aanbieders':[p]});a,c=z.context('angst Nijmegen',Filters())
 b=z.beoordeel(p['id'],analyse=a,context=c)
 assert c.gemeente is None and not b['instroom']['stop'] and b['instroom']['scopewaarschuwing']
