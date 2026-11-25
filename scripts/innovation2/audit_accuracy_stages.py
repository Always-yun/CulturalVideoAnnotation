"""Audit saved traces, including pre-verifier predictions; no inference or GT changes."""
import argparse, collections, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from src.pipeline.cultural_rag import parse_c_layer
from src.knowledge.symbol_kb import SymbolKnowledgeBase
from scripts.innovation2.run_abc_development import score, write


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',required=True);p.add_argument('--output-dir',required=True)
    a=p.parse_args();source=Path(a.source);out=Path(a.output_dir)
    gt={g['video_id']:g for g in map(json.loads,(ROOT/'experiments/innovation2/data/eval/cultural_ablation_gt_final31.jsonl').read_text().splitlines()) if g}
    kb=SymbolKnowledgeBase();rows=[]
    for file in sorted(source.glob('*/*/result.json')):
        result=json.loads(file.read_text());t=json.loads((file.parent/'trace.json').read_text())
        r=dict(result);r['stage']='correct'
        if not r['correct']:
            if not r['recall5'] and r['sample_type']=='known':r['stage']='retrieval_miss'
            elif t.get('identity_verification') and any(not d.get('final_symbol') for d in t['identity_verification']):r['stage']='identity_reject'
            elif t.get('effective_gate',{}).get('level')=='insufficient':r['stage']='retrieval_gate_reject'
            else:r['stage']='annotation_or_constraint'
        raw=dict(t,final_c_layer=parse_c_layer(t.get('raw_final_annotation',t['final_annotation'])))
        r['raw_annotation_correct']=score(raw,gt[r['video_id']],kb)['correct']
        r['identity_reasons']=[d.get('final_reason') for d in t.get('identity_verification',[])]
        r['gate_reason']=t.get('effective_gate',{}).get('reason')
        rows.append(r)
    summary={}
    for g in sorted({r['group'] for r in rows}):
        rs=[r for r in rows if r['group']==g]
        summary[g]={'n':len(rs),'stages':dict(collections.Counter(r['stage'] for r in rs)),
                    'raw_annotation_correct':sum(r['raw_annotation_correct'] for r in rs),
                    'final_correct':sum(r['correct'] for r in rs),
                    'correct_lost_after_annotation':[r['video_id'] for r in rs if r['raw_annotation_correct'] and not r['correct']]}
    write(out/'stage_audit.json',rows);write(out/'stage_summary.json',summary)
    print(json.dumps(summary,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
