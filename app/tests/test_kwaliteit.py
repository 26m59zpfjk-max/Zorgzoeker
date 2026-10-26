"""Kwaliteitscontrole: fictieve mutaties en brongebonden oordelen."""
from copy import deepcopy
from datetime import date,timedelta
from pathlib import Path
import json,socket
import pytest
from zorgzoeker.kwaliteit import analyseer,hashwaarde,voorstel,neem_voorstel_op,valideer_beoordeling
from zorgzoeker.kwaliteitsbronnen import openbare_url,controleer_adres,vergelijk_waarneming
from tests.test_validatie import _minimaal_geldig
from tests.test_betrouwbaarheid import veld


def beoordeling(doc,k='website',**extra):
    a=doc['aanbieders'][0]
    return {'aanbieder_id':a['id'],'veld':k,'waarde_hash':hashwaarde(a.get(k,{})),'bron_url':'https://example.org/bron',
            'gepubliceerd_op':None,'geldig_van':None,'geldig_tot':None,'gecontroleerd_op':date.today().isoformat(),
            'hercontrole_op':(date.today()+timedelta(days=30)).isoformat(),'beoordelaar':'FICTIEF controleur',
            'methode':'openbare_bron_gecontroleerd','status':'geverifieerd','citaat':'FICTIEF letterlijk gecontroleerd gegeven',
            'tegenstrijdigheden':[],**extra}


def test_bereikbaarheid_geen_verificatie_en_brondata_ongewijzigd():
    doc=_minimaal_geldig();a=doc['aanbieders'][0];a['website']=veld('https://example.org/aanbieder',label='afgeleid',toelichting='FICTIEF naamkoppeling')
    origineel=deepcopy(doc)
    r=analyseer(doc,waarnemingen=[{'url':a['website']['waarde'],'status':'opgehaald','http_status':200}])
    assert r['aanbieders'][0]['velden']['website']['status']=='bron_te_controleren'
    assert not r['aanbieders'][0]['kern_voldoende_onderbouwd']
    assert any(p['code']=='website_identiteit_onbevestigd' for p in r['problemen'])
    assert doc==origineel


def test_waarde_en_controleperiode_gebonden():
    doc=_minimaal_geldig();doc['aanbieders'][0]['website']=veld('https://example.org/')
    b=beoordeling(doc)
    assert not valideer_beoordeling(b)
    assert analyseer(doc,beoordelingen=[b])['aanbieders'][0]['velden']['website']['status']=='geverifieerd'
    doc['aanbieders'][0]['website']['waarde']='https://example.net/'
    assert analyseer(doc,beoordelingen=[b])['aanbieders'][0]['velden']['website']['status']=='bron_te_controleren'
    b=beoordeling(doc,gecontroleerd_op=(date.today()-timedelta(days=40)).isoformat(),hercontrole_op=date.today().isoformat())
    assert analyseer(doc,beoordelingen=[b])['aanbieders'][0]['velden']['website']['status']=='tegenstrijdig_of_verouderd'


@pytest.mark.parametrize('extra',[{'methode':'afgeleid'},{'tegenstrijdigheden':['Ander leeftijdsbereik']},{'bron_url':'javascript:1'},
                                  {'gecontroleerd_op':'2099-01-01'},{'hercontrole_op':None}])
def test_onjuist_bewijs(extra):
    assert valideer_beoordeling(beoordeling(_minimaal_geldig(),**extra))


def test_problemen_en_dubbelkandidaten():
    doc=_minimaal_geldig();a=doc['aanbieders'][0]
    a['doelgroepen']=veld(['Kinderen 18-6 jaar']);a['website']=veld('https://example.org/')
    a['expertise']=veld([],label='onbekend');a['productcodes']=veld([{'code':'JW 45A04','omschrijving':'FICTIEF'}])
    a['beschikbaarheid']=veld('Toeleidingsstop Nijmegen',toelichting='Peildatum: 2026-01-01')
    a['wachttijd']=veld('6 weken',toelichting='Peildatum: 2026-01-01')
    ander=deepcopy(a);ander['id']='ander';doc['aanbieders'].append(ander)
    r=analyseer(doc)
    assert {'leeftijd_tegenstrijdig','mogelijke_dubbeling','contractbron_per_product_ontbreekt','stop_scope_en_periode_controleren','wachttijd_verouderd'}<={p['code'] for p in r['problemen']}


def test_voorstel_review_en_bronwijziging():
    doc=_minimaal_geldig();nieuwe=veld('https://example.org/nieuw');b=beoordeling(doc,waarde_hash=hashwaarde(nieuwe))
    p=voorstel(doc,doc['aanbieders'][0]['id'],'website',nieuwe,b,soort='openbare_verandering')
    with pytest.raises(ValueError):neem_voorstel_op(doc,p,beoordelaar='FICTIEF')
    nieuw=neem_voorstel_op(doc,p,beoordelaar='FICTIEF',expliciet=True)
    assert nieuw['aanbieders'][0]['website']==nieuwe and doc['aanbieders'][0]['website']!=nieuwe
    assert nieuw['kwaliteitshistorie'][0]['vorige']==doc['aanbieders'][0]['website']
    doc['meta']['gewijzigd']=True
    with pytest.raises(ValueError):neem_voorstel_op(doc,p,beoordelaar='FICTIEF',expliciet=True)
    with pytest.raises(ValueError):voorstel(doc,doc['aanbieders'][0]['id'],'website',nieuwe,b,soort='rechtstreeks_bevestigd')


@pytest.mark.parametrize('url',['file:///etc/passwd','http://localhost/','http://x.local/','https://u:p@example.org/','http://example.org:9999/','javascript:1'])
def test_url(url):
    assert not openbare_url(url)


def test_dns_en_verandering(monkeypatch):
    monkeypatch.setattr(socket,'getaddrinfo',lambda *a,**kw:[(socket.AF_INET,socket.SOCK_STREAM,6,'',('127.0.0.1',80))])
    with pytest.raises(ValueError):controleer_adres('https://example.org/')
    assert vergelijk_waarneming({'sha256':'oud'},{'sha256':'nieuw','status':'opgehaald'})['soort']=='openbare_verandering'
    assert vergelijk_waarneming(None,{'status':'opgehaald'})['soort']=='vermoeden'


def test_189_profielen_114_links():
    doc=json.loads((Path(__file__).resolve().parents[1]/'data/aanbieders.json').read_text());r=analyseer(doc)
    assert r['samenvatting']['aanbieders']==189 and r['samenvatting']['afgeleide_websites']==114
    assert len({a['id'] for a in r['aanbieders']})==189
    assert all('hercontrole_nodig' in v for a in r['aanbieders'] for v in a['velden'].values())


def test_negatieve_contractbron_maakt_geen_onderaannemer():
    doc=_minimaal_geldig();doc['aanbieders'][0]['gecontracteerd_regio']=veld('nee',label='afgeleid',toelichting='Niet aangetroffen, ook niet als onderaannemer.')
    assert not any(p['code']=='hoofdaannemer_ontbreekt' for p in analyseer(doc)['problemen'])
