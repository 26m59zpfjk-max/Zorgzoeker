"""Waardegebonden veldkwaliteit: alle lezers delen dezelfde conservatieve regels."""
from copy import deepcopy
from datetime import date, timedelta

import pytest

from zorgzoeker.bewijs import Kwaliteitslezing, beoordeel_veld
from zorgzoeker.kwaliteit import analyseer
from tests.test_kwaliteit import beoordeling
from tests.test_validatie import _minimaal_geldig
from tests.test_betrouwbaarheid import veld


def beide(doc, reviews, key='expertise', vandaag=None):
    d={**doc, 'kwaliteitsbeoordelingen':reviews}
    a=d['aanbieders'][0]
    kaart=Kwaliteitslezing(d, vandaag).veld(a,key)
    lijst=analyseer(d, beoordelingen=reviews, vandaag=vandaag)['aanbieders'][0]['velden'][key]
    for k in ('status','herkomst','controle','actualiteit','hash_gewijzigd','laatste_controle','methode'):
        assert kaart[k]==lijst[k]
    return kaart


def document():
    d=_minimaal_geldig();d['aanbieders'][0]['expertise']=veld(['FICTIEF angst'])
    return d


def test_gelijke_datum_conflict_is_onafhankelijk_van_invoervolgorde():
    d=document();goed=beoordeling(d,k='expertise');slecht={**goed,'status':'tegenstrijdig_of_verouderd'}
    assert beide(d,[goed,slecht])['status']=='tegenstrijdig_of_verouderd'
    assert beide(d,[slecht,goed])['status']=='tegenstrijdig_of_verouderd'
    assert beide(d,[slecht,goed])==beide(d,[goed,slecht])


def test_toekomstige_geldigheid_is_niet_nu_geverifieerd():
    d=document();b=beoordeling(d,k='expertise',geldig_van=(date.today()+timedelta(days=1)).isoformat())
    r=beide(d,[b]);assert r['status']=='bron_te_controleren' and r['actualiteit']=='Nog niet geldig'


def test_gewijzigde_hash_blijft_onbevestigd_en_wordt_niet_geindexeerd():
    d=document();b=beoordeling(d,k='expertise');d['aanbieders'][0]['expertise']['waarde']=['FICTIEF trauma']
    r=beide(d,[b]);assert r['hash_gewijzigd'] and r['status']!='geverifieerd'
    origineel=deepcopy(d);indexdoc=Kwaliteitslezing({**d,'kwaliteitsbeoordelingen':[b]}).indexdocument(d)
    assert not indexdoc['aanbieders'][0]['expertise']['waarde'] and d==origineel


@pytest.mark.parametrize('url',[None,'javascript:alert(1)','http://localhost/zorg'])
def test_onbruikbare_bron_wordt_overal_herkend(url):
    d=document();d['aanbieders'][0]['expertise']['bron_url']=url
    assert beide(d,[])['status']=='tegenstrijdig_of_verouderd'


@pytest.mark.parametrize('ouderdom,status',[(30,'bron_te_controleren'),(31,'tegenstrijdig_of_verouderd'),(-1,'tegenstrijdig_of_verouderd')])
def test_wachttijd_actualiteit_grenzen(ouderdom,status,monkeypatch):
    monkeypatch.delenv('ZORGZOEKER_WACHTTIJD_MAX_DAGEN',raising=False)
    d=document();peil=(date.today()-timedelta(days=ouderdom)).isoformat()
    d['aanbieders'][0]['wachttijd']=veld('6 weken',toelichting='Peildatum: '+peil)
    assert beide(d,[],'wachttijd')['status']==status


def test_legacylabel_en_ophalen_worden_geen_inhoudelijke_verificatie():
    d=document();r=beide(d,[])
    assert r['status']=='bron_te_controleren' and r['methode']=='onbekend'
    assert r['herkomst']=='Openbare bron' and r['controle']=='Nog controleren'
    d['aanbieders'][0]['expertise']['label']='afgeleid'
    assert beide(d,[])['herkomst']=='Afgeleid'


def test_controle_en_actualiteit_blijven_afzonderlijk():
    d=document();b=beoordeling(d,k='expertise')
    r=beide(d,[b]);assert r['status']=='geverifieerd' and r['actualiteit']=='Geldigheid onbekend'
    b['geldig_van']=date.today().isoformat();b['geldig_tot']=(date.today()+timedelta(days=5)).isoformat()
    assert beide(d,[b])['actualiteit']=='Binnen vastgelegde periode'


def test_ontbrekende_wachttijd_wordt_niet_uit_review_ingevuld():
    d=document();d['aanbieders'][0]['wachttijd']=veld('onbekend',label='onbekend')
    b=beoordeling(d,k='wachttijd')
    assert beide(d,[b],'wachttijd')['status']=='ontbrekend'


def test_historische_datum_projecteert_controle_niet_terug():
    d=document();b=beoordeling(d,k='expertise')
    r=beoordeel_veld(d['aanbieders'][0],'expertise',[b],date.today()-timedelta(days=1))
    assert r['status']=='bron_te_controleren' and r['actualiteit']=='Nog niet gecontroleerd op beoordelingsdatum'
