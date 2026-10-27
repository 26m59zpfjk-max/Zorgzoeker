"""Fictieve regressies voor complete criteriumbeoordeling, zonder bronmutaties."""
from copy import deepcopy
from datetime import date,timedelta
from pathlib import Path
from unittest.mock import patch
import json
from zorgzoeker.beslissen import Beslisservice
from zorgzoeker.zoeken import Filters
from tests.test_betrouwbaarheid import aanbieder,veld
from tests.test_ronde3 import regel


def service(*ps,regels=()):
    return Beslisservice({'aanbieders':list(ps),'beschikbaarheidsregister':list(regels)})


def test_onbekende_wachttijden_blijven_kandidaat_geen_limietmatch():
    z=service(aanbieder('fictief'))
    r=z.zoek('14 jaar angst maximaal 20 weken')
    assert not r['resultaten'] and not r['onderbouwd']
    assert {x['id'] for x in r['kandidaten']}=={'fictief'}
    b=r['kandidaten'][0]['beoordeling']
    assert next(c for c in b['criteria'] if c['sleutel']=='wachttijd')['status']=='onbekend'
    assert r['context']['max_wachttijd']==20


def test_20_21_behandelstart_intake_en_stop_afzonderlijk():
    r=regel(start_behandeling_weken=21,intake_weken=2,stop=None)
    z=service(aanbieder('fictief'),regels=[r])
    a,c=z.context('angst maximaal 20 weken',Filters())
    b=z.beoordeel('fictief',analyse=a,context=c)
    assert b['instroom']['wachttijd_oordeel']['status']=='voldoet niet'
    a,c=z.context('angst maximaal 20 weken',Filters(),wachttijd_soort='intake')
    assert z.beoordeel('fictief',analyse=a,context=c)['instroom']['wachttijd_oordeel']['status']=='voldoet'
    r['start_behandeling_weken']=20
    assert z.beoordeel('fictief','angst maximaal 20 weken')['instroom']['wachttijd_oordeel']['status']=='voldoet'


def test_geen_gezamenlijke_uitspraak_voor_keuze():
    z=service(aanbieder('fictief'))
    r=z.zoek('Kinderen van 6 en 14 met angst',zoekdoel='kiezen')
    assert r['keuze_nodig'] and not r['resultaten'] and not r['kandidaten']


def test_afzonderlijk_leeftijdstop_niet_overdragen():
    r=regel(leeftijd_van=12,leeftijd_tot=17,stop={'soort':'aanmeldstop','vanaf':date.today().isoformat(),'tot':None,'toelichting':'FICTIEF stop voor oudere jeugdigen'})
    z=service(aanbieder('fictief'),regels=[r])
    result=z.zoek('Kinderen van 6 en 14 met angst',zoekdoel='afzonderlijk')
    jong,oud=result['deelopdrachten']
    assert jong['context']['leeftijden']==[6] and oud['context']['leeftijden']==[14]
    assert not jong['kandidaten'][0]['beoordeling']['instroom']['stop']
    assert oud['uitgesloten'][0]['beoordeling']['instroom']['stop']


def test_kandidaten_volledige_redenen_geen_negatie_laten_verdwijnen():
    z=service(aanbieder('fictief',leeftijd='Jongeren vanaf 16 jaar',expertise=['Angst','EMDR']))
    r=z.zoek('14 jaar angst geen EMDR')
    b=r['uitgesloten'][0]['beoordeling']
    assert {c['sleutel'] for c in b['criteria'] if c['status']=='voldoet niet'}>={'uitsluitingen','leeftijd'}
    assert not r['kandidaten'] and not r['onderbouwd']


def test_gewone_zoekvraag_een_reguliere_berekening():
    z=service(aanbieder('fictief'))
    with patch.object(z.index,'_zoek_geanalyseerd',wraps=z.index._zoek_geanalyseerd) as zoeken:
        z.zoek('14 jaar angst')
    assert zoeken.call_count==1


def test_selectie_zonder_volledige_zoekactie_en_brondata_behouden():
    z=service(aanbieder('fictief'));origineel=deepcopy(z.document)
    with patch.object(z.index,'zoek',side_effect=AssertionError('geen zoekactie')):
        r=z.selecteer('14 jaar angst',Filters(),['fictief'])
    assert len(r['resultaten'])==1 and z.document==origineel


def test_contractbron_filter_geen_actuele_geldigheid_suggereren():
    d=json.loads((Path(__file__).parents[1]/'data/aanbieders.json').read_text());z=Beslisservice(d)
    r=z.zoek('angst',Filters(gemeente='Nijmegen',gecontracteerd='ja'))
    assert r['resultaten']
    for x in r['resultaten']:
        b=x['beoordeling']
        assert next(c for c in b['criteria'] if c['sleutel']=='contractbron')['status']=='voldoet'
        assert b['contract']['geldigheid']=='onbekend'


def test_bevestiging_explicit_datum_referentie_geen_vandaag_mengen():
    r=regel(stop=None);z=service(aanbieder('fictief'),regels=[r])
    op=(date.fromisoformat(r['herbevestigen_op'])+timedelta(days=1)).isoformat()
    b=z.beoordeel('fictief','angst maximaal 20 weken',Filters(op_datum=op))
    assert b['instroom']['wachttijd_oordeel']['status']=='onbekend'
    assert b['instroom']['status']=='onbekend'


def test_gebruiker_kan_wachttijdgrens_wissen_zonder_hulpvraag_te_verliezen():
    z=service(aanbieder('fictief'))
    r=z.zoek('14 jaar angst maximaal 20 weken',max_wachttijd='')
    assert r['context']['max_wachttijd'] is None
    assert r['resultaten']
    assert not any(x['sleutel']=='wachttijd' for x in r['resultaten'][0]['beoordeling']['criteria'])
