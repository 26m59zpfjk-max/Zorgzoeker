"""Echte lokale modelbenchmark op bevroren fictieve casussen. Geen netwerkdownloads.

Geen assertions dat AI beter is; rapporteert fouten, fallback, latentie en kosten.
Mocks zijn geen alternatief voor dit script. Voer vanuit app/ uit.
"""
import argparse,json,time,statistics,sys,hashlib
from copy import deepcopy
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from zorgzoeker.ai_zoeken import HybrideZoeker,pas_interpretatie_aan
from zorgzoeker.ai_modellen import LokaalTaalmodel,E5Embeddings
from zorgzoeker.zoeken import Index,Filters


def maat(verwacht,gevonden):
    verwacht=set(verwacht);gevonden=set(gevonden)
    tp=len(verwacht&gevonden);fp=len(gevonden-verwacht);fn=len(verwacht-gevonden)
    return {'tp':tp,'fp':fp,'fn':fn,'precision':tp/(tp+fp) if tp+fp else (1 if not verwacht else 0),
            'recall':tp/(tp+fn) if tp+fn else 1,'exact':verwacht==gevonden}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--dataset',type=Path,default=Path('tests/ai/aanbieders.json'));p.add_argument('--vragen',type=Path,default=Path('tests/ai/vragen.json'));p.add_argument('--modelantwoorden',type=Path,help='Herhaal alleen zoeken met werkelijk eerder vastgelegde modelinterpretaties; geen nieuwe LLM-calls');p.add_argument('--model-url',default='http://127.0.0.1:8765');p.add_argument('--e5-model',required=True);p.add_argument('--e5-tokenizer',required=True);p.add_argument('--uitvoer',type=Path,required=True);a=p.parse_args()
    if a.uitvoer.exists():p.error('Uitvoer bestaat al.')
    doc=json.loads(a.dataset.read_text());vragen=json.loads(a.vragen.read_text())
    if not all(x['naam']['waarde'].startswith('FICTIEF') for x in doc['aanbieders']):p.error('Benchmark uitsluitend met fictieve dataset.')
    llm=LokaalTaalmodel(a.model_url,timeout=60);emb=E5Embeddings(a.e5_model,a.e5_tokenizer)
    start=time.perf_counter();zoeker=HybrideZoeker(doc,llm,emb);index_ms=(time.perf_counter()-start)*1000
    klassiek=Index(doc);resultaten=[]
    eerdere={x['id']:x for x in json.loads(a.modelantwoorden.read_text())['resultaten']} if a.modelantwoorden else {}
    for c in vragen:
        if eerdere and eerdere[c['id']]['vraag']!=c['vraag']:raise ValueError('Vragen verschillen van de vastgelegde modelrun.')
        filters=Filters.van(**c['filters']);t=time.perf_counter();oud=klassiek.zoek(c['vraag'],filters);oud_ms=(time.perf_counter()-t)*1000
        t=time.perf_counter();r=deepcopy(eerdere[c['id']]['interpretatie']) if eerdere else zoeker.interpreteer(c['vraag']);interpretatie_ms=eerdere[c['id']]['interpretatie_ms'] if eerdere else (time.perf_counter()-t)*1000
        bevestigd=pas_interpretatie_aan(r);nieuw=zoeker.zoek(c['vraag'],bevestigd,filters)
        oud_ids=[x.id+'/dienst' for x in oud[:5]];nieuw_ids=[x['id'] if '/' in x['id'] else x['id']+'/dienst' for x in nieuw['resultaten'][:5]]
        verw=c['relevante_diensten'];observatie={s['concept'] for s in r['signalen']}
        # Alleen klinische/care-vraagbegrippen uit de handmatige referentie; generieke hulpvormen ook los zichtbaar.
        interpretatiemaat=maat(c['concepten'],observatie)
        hardfouten=[]
        if r['leeftijden']!=c['leeftijden']:hardfouten.append('Leeftijdsinterpretatie wijkt af van bevroren referentie')
        beste=set(c.get('beste_diensten',verw))
        top1_juist=bool(nieuw_ids and nieuw_ids[0] in beste) if beste else not nieuw_ids
        for rs in nieuw['resultaten']:
            if rs['aanbieder_id']=='volwassen' and any(n<18 for n in c['leeftijden']):hardfouten.append('Volwassenenaanbod bij minderjarige')
            if rs['aanbieder_id']=='buiten' and rs['contract']['status']=='ja':hardfouten.append('Onjuiste gemeentecontractstatus')
            if rs['aanbieder_id']=='stop' and not rs.get('stop'):hardfouten.append('Stop verdwenen')
            if rs['aanbieder_id']=='onder' and not any(x.get('hoofdaannemer') for x in rs['contract']['routes']):hardfouten.append('Onderaannemerroute verdwenen')
        resultaten.append({'id':c['id'],'vraag':c['vraag'],'referentie':verw,'klassiek_ids_top5':oud_ids,'ai_ids_top5':nieuw_ids,
          'klassiek':maat(verw,oud_ids),'ai':maat(verw,nieuw_ids),'interpretatie':r,'interpretatiemaat':interpretatiemaat,
          'top1_juist':top1_juist,'hardfouten':hardfouten,'klassiek_ms':oud_ms,'interpretatie_ms':interpretatie_ms,'ai_zoeken_ms':nieuw['duur_ms'],
          'backend':nieuw['backend'],'kosten_eur':0,'ai_resultaten':nieuw['resultaten']})
        print(c['id'],r['backend'],f'{interpretatie_ms:.0f}ms',resultaten[-1]['ai'],flush=True)
    sam={'vragen':len(vragen),'referentie':'Door implementerende AI handmatig bevroren fictieve referentie, geen onafhankelijk professioneel oordeel.',
         'model_echt_getest':'Qwen2.5-1.5B-Instruct-Q4_K_M (lokaal llama.cpp)','embeddings_echt_getest':'multilingual-e5-small ONNX quantized',
         'uitvoering':'Finale zoeklaag herhaald met vastgelegde echte LLM-interpretaties en opnieuw uitgevoerde echte embeddings' if eerdere else 'Echte lokale LLM en echte embeddings',
         'modelantwoorden_sha256':hashlib.sha256(a.modelantwoorden.read_bytes()).hexdigest() if eerdere else None,
         'top1_juist':sum(x['top1_juist'] for x in resultaten),'index_ms':index_ms,'hardfouten':sum(len(x['hardfouten']) for x in resultaten),'fallbacks':sum(x['interpretatie']['backend']=='regel_fallback' for x in resultaten),
         'interpretatie_exact':sum(x['interpretatiemaat']['exact'] for x in resultaten),'kosten_per_zoekopdracht_eur':0,
         'kosten_toelichting':'Geen API-kosten. Exclusief bestaande hardware, stroom en beheer; geen productieprijsgarantie.',
         'klassiek_mediaan_ms':statistics.median(x['klassiek_ms'] for x in resultaten),
         'ai_totaal_mediaan_ms':statistics.median(x['interpretatie_ms']+x['ai_zoeken_ms'] for x in resultaten)}
    for methode in ('klassiek','ai'):
        tp=sum(x[methode]['tp'] for x in resultaten);fp=sum(x[methode]['fp'] for x in resultaten);fn=sum(x[methode]['fn'] for x in resultaten)
        sam[methode]={'tp_top5':tp,'fp_top5':fp,'fn_top5':fn,'precision_top5':tp/(tp+fp) if tp+fp else 0,'recall_top5':tp/(tp+fn) if tp+fn else 0,'exact_top5':sum(x[methode]['exact'] for x in resultaten)}
    with a.uitvoer.open('x') as f:json.dump({'samenvatting':sam,'resultaten':resultaten},f,ensure_ascii=False,indent=2);f.write('\n')
    print(json.dumps(sam,ensure_ascii=False,indent=2),flush=True)


if __name__=='__main__':main()
