"""Paired development replay of cached evidence; never modifies source runs or GT."""
import argparse, concurrent.futures, copy, hashlib, json, sys, threading, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.innovation2.run_abc_development import score, write
from src.pipeline.inference_engine import InferenceEngine
from src.pipeline.cultural_rag import CulturalRAGPipeline
from src.knowledge.symbol_kb import SymbolKnowledgeBase
from src.knowledge.multimodal_retriever import MultimodalCulturalRetriever
from src.knowledge.identity_verifier_v2 import IdentityVerifierV2
from src.knowledge.rejection_gate import RejectionGate
from src.knowledge.clip_encoder import CLIPEncoder


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', default=str(ROOT/'experiments/innovation2/results/abc_development_v1'))
    parser.add_argument('--output-dir', required=True)
    parser.add_argument('--workers', type=int, default=3)
    parser.add_argument('--limit', type=int)
    parser.add_argument('--offline', action='store_true', help='Only audit source; no model initialization or API calls')
    args = parser.parse_args()
    source, out = Path(args.source).resolve(), Path(args.output_dir).resolve()
    if out == source or source in out.parents:
        raise ValueError('Use a separate output directory')
    gtpath = ROOT/'experiments/innovation2/data/eval/cultural_ablation_gt_final31.jsonl'
    gt = [json.loads(line) for line in gtpath.read_text().splitlines() if line.strip()]
    active = [g for g in gt if (source/g['video_id']/'B/result.json').exists()]
    if args.limit: active = active[:args.limit]
    files = [p for folder in ['src','config'] for p in (ROOT/folder).rglob('*') if p.suffix in {'.py','.json'}]
    files += [Path(__file__), ROOT/'scripts/innovation2/run_abc_development.py',gtpath,ROOT/'archives/knowledge_base_history_20261119/chinese_cultural_symbols_v2.json']
    for g in active:
        files += list((source/g['video_id']).glob('*/result.json'))
        files.append(source/g['video_id']/'B/00_scene_evidence.json')
    hashes = {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    manifest = {'scope':'development_only_not_independent_test','source':str(source),
                'active_ids':[g['video_id'] for g in active], 'expected':2*len(active),
                'hashes':hashes, 'groups':{'B2':'cached B + background context + KB scope verification + legacy ranking',
                'C2':'same cached B + background context + KB scope verification + evidence_v1 ranking'},
                'thresholds':'unchanged; unrecalibrated', 'evidence_calls':0,
                'missing_source_ids':[g['video_id'] for g in gt if g not in active]}
    if (out/'manifest.json').exists() and json.loads((out/'manifest.json').read_text()) != manifest:
        raise ValueError('Manifest changed; use a new output directory')
    write(out/'manifest.json',manifest)
    if args.offline: print(json.dumps(manifest,ensure_ascii=False));return
    import torch
    torch.set_num_threads(4)
    kb = SymbolKnowledgeBase(); clip = CLIPEncoder(device='cpu')
    legacy = MultimodalCulturalRetriever(kb,clip_encoder=clip); legacy._build_reference_embeddings()
    ranked = copy.copy(legacy);ranked.ranking_strategy = 'evidence_v1'
    template = IdentityVerifierV2(kb=kb,clip_encoder=clip,scope_policy='kb_scope_v3')
    lock = threading.Lock()
    def summarize(status):
        records = []
        for g in active:
            for group in ['B2','C2']:
                p = out/g['video_id']/group/'result.json'
                if p.exists(): records.append(json.loads(p.read_text()))
        summary = {'status':status,'completed':len(records),'expected':len(active)*2,'scope':manifest['scope'],'groups':{},'paired':{}}
        for group in ['B2','C2']:
            rs = [r for r in records if r['group']==group];known=[r for r in rs if r['sample_type']=='known'];unknown=[r for r in rs if r['sample_type']!='known']
            mean = lambda seq,key: sum(r[key] for r in seq)/len(seq) if seq else None
            summary['groups'][group]={'n':len(rs),'known_n':len(known),'unknown_n':len(unknown),
              'accuracy':mean(rs,'correct'),'known_accuracy':mean(known,'correct'),'known_false_reject':mean(known,'rejected'),
              'unknown_false_accept':1-mean(unknown,'rejected') if unknown else None,'recall5':mean(known,'recall5'),
              'api_calls':sum(r['api_calls'] for r in rs)}
            pairs=[]
            for r in rs:
                old=source/r['video_id']/group[0]/'result.json'
                if old.exists():pairs.append((json.loads(old.read_text()),r))
            summary['paired'][group]={'n':len(pairs),'before_correct':sum(a['correct'] for a,b in pairs),
                'after_correct':sum(b['correct'] for a,b in pairs),'improved':[b['video_id'] for a,b in pairs if not a['correct'] and b['correct']],
                'regressed':[b['video_id'] for a,b in pairs if a['correct'] and not b['correct']]}
        write(out/'summary.json',summary)
        write(out/'per_video.json',records)
        return summary
    def work(g):
        engine=InferenceEngine();engine.initialize();calls=[];original=engine.model_manager.call_glm_api
        def counted(messages,temperature=None):
            t=time.monotonic();entry={'status':'running'};calls.append(entry)
            try:
                response=original(messages,temperature=0);entry['status']='ok';return response
            except Exception as exc:entry['status']='error';entry['error']=str(exc);raise
            finally:entry['seconds']=round(time.monotonic()-t,3)
        engine.model_manager.call_glm_api=counted
        verifier=copy.copy(template);verifier.llm_caller=counted
        prepared=json.loads((source/g['video_id']/'B/00_scene_evidence.json').read_text())
        try:
            for group in ['B2','C2']:
                dest=out/g['video_id']/group
                if (dest/'result.json').exists():continue
                before=len(calls);start=time.monotonic()
                try:
                    pipeline=CulturalRAGPipeline(engine=engine,kb=kb,retriever=legacy if group=='B2' else ranked,
                       rejection_gate=RejectionGate(),identity_verifier=verifier,evidence_policy='context_v2')
                    trace=pipeline.run(str(ROOT/g['video_path']),controlled=True,out_dir=str(dest),prepared_evidence=prepared)
                    write(dest/'trace.json',trace)
                    result=score(trace,g,kb);result.update(group=group,api_calls=len(calls)-before,seconds=round(time.monotonic()-start,2))
                    write(dest/'result.json',result);print(g['video_id'],group,result['error_type'],flush=True)
                except Exception as exc:
                    write(dest/'error.json',{'error':str(exc),'video_id':g['video_id'],'group':group});print('ERROR',g['video_id'],group,str(exc),flush=True)
                finally:write(dest/'api_calls.json',calls[before:])
                with lock:summarize('running')
        finally:engine.cleanup()
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:list(pool.map(work,active))
    summary=summarize('finished')
    summary['status']='complete' if summary['completed']==summary['expected'] else 'incomplete'
    write(out/'summary.json',summary);print(json.dumps(summary,ensure_ascii=False),flush=True)
    if summary['status']!='complete':raise SystemExit(1)

if __name__=='__main__':main()
