"""Small, authored regression set, NOT an independent real-world benchmark."""
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from rolecraft.models import SearchRequest
from rolecraft.search import search
from rolecraft.store import demo_store

CASES = [
    ('calm Canadian backend', {'query':'backend Python Go', 'filters':{'country':'Canada','work_mode':'Remote'}, 'preferences':['async','balance']}, {'demo-08':3,'demo-01':2,'demo-20':1}),
    ('AI retrieval engineering', {'query':'RAG embeddings retrieval AI', 'filters':{'country':'Canada'}}, {'demo-01':3,'demo-17':2}),
    ('climate engineering', {'query':'climate clean energy engineering'}, {'demo-02':3,'demo-13':3}),
    ('early career mentorship', {'query':'junior engineering mentorship', 'filters':{'level':'Entry'}}, {'demo-07':3,'demo-24':1}),
    ('health data engineering', {'query':'health data SQL pipelines', 'filters':{'country':'Canada'}}, {'demo-06':3}),
    ('security infrastructure', {'query':'security identity infrastructure', 'filters':{'country':'Netherlands'}}, {'demo-14':3}),
    ('UX interviews', {'query':'UX user interviews research', 'filters':{'country':'Canada'}}, {'demo-09':3,'demo-03':1}),
    ('embedded hardware', {'query':'firmware embedded robotics', 'filters':{'work_mode':'On-site'}}, {'demo-22':3}),
]


def main():
    output=[]
    for name, payload, judgments in CASES:
        result=search(SearchRequest.model_validate({**payload,'page_size':24}),demo_store())
        ids=[j['id'] for j in result['jobs']]
        dcg=sum((2**judgments.get(key,0)-1)/math.log2(i+2) for i,key in enumerate(ids[:10]))
        ideal=sum((2**grade-1)/math.log2(i+2) for i,grade in enumerate(sorted(judgments.values(),reverse=True)[:10]))
        rank=next((i+1 for i,key in enumerate(ids) if judgments.get(key,0)>=2),None)
        output.append({'case':name,'ndcg_at_10':round(dcg/ideal,4) if ideal else 0,'reciprocal_rank':round(1/rank,4) if rank else 0,'top_three':ids[:3]})
    report={'dataset':'8 authored queries over 24 fictional jobs; not a held-out benchmark','results':output,
        'mean_ndcg_at_10':round(sum(r['ndcg_at_10'] for r in output)/len(output),4),
        'mrr':round(sum(r['reciprocal_rank'] for r in output)/len(output),4)}
    print(json.dumps(report,indent=2))
    # A broad regression floor, not a claim of optimal ranking or live quality.
    if any(r['reciprocal_rank']==0 for r in output):
        raise SystemExit('A relevant illustrative role disappeared from retrieval.')


if __name__=='__main__':main()
