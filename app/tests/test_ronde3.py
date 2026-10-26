"""Ronde 3: fictieve hulpvragen en controle van openbare, bestaande brondata."""
from copy import deepcopy
from datetime import date, timedelta
from pathlib import Path
import json

import pytest
from fastapi.testclient import TestClient

from zorgzoeker.app import maak_app, _kaart
from zorgzoeker.beschikbaarheid import (
    VELDEN, actueel, conceptverzoek, keur_verzoek_goed, maak_linkbewijs,
    neem_op, relevante_regels, stop_actief, valideer_regel, verbruik_linkbewijs,
    verouderde_regels, voorstel,
)
from zorgzoeker.contracten import Contractregister, _stop
from zorgzoeker.kaarten import samenvatting
from zorgzoeker.valideer import valideer_document, _valideer_wachttijd
from zorgzoeker.weergave import toon_veld
from zorgzoeker.zoeken import Filters, Index, Treffer, analyseer_vraag, _past_wachttijd
from tests.test_betrouwbaarheid import aanbieder, index_van, veld
from tests.test_validatie import _minimaal_geldig

DATA = Path(__file__).resolve().parents[1] / 'data/aanbieders.json'


@pytest.fixture(scope='module')
def echt():
    doc = json.loads(DATA.read_text())
    return doc, Index(doc), TestClient(maak_app(DATA))


def regel(**extra):
    vandaag = date.today()
    r = dict.fromkeys(VELDEN)
    r.update(id='fictief-regel', aanbieder_id='fictief', dienst='FICTIEF angstbehandeling',
             nieuwe_clienten='ja', capaciteit=2, regios=[], intake_weken=3,
             start_behandeling_weken=7, verificatie='aanbieder_bevestigd',
             bevestigd_op=vandaag.isoformat(), herbevestigen_op=(vandaag+timedelta(days=30)).isoformat(),
             bron_url='https://example.org/fictieve-bevestiging')
    r.update(extra)
    return r


@pytest.mark.parametrize('vraag,leeftijden', [
    ('puber van 15 met angst', [15]), ('tiener van 15 met angst', [15]),
    ('kinderen van 6 en 14 met angst', [6,14]), ('kinderen van 6, 10 en 14 jaar met angst', [6,10,14]),
    ('17,5 jaar angst', [17.5]), ('14jr angst', [14]),
])
def test_alle_leeftijden_herkend(vraag, leeftijden):
    a = analyseer_vraag(vraag, {}, set())
    assert a.leeftijden == leeftijden
    i = index_van(aanbieder('breed', leeftijd='Kinderen 0-18 jaar'),
                  aanbieder('ouder', leeftijd='Jongeren vanaf 16 jaar'))
    ids = {t.id for t in i.zoek(vraag)}
    assert 'breed' in ids
    assert ('ouder' in ids) == all(n >= 16 for n in leeftijden)


def test_meerdere_kinderen_geen_verlies_door_gaten_in_leeftijdsgroepen():
    i = index_van(aanbieder('beide', doelgroepen=veld(['Kinderen 4-8 jaar', 'Jongeren 12-17 jaar'])),
                  aanbieder('alleen-jong', leeftijd='Kinderen 4-8 jaar'),
                  aanbieder('alleen-oud', leeftijd='Kinderen 12-17 jaar'))
    assert {t.id for t in i.zoek('kinderen van 6 en 14 met angst')} == {'beide'}


@pytest.mark.parametrize('vraag', ['geen medicatie, wel hulp bij angst', 'zonder medicatie hulp bij angst',
                                    'medicatie niet gewenst bij angst'])
def test_medicatie_negatie_behoudt_angst(vraag):
    i = index_van(aanbieder('gesprek', expertise=['Angst']),
                  aanbieder('medicatie', expertise=['Angst', 'Medicamenteuze behandeling']))
    a = analyseer_vraag(vraag, {}, set())
    assert a.concepten == ['angst']
    assert a.uitgesloten == ['medicatie']
    assert {t.id for t in i.zoek(vraag)} == {'gesprek'}


@pytest.mark.parametrize('vorm', ['ADHD', 'AD(H)D', 'AD (H) D'])
def test_adhd_ass_vereist_aantoonbare_combinatie(vorm):
    i = index_van(aanbieder('beide', expertise=['AD(H)D', 'ASS']),
                  aanbieder('ass', expertise=['Autisme']), aanbieder('geen-bewijs', expertise=['Speltherapie']))
    rs = i.zoek(f'{vorm} en ASS')
    assert rs[0].id == 'beide'
    assert not rs[0].ontbrekende_expertise
    assert next(t for t in rs if t.id == 'ass').ontbrekende_expertise == ['adhd']
    assert 'geen-bewijs' not in {t.id for t in rs}


@pytest.mark.parametrize('plaats', ['Groesbeek','Berg en Dal'])
def test_gemeente_en_kern_gelijke_dekking_en_aparte_vestiging(echt, plaats):
    _, i, _ = echt
    verwacht = {t.id for t in i.zoek('', Filters(gemeente='Berg en Dal'))}
    assert {t.id for t in i.zoek('', Filters(gemeente=plaats))} == verwacht
    assert {t.id for t in i.zoek('angst in Groesbeek')} == {t.id for t in i.zoek('angst in Berg en Dal')}
    assert 'Groesbeek' not in i.filteropties()['plaatsen']
    assert 'Groesbeek' in i.filteropties()['vestigingsplaatsen']
    assert '0-tot-18' not in {t.id for t in i.zoek('', Filters(vestigingsplaats='Groesbeek'))}


def test_stop_vindbaar_op_naam_en_toon_alle_maar_niet_als_advies(echt):
    doc, i, client = echt
    assert len(i.zoek('')) == len(doc['aanbieders']) == 189
    for q in ('Sentio', ''):
        t = next(t for t in i.zoek(q) if t.id == 'sentio')
        assert t.contracttoets['stop_actief']
        kaart = _kaart(t, q)
        assert 'Nee' in kaart['aanname_kort']
        assert any('STOP' in w for w in kaart['waarschuwingen_kort'])
    assert 'sentio' not in {t.id for t in i.zoek('angst')}
    html = client.get('/', params={'q':'Sentio'}).text
    kern, details = html.split('<details class="meer">', 1)
    assert 'STOP' in kern and 'Aanmeldstop' in kern
    assert 'Kerstvakantie' in kern  # Geen verzonnen einddatum.
    assert 'class="bron"' not in kern.split('<article class="kaart')[1]
    assert 'bronpeildatum' in kern
    assert 'praktijk-sentio.nl/praktische-informatie' in details


def test_stop_per_gemeente_product_en_periode():
    p = aanbieder('fictief', gecontracteerd_regio=veld('ja'))
    r = {'aanbieder_id':'fictief', 'productcode':'JW 45A04','gemeenten':['berg en dal', 'nijmegen'],
         'hoofdaannemer':'FICTIEF Hoofd', 'opmerkingen':['Toeleidingsstop Groesbeek per 1-10-2026 tot 1 november 2026']}
    register = Contractregister({'contractregister':{'peildatum':'2026-10-23','regels':[r]}})
    for plaats in ('groesbeek','berg en dal'):
        assert register.oordeel(p, gemeente=plaats, codes=['JW 45A04'], op_datum='2026-10-26')['toeleiding'] == 'geblokkeerd'
        assert register.oordeel(p, gemeente=plaats, codes=['JW 45A04'], op_datum='2026-11-02')['toeleiding'] != 'geblokkeerd'
    assert register.oordeel(p, gemeente='nijmegen', codes=['JW 45A04'])['toeleiding'] != 'geblokkeerd'
    assert register.oordeel(p, gemeente='groesbeek', codes=['JW 45A55'])['toeleiding'] != 'geblokkeerd'
    assert not _stop('Geen aanmeldstop', 'nijmegen', '2026-10-25')


@pytest.mark.parametrize('status,label,tekst', [
    ('ja','geverifieerd','Bevestigd gecontracteerd'),
    ('nee','geverifieerd','Bevestigd niet-gecontracteerd'),
    ('nee','afgeleid','Niet aangetroffen in beschikbare contractbronnen'),
    ('onbekend','onbekend','Contractstatus onbekend'),
])
def test_vier_contractstatussen_en_filters(status,label,tekst):
    p = aanbieder('fictief', gecontracteerd_regio=veld(status,label=label,toelichting='FICTIEF brongegeven'))
    i = index_van(p)
    t = i.zoek('')[0]
    assert samenvatting(t)['contract_kort'] == tekst
    if status == 'nee':
        f = 'bevestigd_nee' if label == 'geverifieerd' else 'niet_aangetroffen'
        assert i.zoek('', Filters(gecontracteerd=f))
        ander = 'niet_aangetroffen' if f == 'bevestigd_nee' else 'bevestigd_nee'
        assert not i.zoek('', Filters(gecontracteerd=ander))


def test_onderaannemer_nooit_als_rechtstreeks_en_codes_per_vraag(echt):
    _, i, _ = echt
    for product in ('JW 45A04', 'JW 45A55'):
        t = next(t for t in i.zoek('Apollis Zorg', Filters(gemeente='Nijmegen', productcode=product)) if t.id=='apollis-zorg')
        k = samenvatting(t)
        assert 'Via hoofdaannemer' in k['route_kort']
        assert 'Rechtstreeks' not in k['route_kort']
        assert k['codes_kort'] == [product]
        assert t.contracttoets['stop_actief'] == (product=='JW 45A04')


@pytest.mark.parametrize('tekst', ['gemiddeld 13 weken', 'indicatie 6–8 weken', 'indicatie: 6 weken'])
def test_gepubliceerde_indicatie_nooit_actuele_beschikbaarheid(tekst):
    vandaag = date.today().isoformat()
    v = veld(tekst, opgehaald_op=vandaag, toelichting=f'Peildatum: {vandaag}')
    assert _valideer_wachttijd('fictief', {'wachttijd':v}) == []
    getoond = toon_veld('wachttijd',v)
    assert getoond['tekst'] == 'onbekend'
    assert getoond['publicatie_tekst'] == tekst
    assert getoond['indicatief']
    assert not _past_wachttijd(v, 20)
    t = Treffer('x','FICTIEF',0,'',1,aanbieder('x', wachttijd=v))
    assert 'Onbekend' in samenvatting(t)['wachttijd_kort']
    assert 'Onbekend' in samenvatting(t)['aanname_kort']


def test_gemiddelde_in_bestaande_data_blijft_behouden(echt):
    doc, i, _ = echt
    p = next(p for p in doc['aanbieders'] if p['id']=='1-1-vier')
    v = toon_veld('wachttijd',p['wachttijd'])
    assert v['indicatief'] and v['publicatie_tekst'] == p['wachttijd']['waarde']
    assert v['tekst'] == 'onbekend'


def test_register_workflow_bewaart_bron_en_historie():
    doc = {'aanbieders':[{'id':'fictief'}]}
    origineel = deepcopy(doc)
    r = regel()
    assert not valideer_regel(r)
    v = voorstel(doc,r)
    for kwargs in ({}, {'expliciet':True}, {'beoordelaar':'controleur'}):
        with pytest.raises(ValueError):
            neem_op(doc,v,beoordelaar=kwargs.get('beoordelaar',''),expliciet=kwargs.get('expliciet',False))
    nieuw = neem_op(doc,v,beoordelaar='FICTIEF controleur',expliciet=True)
    assert doc == origineel
    assert nieuw['beschikbaarheidsregister'] == [r]
    assert nieuw['beschikbaarheidshistorie'][0]['vorige'] is None
    assert not verouderde_regels(nieuw)
    concept = conceptverzoek(nieuw,r['id'])
    assert concept['status'] == 'concept_niet_verstuurd'
    with pytest.raises(ValueError):
        keur_verzoek_goed(concept,beoordelaar='controleur')
    assert keur_verzoek_goed(concept,beoordelaar='controleur',expliciet=True)['status'] == 'goedgekeurd_niet_verstuurd'
    ander = deepcopy(nieuw); ander['aanbieders'].append({'id':'gewijzigd'})
    with pytest.raises(ValueError,match='Bron gewijzigd'):
        neem_op(ander,voorstel(nieuw,r),beoordelaar='controleur',expliciet=True)
    wijzig = voorstel(nieuw,regel(intake_weken=5))
    vervanging = neem_op(nieuw,wijzig,beoordelaar='controleur',expliciet=True)
    assert vervanging['beschikbaarheidshistorie'][-1]['vorige'] == r
    assert nieuw['beschikbaarheidsregister'][0]['intake_weken'] == 3


@pytest.mark.parametrize('extra', [dict(intake_weken=-1),dict(intake_weken='± 6'),dict(capaciteit=True),
                                  dict(nieuwe_clienten='misschien'), dict(herbevestigen_op=None),
                                  dict(bron_url='javascript:alert(1)'),dict(verificatie='ai_aangenomen'),
                                  dict(leeftijd_van=18,leeftijd_tot=12),dict(intake_weken=float('nan'))])
def test_register_weigert_onbetrouwbare_waarden(extra):
    assert valideer_regel(regel(**extra))
    with pytest.raises(ValueError):
        voorstel({'aanbieders':[{'id':'fictief'}]},regel(**extra))


def test_register_veroudering_en_scope_geen_ja_zonder_bevestiging():
    r = regel(regios=['Berg en Dal'], productcode='JW 45A04', locatie='Groesbeek',leeftijd_van=12, leeftijd_tot=17)
    doc = {'beschikbaarheidsregister':[r]}
    kwargs = dict(gemeente='Groesbeek',codes=['JW 45A04'],leeftijden=[15],locatie='Groesbeek')
    assert relevante_regels(doc,'fictief',**kwargs) == [r]
    for k,v in [('gemeente','Nijmegen'),('codes',['JW 45A55']),('leeftijden',[6]),('locatie','Nijmegen')]:
        assert not relevante_regels(doc,'fictief',**{**kwargs,k:v})
    assert not relevante_regels(doc,'fictief')
    assert actueel(r)
    assert not actueel(r, date.fromisoformat(r['herbevestigen_op']))
    for v in ('gepubliceerd','historisch'):
        pub = regel(verificatie=v, gepubliceerd_op=date.today().isoformat())
        assert not actueel(pub)
        assert verouderde_regels({'beschikbaarheidsregister':[pub]})
    gestopt = regel(stop={'soort':'aanmeldstop','vanaf':'2026-01-01','tot':None,'toelichting':'FICTIEF stop'})
    assert stop_actief(gestopt,date(2027,1,1))  # stopt niet bij veroudering
    gestopt['stop']['tot']='2026-12-31'
    assert not stop_actief(gestopt,date(2027,1,1))


def test_register_actuele_kaart_en_stops_zijn_gescheiden_van_contract():
    p = aanbieder('fictief',gecontracteerd_regio=veld('ja'))
    r = regel(nieuwe_clienten='nee')
    doc = {'aanbieders':[p], 'beschikbaarheidsregister':[r]}
    i = Index(doc)
    assert not i.zoek('angst')
    t = i.zoek('')[0]
    assert t.contracttoets['status']=='ja' and t.contracttoets['stop_actief']
    k = samenvatting(t)
    assert 'Nee' in k['aanname_kort'] and 'intake: 3 weken' in k['wachttijd_kort']
    doc['beschikbaarheidsregister'][0] = regel()
    k = samenvatting(Index(doc).zoek('')[0])
    assert 'Ja — door aanbieder bevestigd' in k['aanname_kort']
    assert 'start behandeling: 7 weken' in k['wachttijd_kort']
    doc['beschikbaarheidsregister'][0]['herbevestigen_op']=date.today().isoformat()
    k = samenvatting(Index(doc).zoek('')[0])
    assert 'Onbekend' in k['aanname_kort'] and k['wachttijd_kort']=='Onbekend'


def test_register_schema_blokkeert_ongeldige_of_dubbele_regels():
    doc=_minimaal_geldig()
    r=regel(aanbieder_id=doc['aanbieders'][0]['id'])
    doc['beschikbaarheidsregister']=[r]
    assert not valideer_document(doc)
    doc['beschikbaarheidsregister'].append(deepcopy(r))
    assert any('dubbel' in f for f in valideer_document(doc))
    doc['beschikbaarheidsregister']=[regel(aanbieder_id='bestaat-niet')]
    assert any('onbekende aanbieder' in f for f in valideer_document(doc))


def test_linkbewijs_begrensd_eenmalig_en_alleen_voorstel():
    from datetime import datetime, timezone
    nu=datetime(2026,10,25,tzinfo=timezone.utc)
    token,bewijs=maak_linkbewijs('fictief','regel',nu=nu)
    assert token not in json.dumps(bewijs)
    for tok,aid,rid,tijd in [(token,'ander','regel',nu),('fout','fictief','regel',nu),
                             (token,'fictief','ander',nu),(token,'fictief','regel',nu+timedelta(hours=48))]:
        with pytest.raises(ValueError):
            verbruik_linkbewijs(bewijs,tok,aid,rid,nu=tijd)
    gebruikt=verbruik_linkbewijs(bewijs,token,'fictief','regel',nu=nu)
    with pytest.raises(ValueError):
        verbruik_linkbewijs(gebruikt,token,'fictief','regel',nu=nu)
    assert not bewijs['verbruikt']


def test_essentiele_kaartinfo_details_en_brondata_behouden(echt):
    doc,i,client=echt
    origineel=deepcopy(doc)
    html=client.get('/',params={'alles':'1'}).text
    assert html.count('<details class="meer">') == len(doc['aanbieders'])
    assert '<details class="meer" open' not in html
    for t in i.zoek(''):
        k=_kaart(t)
        assert {'contract_kort','route_kort','leeftijd_kort','wachttijd_kort','aanname_kort'} <= k.keys()
        assert set(t.aanbieder)-{'id','gevonden_via','_kwaliteit'} <= {v['sleutel'] for v in k['detail_velden']}
    assert doc == origineel
    assert 'Details, voorwaarden en bronnen' in html
    assert 'Productcodes' in html and 'Vestigingen' in html and 'KvK-nummer' in html
    assert 'window.matchMedia' not in (Path(__file__).resolve().parents[1]/'zorgzoeker/statisch/app.js').read_text()


def test_register_maximum_gaat_over_start_behandeling_niet_intake():
    p=aanbieder('fictief')
    doc={'aanbieders':[p],'beschikbaarheidsregister':[regel(intake_weken=1,start_behandeling_weken=7)]}
    assert not Index(doc).zoek('angst maximaal twee weken')
    assert Index(doc).zoek('angst maximaal 8 weken')
    doc['beschikbaarheidsregister'][0]['start_behandeling_weken']=None
    assert not Index(doc).zoek('angst maximaal 8 weken')
    doc['beschikbaarheidsregister'][0]=regel(start_behandeling_weken=1)
    doc['beschikbaarheidsregister'].append(regel(id='ander',start_behandeling_weken=8))
    assert not Index(doc).zoek('angst maximaal twee weken')


def test_oude_of_gepubliceerde_registerregel_geeft_geen_actueel_ja():
    for r in [regel(verificatie='gepubliceerd',gepubliceerd_op=date.today().isoformat()),
              regel(bevestigd_op=(date.today()-timedelta(days=31)).isoformat(),herbevestigen_op=date.today().isoformat())]:
        doc={'aanbieders':[aanbieder('fictief')], 'beschikbaarheidsregister':[r]}
        t=Index(doc).zoek('angst')[0]
        k=samenvatting(t)
        assert 'Onbekend' in k['aanname_kort'] and k['wachttijd_kort']=='Onbekend'
        assert k['beschikbaarheidsdetails'] and not k['beschikbaarheidsdetails'][0]['actueel']
        assert not Index(doc).zoek('angst maximaal 8 weken')


def test_dienstspecifieke_stop_wordt_niet_algemeen_gemaakt():
    p=aanbieder('fictief',gecontracteerd_regio=veld('ja'),productcodes=veld([{'code':'JW 45A04','omschrijving':'Begeleiding'},
                                           {'code':'JW 45A55','omschrijving':'Begeleiding intensief'}]))
    r=regel(productcode='JW 45A04',regios=['Nijmegen'],stop={
        'soort':'toeleidingsstop','vanaf':date.today().isoformat(),'tot':None,'toelichting':'FICTIEF stop'})
    doc={'meta':{'regio':'Rijk van Nijmegen'}, 'aanbieders':[p], 'beschikbaarheidsregister':[r]}
    i=Index(doc)
    assert not i.zoek('angst',Filters(gemeente='Nijmegen',productcode='JW 45A04'))
    assert i.zoek('angst',Filters(gemeente='Nijmegen',productcode='JW 45A55'))
    assert i.zoek('angst',Filters(productcode='JW 45A04'))  # scope onbekend: geen algemene stop afleiden
    kaart=samenvatting(i.zoek('',Filters(gemeente='Nijmegen',productcode='JW 45A04'))[0])
    assert any('STOP' in w for w in kaart['waarschuwingen_kort'])


def test_kaart_escapet_brontekst_en_verwijzingsprocedure_blijft_beschikbaar(tmp_path):
    doc=_minimaal_geldig()
    p=doc['aanbieders'][0]
    p['expertise']=veld(['Angst <script>alert(1)</script>'])
    p['aanmeldprocedure']=veld('FICTIEF: eerst gemeentelijke verwijzing, daarna contact met hoofdaannemer')
    p['uitsluitingscriteria']=veld('FICTIEF: uitsluitend vanaf 12 jaar')
    path=tmp_path/'fixture.json';path.write_text(json.dumps(doc))
    response=TestClient(maak_app(path)).get('/',params={'alles':'1'})
    assert response.status_code==200
    assert '<script>alert(1)</script>' not in response.text
    assert '&lt;script&gt;' in response.text
    kern,details=response.text.split('<details class="meer">',1)
    assert 'eerst gemeentelijke verwijzing' not in kern
    assert 'eerst gemeentelijke verwijzing' in details
    assert 'uitsluitend vanaf 12 jaar' in kern  # belangrijke voorwaarden niet verstoppen


def test_stops_zonder_datumfilter_toetsen_vandaag_niet_de_oude_snapshot(monkeypatch):
    import zorgzoeker.contracten as c
    class Later(date):
        @classmethod
        def today(cls):
            return cls(2026,11,2)
    monkeypatch.setattr(c,'date',Later)
    p=aanbieder('fictief',beschikbaarheid=veld('Aanmeldstop tot 1 november 2026'),gecontracteerd_regio=veld('ja'))
    assert not c.algemene_stop(p,'nijmegen')
    r={'aanbieder_id':'fictief','productcode':'JW 45A04','gemeenten':['nijmegen'],
       'hoofdaannemer':None,'opmerkingen':['Toeleidingsstop tot 1 november 2026']}
    toets=Contractregister({'contractregister':{'peildatum':'2026-10-23','regels':[r]}}).oordeel(p,gemeente='nijmegen')
    assert toets['toeleiding']!='geblokkeerd'
    p['wachttijd']=veld('18+: aanmeldstop tot 1 november 2026')
    assert not c.algemene_stop(p,'nijmegen',leeftijd=18)


def test_vergelijking_toont_intake_en_behandelstart_apart():
    from zorgzoeker.weergave import vergelijk_rijen
    p=aanbieder('fictief')
    i=Index({'aanbieders':[p],'beschikbaarheidsregister':[regel()]})
    toets=i.contracttoets_voor('fictief')
    rijen=vergelijk_rijen([p,p],[toets,toets])
    actuele={r['sleutel']:r for r in rijen if r['label_nl'].startswith('Actueel bevestigd:')}
    assert actuele['intake_weken']['cellen'][0]['tekst']=='3 weken'
    assert actuele['start_behandeling_weken']['cellen'][0]['tekst']=='7 weken'
    assert actuele['nieuwe_clienten']['cellen'][0]['tekst']=='ja'
