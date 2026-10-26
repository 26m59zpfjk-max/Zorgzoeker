"""Gedeelde, brongebonden beoordeling; geen opslag van zoekcontext."""
from dataclasses import dataclass,asdict,replace
from datetime import date
from zorgzoeker.bewijs import Kwaliteitslezing,hashwaarde
from zorgzoeker.zoeken import Index,Filters,analyseer_vraag,leeftijd_oordeel,leeftijdsgrenzen
from zorgzoeker.contracten import algemene_stop
from zorgzoeker.beschikbaarheid import relevante_regels,actueel,stop_actief
from zorgzoeker.weergave import toon_veld
from zorgzoeker.synoniemen import CONCEPT_LABEL


@dataclass
class Zoekcontext:
    gemeente: str|None
    leeftijden: list
    concepten: list
    uitsluitingen: list
    productcode: str|None
    op_datum: str
    datasetversie: str
    dienst: str|None = None


@dataclass
class Beoordeling:
    context: dict
    inhoud: dict
    leeftijden: list
    contract: dict
    instroom: dict
    controlepunten: list
    kwaliteit: dict


class Beslisservice:
    def __init__(self,document,index=None):
        self.document=document;self.index=index or Index(document)
        self.kwaliteit=Kwaliteitslezing(document);self.versie=hashwaarde(document)
        self.ruw={a['id']:a for a in document['aanbieders']}
    def context(self,q,filters,leeftijden=None,concepten=None,uitsluitingen=None):
        a=analyseer_vraag(q,self.index.plaatstabel,self.index.bekende_codes)
        if leeftijden is not None:
            import math
            if len(leeftijden)>10 or any(type(n) not in (int,float) or not math.isfinite(n) or not 0<=n<=120 for n in leeftijden):raise ValueError('Ongeldige leeftijd')
            a=replace(a,leeftijden=leeftijden,leeftijd=leeftijden[0] if len(leeftijden)==1 else None,leeftijdsband=(min(leeftijden),max(leeftijden)) if leeftijden else None)
        if concepten is not None:
            if not isinstance(concepten,list) or any(not isinstance(c,str) or (c not in CONCEPT_LABEL and c!='medicatie') for c in concepten):raise ValueError('Onbekend begrip')
            a=replace(a,concepten=concepten,tokens=['c_'+c for c in concepten]+a.codes)
        if uitsluitingen is not None:
            if not isinstance(uitsluitingen,list) or any(not isinstance(c,str) or (c not in CONCEPT_LABEL and c!='medicatie') for c in uitsluitingen):raise ValueError('Onbekende uitsluiting')
            a=replace(a,uitgesloten=uitsluitingen)
        if set(a.concepten)&set(a.uitgesloten):raise ValueError('Gewenst en uitgesloten begrip overlappen')
        gemeente=filters.gemeente or (a.gemeenten[0] if len(a.gemeenten)==1 else None)
        gemeente=self.index.plaatstabel.get((gemeente or '').lower(),gemeente)
        datum=filters.op_datum or a.op_datum or date.today().isoformat()
        if not (len(datum)==4 and datum.isdigit()):date.fromisoformat(datum)
        return a,Zoekcontext(gemeente,a.leeftijden,a.concepten,a.uitgesloten,filters.productcode,datum,self.versie)
    def beoordeel(self,id,q='',filters=None,*,analyse=None,context=None,dienst=None,profielbron=None):
        filters=filters or Filters()
        if analyse is None:analyse,context=self.context(q,filters)
        p=profielbron or self.ruw[id];profiel=self.index._profiel(p) if profielbron else self.index._op_id[id]
        if dienst is not None:context=replace(context,dienst=dienst)
        codes=list(analyse.codes)+([filters.productcode] if filters.productcode else [])
        t=self.index.contractregister.oordeel(p,gemeente=context.gemeente,codes=codes,op_datum=context.op_datum)
        leeftijden=[];alle_regels=[]
        for n in context.leeftijden or [None]:
            regels=relevante_regels(self.document,id,gemeente=context.gemeente,codes=codes,leeftijden=[n] if n is not None else [],locatie=filters.vestigingsplaats,dienst=dienst)
            dicht=t['toeleiding']=='geblokkeerd' or algemene_stop(p,context.gemeente,context.op_datum,n,[] if t['routes'] else codes) or any(stop_actief(r,date.fromisoformat(context.op_datum) if len(context.op_datum)==10 else date.today()) or (actueel(r) and r['nieuwe_clienten']=='nee') for r in regels)
            status=leeftijd_oordeel(n,n,profiel.doel_bereiken)[0] if n is not None else 'onbekend'
            leeftijden.append({'leeftijd':n,'status':status,'stop':dicht})
            for r in regels:
                if r not in alle_regels:alle_regels.append(r)
        k={v:self.kwaliteit.veld(p,v) for v in ('expertise','doelgroepen','gecontracteerd_regio','wachttijd','beschikbaarheid','website')}
        dekt,ontbreekt=self.index._inhoudelijke_dekking(profiel,analyse)
        punten=[]
        if not context.gemeente:punten.append('Verantwoordelijke gemeente nog bevestigen; woonplaats is niet automatisch verantwoordelijke gemeente.')
        if t['status']=='onbekend':punten.append('Contractgeldigheid op beoordelingsdatum niet vastgesteld.')
        for v,b in k.items():
            if b['status']!='geverifieerd':punten.append(v+': '+b['status'])
        if ontbreekt:punten.append('Niet in bron bevestigd: '+', '.join(ontbreekt))
        if any(x['status']=='buiten' for x in leeftijden):punten.append('Leeftijd valt buiten gepubliceerd bereik.')
        if any(x['stop'] for x in leeftijden):punten.append('STOP: voor minstens één gevraagde leeftijd geldt een beperking.')
        beschikbaar='nee — relevante stop' if any(x['stop'] for x in leeftijden) else 'onbekend'
        if beschikbaar=='onbekend' and len(alle_regels)==1 and actueel(alle_regels[0]) and alle_regels[0]['nieuwe_clienten']=='ja':beschikbaar='ja — aanbieder bevestigd'
        veld=p.get('gecontracteerd_regio') or {}
        bronstatus=('bevestigd niet-gecontracteerd' if veld.get('label')=='geverifieerd' else 'niet aangetroffen in contractbronnen') if t['status']=='nee' else ('vermeld in contractbron' if t['routes'] or t['status']=='ja' else 'onbekend')
        return asdict(Beoordeling(asdict(context),{'status':'bronbewijs gevonden' if dekt else 'onvoldoende bronbewijs','ontbreekt':ontbreekt,'expertise':(p.get('expertise') or {}).get('waarde'), 'kwaliteit':k['expertise']['status']},leeftijden,
            {'bronstatus':bronstatus,'geldigheid':t['status'] if context.gemeente else 'onbekend','peildatum':t['peildatum'],'routes':t['routes'],'bron_url':t['bron_url'],'waarschuwingen':t['waarschuwingen']},
            {'status':beschikbaar,'stop':any(x['stop'] for x in leeftijden),'wachttijd':toon_veld('wachttijd',p.get('wachttijd')),'bevestigingen':alle_regels},list(dict.fromkeys(punten)),k))
    def zoek(self,q,filters=None,**correcties):
        filters=filters or Filters();a,c=self.context(q,filters,**correcties)
        ts=self.index._zoek_geanalyseerd(a,filters)
        if not correcties:ts=self.index.zoek(q,filters)
        resultaten=[{'id':t.id,'naam':t.naam,'reden':t.reden,'beoordeling':self.beoordeel(t.id,q,filters,analyse=a,context=c)} for t in ts]
        # Raadpleeg alleen inhoudelijk relevante afgevallen kandidaten; geen automatische versoepeling.
        gezien={x['id'] for x in resultaten};afgevallen=[]
        for p in self.index.profielen:
            if p.id in gezien or not self.index._inhoudelijke_dekking(p,a)[0]:continue
            b=self.beoordeel(p.id,q,filters,analyse=a,context=c)
            if b['instroom']['stop'] or any(x['status']=='buiten' for x in b['leeftijden']):
                afgevallen.append({'id':p.id,'naam':p.naam,'reden':'Niet geschikt voor alle geselecteerde toelatingsvoorwaarden','beoordeling':b})
        specifiek=bool(a.concepten or a.codes or any(self.index._naamvraag(a,p) for p in self.index.profielen))
        meldingen=[]
        if q.strip() and not specifiek:meldingen.append('Verduidelijk welke hulp of ondersteuning nodig is. U kunt ook alle aanbieders bekijken.')
        if not resultaten:
            meldingen.append('Geen resultaten binnen deze vraag en filters; dit bewijst niet dat passende zorg ontbreekt.')
            if a.max_wachttijd is not None:meldingen.append('Een voldoende korte, betrouwbare wachttijd is mogelijk niet onderbouwd.')
            if filters.op_datum:meldingen.append('Controleer of contractgeldigheid voor deze datum is onderbouwd.')
        return {'context':asdict(c),'resultaten':resultaten if specifiek or not q.strip() else [],'afgevallen':afgevallen,'meldingen':meldingen}
