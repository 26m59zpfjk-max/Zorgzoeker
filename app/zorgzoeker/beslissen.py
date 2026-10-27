"""Gedeelde, brongebonden beoordeling; geen opslag van zoekcontext."""
from dataclasses import dataclass,asdict,replace,field
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
    max_wachttijd: int|None = None
    zoekdoel: str = "gezamenlijk"
    wachttijd_soort: str = "start_behandeling"
    genoemde_plaatsen: list = field(default_factory=list)
    gemeente_bevestigd: bool = False


@dataclass
class Beoordeling:
    context: dict
    inhoud: dict
    leeftijden: list
    contract: dict
    instroom: dict
    controlepunten: list
    kwaliteit: dict
    criteria: list = field(default_factory=list)
    groep: str = "kandidaten"


class Beslisservice:
    def __init__(self,document,index=None):
        self.document=document;self.index=index or Index(document)
        self.kwaliteit=Kwaliteitslezing(document);self.versie=hashwaarde(document)
        self.ruw={a['id']:a for a in document['aanbieders']}
    def context(self,q,filters,leeftijden=None,concepten=None,uitsluitingen=None,zoekdoel="gezamenlijk",max_wachttijd=None,wachttijd_soort="start_behandeling"):
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
        if zoekdoel not in {'gezamenlijk','afzonderlijk','verkennen','kiezen'}:raise ValueError('Onbekend zoekdoel')
        if zoekdoel=='kiezen' and len(a.leeftijden)<=1:zoekdoel='gezamenlijk'
        if wachttijd_soort not in {'intake','start_behandeling'}:raise ValueError('Onbekende wachttijdsoort')
        if max_wachttijd == '':
            a=replace(a,max_wachttijd=None)
        elif max_wachttijd is not None:
            if type(max_wachttijd) is not int or not 0<=max_wachttijd<=520:raise ValueError('Ongeldige wachttijdgrens')
            a=replace(a,max_wachttijd=max_wachttijd)
        if set(a.concepten)&set(a.uitgesloten):raise ValueError('Gewenst en uitgesloten begrip overlappen')
        gemeente=filters.gemeente
        gemeente=self.index.plaatstabel.get((gemeente or '').lower(),gemeente)
        if gemeente and gemeente.lower() not in set(self.index.plaatstabel.values())|set(self.index.plaatstabel):raise ValueError('Gemeente niet bekend; kies een gemeente uit de lijst')
        datum=filters.op_datum or a.op_datum or date.today().isoformat()
        if not (len(datum)==4 and datum.isdigit()):date.fromisoformat(datum)
        return a,Zoekcontext(gemeente,a.leeftijden,a.concepten,a.uitgesloten,filters.productcode,datum,self.versie,max_wachttijd=a.max_wachttijd,zoekdoel=zoekdoel,wachttijd_soort=wachttijd_soort,genoemde_plaatsen=a.plaatsen,gemeente_bevestigd=bool(filters.gemeente))
    def beoordeel(self,id,q='',filters=None,*,analyse=None,context=None,dienst=None,profielbron=None):
        filters=filters or Filters()
        if analyse is None:analyse,context=self.context(q,filters)
        p=profielbron or self.ruw[id];profiel=self.index._profiel(p) if profielbron else self.index._op_id[id]
        if dienst is not None:context=replace(context,dienst=dienst)
        op=date.fromisoformat(context.op_datum) if len(context.op_datum)==10 else date.today()
        codes=list(analyse.codes)+([filters.productcode] if filters.productcode else [])
        t=self.index.contractregister.oordeel(p,gemeente=context.gemeente,codes=codes,op_datum=context.op_datum)
        leeftijden=[];alle_regels=[]
        for n in context.leeftijden or [None]:
            regels=relevante_regels(self.document,id,gemeente=context.gemeente,codes=codes,leeftijden=[n] if n is not None else [],locatie=filters.vestigingsplaats,dienst=dienst)
            dicht=t['toeleiding']=='geblokkeerd' or algemene_stop(p,context.gemeente,context.op_datum,n,[] if t['routes'] else codes) or any(stop_actief(r,date.fromisoformat(context.op_datum) if len(context.op_datum)==10 else date.today()) or (actueel(r,op) and r['nieuwe_clienten']=='nee') for r in regels)
            status=leeftijd_oordeel(n,n,profiel.doel_bereiken)[0] if n is not None else 'onbekend'
            leeftijden.append({'leeftijd':n,'status':status,'stop':dicht})
            for r in regels:
                if r not in alle_regels:alle_regels.append(r)
        k={v:self.kwaliteit.veld(p,v,vandaag=op) for v in ('expertise','doelgroepen','gecontracteerd_regio','wachttijd','beschikbaarheid','website')}
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
        if beschikbaar=='onbekend' and len(alle_regels)==1 and actueel(alle_regels[0],op) and alle_regels[0]['nieuwe_clienten']=='ja':beschikbaar='ja — aanbieder bevestigd'
        veld=p.get('gecontracteerd_regio') or {}
        bronstatus=('bevestigd niet-gecontracteerd' if veld.get('label')=='geverifieerd' else 'niet aangetroffen in contractbronnen') if t['status']=='nee' else ('vermeld in contractbron' if t['routes'] or t['status']=='ja' else 'onbekend')
        resultaat=asdict(Beoordeling(asdict(context),{'status':'bronbewijs gevonden' if dekt else 'onvoldoende bronbewijs','ontbreekt':ontbreekt,'expertise':(p.get('expertise') or {}).get('waarde'), 'kwaliteit':k['expertise']['status']},leeftijden,
            {'bronstatus':bronstatus,'geldigheid':t['status'] if context.gemeente else 'onbekend','peildatum':t['peildatum'],'routes':t['routes'],'bron_url':t['bron_url'],'waarschuwingen':t['waarschuwingen']},
            {'status':beschikbaar,'stop':any(x['stop'] for x in leeftijden),'wachttijd':toon_veld('wachttijd',p.get('wachttijd')),'bevestigingen':alle_regels},list(dict.fromkeys(punten)),k))
        resultaat['contract']['redenen_onzeker']=[]
        redenen=resultaat['contract']['redenen_onzeker']
        if not context.gemeente:redenen.append('verantwoordelijke_gemeente_onbevestigd')
        if not codes:redenen.append('hulpvorm_niet_productgebonden_vastgesteld')
        if not t['routes']:redenen.append('geen_toepasselijke_contractroute')
        if t['status']=='onbekend':redenen.append('geldigheid_niet_onderbouwd')
        if not context.gemeente or not codes:resultaat['contract']['geldigheid']='onbekend'
        resultaat['contract']['bronvermelding']=self.index.contractregister.oordeel(p,gemeente=context.gemeente,codes=codes,op_datum=None)['status']
        import re
        bronnotities=[str((p.get('beschikbaarheid') or {}).get('waarde',''))]+[str(note) for route in t['routes'] for note in route.get('opmerkingen',[])]
        mogelijk=any(re.search(r'(?:aanmeld|toeleidings|cliënten)stop',re.sub(r'\b(?:geen|zonder)\s+(?:aanmeld|toeleidings|cliënten)stop','',n,flags=re.I),re.I) for n in bronnotities)
        resultaat['instroom']['scopewaarschuwing']='Bron noemt een beperking; kies de gemeente en controleer scope en periode.' if not context.gemeente and mogelijk and not resultaat['instroom']['stop'] else None
        resultaat['instroom']['wachttijd_oordeel']=self._wachttijd(alle_regels,p,context,op)
        resultaat['criteria']=self._criteria(profiel,analyse,filters,context,resultaat,dekt,ontbreekt)
        statussen={x['status'] for x in resultaat['criteria']}
        resultaat['groep']='uitgesloten' if 'voldoet niet' in statussen else ('kandidaten' if 'onbekend' in statussen else 'onderbouwd')
        return resultaat
    @staticmethod
    def _wachttijd(regels,p,context,op):
        """Alleen een toepasselijke, actuele bevestiging bewijst behandelstart/intake."""
        antwoord={'status':'onbekend','weken':None,'soort':context.wachttijd_soort,'bevestigd_op':None,'herbevestigen_op':None,
                  'reden':'Geen actuele, eenduidige aanbiederbevestiging voor deze context.'}
        if len(regels)==1:
            r=regels[0]
            antwoord.update(bevestigd_op=r.get('bevestigd_op'),herbevestigen_op=r.get('herbevestigen_op'))
            sleutel='intake_weken' if context.wachttijd_soort=='intake' else 'start_behandeling_weken'
            if actueel(r,op) and r.get(sleutel) is not None:
                weken=r[sleutel]
                antwoord.update(weken=weken,status='voldoet' if context.max_wachttijd is None or weken<=context.max_wachttijd else 'voldoet niet',
                                reden='Door aanbieder bevestigd binnen de vastgelegde herbevestigingsperiode.')
        return antwoord

    def _criteria(self,profiel,analyse,filters,context,b,dekt,ontbreekt):
        criteria=[]
        def voeg(sleutel,status,reden):criteria.append({'sleutel':sleutel,'status':status,'reden':reden})
        inhoud_gewenst=bool(analyse.concepten or analyse.codes)
        if inhoud_gewenst:
            status='voldoet' if dekt and not ontbreekt else ('onbekend' if dekt else 'voldoet niet')
            if status=='voldoet' and b['kwaliteit']['expertise']['status']!='geverifieerd':status='onbekend'
            voeg('hulpvraag',status,'Aanknopingspunt in profiel; controleer inhoud en ontbrekende expertise.' if status=='onbekend' else ('Aansluiting in gecontroleerde bron.' if status=='voldoet' else 'Gevraagde expertise niet onderbouwd in profiel.'))
        if not context.gemeente:voeg('verantwoordelijke_gemeente','onbekend','Kies de verantwoordelijke gemeente; een genoemde plaats is geen bevestiging.')
        if b['contract']['geldigheid']=='onbekend':voeg('contractcontext','onbekend','Contract voor deze gemeente, hulpvorm en datum nog te controleren.')
        if context.leeftijden:
            statussen={x['status'] for x in b['leeftijden']}
            voeg('leeftijd','voldoet niet' if 'buiten' in statussen else ('onbekend' if 'onbekend' in statussen else 'voldoet'),'Leeftijd getoetst aan gepubliceerd doelgroepbereik, per gevraagde leeftijd.')
        if context.gemeente:
            past=self.index._plaatsfilter(profiel,context.gemeente)
            voeg('gemeente','voldoet' if past else 'voldoet niet','Gemeentelijke dekking getoetst; vestigingsplaats is een afzonderlijk criterium.')
        if filters.vestigingsplaats:
            from zorgzoeker.zoeken import plaats_match
            voeg('vestigingsplaats','voldoet' if any(plaats_match(filters.vestigingsplaats,x) for x in profiel.vestiging_plaatsen) else 'voldoet niet','Vestigingsplaats uit profiel.')
        if filters.doelgroep:
            from zorgzoeker.zoeken import normaliseer
            voeg('doelgroep','voldoet' if any(normaliseer(filters.doelgroep) in normaliseer(x) for x in profiel.doelgroepen) else 'voldoet niet','Gekozen doelgroeptekst uit profiel.')
        if filters.productcode:
            from zorgzoeker.zoeken import _code_token
            voeg('productcode','voldoet' if _code_token(filters.productcode) in profiel.code_tokens else 'voldoet niet','Productcode getoetst aan bronprofiel; geen garantie op actuele contractgeldigheid.')
        if context.uitsluitingen:
            overlap=set(context.uitsluitingen)&profiel.bewijzen.keys()
            voeg('uitsluitingen','voldoet niet' if overlap else 'onbekend','Uitgesloten methode genoemd: '+', '.join(sorted(overlap)) if overlap else 'Niet vermeld is geen bevestiging dat uitgesloten behandeling achterwege kan blijven.')
        contractwens=filters.gecontracteerd or analyse.contract
        if contractwens:
            # Legacy ja/nee zonder datum betreft bronvermelding; het criterium noemt dat expliciet.
            datum_expliciet=bool(filters.op_datum or analyse.op_datum)
            status=b['contract']['geldigheid'] if datum_expliciet else b['contract']['bronvermelding']
            gewenst='nee' if contractwens in ('bevestigd_nee','niet_aangetroffen') else contractwens
            if status=='onbekend':uitkomst='onbekend'
            else:
                uitkomst='voldoet' if status==gewenst else 'voldoet niet'
                if contractwens in ('bevestigd_nee','niet_aangetroffen') and status=='nee':
                    verwacht='geverifieerd' if contractwens=='bevestigd_nee' else 'afgeleid'
                    if (profiel.ruw.get('gecontracteerd_regio') or {}).get('label')!=verwacht:uitkomst='voldoet niet'
            voeg('contractgeldigheid' if datum_expliciet else 'contractbron',uitkomst,('Geldigheid op '+context.op_datum if datum_expliciet else 'Vermelding in contractbron met peildatum '+str(b['contract']['peildatum']))+'; een bronmoment bewijst geen andere periode.')
        voeg('stop','voldoet niet' if b['instroom']['stop'] else 'onbekend','Relevante stop: aanmelden niet mogelijk.' if b['instroom']['stop'] else 'Geen relevante stop vastgesteld; dat bewijst geen actuele aanname.')
        if b['instroom']['status']=='ja — aanbieder bevestigd':criteria[-1]['status']='voldoet';criteria[-1]['reden']='Actuele aanname door aanbieder bevestigd.'
        if context.max_wachttijd is not None:
            w=b['instroom']['wachttijd_oordeel'];voeg('wachttijd',w['status'],w['reden'])
        return criteria

    def selecteer(self,q,filters,ids,**correcties):
        a,c=self.context(q,filters,**correcties)
        return {'interpretatie':getattr(a,'interpretatiefragmenten',[]),'context':asdict(c),'resultaten':[{'id':i,'naam':self.ruw[i]['naam']['waarde'],'beoordeling':self.beoordeel(i,filters=filters,analyse=a,context=c)} for i in ids],
                'afgevallen':[],'meldingen':[]}

    def zoek(self,q,filters=None,**correcties):
        filters=filters or Filters();a,c=self.context(q,filters,**correcties)
        specifiek=bool(a.concepten or a.codes or any(self.index._naamvraag(a,p) for p in self.index.profielen))
        keuze_nodig=len(c.leeftijden)>1 and c.zoekdoel=='kiezen'
        if keuze_nodig:
            return {'interpretatie':getattr(a,'interpretatiefragmenten',[]),'context':asdict(c),'resultaten':[],'afgevallen':[],'onderbouwd':[],'kandidaten':[],'uitgesloten':[],
                    'keuze_nodig':True,'deelopdrachten':[],'meldingen':['Kies één gezamenlijke aanbieder of afzonderlijk zoeken per leeftijd.']}
        if len(c.leeftijden)>1 and c.zoekdoel=='afzonderlijk':
            delen=[self.zoek(q,filters,**{**correcties,'leeftijden':[n],'zoekdoel':'gezamenlijk'}) for n in c.leeftijden]
            return {'interpretatie':getattr(a,'interpretatiefragmenten',[]),'context':asdict(c),'resultaten':[],'afgevallen':[],'onderbouwd':[],'kandidaten':[],'uitgesloten':[],
                    'keuze_nodig':False,'deelopdrachten':delen,'meldingen':['Afzonderlijke zoekroutes per leeftijd; geschiktheid is niet gezamenlijk beoordeeld.']}
        # Bestaande ranking/verbreding éénmaal; bij expliciete correcties dezelfde index met gewijzigde analyse.
        ts=self.index._zoek_geanalyseerd(a,filters) if set(correcties)&{'leeftijden','concepten','uitsluitingen','max_wachttijd'} else self.index.zoek(q,filters)
        resultaten=[{'id':t.id,'naam':t.naam,'reden':t.reden,'beoordeling':self.beoordeel(t.id,q,filters,analyse=a,context=c)} for t in ts]
        for x in resultaten:x['resultaatstatus']=x['beoordeling']['groep']
        groepen={'onderbouwd':[],'kandidaten':[],'uitgesloten':[]};gezien=set()
        for x in resultaten:
            groepen[x['beoordeling']['groep']].append(x);gezien.add(x['id'])
        for p in self.index.profielen:
            if p.id in gezien:continue
            dekt=self.index._inhoudelijke_dekking(p,a)[0]
            if not dekt and c.zoekdoel!='verkennen' and not self.index._naamvraag(a,p):continue
            b=self.beoordeel(p.id,q,filters,analyse=a,context=c)
            x={'id':p.id,'naam':p.naam,'reden':'Controleer de hieronder genoemde voorwaarden.','beoordeling':b,'resultaatstatus':b['groep']}
            groepen[b['groep']].append(x)
        afgevallen=[x for x in groepen['uitgesloten'] if x['beoordeling']['instroom']['stop'] or any(y['status']=='buiten' for y in x['beoordeling']['leeftijden'])]
        meldingen=[]
        if q.strip() and not specifiek and c.zoekdoel!='verkennen':
            meldingen.append('Verduidelijk welke hulp of ondersteuning nodig is. U kunt ook alle aanbieders bekijken.')
            resultaten=[];groepen={k:[] for k in groepen}
        if not groepen['onderbouwd'] and groepen['kandidaten']:
            meldingen.append('Geen bevestigde matches; wel kandidaten om te controleren.')
        elif not groepen['onderbouwd'] and not groepen['kandidaten']:
            meldingen.append('Geen kandidaten binnen deze vraag en filters.')
            if a.max_wachttijd is not None:meldingen.append('Een voldoende korte, betrouwbare wachttijd is mogelijk niet onderbouwd; bekijk kandidaten met ontbrekend bewijs.')
            if filters.op_datum:meldingen.append('Controleer of contractgeldigheid voor deze datum is onderbouwd.')
        return {'interpretatie':getattr(a,'interpretatiefragmenten',[]),'context':asdict(c),'resultaten':resultaten,'afgevallen':afgevallen,'meldingen':meldingen,**groepen,
                'keuze_nodig':False,'deelopdrachten':[], 'schema_versie':'5G', 'aantallen':{k:len(v) for k,v in groepen.items()},'groepen':groepen}
