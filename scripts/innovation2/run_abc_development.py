"""统一A/B/C开发对照；断点续跑，B/C共享证据，不重用历史最终预测。"""
import argparse, concurrent.futures, copy, csv, hashlib, json, os, sys, threading, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from src.pipeline.inference_engine import InferenceEngine
from src.pipeline.cultural_rag import CulturalRAGPipeline, extract_pred_names, alias_set_of
from src.knowledge.symbol_kb import SymbolKnowledgeBase
from src.knowledge.multimodal_retriever import MultimodalCulturalRetriever
from src.knowledge.identity_verifier_v2 import IdentityVerifierV2
from src.knowledge.rejection_gate import RejectionGate
from src.knowledge.clip_encoder import CLIPEncoder


def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2));tmp.replace(path)


def score(trace,gt,kb):
    c=trace['final_c_layer']; names=extract_pred_names(c.get('core_symbol',''))
    ids=set()
    for name in names:
        for s in kb.symbols:
            if name in alias_set_of(kb,s): ids.add(s['symbol_id'])
    rejected=bool(c.get('unknown_symbol')) or not ids
    truth=set(gt['gt_symbol_ids']);known=gt['sample_type']=='known'
    # 多实体输出必须全部落在GT中且至少命中一个；不靠子串算正确。
    correct=(bool(ids) and ids<=truth and not rejected) if known else rejected
    top=[x['symbol_id'] for x in trace['topk_candidates']]
    rank=next((i+1 for i,sid in enumerate(top) if sid in truth),None)
    return dict(video_id=gt['video_id'],sample_type=gt['sample_type'],gt_ids=sorted(truth),pred_ids=sorted(ids),
                rejected=rejected,correct=correct,recall1=bool(top and top[0] in truth),recall5=rank is not None,
                reciprocal_rank=1/rank if rank else 0,
                error_type=('correct' if correct else 'false_reject' if known and rejected else 'retrieval_miss' if known and not rank else 'wrong_selection' if known else 'unknown_false_accept'))


def summarize(out,active):
    rows=[]; errors=[]
    for gt in active:
        for group in 'ABC':
            p=out/gt['video_id']/group/'result.json'
            if p.exists():rows.append(json.loads(p.read_text()))
            e=p.parent/'error.json'
            if not p.exists() and e.exists():errors.append(json.loads(e.read_text()))
    summary={'status':'complete' if len(rows)==len(active)*3 else 'running','completed':len(rows),'expected':len(active)*3,'errors':errors,'groups':{}}
    for g in 'ABC':
        rs=[x for x in rows if x['group']==g]; k=[x for x in rs if x['sample_type']=='known']; u=[x for x in rs if x['sample_type']!='known']
        mean=lambda seq,key:sum(x[key] for x in seq)/len(seq) if seq else None
        summary['groups'][g]={'n':len(rs),'known_n':len(k),'unknown_n':len(u),'accuracy':mean(rs,'correct'),
           'known_accuracy':mean(k,'correct'),'known_false_reject':mean(k,'rejected'),
           'unknown_false_accept':None if not u else 1-mean(u,'rejected'),'recall1':mean(k,'recall1'),
           'recall5':mean(k,'recall5'),'mrr_at5':mean(k,'reciprocal_rank'),
           'actual_api_calls':sum(x['api_calls'] for x in rs),'mean_runtime_seconds':mean(rs,'seconds')}
    write(out/'summary.json',summary)
    lines=['# A/B/C统一开发对照', '', f"状态：{summary['status']}；完成 {len(rows)}/{len(active)*3}。", '',
           '历史样本已参与开发诊断，不作为独立测试收益；缺失素材见manifest.json。', '',
           '|组别|完成|Known准确率|Known误拒率|Unknown错误接受率|Recall@5|API调用数|',
           '|---|---:|---:|---:|---:|---:|---:|']
    fmt=lambda v: '-' if v is None else f'{v:.2%}'
    for g,v in summary['groups'].items():
        lines.append(f"|{g}|{v['n']}|{fmt(v['known_accuracy'])}|{fmt(v['known_false_reject'])}|{fmt(v['unknown_false_accept'])}|{fmt(v['recall5'])}|{v['actual_api_calls']}|")
    lines += ['', 'A为旧描述与旧排序；B为结构化证据及文字复核、旧排序；C严格复用B证据并使用新排序。',
              'C的运行成本不含已由B支付的证据提取成本；逐阶段调用与耗时见各视频目录。金额与token数未取得，不估算。',
              '严格按GT符号ID评分，多符号输出含额外错误符号判错；因此不能直接与旧版宽松子串指标作提升比较。',
              '所有组共用现有门控；新排序未重新标定，此次只检验固定门控下的开发效果。']
    (out/'report.md').write_text('\n'.join(lines)+'\n')
    by_video={}
    for row in rows: by_video.setdefault(row['video_id'],{})[row['group']]=row
    write(out/'paired_differences.json',[{'video_id':vid,'groups':groups} for vid,groups in by_video.items() if len(groups)==3 and len({(x['correct'],x['rejected'],tuple(x['pred_ids'])) for x in groups.values()})>1])

    if rows:
        with (out/'per_video.csv').open('w',newline='',encoding='utf-8-sig') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    return summary


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output-dir',required=True);p.add_argument('--workers',type=int,default=3);p.add_argument('--prepare-only',action='store_true');a=p.parse_args()
    out=Path(a.output_dir).resolve();out.mkdir(parents=True,exist_ok=True)
    gtpath=ROOT/'experiments/innovation2/data/eval/cultural_ablation_gt_final31.jsonl'
    gt=[json.loads(x) for x in gtpath.read_text().splitlines() if x.strip()]
    active=[x for x in gt if (ROOT/x['video_path']).is_file()]
    hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for folder in ['src','config'] for p in (ROOT/folder).rglob('*') if p.is_file() and p.suffix in {'.py','.json'}}
    for p in [gtpath,ROOT/'archives/knowledge_base_history_20261119/chinese_cultural_symbols_v2.json',ROOT/'experiments/innovation2/data/eval/rejection_thresholds.json',Path(__file__)]:hashes[str(p.relative_to(ROOT))]=hashlib.sha256(p.read_bytes()).hexdigest()
    manifest={'date':'2026-11-12','scope':'development_only; not independent test','groups':{'A':'legacy scene + legacy retrieval','B':'structured scene + text review + legacy retrieval','C':'B exact evidence + evidence_v1 retrieval'},'active_ids':[x['video_id'] for x in active],'missing_ids':[x['video_id'] for x in gt if x not in active],'hashes':hashes,'workers':a.workers,'temperature':0,'top_k':5,'same_gate':'existing thresholds + IdentityVerifierV2','scoring':'strict all predicted symbol IDs subset of GT; unknown requires rejection','cost':'API request counts and timings; no token or currency cost available; C excludes shared B preprocessing'}
    if (out/'manifest.json').exists():
        previous=json.loads((out/'manifest.json').read_text())
        if previous['hashes']!=hashes:raise RuntimeError('Code/config changed: use new output directory')
    else:write(out/'manifest.json',manifest)
    if a.prepare_only:print(json.dumps(manifest,ensure_ascii=False));return
    import torch
    torch.set_num_threads(4)
    kb=SymbolKnowledgeBase();clip=CLIPEncoder();legacy=MultimodalCulturalRetriever(kb,clip_encoder=clip);legacy._build_reference_embeddings()
    revised=copy.copy(legacy);revised.ranking_strategy='evidence_v1'
    verifier_template=IdentityVerifierV2(kb=kb,clip_encoder=clip)
    lock=threading.Lock()
    def work(gt):
        engine=InferenceEngine();engine.initialize();calls=[]; original=engine.model_manager.call_glm_api
        def counted(messages,temperature=None):
            start=time.monotonic();entry={'started':time.time(),'status':'running'};calls.append(entry)
            try:
                answer=original(messages,temperature=0);entry['status']='ok';return answer
            except Exception as exc:entry['status']='error';entry['error']=str(exc);raise
            finally:entry['seconds']=round(time.monotonic()-start,3)
        engine.model_manager.call_glm_api=counted
        verifier=copy.copy(verifier_template);verifier.llm_caller=counted
        try:
            for group in 'ABC':
                dest=out/gt['video_id']/group
                if (dest/'result.json').exists():continue
                before=len(calls);start=time.monotonic()
                try:
                    pipeline=CulturalRAGPipeline(engine=engine,kb=kb,retriever=revised if group=='C' else legacy,
                        rejection_gate=RejectionGate(),identity_verifier=verifier,scene_mode='legacy' if group=='A' else 'structured')
                    prepared=None
                    if group=='C':prepared=json.loads((out/gt['video_id']/'B'/'00_scene_evidence.json').read_text())
                    trace=pipeline.run(str(ROOT/gt['video_path']),controlled=True,out_dir=str(dest),prepared_evidence=prepared)
                    write(dest/'trace.json',trace)
                    result=score(trace,gt,kb);result.update(group=group,api_calls=len(calls)-before,seconds=round(time.monotonic()-start,2))
                    write(dest/'api_calls.json',calls[before:]);write(dest/'result.json',result)
                    print(gt['video_id'],group,result['error_type'],flush=True)
                except Exception as exc:
                    write(dest/'error.json',{'video_id':gt['video_id'],'group':group,'error':str(exc)})
                    write(dest/'api_calls.json',calls[before:]);print('ERROR',gt['video_id'],group,str(exc),flush=True)
                    if group=='B':break
                with lock:summarize(out,active)
        finally:engine.cleanup()
    with concurrent.futures.ThreadPoolExecutor(max_workers=a.workers) as pool:list(pool.map(work,active))
    summary=summarize(out,active)
    if summary['completed']<summary['expected']:
        summary['status']='incomplete';write(out/'summary.json',summary)
    print(json.dumps(summary,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
