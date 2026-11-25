"""只复用既有Pass-1并重新计算本地CLIP分数，配对比较排序；不调用GLM、不改GT。"""
import argparse
import json
import sys
from pathlib import Path
import torch
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from src.knowledge.symbol_kb import SymbolKnowledgeBase
from src.knowledge.clip_encoder import CLIPEncoder
from src.knowledge.multimodal_retriever import MultimodalCulturalRetriever


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output-dir', required=True)
    p.add_argument('--cached-scene-report', help='使用第一步已保存证据，只对对应视频离线比较，无GLM调用')
    args = p.parse_args()
    torch.set_num_threads(4)
    out = Path(args.output_dir);out.mkdir(parents=True, exist_ok=True)
    kb = SymbolKnowledgeBase()
    legacy = MultimodalCulturalRetriever(kb=kb, clip_encoder=CLIPEncoder(device='cpu'))
    new = MultimodalCulturalRetriever(kb=kb, ranking_strategy='evidence_v1')
    source = ROOT/'experiments/innovation2/runs/cultural_ablation/final30_exp1_imgfix/results.json'
    records = [r for r in json.loads(source.read_text())['records'] if r['mode']=='multimodal_controlled']
    cached = json.loads(Path(args.cached_scene_report).read_text()) if args.cached_scene_report else None
    if cached:
        cached_path = Path(cached['video_path'])
        cached_path = cached_path if cached_path.is_absolute() else ROOT/cached_path
        records = [r for r in records if (Path(r['video_path']) if Path(r['video_path']).is_absolute() else ROOT/r['video_path']).resolve() == cached_path.resolve()]
        if not records:
            raise ValueError('Cached evidence does not match any source record')
    rows=[]; skipped=[]
    def pack(cs):
        return [{'symbol_id':c.symbol_id,'canonical_name':c.canonical_name, 'text_score':c.text_score,
                 'image_score':c.image_score,'fusion_score':c.fusion_score,'ranking_score':c.ranking_score,
                 'retrieval_evidence':c.retrieval_evidence} for c in cs]
    for record in records:
        path = Path(record['video_path']);path = path if path.is_absolute() else ROOT/path
        if not path.is_file():
            skipped.append({'video_id':record['video_id'],'reason':'source_video_missing'});continue
        ctx={'video_path':str(path),'scene_text':record['scene_description']}
        if cached:
            ctx.update(scene_text=cached['retrieval_text'], structured_scene=cached['structured_scene'],
                       text_recognition=cached['text_recognition'])
        full=legacy.retrieve(ctx, top_k=len(kb))
        image_scores={c.symbol_id:c.image_score for c in full if c.symbol_id not in legacy.image_unavailable_symbols}
        # 两种排序使用完全相同的四舍五入图像分数与同一份历史场景描述。
        a=legacy.rank_with_scores(ctx, image_scores);b=new.rank_with_scores(ctx, image_scores)
        gt=set(record['gt_symbol_ids'])
        row={'video_id':record['video_id'],'sample_type':record['sample_type'],'gt_symbol_ids':list(gt),
             'legacy_topk':pack(a),'evidence_topk':pack(b)}
        for label,cs in [('legacy',a),('evidence',b)]:
            ids=[c.symbol_id for c in cs];rank=next((i+1 for i,sid in enumerate(ids) if sid in gt),None)
            row[label+'_hit1']=bool(ids and ids[0] in gt);row[label+'_hit5']=rank is not None
            row[label+'_rr']=1/rank if rank else 0
        rows.append(row)
        print(record['video_id'],a[0].canonical_name if a else '-', '=>', b[0].canonical_name if b else '-', flush=True)
        (out/'paired_records.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2))
    known=[r for r in rows if r['sample_type']=='known']
    summary={'source':str(source),'scope':'历史测试样本已用于诊断，仅作开发回放；非独立测试收益',
             'total_replayed':len(rows),'known_replayed':len(known),'skipped':skipped,
             'cached_scene_report':args.cached_scene_report,
             'glm_calls':0,'image_scores':'本地CLIP重新计算，共享分数用于两种排序',
             'gate_calibration':'未重新标定，未运行门控或最终标注','metrics':{}}
    if not known:
        raise ValueError('No available Known videos for paired recall metrics')
    for label in ['legacy','evidence']:
        summary['metrics'][label]={'recall1':sum(x[label+'_hit1'] for x in known)/len(known),
                                  'recall5':sum(x[label+'_hit5'] for x in known)/len(known),
                                  'mrr_at5':sum(x[label+'_rr'] for x in known)/len(known)}
    (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
    print(json.dumps(summary,ensure_ascii=False),flush=True)


if __name__=='__main__':main()
