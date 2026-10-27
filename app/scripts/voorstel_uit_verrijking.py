"""Maak uitsluitend na expliciete inhoudelijke review een offline voorstel."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from zorgzoeker.verrijking import voorstel_uit_bevinding
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('dataset',type=Path);p.add_argument('review',type=Path);p.add_argument('--uitvoer',type=Path,required=True);p.add_argument('--beoordelaar',required=True);p.add_argument('--expliciet-goedgekeurd',action='store_true');a=p.parse_args()
 d=json.loads(a.dataset.read_text());v=json.loads(a.review.read_text())
 result=voorstel_uit_bevinding(d,v['bevinding'],beoordelaar=a.beoordelaar,expliciet=a.expliciet_goedgekeurd,nieuwe_waarde=v['nieuwe_waarde'],beoordeling=v['beoordeling'])
 with a.uitvoer.open('x') as f:json.dump(result,f,ensure_ascii=False,indent=2)
