from copy import deepcopy
from pathlib import Path
import json
import pytest
from fastapi.testclient import TestClient
from zorgzoeker.app import maak_app
from zorgzoeker.beslissen import Beslisservice
from zorgzoeker.bewijs import hashwaarde
from zorgzoeker.zoeken import Index,Filters
from zorgzoeker.beschikbaarheid import relevante_regels
from tests.test_validatie import _minimaal_geldig
from tests.test_kwaliteit import beoordeling
from tests.test_betrouwbaarheid import veld,aanbieder
from tests.test_ronde3 import regel


def document():
 d=_minimaal_geldig();p=d['aanbieders'][0];p['expertise']=veld(['Angst']);p['doelgroepen']=veld(['Kinderen tot 18 jaar']);return d


def test_conflict_niet_als_positief_bewijs():
 d=document();d['kwaliteitsbeoordelingen']=[beoordeling(d,k='expertise',status='tegenstrijdig_of_verouderd',tegenstrijdigheden=['FICTIEF conflict'])]
 assert not Index(d).zoek('angst')
 b=Beslisservice(d).beoordeel(d['aanbieders'][0]['id'],'angst')
 assert b['inhoud']['status']=='onvoldoende bronbewijs' and b['kwaliteit']['expertise']['status']=='tegenstrijdig_of_verouderd'


def test_stop_per_kind_en_geen_verzonnen_beschikbaarheid():
 p=aanbieder('fictief');d={'aanbieders':[p],'beschikbaarheidsregister':[regel(leeftijd_van=12,leeftijd_tot=17,stop={'soort':'aanmeldstop','vanaf':'2026-10-26','tot':None,'toelichting':'FICTIEF'})]}
 z=Beslisservice(d);q='Kinderen van 6 en 14 met angst'
 assert not z.index.zoek(q)
 r=z.zoek(q);assert not r['resultaten'] and r['afgevallen']
 b=r['afgevallen'][0]['beoordeling'];assert [x['stop'] for x in b['leeftijden']]==[False,True]
 assert z.index.zoek('Kind van 6 met angst')


def test_dienstregels_niet_op_andere_dienst():
 r=regel(dienst='Dienst A',dienst_id='A');d={'beschikbaarheidsregister':[r]}
 assert not relevante_regels(d,'fictief',dienst='B')
 assert not relevante_regels(d,'fictief')
 assert relevante_regels(d,'fictief',dienst='A')


def test_context_bronperiode_en_gemeente():
 d=document();z=Beslisservice(d);id=d['aanbieders'][0]['id']
 b=z.beoordeel(id,'14 jaar angst',Filters(gemeente='Groesbeek',op_datum='2027-01-01'))
 assert b['context']['gemeente']=='berg en dal'
 assert b['contract']['geldigheid']=='onbekend' and b['context']['datasetversie']==z.versie


@pytest.fixture
def client(tmp_path):
 d=document();p=deepcopy(d['aanbieders'][0]);p['id']='tweede';p['naam']=veld('FICTIEF tweede');d['aanbieders'].append(p)
 path=tmp_path/'fixture.json';path.write_text(json.dumps(d));return TestClient(maak_app(path)),d


def test_post_flow_context_terug_export_privacy(client):
 c,d=client;payload={'q':'FICTIEF geheimvraag met angst','gemeente':'Nijmegen','ids':[p['id'] for p in d['aanbieders']]}
 r=c.post('/zoeken',json=payload);assert r.status_code==200 and r.headers['cache-control']=='no-store'
 assert 'geheimvraag' not in r.text.split('<title>')[1].split('</title>')[0]
 a=c.post('/api/zoek',json=payload).json();assert a['context']['datasetversie']
 vergelijk=c.post('/vergelijken',json=payload);assert vergelijk.status_code==200 and 'Terug naar zoeken met selectie' in vergelijk.text
 assert all('value="'+id+'" checked' in vergelijk.text for id in payload['ids'])
 export=c.post('/bronchecklijst',json=payload);assert export.status_code==200 and 'geheimvraag' not in export.text and 'datasetversie' in export.text
 assert c.get('/kwaliteit').status_code==200 and c.get('/kwaliteit?export=true').status_code==200
 assert c.post('/kwaliteit',json={}).status_code==405
 assert c.post('/api/zoek',json={'q':'x'*501}).status_code==400
 assert c.post('/vergelijken',json={**payload,'ids':[payload['ids'][0]]}).status_code==400


def test_aanpassing_werkt_zonder_ai(client):
 c,d=client;r=c.post('/api/zoek',json={'q':'14 jaar angst','aanpassing':True,'leeftijden':[18],'concepten':['angst'],'uitsluitingen':[]}).json()
 assert not r['resultaten'] and r['afgevallen']
 assert c.post('/api/zoek',json={'q':'angst','aanpassing':True,'leeftijden':[999]}).status_code==400


def test_vrijgegeven_pakket_en_andere_dataset_geweigerd(tmp_path,monkeypatch):
 d=document();p=tmp_path/'fixture.json';p.write_text(json.dumps(d));b=beoordeling(d,k='expertise')
 m=tmp_path/'manifest.json';m.write_text(json.dumps({'dataset_hash':hashwaarde(d),'beoordelingen':[b]}));monkeypatch.setenv('ZORGZOEKER_KWALITEIT_PAD',str(m))
 c=TestClient(maak_app(p));r=c.post('/api/zoek',json={'q':'angst'}).json();assert r['resultaten'][0]['beoordeling']['kwaliteit']['expertise']['status']=='geverifieerd'
 d['meta']['nieuw']=True;p.write_text(json.dumps(d));assert TestClient(maak_app(p)).get('/gezondheid').json()['status']=='fout'


def test_algemene_hulpvraag_vraagt_verduidelijking(client):
 c,_=client;r=c.post('/api/zoek',json={'q':'Kinderen van 6 en 14 hebben ondersteuning nodig'}).json()
 assert not r['resultaten'] and (r.get('keuze_nodig') or any('Verduidelijk' in x for x in r['meldingen']))


def test_onbekende_dienstscope_geen_brede_toezegging():
 d={'aanbieders':[{'id':'fictief','diensten':[{'id':'a'},{'id':'b'}]}],'beschikbaarheidsregister':[regel(dienst='Dienst A')]}
 assert not relevante_regels(d,'fictief')
 assert relevante_regels(d,'fictief',dienst='Dienst A')
 assert not relevante_regels(d,'fictief',dienst='Dienst B')


def test_beoordeling_identiek_kaart_api_vergelijk(client):
 c,d=client;q='14 jaar angst';id=d['aanbieders'][0]['id']
 get=c.get('/api/zoek',params={'q':q}).json()
 oud=next(t for t in get['resultaten'] if t['id']==id)['contracttoets']['beoordeling']
 nieuw=next(t for t in c.post('/api/zoek',json={'q':q}).json()['resultaten'] if t['id']==id)['beoordeling']
 assert oud==nieuw


def test_conflicterende_gelijke_reviews_geen_willekeurige_winnaar():
 from zorgzoeker.bewijs import Kwaliteitslezing
 d=document();b=beoordeling(d,k='expertise');d['kwaliteitsbeoordelingen']=[b,{**b,'status':'tegenstrijdig_of_verouderd'}]
 assert Kwaliteitslezing(d).veld(d['aanbieders'][0],'expertise')['status']=='tegenstrijdig_of_verouderd'
