"""Hybrid retrieval + independent video verification, paired development experiment."""
import argparse,concurrent.futures,copy,csv,hashlib,json,sys,threading,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from scripts.innovation2.run_abc_development import score,write
from src.pipeline.cultural_rag import CulturalRAGPipeline,parse_c_layer
from src.pipeline.inference_engine import InferenceEngine
from src.pipeline.hybrid_evidence import prepare_hybrid_evidence,IndependentVideoVerifier
from src.knowledge.symbol_kb import SymbolKnowledgeBase
from src.knowledge.retriever import KeywordCulturalRetriever


def summarize(out,source,active,status):
    rows=[];errors=[]
    for g in active:
        dest=out/g['video_id']
        if (dest/'result.json').exists():rows.append(json.loads((dest/'result.json').read_text()))
        elif (dest/'error.json').exists():errors.append(json.loads((dest/'error.json').read_text()))
    mean=lambda rs,k:sum(r[k] for r in rs)/len(rs) if rs else None
    known=[r for r in rows if r['sample_type']=='known'];unknown=[r for r in rows if r['sample_type']!='known']
    summary={'status':status,'completed':len(rows),'expected':len(active),'scope':'development_only_not_independent_test',
        'known_n':len(known),'unknown_n':len(unknown),'accuracy':mean(rows,'correct'),
        'known_accuracy':mean(known,'correct'),'known_false_reject':mean(known,'rejected'),
        'unknown_false_accept':1-mean(unknown,'rejected') if unknown else None,
        'recall1':mean(known,'recall1'),'recall5':mean(known,'recall5'),
        'new_api_calls':sum(r['api_calls'] for r in rows),'errors':errors,'paired':{},
        'pre_verification_correct':sum(r['pre_verification_correct'] for r in rows)}
    for group in 'ABC':
        pairs=[]
        for r in rows:
            p=source/r['video_id']/group/'result.json'
            if p.exists():pairs.append((json.loads(p.read_text()),r))
        summary['paired'][group]={'n':len(pairs),'before_correct':sum(a['correct'] for a,b in pairs),
          'after_correct':sum(b['correct'] for a,b in pairs),'improved':[b['video_id'] for a,b in pairs if b['correct'] and not a['correct']],
          'regressed':[b['video_id'] for a,b in pairs if a['correct'] and not b['correct']]}
    write(out/'summary.json',summary);write(out/'per_video.json',rows)
    if rows:
        with (out/'per_video.csv').open('w',newline='',encoding='utf-8-sig') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    fmt=lambda n:'—' if n is None else f'{n:.2%}'
    lines=['# 联合召回与独立视频核验 v3','',f"状态：{status}；完成 {len(rows)}/{len(active)}。",'',
      '|严格准确率|Known准确率|Known误拒率|Unknown错误接受率|Recall@5|新增API调用|',
      '|---:|---:|---:|---:|---:|---:|',
      '|'+ '|'.join([fmt(summary[k]) for k in ['accuracy','known_accuracy','known_false_reject','unknown_false_accept','recall5']]+[str(summary['new_api_calls'])])+'|',
      '','|基线|共同视频数|基线正确|v3正确|改善|退步|','|---|---:|---:|---:|---|---|']
    for group,p in summary['paired'].items():lines.append(f"|{group}|{p['n']}|{p['before_correct']}|{p['after_correct']}|{'、'.join(p['improved']) or '无'}|{'、'.join(p['regressed']) or '无'}|")
    lines+=['','仅为开发实验；命名假设仅用于检索，独立核验不读取假设、分数或未审核参考图。',
      '新增调用数不含缓存A/B证据原先的提取成本；逐条记录preparation_api_calls。重用证据不能声称完整系统免费。',
      f"独立核验前严格正确 {summary['pre_verification_correct']}/{len(rows)}；该分数用于分析核验损失，不作为已验证系统结果。",
      '本轮同时改变召回与核验策略，不能将整体差异归因于某一个改动。与历史A/B配对不等于同时间重新采样，需后续冻结方法并做正式消融。',
      '旧验证集与final31有重复视频；未审核参考图曾被旧实现加载。正式论文须去重、审查数据与知识库，再用独立数据评估。']
    (out/'report.md').write_text('\n'.join(lines)+'\n')
    return summary


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',default=str(ROOT/'experiments/innovation2/results/abc_development_v1'))
    parser.add_argument('--output-dir',required=True);parser.add_argument('--workers',type=int,default=3)
    parser.add_argument('--prepare-only',action='store_true');args=parser.parse_args()
    source=Path(args.source).resolve();out=Path(args.output_dir).resolve()
    if out==source or source in out.parents:raise ValueError('Use separate output directory')
    gtpath=ROOT/'experiments/innovation2/data/eval/cultural_ablation_gt_final31.jsonl'
    gt=[json.loads(l) for l in gtpath.read_text().splitlines() if l.strip()]
    active=[g for g in gt if all((source/g['video_id']/group/'result.json').exists() for group in 'AB')]
    files=[p for folder in ['src','config'] for p in (ROOT/folder).rglob('*') if p.suffix in {'.py','.json'}]
    files += [Path(__file__),ROOT/'scripts/innovation2/run_abc_development.py',gtpath,ROOT/'archives/knowledge_base_history_20261119/chinese_cultural_symbols_v2.json']
    for g in active:
        files+=list((source/g['video_id']).glob('*/result.json'))
        files += [source/g['video_id']/group/'00_scene_evidence.json' for group in 'AB']
    hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    manifest={'scope':'development_only_not_independent_test','active_ids':[g['video_id'] for g in active],
      'expected':len(active),'hashes':hashes,'retrieval':'keyword top5 on A hypotheses + observed B',
      'verification':'independent video frames and KB definition; no hypotheses, scores or reference images',
      'gate':'no keyword-only rejection; every emitted identity must pass independent verifier',
      'reference_images_used':0,'temperature':0,'workers':args.workers,
      'missing_source_ids':[g['video_id'] for g in gt if g not in active]}
    if (out/'manifest.json').exists() and json.loads((out/'manifest.json').read_text())!=manifest:raise ValueError('Frozen inputs changed; use a new directory')
    write(out/'manifest.json',manifest)
    if args.prepare_only:print(json.dumps(manifest,ensure_ascii=False));return
    kb=SymbolKnowledgeBase();retriever=KeywordCulturalRetriever(kb);lock=threading.Lock()
    def work(g):
        dest=out/g['video_id']
        if (dest/'result.json').exists():return
        engine=InferenceEngine();engine.initialize();calls=[];original=engine.model_manager.call_glm_api
        start=time.monotonic()
        def counted(messages,temperature=None):
            t=time.monotonic();entry={'status':'running','started':time.time()};calls.append(entry)
            try:
                response=original(messages,temperature=0);entry['status']='ok';return response
            except Exception as exc:entry.update(status='error',error=str(exc));raise
            finally:entry['seconds']=round(time.monotonic()-t,3)
        engine.model_manager.call_glm_api=counted
        try:
            evidence_path=dest/'prepared_evidence.json'
            if evidence_path.exists():prepared=json.loads(evidence_path.read_text());preparation_calls=0
            else:
                a=json.loads((source/g['video_id']/'A/00_scene_evidence.json').read_text())
                b=json.loads((source/g['video_id']/'B/00_scene_evidence.json').read_text())
                prepared=prepare_hybrid_evidence(a,b,engine.model_manager,str(ROOT/g['video_path']),dest/'text_recovery')
                preparation_calls=len(calls);write(evidence_path,prepared)
            verifier=IndependentVideoVerifier(kb,counted)
            pipeline=CulturalRAGPipeline(engine=engine,kb=kb,retriever=retriever,identity_verifier=verifier)
            trace=pipeline.run(str(ROOT/g['video_path']),controlled=True,out_dir=str(dest),prepared_evidence=prepared)
            write(dest/'trace.json',trace)
            result=score(trace,g,kb)
            raw=dict(trace,final_c_layer=parse_c_layer(trace['raw_final_annotation']))
            result.update(group='H3',api_calls=len(calls),preparation_api_calls=preparation_calls,
                pre_verification_correct=score(raw,g,kb)['correct'],seconds=round(time.monotonic()-start,2))
            write(dest/'result.json',result);print(g['video_id'],result['error_type'],flush=True)
        except Exception as exc:
            write(dest/'error.json',{'video_id':g['video_id'],'error':str(exc)});print('ERROR',g['video_id'],str(exc),flush=True)
        finally:
            attempt=dest/f'api_calls_{time.time_ns()}.json';write(attempt,calls)
            engine.cleanup()
            with lock:summarize(out,source,active,'running')
    summarize(out,source,active,'running')
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:list(pool.map(work,active))
    s=summarize(out,source,active,'finished');s=summarize(out,source,active,'complete' if s['completed']==s['expected'] else 'incomplete')
    print(json.dumps(s,ensure_ascii=False),flush=True)
    if s['status']!='complete':raise SystemExit(1)

if __name__=='__main__':main()
