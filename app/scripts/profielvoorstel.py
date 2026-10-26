"""Offline kwaliteitsvoorstellen; geen automatische bronmutatie."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from zorgzoeker.kwaliteit import voorstel,neem_voorstel_op

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('actie',choices=['voorstel','neem-op']);p.add_argument('dataset',type=Path);p.add_argument('invoer',type=Path);p.add_argument('--uitvoer',type=Path,required=True);p.add_argument('--beoordelaar',default='');p.add_argument('--expliciet-goedgekeurd',action='store_true');a=p.parse_args()
    doc=json.loads(a.dataset.read_text());v=json.loads(a.invoer.read_text())
    if a.actie=='voorstel':resultaat=voorstel(doc,v['aanbieder_id'],v['veld'],v['nieuwe_waarde'],v['beoordeling'],soort=v.get('soort','vermoeden'))
    else:resultaat=neem_voorstel_op(doc,v,beoordelaar=a.beoordelaar,expliciet=a.expliciet_goedgekeurd)
    with a.uitvoer.open('x') as f:json.dump(resultaat,f,ensure_ascii=False,indent=2);f.write('\n')
