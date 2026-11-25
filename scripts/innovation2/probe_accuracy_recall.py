"""Offline retrieval-only probe; named hypotheses are not identity evidence."""
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
import torch
from src.knowledge.clip_encoder import CLIPEncoder
from src.knowledge.multimodal_retriever import MultimodalCulturalRetriever
from src.knowledge.symbol_kb import SymbolKnowledgeBase
from src.pipeline.scene_evidence import contextual_evidence_text


def main():
    torch.set_num_threads(2)
    kb=SymbolKnowledgeBase();retriever=MultimodalCulturalRetriever(kb,clip_encoder=CLIPEncoder(device='cpu'))
    source=ROOT/'experiments/innovation2/results/abc_development_v1';out=ROOT/'experiments/innovation2/outputs/accuracy_repair_v2/recall_probe.json'
    gt=[json.loads(l) for l in (ROOT/'experiments/innovation2/data/eval/cultural_ablation_gt_final31.jsonl').read_text().splitlines() if l.strip()]
    rows=[]
    for g in gt:
        folder=source/g['video_id']
        if not (folder/'B/result.json').exists():continue
        a=json.loads((folder/'A/trace.json').read_text());b=json.loads((folder/'B/trace.json').read_text())
        scene=b.get('structured_scene');review=b.get('text_recognition',{})
        context=contextual_evidence_text(scene,review.get('items',[]),reviewed=review.get('status') in {'completed','partial_failure'}) if scene else b['scene_description']
        # Recompute full-library image scores once, shared across all four query variants.
        full=retriever.retrieve({'video_path':str(ROOT/g['video_path']),'scene_text':b['scene_description']},top_k=len(kb))
        images={c.symbol_id:c.image_score for c in full if c.symbol_id not in retriever.image_unavailable_symbols}
        row={'video_id':g['video_id'],'sample_type':g['sample_type'],'variants':{}}
        for name,text in [('B',b['scene_description']),('B_context',context),('A',a['scene_description']),('A_plus_B',a['scene_description']+'\n'+context)]:
            cs=retriever.rank_with_scores({'scene_text':text},images,top_k=5);ids=[c.symbol_id for c in cs]
            rank=next((i+1 for i,sid in enumerate(ids) if sid in g['gt_symbol_ids']),None)
            row['variants'][name]={'top5':ids,'hit1':bool(rank==1),'hit5':rank is not None}
        rows.append(row);print(g['video_id'],{k:v['hit5'] for k,v in row['variants'].items()},flush=True)
    known=[r for r in rows if r['sample_type']=='known']
    metrics={k:{'known_n':len(known),'recall1':sum(r['variants'][k]['hit1'] for r in known)/len(known),'recall5':sum(r['variants'][k]['hit5'] for r in known)/len(known)} for k in ['A','B','B_context','A_plus_B']}
    out.write_text(json.dumps({'scope':'development_retrieval_only_no_acceptance_claim','api_calls':0,'metrics':metrics,'rows':rows},ensure_ascii=False,indent=2))
    print(json.dumps(metrics,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
